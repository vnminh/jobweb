"""Logging helpers and run manifest."""

from __future__ import annotations

import datetime as dt
import json
import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from jobunicorn.config import REPO_ROOT


def get_logger(name: str = "jobunicorn", log_file: str | Path | None = None) -> logging.Logger:
    """Console logger (and optional file handler) with a compact format."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in logger.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    if log_file is not None:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    logger.propagate = False
    return logger


def git_commit() -> str:
    """Current git commit hash (with '-dirty' suffix), or 'unknown'."""
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.call(["git", "diff", "--quiet"], cwd=REPO_ROOT, stderr=subprocess.DEVNULL) != 0
        return sha + ("-dirty" if dirty else "")
    except Exception:
        # inside Modal containers there's no .git; launcher passes it via env
        import os

        return os.environ.get("JOBUNICORN_GIT_COMMIT", "unknown")


def write_manifest(out_dir: str | Path, cfg: dict[str, Any], extra: dict[str, Any] | None = None) -> Path:
    """Write run_manifest.json (config, seed, git commit, time, argv, host) to out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "time_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "seed": cfg.get("seed"),
        "argv": sys.argv,
        "python": sys.version.split()[0],
        "host": platform.node(),
        "config": cfg,
    }
    if extra:
        manifest.update(extra)
    p = out_dir / "run_manifest.json"
    p.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return p
