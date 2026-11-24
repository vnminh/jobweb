"""Inductive embeddings for jobs / seekers created on the web, computed the normal way: the trained P5 encoder
(HeteroGNN `d_gnn_aux`, 2 R-GCN layers) is run on the window-7 subgraph with the new nodes attached by the same edge
types the graph builder (P4) uses, and the same input features (P5):

  job  : bge-small-en-v1.5 embedding of  "title. desc[:1200] Requirements: req[:500]"  + job_num = log1p(#history apps)/5 (= 0)
         edges is_occupation (weight 1: chosen by the recruiter), requires_skill, located_in, job_seniority, has_type,
         requires_degree (+ reverse edges)
  user : recency-weighted (0.7^(seq-1)) mean of bge-small embeddings of the cleaned history titles, L2-normalised
         + the 8 numeric features of data.load_encoder_data; edges held (sum of 0.7^(seq-1) per confident O*NET code),
         has_degree, has_major, lives_in, user_seniority, applied (jobs applied to on the web) (+ reverse edges)

Dataset nodes keep their exported embeddings (node_emb_*), so the recommender behaves exactly as in the report for them;
only rows of web entities are written. `validate()` checks that the local forward pass reproduces node_emb_* for window 7.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ATTR_TYPES = ["occupation", "occ_group", "skill", "city", "state", "seniority", "job_type", "degree", "major"]
TEXT_MODEL = "BAAI/bge-small-en-v1.5"


class GraphEncoder:
    def __init__(self, data_root: Path, model_path: Path, window: int, cache_dir: Path):
        from jobunicorn.encoder.data import subgraph_by_windows
        from jobunicorn.encoder.models import HeteroGNN

        t0 = time.time()
        self._text = None
        self.dr, self.window, self.cache = Path(data_root), window, Path(cache_dir)
        gd, emb = self.dr / "processed/graph", self.dr / "processed/embeddings"
        data = torch.load(gd / "hetero.pt", weights_only=False)
        self.n_nodes = {t: data[t].num_nodes for t in data.node_types}
        sub, subset = subgraph_by_windows(data, [window])
        del data
        self.meta = sub.metadata()
        self.gid = {t: subset[t].numpy() for t in ("user", "job")}  # local -> global idx
        self.lid = {t: pd.Series(np.arange(len(v)), index=v) for t, v in self.gid.items()}  # global -> local
        self.ei = {et: sub[et].edge_index for et in sub.edge_types}
        self.ew = {et: sub[et].edge_weight.float() for et in sub.edge_types}
        self.node_ids = {t: subset[t] for t in sub.node_types if t in ATTR_TYPES}
        self.nodes = {t: pd.read_parquet(gd / f"nodes_{t}.parquet") for t in ["user", "job"] + ATTR_TYPES}
        self.key2idx = {t: dict(zip(self.nodes[t]["key"].astype(str), self.nodes[t]["idx"])) for t in ATTR_TYPES}
        # ---- input features (P5)
        x = {}
        jk = pd.read_parquet(emb / "job_text_txt_keys.parquet")["job_id"].to_numpy()
        pos = pd.Series(np.arange(len(jk)), index=jk)
        je = np.load(emb / "job_text_txt.npy", mmap_mode="r")
        keys = self.nodes["job"]["key"].to_numpy()[self.gid["job"]]
        x["job"] = torch.from_numpy(np.asarray(je[pos.reindex(keys).to_numpy()], dtype=np.float32))
        ae = np.load(emb / "attr_text_txt.npy").astype(np.float32)
        ak = pd.read_parquet(emb / "attr_text_txt_keys.parquet")
        for t in ATTR_TYPES:
            m = ak[ak.attr_type == t]
            arr = np.zeros((len(self.nodes[t]), ae.shape[1]), np.float32)
            arr[m["idx"].to_numpy()] = ae[m.index.to_numpy()]
            x[t] = torch.from_numpy(arr)
        ut, un = self._user_features()
        x["user"] = torch.from_numpy(ut)
        self.x, self.user_num = x, torch.from_numpy(un)
        self.job_num = torch.from_numpy(self._job_num())
        self.years_median = float(self._years_median)
        self.model = HeteroGNN(self.meta, {t: x[t].shape[1] for t in self.meta[0]}, self.n_nodes, hidden=64, out=64, layers=2,
                               user_num_dim=8, dropout=0.1, job_num_dim=1)
        self.model.load_state_dict(torch.load(model_path, map_location="cpu"))
        self.model.eval()
        self.load_sec = time.time() - t0

    # ------------------------------------------------------------------ features of dataset nodes (window 7)
    def text_model(self):
        if self._text is None:
            from sentence_transformers import SentenceTransformer

            self._text = SentenceTransformer(TEXT_MODEL, device="cpu")
            self._text.max_seq_length = 256
        return self._text

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.text_model().encode(texts, batch_size=256, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).astype(np.float32)

    def _user_features(self):
        """x_text['user'] and user_num for window-7 users, as in jobunicorn.encoder.data.load_encoder_data. The title
        embeddings (computed on Modal in P5) are re-encoded locally once and cached."""
        users_g = self.gid["user"]
        ukeys = self.nodes["user"]["key"].to_numpy()[users_g]
        cache = self.cache / f"title_text_w{self.window}.npz"
        hk = pd.read_parquet(self.dr / "processed/p3/hist_title_keys.parquet", filters=[("window", "==", self.window)])
        hk = hk[hk.title_key != ""]
        if cache.exists():
            z = np.load(cache, allow_pickle=True)
            tkeys, te = z["keys"], z["emb"]
        else:
            tkeys = np.array(sorted(hk.title_key.unique()), dtype=object)
            te = self.encode(tkeys.tolist()).astype(np.float16)
            np.savez(cache, keys=tkeys, emb=te)
        tpos = pd.Series(np.arange(len(tkeys)), index=tkeys)
        uix = pd.Series(np.arange(len(ukeys)), index=ukeys)
        hk = hk.assign(u=hk.user_id.map(uix), t=hk.title_key.map(tpos), w=0.7 ** (hk.seq - 1)).dropna(subset=["u", "t"])
        ue = np.zeros((len(ukeys), te.shape[1]), np.float32)
        np.add.at(ue, hk.u.astype(int).to_numpy(), te[hk.t.astype(int).to_numpy()].astype(np.float32) * hk.w.to_numpy()[:, None])
        norm = np.linalg.norm(ue, axis=1, keepdims=True)
        ue = np.where(norm > 0, ue / np.maximum(norm, 1e-9), 0).astype(np.float32)
        users_all = pd.read_parquet(self.dr / "interim/users.parquet", columns=["user_id", "years_exp"])
        self._years_median = users_all.years_exp.astype(float).median()  # median over ALL users (as in P5)
        users = pd.read_parquet(self.dr / "interim/users.parquet").set_index("user_id").reindex(ukeys)
        sp = pd.read_parquet(self.dr / "interim/user_splits.parquet").set_index("user_id").reindex(ukeys)
        num = np.stack([
            users.years_exp.astype(float).fillna(self._years_median).clip(0, 50).to_numpy() / 50,
            users.years_exp.isna().astype(float).to_numpy(),
            users.degree_ord.astype(float).fillna(0).to_numpy() / 6,
            users.currently_employed.astype(float).fillna(0.5).to_numpy(),
            users.managed_others.astype(float).fillna(0).to_numpy(),
            np.log1p(pd.to_numeric(users.managed_how_many, errors="coerce").fillna(0).clip(0, 1000).to_numpy()) / 7,
            np.log1p(sp.n_hist.fillna(0).to_numpy()) / 4,
            (norm[:, 0] > 0).astype(float),
        ], axis=1).astype(np.float32)
        return ue, num

    def _job_num(self):
        apps = pd.read_parquet(self.dr / "interim/apps.parquet", columns=["user_id", "canonical_job_id", "role"])
        h = apps[apps.role == "history"].drop_duplicates(["user_id", "canonical_job_id"])
        cnt = h.canonical_job_id.value_counts()
        keys = self.nodes["job"]["key"].to_numpy()[self.gid["job"]]
        pop = cnt.reindex(keys).fillna(0).to_numpy().astype(np.float32)
        return (np.log1p(pop) / 5.0)[:, None].astype(np.float32)

    # ------------------------------------------------------------------ web nodes
    def job_text(self, j: dict) -> str:
        return (f"{j.get('title') or ''}. " + (j.get("description") or "")[:1200].replace("\n", " ") + " Requirements: "
                + (j.get("requirements") or "")[:500].replace("\n", " "))

    def _idx(self, t, key):
        return None if key is None else self.key2idx[t].get(str(key))

    def embed(self, jobs: list[dict], users: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        """jobs: dicts with title, description, requirements, occupation_code, skills (keys), city_key, seniority, job_type,
        degree_req. users: dicts with titles (most recent first), title_occ (O*NET code per title or None), years_exp,
        degree_ord, currently_employed, managed_others, managed_how_many, major, city_key, seniority, applied (global job idx).
        Returns (job vectors, user vectors) from one forward pass over window 7 + all given web nodes."""
        from jobunicorn.attributes.occupation import clean_title_for_mapping

        x = dict(self.x)
        nJ, nU = len(self.gid["job"]), len(self.gid["user"])
        new_e = {et: ([], [], []) for et in self.meta[1]}

        def add(rel, s, d, w=1.0):
            new_e[rel][0].append(s); new_e[rel][1].append(d); new_e[rel][2].append(w)

        rev = {et: next((r for r in self.meta[1] if r[0] == et[2] and r[2] == et[0] and r[1] == "rev_" + et[1]), None) for et in self.meta[1]}

        def edge(et_name, src_t, s, dst_t, d, w=1.0):
            et = (src_t, et_name, dst_t)
            add(et, s, d, w)
            if rev.get(et):
                add(rev[et], d, s, w)

        # jobs
        jx = self.encode([self.job_text(j) for j in jobs]) if jobs else np.zeros((0, 384), np.float32)
        x["job"] = torch.cat([x["job"], torch.from_numpy(jx)])
        job_num = torch.cat([self.job_num, torch.zeros(len(jobs), 1)])
        for k, j in enumerate(jobs):
            v = nJ + k
            o = self._idx("occupation", j.get("occupation_code"))
            if o is not None:
                edge("is_occupation", "job", v, "occupation", o, 1.0)
            for s in j.get("skills", []):
                si = self._idx("skill", s)
                if si is not None:
                    edge("requires_skill", "job", v, "skill", si)
            for rel, t, key in (("located_in", "city", j.get("city_key")), ("job_seniority", "seniority", j.get("seniority")),
                                ("has_type", "job_type", j.get("job_type")),
                                ("requires_degree", "degree", None if j.get("degree_req") is None else str(int(j["degree_req"])))):
                i = self._idx(t, key)
                if i is not None:
                    edge(rel, "job", v, t, i)
        # users
        ux, un = [], []
        for k, u in enumerate(users):
            uidx = nU + k
            titles = [clean_title_for_mapping(t) for t in u.get("titles", [])]
            vec = np.zeros(384, np.float32)
            if any(titles):
                te = self.encode([t for t in titles if t])
                w = np.array([0.7 ** i for i, t in enumerate(titles) if t], np.float32)
                vec = (te * w[:, None]).sum(0)
                vec = vec / max(np.linalg.norm(vec), 1e-9)
            ux.append(vec)
            yrs = u.get("years_exp")
            un.append([min(max(yrs if yrs is not None else self.years_median, 0), 50) / 50, float(yrs is None), (u.get("degree_ord") or 0) / 6,
                       float(u.get("currently_employed") or 0), float(u.get("managed_others") or 0),
                       np.log1p(min(max(u.get("managed_how_many") or 0, 0), 1000)) / 7, np.log1p(len(u.get("applied", []))) / 4,
                       float(np.linalg.norm(vec) > 0)])
            held = {}
            for i, code in enumerate(u.get("title_occ", [])):
                oi = self._idx("occupation", code)
                if oi is not None:
                    held[oi] = held.get(oi, 0.0) + 0.7 ** i
            for oi, w in held.items():
                edge("held", "user", uidx, "occupation", oi, w)
            for rel, t, key in (("has_degree", "degree", str(int(u.get("degree_ord") or 0))), ("has_major", "major", (u.get("major") or "").strip().lower() or None),
                                ("lives_in", "city", u.get("city_key")), ("user_seniority", "seniority", u.get("seniority"))):
                i = self._idx(t, key)
                if i is not None:
                    edge(rel, "user", uidx, t, i)
            for gj in u.get("applied", []):
                lj = self.lid["job"].get(gj)
                if lj is not None:
                    edge("applied", "user", uidx, "job", int(lj))
        if users:
            x["user"] = torch.cat([x["user"], torch.from_numpy(np.stack(ux))])
        user_num = torch.cat([self.user_num, torch.tensor(un, dtype=torch.float32).reshape(-1, 8)])
        ei, ew = {}, {}
        for et in self.meta[1]:
            s, d, w = new_e[et]
            if s:
                ei[et] = torch.cat([self.ei[et], torch.tensor([s, d], dtype=torch.long)], 1)
                ew[et] = torch.cat([self.ew[et], torch.tensor(w, dtype=torch.float32)])
            else:
                ei[et], ew[et] = self.ei[et], self.ew[et]
        with torch.no_grad():
            out = self.model(x, user_num, self.node_ids, ei, ew, job_num)
        return out["job"][nJ:].numpy(), out["user"][nU:].numpy()

    def validate(self, E_job: np.ndarray, E_user: np.ndarray, n: int = 2000) -> dict:
        """Forward pass without web nodes must reproduce the exported window-7 embeddings."""
        with torch.no_grad():
            out = self.model(self.x, self.user_num, self.node_ids, self.ei, self.ew, self.job_num)
        rng = np.random.default_rng(0)
        res = {}
        for t, E in (("job", E_job), ("user", E_user)):
            loc = rng.choice(len(self.gid[t]), min(n, len(self.gid[t])), replace=False)
            a, b = out[t][loc].numpy(), E[self.gid[t][loc]]
            cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-9)
            res[t] = {"max_abs_diff": float(np.abs(a - b).max()), "mean_cos": float(cos.mean()), "min_cos": float(cos.min())}
        return res
