"""Robust readers for the CareerBuilder 2012 TSV files.

The raw files are tab-separated, CRLF-terminated, unquoted (fields may contain `"`),
and job text contains HTML plus literal "\\r" escape sequences. We therefore parse
line by line instead of relying on pandas' quoting logic:

* decode each line as UTF-8 (invalid bytes replaced, counted);
* strip the trailing CR/LF;
* if a line has too few fields (an embedded newline inside a text field), stitch it with
  the following line(s) up to `max_stitch` lines; if it still does not match, skip it;
* lines with too many fields are skipped (counted, a few examples kept).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

USERS_COLS = [
    "UserID", "WindowID", "Split", "City", "State", "Country", "ZipCode", "DegreeType", "Major",
    "GraduationDate", "WorkHistoryCount", "TotalYearsExperience", "CurrentlyEmployed", "ManagedOthers",
    "ManagedHowMany",
]
APPS_COLS = ["UserID", "WindowID", "Split", "ApplicationDate", "JobID"]
USER_HISTORY_COLS = ["UserID", "WindowID", "Split", "Sequence", "JobTitle"]
JOBS_COLS = [
    "JobID", "WindowID", "Title", "Description", "Requirements", "City", "State", "Country", "Zip5",
    "StartDate", "EndDate",
]
JOBS_TEXT_COLS = ["Title", "Description", "Requirements"]
WINDOW_DATES_COLS = ["Window", "Train Start", "Train End / Test Start", "Test End"]
TEST_USERS_COLS = ["UserID", "WindowID"]


@dataclass
class ReadStats:
    """Bookkeeping for one file read."""

    path: str
    header: list[str] = field(default_factory=list)
    n_lines: int = 0  # physical data lines (excluding header)
    n_rows: int = 0  # records returned
    n_skipped: int = 0  # records dropped (bad field count)
    n_stitched: int = 0  # records rebuilt from >1 physical line
    n_decode_errors: int = 0  # lines with invalid UTF-8
    n_filtered: int = 0  # records dropped by a user filter (not an error)
    skipped_examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["skipped_examples"] = [s[:200] for s in self.skipped_examples]
        return d


def _decode(raw: bytes, stats: ReadStats) -> str:
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        stats.n_decode_errors += 1
        s = raw.decode("utf-8", errors="replace")
    return s.rstrip("\r\n")


def iter_records(
    path: str | Path,
    expected_header: list[str] | None = None,
    max_stitch: int = 5,
    stats: ReadStats | None = None,
) -> Iterator[list[str]]:
    """Yield records (lists of str fields) from a TSV file, robust to bad lines.

    Pass a ReadStats to collect counts; header is validated against expected_header if given.
    """
    stats = stats if stats is not None else ReadStats(path=str(path))
    with open(path, "rb") as f:
        header_line = f.readline()
        header = _decode(header_line, stats).split("\t")
        stats.header = header
        if expected_header is not None and header != expected_header:
            raise ValueError(f"{path}: header {header} != expected {expected_header}")
        n_cols = len(header)
        pending: list[str] | None = None
        pending_lines = 0
        for raw in f:
            stats.n_lines += 1
            line = _decode(raw, stats)
            if pending is not None:
                # continue an under-filled record: the newline was inside the last field
                parts = line.split("\t")
                pending[-1] = pending[-1] + "\n" + parts[0]
                pending.extend(parts[1:])
                pending_lines += 1
                fields = pending
            else:
                fields = line.split("\t")
                pending_lines = 1
            if len(fields) == n_cols:
                if pending_lines > 1:
                    stats.n_stitched += 1
                pending = None
                stats.n_rows += 1
                yield fields
            elif len(fields) < n_cols and pending_lines < max_stitch:
                pending = fields
            else:
                stats.n_skipped += 1
                if len(stats.skipped_examples) < 5:
                    stats.skipped_examples.append("\t".join(fields))
                pending = None
        if pending is not None:
            stats.n_skipped += 1
            if len(stats.skipped_examples) < 5:
                stats.skipped_examples.append("\t".join(pending))


def read_tsv(
    path: str | Path,
    expected_header: list[str] | None = None,
    usecols: list[str] | None = None,
    row_filter: Callable[[list[str]], bool] | None = None,
    max_rows: int | None = None,
) -> tuple[pd.DataFrame, ReadStats]:
    """Read a TSV into a DataFrame of strings (empty string -> NA). Returns (df, stats).

    row_filter receives the full field list and returns True to keep the row.
    """
    stats = ReadStats(path=str(path))
    it = iter_records(path, expected_header=expected_header, stats=stats)
    header = None
    cols_idx: list[int] | None = None
    data: list[list[str]] = []
    for fields in it:
        if header is None:
            header = stats.header
            cols_idx = [header.index(c) for c in usecols] if usecols else list(range(len(header)))
        if row_filter is not None and not row_filter(fields):
            stats.n_filtered += 1
            continue
        data.append([fields[i] for i in cols_idx])  # type: ignore[union-attr]
        if max_rows is not None and len(data) >= max_rows:
            break
    if header is None:
        header = stats.header
        cols_idx = [header.index(c) for c in usecols] if usecols else list(range(len(header)))
    names = [header[i] for i in cols_idx]  # type: ignore[union-attr]
    df = pd.DataFrame(data, columns=names, dtype=object)
    df = df.replace({"": pd.NA})
    return df, stats


# ---------------------------------------------------------------- typed loaders

def _to_int(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def _to_dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", format="mixed")


def load_users(raw_dir: str | Path) -> tuple[pd.DataFrame, ReadStats]:
    df, st = read_tsv(Path(raw_dir) / "users.tsv", USERS_COLS)
    for c in ["UserID", "WindowID", "WorkHistoryCount", "TotalYearsExperience", "ManagedHowMany"]:
        df[c] = _to_int(df[c])
    df["GraduationDate"] = _to_dt(df["GraduationDate"])
    return df, st


def load_apps(raw_dir: str | Path) -> tuple[pd.DataFrame, ReadStats]:
    df, st = read_tsv(Path(raw_dir) / "apps.tsv", APPS_COLS)
    for c in ["UserID", "WindowID", "JobID"]:
        df[c] = _to_int(df[c])
    df["ApplicationDate"] = _to_dt(df["ApplicationDate"])
    return df, st


def load_user_history(raw_dir: str | Path) -> tuple[pd.DataFrame, ReadStats]:
    df, st = read_tsv(Path(raw_dir) / "user_history.tsv", USER_HISTORY_COLS)
    for c in ["UserID", "WindowID", "Sequence"]:
        df[c] = _to_int(df[c])
    return df, st


def load_window_dates(raw_dir: str | Path) -> pd.DataFrame:
    df, _ = read_tsv(Path(raw_dir) / "window_dates.tsv", WINDOW_DATES_COLS)
    out = pd.DataFrame(
        {
            "WindowID": _to_int(df["Window"]),
            "train_start": _to_dt(df["Train Start"]),
            "test_start": _to_dt(df["Train End / Test Start"]),
            "test_end": _to_dt(df["Test End"]),
        }
    )
    return out


def load_test_users(raw_dir: str | Path) -> pd.DataFrame:
    df, _ = read_tsv(Path(raw_dir) / "test_users.tsv", TEST_USERS_COLS)
    return df.apply(_to_int)


def load_jobs(
    raw_dir: str | Path,
    with_text: bool = True,
    windows: list[int] | None = None,
    max_rows: int | None = None,
) -> tuple[pd.DataFrame, ReadStats]:
    """Load jobs.tsv. with_text=False drops Description/Requirements (keeps Title) to save memory."""
    usecols = JOBS_COLS if with_text else [c for c in JOBS_COLS if c not in ("Description", "Requirements")]
    wset = {str(w) for w in windows} if windows else None
    row_filter = (lambda f: f[1] in wset) if wset else None
    df, st = read_tsv(Path(raw_dir) / "jobs.tsv", JOBS_COLS, usecols=usecols, row_filter=row_filter, max_rows=max_rows)
    df["JobID"] = _to_int(df["JobID"])
    df["WindowID"] = _to_int(df["WindowID"])
    for c in ["StartDate", "EndDate"]:
        df[c] = _to_dt(df[c])
    return df, st


def assign_period(app_dates: pd.Series, window_ids: pd.Series, window_dates: pd.DataFrame) -> pd.Series:
    """Label each application 'train' / 'test' / 'outside' by its window's date boundaries.

    train: train_start <= date < test_start ; test: test_start <= date < test_end.
    """
    wd = window_dates.set_index("WindowID")
    ts = window_ids.map(wd["train_start"])
    tt = window_ids.map(wd["test_start"])
    te = window_ids.map(wd["test_end"])
    out = np.where(
        (app_dates >= ts) & (app_dates < tt), "train", np.where((app_dates >= tt) & (app_dates < te), "test", "outside")
    )
    return pd.Series(out, index=app_dates.index, dtype="object")


def window_position(app_dates: pd.Series, window_ids: pd.Series, window_dates: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Finer position of each application w.r.t. its window.

    Returns (pos, day): pos in {'before','train','test','after'} and day = (date - train_start) in
    fractional days (negative before the window starts).
    """
    wd = window_dates.set_index("WindowID")
    ts = window_ids.map(wd["train_start"])
    tt = window_ids.map(wd["test_start"])
    te = window_ids.map(wd["test_end"])
    pos = np.where(app_dates < ts, "before", np.where(app_dates < tt, "train", np.where(app_dates < te, "test", "after")))
    day = (app_dates - ts).dt.total_seconds() / 86400.0
    return pd.Series(pos, index=app_dates.index, dtype="object"), day
