"""Configuration: load YAML, merge CLI overrides, set seeds."""

from __future__ import annotations

import argparse
import copy
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file; supports a top-level `base:` key pointing to another YAML (relative path)."""
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    base = cfg.pop("base", None)
    if base:
        base_cfg = load_yaml((path.parent / base).resolve())
        cfg = deep_merge(base_cfg, cfg)
    return cfg


def deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict: b merged into a recursively (b wins)."""
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _parse_value(s: str) -> Any:
    """Parse a CLI override value with YAML semantics (ints, floats, bools, lists)."""
    return yaml.safe_load(s)


def apply_overrides(cfg: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """Apply `a.b.c=value` overrides to a config dict."""
    cfg = copy.deepcopy(cfg)
    for ov in overrides:
        if "=" not in ov:
            raise ValueError(f"Override must be key=value, got {ov!r}")
        key, val = ov.split("=", 1)
        node = cfg
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = _parse_value(val)
    return cfg


def set_seed(seed: int) -> None:
    """Seed python, numpy and torch (if installed)."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def base_arg_parser(description: str = "") -> argparse.ArgumentParser:
    """Standard parser every script uses: --config, --seed, --data-root, --out, and key=value overrides."""
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--config", type=str, default=str(REPO_ROOT / "configs" / "default.yaml"))
    ap.add_argument("--seed", type=int, default=None, help="overrides cfg.seed")
    ap.add_argument("--data-root", type=str, default=None, help="overrides cfg.paths.data_root")
    ap.add_argument("--out", type=str, default=None, help="output directory (overrides cfg.paths.out)")
    ap.add_argument("overrides", nargs="*", help="config overrides key.sub=value")
    return ap


def resolve_config(args: argparse.Namespace) -> dict[str, Any]:
    """Build the final config from parsed args; also seeds RNGs."""
    cfg = load_yaml(args.config)
    cfg = apply_overrides(cfg, args.overrides or [])
    if args.seed is not None:
        cfg["seed"] = args.seed
    cfg.setdefault("seed", 0)
    cfg.setdefault("paths", {})
    if args.data_root is not None:
        cfg["paths"]["data_root"] = args.data_root
    if args.out is not None:
        cfg["paths"]["out"] = args.out
    dr = cfg["paths"].get("data_root", "data")
    if not os.path.isabs(dr):
        cfg["paths"]["data_root"] = str((REPO_ROOT / dr).resolve())
    cfg["_config_path"] = str(args.config)
    set_seed(int(cfg["seed"]))
    return cfg
