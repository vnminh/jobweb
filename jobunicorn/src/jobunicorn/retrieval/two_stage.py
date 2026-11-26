"""Two-stage retrieval (DESIGN 8).

Tier 1: hard filter (window, still open, C_hard, rejected values/jobs) -> maximum-inner-product search with
        q_t = e_u + sum_p alpha_p e_p over the filtered jobs (FAISS IndexFlatIP + IDSelectorBatch), keep top N_c.
        Re-queried only when P_acc or C_hard changes; otherwise the previous list is intersected with the new filter.
Tier 2: the environment scores the N_c candidates fully (penalties, fit, EIG, policy graph).
"""

from __future__ import annotations

import time

import numpy as np


class TwoStageRetriever:
    def __init__(self, world, n_c: int, use_faiss: bool = True, open_only: bool = False, open_mask: np.ndarray | None = None):
        self.W, self.n_c, self.use_faiss = world, int(n_c), use_faiss
        self.open_mask = open_mask if open_only else None
        self._index: dict[int, tuple] = {}
        self._key = None
        self._last: np.ndarray | None = None
        self.n_queries = 0
        self.query_time = 0.0

    def _faiss(self, window: int):
        if window not in self._index:
            import faiss

            jobs = self.W.window_jobs[window]
            idx = faiss.IndexFlatIP(self.W.E_job.shape[1])
            idx.add(np.ascontiguousarray(self.W.E_job[jobs], dtype=np.float32))
            pos = np.full(self.W.E_job.shape[0], -1, np.int64)  # global job index -> row in this window's index
            pos[jobs] = np.arange(len(jobs))
            self._index[window] = (idx, jobs, pos)
        return self._index[window]

    def query(self, q: np.ndarray, window: int, allowed: np.ndarray) -> np.ndarray:
        t0 = time.perf_counter()
        k = min(self.n_c, len(allowed))
        if self.use_faiss:
            import faiss

            idx, jobs, pos = self._faiss(window)
            local = pos[np.asarray(allowed, dtype=np.int64)]
            assert (local >= 0).all(), "allowed jobs must belong to the session window"
            params = faiss.SearchParameters(sel=faiss.IDSelectorBatch(local))
            _, I = idx.search(np.ascontiguousarray(q[None, :], dtype=np.float32), k, params=params)
            out = jobs[I[0][I[0] >= 0]]
        else:
            s = self.W.E_job[allowed] @ q
            out = allowed[np.argpartition(-s, k - 1)[:k]] if k < len(allowed) else allowed
        self.n_queries += 1
        self.query_time += time.perf_counter() - t0
        return out

    def select(self, env, filtered: np.ndarray) -> np.ndarray:
        if self.open_mask is not None:
            filtered = filtered[self.open_mask[filtered]]
        if len(filtered) <= self.n_c:
            self._key, self._last = None, None
            return filtered
        key = (env.sess["user_idx"], tuple(env.P_acc), tuple(sorted((t, tuple(sorted(v))) for t, v in env.C_hard.items())))
        if key == self._key and self._last is not None:
            keep = self._last[np.isin(self._last, filtered)]
            if len(keep) >= self.n_c // 2:
                return keep
        q = env.e_u + (sum(env.alpha[a] * self.W.E_attr[a] for a in env.P_acc) if env.P_acc else 0)
        out = self.query(np.asarray(q, dtype=np.float32), int(env.sess["window"]), filtered)
        self._key, self._last = key, out
        return out
