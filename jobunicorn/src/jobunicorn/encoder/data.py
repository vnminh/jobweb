"""Assemble encoder inputs: node text features, user numeric features, supervision pairs, window subgraphs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from jobunicorn.data.splits import ROLE_HISTORY, ROLE_TARGET

ATTR_TYPES = ["occupation", "occ_group", "skill", "city", "state", "seniority", "job_type", "degree", "major"]


@dataclass
class EncoderData:
    data: object  # HeteroData (all windows)
    x_text: dict[str, torch.Tensor]  # global features per node type (float32)
    user_num: torch.Tensor
    job_num: torch.Tensor  # log1p(# history applications) / 5 (history only: no target leakage)
    user_prof: torch.Tensor  # profile title embedding (same as x_text['user'])
    user_window: np.ndarray
    job_window: np.ndarray
    user_state: np.ndarray  # state node idx or -1
    job_state: np.ndarray
    hist: dict[int, list[int]]  # user idx -> history job idx (global)
    tgt: dict[int, list[int]]  # user idx -> NEW target job idx (global)
    splits: pd.DataFrame  # user_splits joined with idx
    nodes: dict[str, pd.DataFrame]


def _load_emb(emb_dir: Path, name: str) -> np.ndarray:
    return np.load(emb_dir / f"{name}.npy").astype(np.float32)


def load_encoder_data(dr: Path, tag: str, history_decay: float = 0.7) -> EncoderData:
    gd, emb, interim = dr / "processed" / "graph", dr / "processed" / "embeddings", dr / "interim"
    data = torch.load(gd / "hetero.pt", weights_only=False)
    nodes = {t: pd.read_parquet(gd / f"nodes_{t}.parquet") for t in ["user", "job"] + ATTR_TYPES}
    x = {}
    # jobs
    je = _load_emb(emb, f"job_text_{tag}")
    jk = pd.read_parquet(emb / f"job_text_{tag}_keys.parquet")["job_id"].to_numpy()
    pos = pd.Series(np.arange(len(jk)), index=jk)
    x["job"] = torch.from_numpy(je[pos.reindex(nodes["job"]["key"]).to_numpy()])
    # attributes
    ae = _load_emb(emb, f"attr_text_{tag}")
    ak = pd.read_parquet(emb / f"attr_text_{tag}_keys.parquet")
    for t in ATTR_TYPES:
        m = ak[ak.attr_type == t]
        arr = np.zeros((len(nodes[t]), ae.shape[1]), dtype=np.float32)
        arr[m["idx"].to_numpy()] = ae[m.index.to_numpy()]
        x[t] = torch.from_numpy(arr)
    # users: recency-weighted mean of history title embeddings
    te = _load_emb(emb, f"title_text_{tag}")
    tkeys = pd.read_parquet(emb / f"title_text_{tag}_keys.parquet")["title_key"]
    tpos = pd.Series(np.arange(len(tkeys)), index=tkeys.values)
    hk = pd.read_parquet(dr / "processed" / "p3" / "hist_title_keys.parquet")
    hk = hk[hk.title_key != ""]
    uix = pd.Series(nodes["user"]["idx"].to_numpy(), index=nodes["user"]["key"].to_numpy())
    hk = hk.assign(u=hk.user_id.map(uix), t=hk.title_key.map(tpos), w=history_decay ** (hk.seq - 1)).dropna(subset=["u", "t"])
    ue = np.zeros((len(nodes["user"]), te.shape[1]), dtype=np.float32)
    np.add.at(ue, hk.u.astype(int).to_numpy(), te[hk.t.astype(int).to_numpy()] * hk.w.to_numpy()[:, None])
    norm = np.linalg.norm(ue, axis=1, keepdims=True)
    ue = np.where(norm > 0, ue / np.maximum(norm, 1e-9), 0)
    x["user"] = torch.from_numpy(ue.astype(np.float32))
    # numeric user features
    users = pd.read_parquet(interim / "users.parquet").set_index("user_id").reindex(nodes["user"]["key"])
    sp = pd.read_parquet(interim / "user_splits.parquet").set_index("user_id").reindex(nodes["user"]["key"])
    num = np.stack([
        users.years_exp.astype(float).fillna(users.years_exp.astype(float).median()).clip(0, 50).to_numpy() / 50,
        users.years_exp.isna().astype(float).to_numpy(),
        users.degree_ord.astype(float).fillna(0).to_numpy() / 6,
        users.currently_employed.astype(float).fillna(0.5).to_numpy(),
        users.managed_others.astype(float).fillna(0).to_numpy(),
        np.log1p(pd.to_numeric(users.managed_how_many, errors="coerce").fillna(0).clip(0, 1000).to_numpy()) / 7,
        np.log1p(sp.n_hist.fillna(0).to_numpy()) / 4,
        (norm[:, 0] > 0).astype(float),
    ], axis=1).astype(np.float32)
    # states
    city = nodes["city"].set_index("idx")
    st_ix = pd.Series(nodes["state"]["idx"].to_numpy(), index=nodes["state"]["key"].to_numpy())
    jobs_i = pd.read_parquet(interim / "jobs.parquet", columns=["job_id", "state"]).set_index("job_id")
    job_state = jobs_i["state"].reindex(nodes["job"]["key"]).map(st_ix).fillna(-1).astype(int).to_numpy()
    user_state = users["state"].map(st_ix).fillna(-1).astype(int).to_numpy()
    # supervision
    apps = pd.read_parquet(interim / "apps.parquet", columns=["user_id", "canonical_job_id", "role", "app_date"])
    jix = pd.Series(nodes["job"]["idx"].to_numpy(), index=nodes["job"]["key"].to_numpy())
    apps = apps.assign(u=apps.user_id.map(uix), j=apps.canonical_job_id.map(jix)).dropna(subset=["u", "j"])
    apps["u"] = apps.u.astype(int)
    apps["j"] = apps.j.astype(int)
    h = apps[apps.role == ROLE_HISTORY].sort_values("app_date").drop_duplicates(["u", "j"])
    hist = h.groupby("u")["j"].agg(list).to_dict()
    hs = set(zip(h.u, h.j))
    t = apps[apps.role == ROLE_TARGET].drop_duplicates(["u", "j"])
    t = t[[p not in hs for p in zip(t.u, t.j)]]
    tgt = t.groupby("u")["j"].agg(list).to_dict()
    splits = pd.read_parquet(interim / "user_splits.parquet").assign(idx=lambda d: d.user_id.map(uix))
    pop = np.bincount(h.j.to_numpy(), minlength=len(nodes["job"])).astype(np.float32)
    job_num = torch.from_numpy((np.log1p(pop) / 5.0)[:, None].astype(np.float32))
    return EncoderData(data=data, x_text=x, user_num=torch.from_numpy(num), job_num=job_num, user_prof=x["user"],
                       user_window=nodes["user"]["window"].to_numpy(), job_window=nodes["job"]["window"].to_numpy(),
                       user_state=user_state, job_state=job_state, hist=hist, tgt=tgt, splits=splits, nodes=nodes)


def subgraph_by_windows(data, windows: list[int]):
    """Subgraph keeping users/jobs whose window is in `windows` + all attribute nodes. Returns (sub, subset dict)."""
    subset = {}
    wt = torch.tensor(windows)
    for t in data.node_types:
        if "window" in data[t]:
            subset[t] = torch.isin(data[t].window, wt).nonzero().view(-1)
        else:
            subset[t] = torch.arange(data[t].num_nodes)
    return data.subgraph(subset), subset


def history_mean(job_feat: torch.Tensor, hist: dict[int, list[int]], users: np.ndarray) -> torch.Tensor:
    """Mean feature of history-applied jobs for each user (zeros if none)."""
    out = torch.zeros(len(users), job_feat.shape[1])
    for i, u in enumerate(users):
        h = hist.get(int(u))
        if h:
            out[i] = job_feat[h].mean(0)
    return out
