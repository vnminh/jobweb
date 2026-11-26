"""Heterogeneous graph construction (DESIGN 5).

Node tables: contiguous integer ids per node type. Edge tables: (src, dst, weight) per relation.
Leakage rule (DESIGN 5.3, A_cut5): `applied` edges only from role == 'history'; career_transition counts only from
users of TRAIN windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from jobunicorn.data.splits import ROLE_HISTORY

ATTR_TYPES = ["occupation", "occ_group", "skill", "city", "state", "seniority", "job_type", "degree", "major"]

# relation name -> (src type, dst type)
RELATIONS = {
    "applied": ("user", "job"),
    "held": ("user", "occupation"),
    "has_degree": ("user", "degree"),
    "has_major": ("user", "major"),
    "lives_in": ("user", "city"),
    "user_seniority": ("user", "seniority"),
    "is_occupation": ("job", "occupation"),
    "requires_skill": ("job", "skill"),
    "located_in": ("job", "city"),
    "job_seniority": ("job", "seniority"),
    "has_type": ("job", "job_type"),
    "requires_degree": ("job", "degree"),
    "occ_child_of": ("occupation", "occ_group"),
    "city_child_of": ("city", "state"),
    "related_skill": ("occupation", "skill"),
    "career_transition": ("occupation", "occupation"),
    "near": ("city", "city"),
}


@dataclass
class GraphTables:
    nodes: dict[str, pd.DataFrame] = field(default_factory=dict)  # type -> DataFrame(idx, key, name, [window])
    edges: dict[str, pd.DataFrame] = field(default_factory=dict)  # relation -> DataFrame(src, dst, weight)

    def save(self, d: Path) -> None:
        d.mkdir(parents=True, exist_ok=True)
        for t, df in self.nodes.items():
            df.to_parquet(d / f"nodes_{t}.parquet", index=False)
        for r, df in self.edges.items():
            df.to_parquet(d / f"edges_{r}.parquet", index=False)

    @classmethod
    def load(cls, d: Path) -> "GraphTables":
        g = cls()
        for p in sorted(d.glob("nodes_*.parquet")):
            g.nodes[p.stem[len("nodes_"):]] = pd.read_parquet(p)
        for p in sorted(d.glob("edges_*.parquet")):
            g.edges[p.stem[len("edges_"):]] = pd.read_parquet(p)
        return g


def _index(keys: pd.Series) -> dict:
    return {k: i for i, k in enumerate(keys)}


def career_transitions(user_occ: pd.DataFrame, train_users: set[int], min_count: int = 5, alpha: float = 1.0) -> pd.DataFrame:
    """Count consecutive occupation pairs (older -> newer; seq k+1 -> seq k since seq 1 is the most recent job)
    over TRAIN-window users only; P(o_j | o_i) with additive smoothing over observed successors; drop rare pairs.

    user_occ needs: user_id, seq, occ_code (confident mappings only, recommended).
    """
    u = user_occ[user_occ["user_id"].isin(train_users)][["user_id", "seq", "occ_code"]].dropna()
    nxt = u.assign(seq=u["seq"] + 1).rename(columns={"occ_code": "to_code"})  # newer job (seq s-1) keyed by s
    pairs = u.rename(columns={"occ_code": "from_code"}).merge(nxt, on=["user_id", "seq"])
    cnt = pairs.groupby(["from_code", "to_code"]).size().rename("count").reset_index()
    tot = cnt.groupby("from_code")["count"].transform("sum")
    nsucc = cnt.groupby("from_code")["count"].transform("size")
    cnt["prob"] = (cnt["count"] + alpha) / (tot + alpha * nsucc)
    return cnt[cnt["count"] >= min_count].reset_index(drop=True)


def near_cities(cities: pd.DataFrame, radius_km: float = 50.0, scale_km: float = 25.0) -> pd.DataFrame:
    """Undirected city pairs within radius (both directions), weight exp(-d/scale). cities: idx, lat, lon."""
    from sklearn.neighbors import BallTree

    c = cities.dropna(subset=["lat", "lon"])
    X = np.radians(c[["lat", "lon"]].to_numpy())
    tree = BallTree(X, metric="haversine")
    ind, dist = tree.query_radius(X, r=radius_km / 6371.0088, return_distance=True)
    idx = c["idx"].to_numpy()
    src, dst, w = [], [], []
    for i, (nb, dd) in enumerate(zip(ind, dist)):
        m = nb != i
        src.append(np.full(m.sum(), idx[i]))
        dst.append(idx[nb[m]])
        w.append(np.exp(-dd[m] * 6371.0088 / scale_km))
    return pd.DataFrame({"src": np.concatenate(src), "dst": np.concatenate(dst), "weight": np.concatenate(w).astype(np.float32)})


def job_attr_matrix(edges: pd.DataFrame, n_jobs: int, n_attr: int, binary: bool = True) -> sp.csr_matrix:
    """Sparse job x attribute matrix from an edge table (src=job idx, dst=attr idx)."""
    data = np.ones(len(edges), dtype=np.float32) if binary else edges["weight"].to_numpy(np.float32)
    m = sp.csr_matrix((data, (edges["src"].to_numpy(), edges["dst"].to_numpy())), shape=(n_jobs, n_attr))
    m.sum_duplicates()
    if binary:
        m.data[:] = 1.0
    return m


def check_graph(g: GraphTables, apps: pd.DataFrame) -> dict:
    """Leakage/consistency checks used by tests and the P4 report. All '*_violations' must be 0."""
    users = g.nodes["user"]
    jobs = g.nodes["job"]
    ap = g.edges["applied"]
    uid = users["key"].to_numpy()[ap["src"].to_numpy()]
    jid = jobs["key"].to_numpy()[ap["dst"].to_numpy()]
    pair = pd.DataFrame({"user_id": uid, "canonical_job_id": jid})
    roles = apps.groupby(["user_id", "canonical_job_id"])["role"].agg(lambda s: ROLE_HISTORY in set(s)).rename("has_hist").reset_index()
    chk = pair.merge(roles, on=["user_id", "canonical_job_id"], how="left")
    win_u = users["window"].to_numpy()[ap["src"].to_numpy()]
    win_j = jobs["window"].to_numpy()[ap["dst"].to_numpy()]
    occ_jobs = set(g.edges["is_occupation"]["src"])
    return {
        "applied_edges_without_history_app_violations": int((~chk["has_hist"].fillna(False).astype(bool)).sum()),
        "applied_cross_window_violations": int((win_u != win_j).sum()),
        "jobs_without_occupation": int(len(jobs) - len(occ_jobs)),
    }


def window_subgraph_ids(g: GraphTables, window: int) -> dict[str, np.ndarray]:
    """Node indices per type for the subgraph of one window: its users and jobs + every shared attribute node."""
    out = {}
    for t, df in g.nodes.items():
        if "window" in df.columns:
            out[t] = df.loc[df["window"] == window, "idx"].to_numpy()
        else:
            out[t] = df["idx"].to_numpy()
    return out
