"""Non-conversational ranking metrics (Recall@K, NDCG@K, MAP@K) and paired bootstrap."""

from __future__ import annotations

import numpy as np
import torch


def rank_metrics_batch(scores: torch.Tensor, targets: list[set[int]], exclude: list[set[int]],
                       ks_recall=(10, 50, 150), ks_ndcg=(10, 50), k_map: int = 150) -> dict[str, np.ndarray]:
    """scores: (B, N) for B users over N candidate jobs. targets/exclude: column indices per user.
    Returns per-user metric arrays."""
    s = scores.clone()
    for i, ex in enumerate(exclude):
        if ex:
            s[i, list(ex)] = -float("inf")
    kmax = max(max(ks_recall), max(ks_ndcg), k_map)
    kmax = min(kmax, s.shape[1])
    top = torch.topk(s, kmax, dim=1).indices.cpu().numpy()
    out = {f"recall@{k}": np.zeros(len(targets)) for k in ks_recall}
    out.update({f"ndcg@{k}": np.zeros(len(targets)) for k in ks_ndcg})
    out[f"map@{k_map}"] = np.zeros(len(targets))
    disc = 1.0 / np.log2(np.arange(2, kmax + 2))
    for i, T in enumerate(targets):
        if not T:
            continue
        rel = np.fromiter((1.0 if j in T else 0.0 for j in top[i]), dtype=float, count=kmax)
        for k in ks_recall:
            out[f"recall@{k}"][i] = rel[:k].sum() / len(T)
        for k in ks_ndcg:
            ideal = disc[: min(len(T), k)].sum()
            out[f"ndcg@{k}"][i] = (rel[:k] * disc[:k]).sum() / ideal
        r = rel[:k_map]
        if r.sum() > 0:
            prec = np.cumsum(r) / np.arange(1, len(r) + 1)
            out[f"map@{k_map}"][i] = (prec * r).sum() / min(len(T), k_map)
    return out


def bootstrap_ci(x: np.ndarray, n: int = 1000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float]:
    """Mean and percentile bootstrap CI of a per-unit metric."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    m = x[idx].mean(1)
    return float(x.mean()), float(np.quantile(m, alpha / 2)), float(np.quantile(m, 1 - alpha / 2))


def paired_bootstrap(a: np.ndarray, b: np.ndarray, n: int = 1000, seed: int = 0) -> dict[str, float]:
    """Paired bootstrap of mean(a - b): mean diff, 95% CI, and one-sided p-value P(diff <= 0)."""
    d = a - b
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    m = d[idx].mean(1)
    return {"diff": float(d.mean()), "ci_low": float(np.quantile(m, 0.025)), "ci_high": float(np.quantile(m, 0.975)),
            "p_le_0": float((m <= 0).mean())}
