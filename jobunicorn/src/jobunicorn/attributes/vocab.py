"""Attribute vocabulary helpers: frequency filter (train windows only, DESIGN 4.3/5.3)."""

from __future__ import annotations

import pandas as pd


def frequency_filter(job_attr: pd.DataFrame, train_windows: list[int], min_df: int = 20, max_frac: float = 0.30,
                     n_train_jobs: int | None = None, attr_col: str = "skill_id") -> tuple[list, pd.DataFrame]:
    """Keep attributes whose document frequency over TRAIN-window jobs is in [min_df, max_frac * n_train_jobs].

    job_attr needs: job_id, window, <attr_col>. Statistics never look at validation/test windows.
    Returns (kept attribute ids, stats DataFrame indexed by attribute with df_train, frac_train, kept).
    """
    tr = job_attr[job_attr["window"].isin(train_windows)]
    if n_train_jobs is None:
        n_train_jobs = int(tr["job_id"].nunique())
    df = tr.drop_duplicates(["job_id", attr_col]).groupby(attr_col).size()
    all_attrs = pd.Index(job_attr[attr_col].unique())
    df = df.reindex(all_attrs, fill_value=0)
    stats = pd.DataFrame({"df_train": df, "frac_train": df / max(1, n_train_jobs)})
    stats["kept"] = (stats["df_train"] >= min_df) & (stats["frac_train"] <= max_frac)
    return stats.index[stats["kept"]].tolist(), stats
