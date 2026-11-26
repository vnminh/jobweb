"""Conversational metrics (DESIGN 11.2): SR@t, AT, hDCG@(T,K), user effort, unqualified rate, catalog coverage."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from jobunicorn.eval.ranking import bootstrap_ci, paired_bootstrap


def hdcg(turn: int | None, rank: int | None) -> float:
    """hDCG for one episode (UNICORN Eq. 20). In multi-target sessions only the first (highest-ranked) hit counts,
    so the value stays in [0, 1]."""
    if turn is None or rank is None:
        return 0.0
    t, k = turn, rank
    return 1 / math.log2(t + 2) + (1 / math.log2(t + 1) - 1 / math.log2(t + 2)) / math.log2(k + 1)


def episode_record(env) -> dict:
    qtypes = [h["action"][0] for h in env.history if h.get("action", ("",))[0] not in ("init",)]
    recs = [h for h in env.history if h["action"][0] == "rec"]
    unq = [h.get("unqualified", 0.0) for h in recs]
    return {
        "success": env.success_turn is not None,
        "turn": env.success_turn if env.success_turn is not None else env.cfg.T,
        "success_turn": env.success_turn,
        "rank": env.success_rank,
        "hdcg": hdcg(env.success_turn, env.success_rank),
        "effort": env.effort,
        "n_questions": sum(q != "rec" for q in qtypes),
        "n_recs": len(recs),
        "qtypes": "|".join(qtypes),
        "unqualified_rate": float(np.mean(unq)) if unq else np.nan,
        "rec_jobs": [j for h in recs for j in h.get("list", [])],
    }


def summarize(df: pd.DataFrame, T: int = 15, seed: int = 0, n_jobs_catalog: int | None = None) -> dict:
    out = {"n": int(len(df))}
    for t in (5, 10, 15):
        x = (df["success"] & (df["turn"] <= t)).to_numpy(float)
        m, lo, hi = bootstrap_ci(x, seed=seed)
        out[f"SR@{t}"] = m
        out[f"SR@{t}_ci"] = (lo, hi)
    out["AT"] = float(df["turn"].mean())
    out["AT_ci"] = bootstrap_ci(df["turn"].to_numpy(float), seed=seed)[1:]
    out["hDCG"] = float(df["hdcg"].mean())
    out["effort"] = float(df["effort"].mean())
    out["n_questions"] = float(df["n_questions"].mean())
    out["unqualified_rate"] = float(np.nanmean(df["unqualified_rate"])) if df["unqualified_rate"].notna().any() else float("nan")
    if n_jobs_catalog:
        rec = {j for L in df["rec_jobs"] for j in L}
        out["catalog_coverage"] = len(rec) / n_jobs_catalog
    return out


def compare(a: pd.DataFrame, b: pd.DataFrame, metric: str = "success", seed: int = 0) -> dict:
    """Paired bootstrap of a vs b on the same sessions (same order)."""
    return paired_bootstrap(a[metric].to_numpy(float), b[metric].to_numpy(float), seed=seed)
