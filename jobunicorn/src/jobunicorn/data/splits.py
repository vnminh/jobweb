"""Candidate session (history / target) definitions over the applications table.

P1 found that the public apps.tsv contains NO application inside any window's 4-day test period,
so DESIGN.md 9.1 (history = 9 train days, target = 4 test days) cannot be built. This module
implements the alternatives measured in reports/p1_eda; the owner picks one at Gate A.

Every definition returns boolean masks over `apps` rows: (history_mask, target_mask).
Required apps columns: UserID, JobID, WindowID, ApplicationDate, pos, day (see io.window_position).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def session_definitions(apps: pd.DataFrame, cuts: list[int] | tuple[int, ...] = (5, 6, 7)) -> dict[str, tuple[pd.Series, pd.Series, str]]:
    """Return {name: (history_mask, target_mask, note)} for every candidate definition."""
    out: dict[str, tuple[pd.Series, pd.Series, str]] = {}
    in_train = apps["pos"].eq("train")
    for c in cuts:
        hm = apps["day"] < c
        tm = in_train & (apps["day"] >= c)
        out[f"A_cut{c}"] = (
            hm, tm,
            f"Cắt cố định trong 9 ngày train của window tại ngày {c}: lịch sử = mọi đơn trước train_start+{c} "
            f"(kể cả đơn trước window); đích = đơn trong [train_start+{c}, test_start).",
        )
    c0 = 6 if 6 in cuts else cuts[0]
    out[f"A_cut{c0}_inwindow"] = (
        in_train & (apps["day"] < c0), in_train & (apps["day"] >= c0),
        f"Như A_cut{c0} nhưng lịch sử chỉ gồm đơn trong window (bỏ đơn trước train_start).",
    )
    out["B_after"] = (
        apps["pos"].isin(["before", "train"]), apps["pos"].eq("after"),
        "Lịch sử = đơn đến hết giai đoạn train; đích = đơn sau test_end (nằm trong giai đoạn train của window sau). "
        "Window 7 không có đơn 'after'.",
    )
    hm, tm = last_k_masks(apps, k=1)
    out["C_last1"] = (
        hm, tm,
        "Mỗi user: job nộp muộn nhất là đích, còn lại là lịch sử. Không có mốc thời gian chung → "
        "đồ thị/thống kê có thể chứa đơn xảy ra sau đích của user khác (rò rỉ thời gian, [Ji+23]).",
    )
    return out


def last_k_masks(apps: pd.DataFrame, k: int = 1) -> tuple[pd.Series, pd.Series]:
    """Per user: the k most recent distinct jobs are targets, earlier rows are history."""
    a = apps[["UserID", "JobID", "ApplicationDate"]].copy()
    a["_i"] = np.arange(len(a))
    first = a.sort_values("ApplicationDate").drop_duplicates(["UserID", "JobID"], keep="first")
    rank = first.groupby("UserID")["ApplicationDate"].rank(method="first", ascending=False)
    tgt_pairs = set(map(tuple, first.loc[rank <= k, ["UserID", "JobID"]].to_numpy().tolist()))
    pair = list(zip(a["UserID"].tolist(), a["JobID"].tolist()))
    tm = pd.Series([p in tgt_pairs for p in pair], index=apps.index)
    return ~tm, tm


def sessions_for_definition(apps: pd.DataFrame, hist_mask: pd.Series, tgt_mask: pd.Series) -> dict:
    """Count usable sessions: users with >=1 history job and >=1 target job not already in history."""
    h = apps.loc[hist_mask, ["UserID", "JobID"]].drop_duplicates()
    t_all = apps.loc[tgt_mask, ["UserID", "JobID"]].drop_duplicates()
    hkey = set(zip(h["UserID"].tolist(), h["JobID"].tolist()))
    in_h = np.array([p in hkey for p in zip(t_all["UserID"].tolist(), t_all["JobID"].tolist())], dtype=bool)
    t = t_all[~in_h]
    hu = h.groupby("UserID").size()
    tu = t.groupby("UserID").size()
    both = hu.index.intersection(tu.index)
    uw = apps.drop_duplicates("UserID").set_index("UserID")["WindowID"]
    per_window = uw.reindex(both).value_counts().to_dict()
    return {
        "total": int(len(both)),
        "per_window": per_window,
        "users": both,
        "median_targets": float(tu.reindex(both).median()) if len(both) else float("nan"),
        "median_history": float(hu.reindex(both).median()) if len(both) else float("nan"),
        "repeat_rate": float(in_h.mean()) if len(in_h) else 0.0,
    }


# ------------------------------------------------------------------ chosen definition (Gate A): A_cut5

ROLE_HISTORY, ROLE_TARGET, ROLE_FUTURE = "history", "target", "future"


def label_roles(apps: pd.DataFrame, cut_days: float = 5.0) -> pd.Series:
    """A_cut<c> roles per application: history (day < c), target (c <= day < 9, i.e. inside the train period),
    future (test period or after: never used anywhere)."""
    hist = apps["day"] < cut_days
    tgt = apps["pos"].eq("train") & (apps["day"] >= cut_days)
    return pd.Series(np.where(hist, ROLE_HISTORY, np.where(tgt, ROLE_TARGET, ROLE_FUTURE)), index=apps.index, dtype="object")


def window_role(window: pd.Series, train_windows: list[int], val_window: int, test_window: int) -> pd.Series:
    """Map WindowID -> 'train' / 'val' / 'test'."""
    m = {w: "train" for w in train_windows}
    m[val_window] = "val"
    m[test_window] = "test"
    return window.map(m).astype("object")


def build_user_splits(apps: pd.DataFrame, users: pd.DataFrame, split_cfg: dict, es_frac: float, seed: int) -> pd.DataFrame:
    """One row per user: window, window_role, es_holdout (10% of train-window users), n_hist, n_target (new canonical
    jobs not in history) and usable (n_hist >= 1 and n_target >= 1).

    apps needs: user_id, canonical_job_id, role. users needs: user_id, window.
    """
    h = apps.loc[apps["role"] == ROLE_HISTORY, ["user_id", "canonical_job_id"]].drop_duplicates()
    t = apps.loc[apps["role"] == ROLE_TARGET, ["user_id", "canonical_job_id"]].drop_duplicates()
    t = t.merge(h.assign(_h=1), on=["user_id", "canonical_job_id"], how="left")
    t = t[t["_h"].isna()]
    out = users[["user_id", "window"]].copy()
    out["window_role"] = window_role(out["window"], split_cfg["train_windows"], split_cfg["val_window"], split_cfg["test_window"])
    out["n_hist"] = out["user_id"].map(h.groupby("user_id").size()).fillna(0).astype(int)
    out["n_target"] = out["user_id"].map(t.groupby("user_id").size()).fillna(0).astype(int)
    out["usable"] = (out["n_hist"] >= 1) & (out["n_target"] >= 1)
    rng = np.random.default_rng(seed)
    out["es_holdout"] = (out["window_role"] == "train") & (rng.random(len(out)) < es_frac)
    return out


def history_and_targets(apps: pd.DataFrame) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Per user: history canonical jobs (chronological, unique) and NEW target canonical jobs (sorted)."""
    a = apps.sort_values("app_date")
    h = a[a["role"] == ROLE_HISTORY].drop_duplicates(["user_id", "canonical_job_id"])
    hist = h.groupby("user_id")["canonical_job_id"].agg(list).to_dict()
    t = a[a["role"] == ROLE_TARGET].drop_duplicates(["user_id", "canonical_job_id"])
    hs = set(zip(h["user_id"], h["canonical_job_id"]))
    t = t[[p not in hs for p in zip(t["user_id"], t["canonical_job_id"])]]
    tg = t.groupby("user_id")["canonical_job_id"].agg(lambda s: sorted(s)).to_dict()
    return hist, tg


def check_no_leakage(apps: pd.DataFrame, cut_days: float = 5.0) -> dict[str, int]:
    """Data-level leakage audit. All counts must be 0."""
    r = apps["role"]
    return {
        "history_rows_on_or_after_cut": int(((r == ROLE_HISTORY) & (apps["day"] >= cut_days)).sum()),
        "target_rows_before_cut": int(((r == ROLE_TARGET) & (apps["day"] < cut_days)).sum()),
        "target_rows_outside_train_period": int(((r == ROLE_TARGET) & (apps["pos"] != "train")).sum()),
        "future_rows_before_cut": int(((r == ROLE_FUTURE) & (apps["day"] < cut_days)).sum()),
    }
