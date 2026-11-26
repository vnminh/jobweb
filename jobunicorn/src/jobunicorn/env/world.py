"""Static data shared by every conversation: embeddings, job x attribute matrix, hierarchy, job metadata.

Attribute ids are global over the askable types: attr_id = offset[type] + local idx.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

ASKABLE_TYPES = ["occ_group", "occupation", "skill", "seniority", "job_type", "city", "state"]
SINGLE_VALUED = {"occ_group", "occupation", "seniority", "job_type", "city", "state"}  # one value per job
HARD_TYPES_DEFAULT = {"state", "city", "job_type"}  # DESIGN 4.2 (location hard by default; job type hard if answered)
ORDINAL_TYPES = {"seniority": ["entry", "mid", "senior", "manager", "executive"]}


@dataclass
class World:
    types: list[str]
    offset: dict[str, int]
    n_attr: int
    attr_type: np.ndarray  # attr id -> type index
    attr_name: list[str]
    attr_parent: np.ndarray  # attr id -> parent attr id (occupation->group, city->state) or -1
    A: sp.csr_matrix  # jobs x attrs (binary)
    AT: sp.csr_matrix  # attrs x jobs
    E_job: np.ndarray  # (n_jobs, d)
    E_user: np.ndarray
    E_attr: np.ndarray  # (n_attr, d)
    job_window: np.ndarray
    job_state: np.ndarray  # state attr id (global) or -1
    job_city: np.ndarray  # city attr id or -1
    job_seniority_ord: np.ndarray  # 0..4 or -1
    job_ids: np.ndarray  # canonical JobID per job idx
    window_jobs: dict[int, np.ndarray]
    score_temp: float = 1.0

    def type_of(self, a: int) -> str:
        return self.types[self.attr_type[a]]

    def attrs_of_type(self, t: str) -> np.ndarray:
        return np.flatnonzero(self.attr_type == self.types.index(t))


def load_world(dr: Path, types: list[str] | None = None, emb_prefix: str = "node_emb") -> World:
    """Load graph tables + P5 embeddings into a World."""
    types = types or ASKABLE_TYPES
    gd, emb = dr / "processed" / "graph", dr / "processed" / "embeddings"
    mats, names, parents, tix, offset, Es = [], [], [], [], {}, []
    off = 0
    nodes = {t: pd.read_parquet(gd / f"nodes_{t}.parquet") for t in types}
    for i, t in enumerate(types):
        m = sp.load_npz(gd / f"job_attr_{t}.npz").tocsr()
        mats.append(m)
        offset[t] = off
        n = m.shape[1]
        names += [f"{t}:{x}" for x in nodes[t]["name"].astype(str)]
        tix.append(np.full(n, i))
        Es.append(np.load(emb / f"{emb_prefix}_{t}.npy").astype(np.float32))
        off += n
    par = np.full(off, -1, dtype=np.int64)
    if "occupation" in types and "occ_group" in types:
        e = pd.read_parquet(gd / "edges_occ_child_of.parquet")
        par[offset["occupation"] + e.src.to_numpy()] = offset["occ_group"] + e.dst.to_numpy()
    if "city" in types and "state" in types:
        e = pd.read_parquet(gd / "edges_city_child_of.parquet")
        par[offset["city"] + e.src.to_numpy()] = offset["state"] + e.dst.to_numpy()
    A = sp.hstack(mats).tocsr()
    jobs = pd.read_parquet(gd / "nodes_job.parquet")
    jw = jobs["window"].to_numpy()

    def single(t):
        if t not in types:
            return np.full(A.shape[0], -1)
        m = mats[types.index(t)]
        out = np.full(m.shape[0], -1, dtype=np.int64)
        r, c = m.nonzero()
        out[r] = c + offset[t]
        return out

    sen = single("seniority")
    sen_ord = np.where(sen >= 0, sen - offset.get("seniority", 0), -1)
    return World(types=types, offset=offset, n_attr=off, attr_type=np.concatenate(tix), attr_name=names, attr_parent=par,
                 A=A, AT=A.T.tocsr(), E_job=np.load(emb / f"{emb_prefix}_job.npy").astype(np.float32),
                 E_user=np.load(emb / f"{emb_prefix}_user.npy").astype(np.float32), E_attr=np.vstack(Es),
                 job_window=jw, job_state=single("state"), job_city=single("city"), job_seniority_ord=sen_ord,
                 job_ids=jobs["key"].to_numpy(), window_jobs={int(w): np.flatnonzero(jw == w) for w in np.unique(jw)})
