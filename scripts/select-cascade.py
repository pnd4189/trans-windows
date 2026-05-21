#!/usr/bin/env python3
"""
select-cascade.py — Pick the next backend for the translation loop.

New cascade (replaces Pro1->Pro2):
  1. gemini-2.5-flash     (via `gemini -p -m <name>`)  -- strongest text Flash
  2. agy                  (via `agy -p`)               -- uses Claude Opus from
                                                          ~/.gemini/antigravity-cli/settings.json
  3. ""                   -- nothing left; caller halts

A 5-minute negative cache (per-novel) tracks recently-failed backends so the
loop does not re-probe a dead model on every chapter. A 1-hour positive cache
short-circuits the probe on the happy path.

Usage:
  python3 select-cascade.py --state <state.json> [--mark-fail <backend>] [--json]

`--mark-fail` records the backend as exhausted (for the negative-cache window)
and then prints the next backend in the chain. This is the call shape the
driver uses after a subprocess returns a quota / RESOURCE_EXHAUSTED error.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROBE_TIMEOUT_SECS = 60  # Claude Opus cold-start in agy can exceed 20s.
CACHE_TTL_ALIVE = 3600
CACHE_TTL_DEAD = 300

GEMINI_FLASH_MODEL = "gemini-2.5-flash"

BACKENDS = ("gemini", "agy")

_API_KEY_STRIP = (
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_GCA",
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
    "VERTEXAI_PROJECT", "VERTEXAI_LOCATION",
)


def _oauth_env() -> dict:
    env = os.environ.copy()
    for k in _API_KEY_STRIP:
        env.pop(k, None)
    return env


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
    p = _cache_path(state_file)
    p.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _is_fresh(entry: dict) -> bool:
    probed_at = entry.get("probed_at", 0)
    ttl = CACHE_TTL_ALIVE if entry.get("alive") else CACHE_TTL_DEAD
    return (time.time() - probed_at) < ttl


def _probe_gemini() -> tuple[bool, str]:
    if not shutil.which("gemini"):
        return False, "gemini CLI not installed"
    cmd = [
        "gemini", "-p", "OK", "-m", GEMINI_FLASH_MODEL, "--yolo",
        "-e", "__none__",
        "--allowed-mcp-server-names", "__none__",
        "--skip-trust",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=PROBE_TIMEOUT_SECS, env=_oauth_env())
    except subprocess.TimeoutExpired:
        return False, "probe timeout"
    except FileNotFoundError:
        return False, "gemini CLI missing"
    if proc.returncode != 0:
        return False, f"exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}"
    blob = (proc.stdout or "") + (proc.stderr or "")
    for marker in ("Daily quota", "Per-minute quota", "RESOURCE_EXHAUSTED",
                   "QUOTA_EXHAUSTED", "PERMISSION_DENIED"):
        if marker in blob:
            return False, marker
    return True, "ok"


def _probe_agy() -> tuple[bool, str]:
    if not shutil.which("agy"):
        return False, "agy CLI not installed"
    cmd = ["agy", "-p", "OK"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=PROBE_TIMEOUT_SECS, env=_oauth_env())
    except subprocess.TimeoutExpired:
        return False, "probe timeout"
    if proc.returncode != 0:
        return False, f"exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}"
    blob = (proc.stdout or "") + (proc.stderr or "")
    for marker in ("RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED", "PERMISSION_DENIED",
                   "quota exhausted", "Daily quota"):
        if marker in blob:
            return False, marker
    return True, "ok"


PROBES = {"gemini": _probe_gemini, "agy": _probe_agy}


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
