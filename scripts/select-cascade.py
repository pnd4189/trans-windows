#!/usr/bin/env python3
"""
select-cascade.py — Pick the next backend for the translation loop.

Single backend: agy (via `agy -p`), uses the model configured in
~/.gemini/antigravity-cli/settings.json.

Probe checks binary presence via shutil.which (no live subprocess). A 5-minute
negative cache tracks recently-failed backends. A 1-hour positive cache
short-circuits the check on the happy path.

Usage:
  python select-cascade.py --state <state.json> [--mark-fail <backend>] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from lib.io_utils import atomic_write_json as _atomic_write_json
from lib.platform_paths import find_agy as _find_agy


CACHE_TTL_ALIVE = 3600
CACHE_TTL_DEAD = 300

BACKENDS = ("agy",)



def _cache_path(state_file: Path) -> Path:
    return state_file.parent / "backend_cache.json"


def _load_cache(state_file: Path) -> dict:
    p = _cache_path(state_file)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(state_file: Path, cache: dict) -> None:
    _atomic_write_json(_cache_path(state_file), cache)


def _is_fresh(entry: dict) -> bool:
    probed_at = entry.get("probed_at", 0)
    ttl = CACHE_TTL_ALIVE if entry.get("alive") else CACHE_TTL_DEAD
    return (time.time() - probed_at) < ttl


def _probe_agy() -> tuple[bool, str]:
    agy_path = _find_agy()
    if agy_path != "agy":
        return True, "ok"
    return False, "agy CLI not installed"


PROBES = {"agy": _probe_agy}


def _check_backend(state_file: Path, name: str) -> tuple[bool, str]:
    cache = _load_cache(state_file)
    entry = cache.get(name)
    if entry and _is_fresh(entry):
        return entry["alive"], entry.get("reason", "cache hit")
    alive, reason = PROBES[name]()
    cache[name] = {"alive": alive, "reason": reason, "probed_at": time.time()}
    _save_cache(state_file, cache)
    return alive, reason


def pick(state_file: Path) -> tuple[str, str]:
    """Return (backend, reason). backend is "" if nothing alive."""
    forced = os.environ.get("CLI_TRAN_FORCE_BACKEND", "").strip().lower()
    if forced in BACKENDS:
        alive, reason = _check_backend(state_file, forced)
        if alive:
            return forced, f"forced via CLI_TRAN_FORCE_BACKEND ({reason})"
        return "", f"forced backend {forced} not alive: {reason}"
    for name in BACKENDS:
        alive, reason = _check_backend(state_file, name)
        if alive:
            return name, reason
    return "", "all backends exhausted"


def mark_fail(state_file: Path, name: str, reason: str = "marked failed") -> None:
    cache = _load_cache(state_file)
    cache[name] = {"alive": False, "reason": reason, "probed_at": time.time()}
    _save_cache(state_file, cache)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", required=True, type=Path)
    ap.add_argument("--mark-fail", default=None,
                    help="Mark this backend as failed before picking next")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.state.exists():
        print("", flush=True)
        return 2

    if args.mark_fail:
        mark_fail(args.state, args.mark_fail, "explicit fail")

    backend, reason = pick(args.state)
    if args.json:
        print(json.dumps({"backend": backend, "reason": reason}))
    else:
        print(backend)
    return 0 if backend else 1


if __name__ == "__main__":
    sys.exit(main())
