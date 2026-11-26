"""Candidate-job fit features (DESIGN 7.3), vectorised for one user against many jobs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from jobunicorn.data.clean import haversine_km

FEATURES = [
    "degree_gap", "degree_missing", "exp_gap", "exp_missing", "skill_coverage", "skill_overlap", "job_has_skills",
    "transition_prob", "same_occupation", "seniority_gap", "seniority_missing", "log_distance_km", "distance_missing", "text_cos",
]


@dataclass
class FitData:
    job_degree: np.ndarray  # required degree ordinal or -1
    job_years: np.ndarray  # required years or nan
    job_sen: np.ndarray  # seniority ord or -1
    job_lat: np.ndarray
    job_lon: np.ndarray
    job_occ: np.ndarray  # occupation local idx or -1
    job_skill: sp.csr_matrix  # jobs x skills (binary)
    job_skill_n: np.ndarray
    job_text: np.ndarray  # (n_jobs, d) normalised text embedding (float16 ok)
    user_degree: np.ndarray
    user_years: np.ndarray
    user_sen: np.ndarray
    user_lat: np.ndarray
    user_lon: np.ndarray
    user_occ: np.ndarray  # last occupation local idx or -1
    user_skill: sp.csr_matrix  # users x skills (binary)
    user_text: np.ndarray  # (n_users, d)
    trans: np.ndarray  # occ x occ transition probability (train windows only)

    def features(self, u: int, jobs: np.ndarray) -> np.ndarray:
        """Feature matrix (len(jobs), len(FEATURES)) for user u."""
        jd, ud = self.job_degree[jobs], self.user_degree[u]
        dmiss = (jd < 0) | (ud < 0)
        jy, uy = self.job_years[jobs], self.user_years[u]
        ymiss = np.isnan(jy) | np.isnan(uy)
        su = self.user_skill[u]
        ov = np.asarray((self.job_skill[jobs] @ su.T).todense()).ravel()
        n = self.job_skill_n[jobs]
        cov = np.where(n > 0, ov / np.maximum(n, 1), 0.0)
        uo, jo = self.user_occ[u], self.job_occ[jobs]
        tp = np.where((uo >= 0) & (jo >= 0), self.trans[max(uo, 0), np.maximum(jo, 0)], 0.0)
        js, us = self.job_sen[jobs], self.user_sen[u]
        smiss = (js < 0) | (us < 0)
        lat, lon = self.job_lat[jobs], self.job_lon[jobs]
        gmiss = np.isnan(lat) | np.isnan(self.user_lat[u])
        dist = np.where(gmiss, 0.0, haversine_km(np.nan_to_num(lat), np.nan_to_num(lon), np.nan_to_num(self.user_lat[u]), np.nan_to_num(self.user_lon[u])))
        tc = (self.job_text[jobs].astype(np.float32) @ self.user_text[u].astype(np.float32))
        return np.stack([
            np.where(dmiss, 0, ud - jd), dmiss, np.where(ymiss, 0, np.clip(np.nan_to_num(uy) - np.nan_to_num(jy), -20, 30)), ymiss,
            cov, np.log1p(ov), n > 0, tp, (uo >= 0) & (uo == jo), np.where(smiss, 0, js - us), smiss,
            np.log1p(dist), gmiss, tc,
        ], axis=1).astype(np.float32)

    def unqualified(self, u: int, jobs: np.ndarray) -> np.ndarray:
        """Rule (DESIGN 7.3): user lacks the minimum degree, or has > 2 years less than required (both known)."""
        jd, ud = self.job_degree[jobs], self.user_degree[u]
        lack_deg = (jd >= 0) & (ud >= 0) & (ud < jd)
        jy, uy = self.job_years[jobs], self.user_years[u]
        lack_exp = ~np.isnan(jy) & ~np.isnan(uy) & (uy < jy - 2)
        return lack_deg | lack_exp


def load_fit_data(dr: Path, text_tag: str = "txt") -> FitData:
    gd, attrd, interim, emb = dr / "processed" / "graph", dr / "processed" / "attributes", dr / "interim", dr / "processed" / "embeddings"
    jobs = pd.read_parquet(gd / "nodes_job.parquet")
    users = pd.read_parquet(gd / "nodes_user.parquet")
    nj, nu = len(jobs), len(users)
    jf = pd.read_parquet(attrd / "job_fields.parquet", columns=["job_id", "degree_req", "years_req", "seniority"]).set_index("job_id").reindex(jobs["key"])
    sen_levels = ["entry", "mid", "senior", "manager", "executive"]
    sen_map = {s: i for i, s in enumerate(sen_levels)}
    ji = pd.read_parquet(interim / "jobs.parquet", columns=["job_id", "lat", "lon"]).set_index("job_id").reindex(jobs["key"])
    occ_nodes = pd.read_parquet(gd / "nodes_occupation.parquet")
    occ_ix = dict(zip(occ_nodes["key"], occ_nodes["idx"]))
    jo = pd.read_parquet(gd / "edges_is_occupation.parquet")
    job_occ = np.full(nj, -1)
    job_occ[jo["src"].to_numpy()] = jo["dst"].to_numpy()
    js = sp.load_npz(gd / "job_attr_skill.npz").tocsr()
    ns = js.shape[1]
    skill_nodes = pd.read_parquet(gd / "nodes_skill.parquet")
    sk_ix = dict(zip(skill_nodes["key"], skill_nodes["idx"]))
    uf = pd.read_parquet(attrd / "user_fields.parquet").set_index("user_id").reindex(users["key"])
    ui = pd.read_parquet(interim / "users.parquet", columns=["user_id", "lat", "lon"]).set_index("user_id").reindex(users["key"])
    uix = dict(zip(users["key"], users["idx"]))
    us = pd.read_parquet(attrd / "user_skills.parquet")
    us = us.assign(u=us.user_id.map(uix), s=us.skill_id.map(sk_ix)).dropna()
    user_skill = sp.csr_matrix((np.ones(len(us), np.float32), (us.u.astype(int), us.s.astype(int))), shape=(nu, ns))
    ct = pd.read_parquet(gd / "career_transitions_full.parquet")
    trans = np.zeros((len(occ_nodes), len(occ_nodes)), np.float32)
    a, b = ct.from_code.map(occ_ix), ct.to_code.map(occ_ix)
    ok = a.notna() & b.notna()
    trans[a[ok].astype(int), b[ok].astype(int)] = ct.prob[ok].to_numpy()
    jt = np.load(emb / f"job_text_{text_tag}.npy")
    jk = pd.read_parquet(emb / f"job_text_{text_tag}_keys.parquet")["job_id"]
    pos = pd.Series(np.arange(len(jk)), index=jk.values).reindex(jobs["key"]).to_numpy()
    ut = np.load(emb / f"user_profile_{text_tag}.npy")
    return FitData(
        job_degree=jf["degree_req"].fillna(-1).astype(int).to_numpy(), job_years=jf["years_req"].astype(float).to_numpy(),
        job_sen=jf["seniority"].map(sen_map).fillna(-1).astype(int).to_numpy(), job_lat=ji["lat"].to_numpy(float), job_lon=ji["lon"].to_numpy(float),
        job_occ=job_occ, job_skill=js, job_skill_n=np.asarray(js.sum(1)).ravel(), job_text=jt[pos],
        user_degree=uf["degree_ord"].fillna(-1).astype(int).to_numpy(), user_years=uf["years_exp"].astype(float).to_numpy(),
        user_sen=uf["seniority"].map(sen_map).fillna(-1).astype(int).to_numpy(), user_lat=ui["lat"].to_numpy(float), user_lon=ui["lon"].to_numpy(float),
        user_occ=uf["last_occ"].map(occ_ix).fillna(-1).astype(int).to_numpy(), user_skill=user_skill, user_text=ut, trans=trans)
