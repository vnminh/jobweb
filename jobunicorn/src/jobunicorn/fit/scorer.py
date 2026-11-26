"""Fit scorer used inside the conversation environment: s_fit(u, v) = centred logit of g_phi; per-session cache."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from jobunicorn.fit.features import load_fit_data


class FitScorer:
    def __init__(self, data, model, scaler, base_logit: float):
        self.data, self.model, self.scaler, self.base = data, model, scaler, base_logit
        self._cache_u, self._cache = None, {}

    @classmethod
    def load(cls, dr: Path, world, fcfg: dict) -> "FitScorer":
        with open(dr / "processed" / "fit" / f"{fcfg.get('model', 'g_phi')}.pkl", "rb") as f:
            obj = pickle.load(f)
        return cls(load_fit_data(dr, fcfg.get("text_tag", "txt")), obj["model"], obj["scaler"], obj["base_logit"])

    def logit(self, u: int, jobs: np.ndarray) -> np.ndarray:
        X = self.scaler.transform(self.data.features(u, jobs))
        if hasattr(self.model, "decision_function"):
            z = self.model.decision_function(X)
        else:
            p = np.clip(self.model.predict_proba(X)[:, 1], 1e-6, 1 - 1e-6)
            z = np.log(p / (1 - p))
        return z - self.base

    def score(self, sess: dict, jobs: np.ndarray) -> np.ndarray:
        u = int(sess["user_idx"])
        if self._cache_u != u:
            self._cache_u, self._cache = u, {}
        miss = [j for j in jobs.tolist() if j not in self._cache]
        if miss:
            for j, z in zip(miss, self.logit(u, np.asarray(miss))):
                self._cache[j] = float(z)
        return np.fromiter((self._cache[j] for j in jobs.tolist()), dtype=np.float64, count=len(jobs))

    def unqualified_rate(self, sess: dict, jobs: list[int]) -> float:
        if not jobs:
            return 0.0
        return float(self.data.unqualified(int(sess["user_idx"]), np.asarray(jobs)).mean())
