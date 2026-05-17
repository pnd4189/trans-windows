#!/usr/bin/env python3
"""
select-model.py — Auto-select strongest available Gemini model.

Resolution priority:
  1. GEMINI_MODEL env var (explicit override)
  2. strongest_available() — Pro1 → Pro2 → Flash cascade with probe
  3. ~/.gemini/settings.json model field
  4. Most recent session log
  5. Empty → CLI default

Usage:
  python3 scripts/select-model.py [--json] [--quiet] [--exhausted model1,model2]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.model_registry import (
    GEMINI_HOME,
    discover_used_models,
    rank_pro_candidates,
    rank_flash_candidates,
)

# --- Constants ---

PROBE_TIMEOUT_SECS = 20
ISOLATION_FLAGS = [
    "-e", "__none__",
    "--allowed-mcp-server-names", "__none__",
    "--skip-trust",
]

_API_KEY_ENV_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_GCA",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "VERTEXAI_PROJECT",
    "VERTEXAI_LOCATION",
)

CACHE_DIR = GEMINI_HOME / "cli-translator"
CACHE_FILE = CACHE_DIR / "model_cache.json"
CACHE_TTL_ALIVE_SECS = 3600    # 1 hour for alive models
CACHE_TTL_DEAD_SECS = 300      # 5 minutes for dead models

_MIN_SESSION_BYTES = 300
_MODEL_PATTERN = re.compile(r'"model"\s*:\s*"(gemini-[A-Za-z0-9.\-]+)"')

_quiet = False


def _log(msg: str):
    if not _quiet:
        print(msg, file=sys.stderr, flush=True)


# --- OAuth environment ---

def _build_oauth_env() -> dict:
    """Return os.environ copy with API-key/Vertex selectors stripped, forcing OAuth."""
    env = os.environ.copy()
    for k in _API_KEY_ENV_VARS:
        env.pop(k, None)
    return env


# --- Settings and session scanning ---

def _read_settings_model() -> str:
    """Read ~/.gemini/settings.json → model field."""
    settings = GEMINI_HOME / "settings.json"
    if not settings.exists():
        return ""
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except Exception:
        return ""
    val = data.get("model")
    if isinstance(val, str) and val.strip():
        return val.strip()
    if isinstance(val, dict) and isinstance(val.get("name"), str):
        return val["name"].strip()
    return ""


def _scan_recent_session_model() -> str:
    """Return model id from most recent non-empty session log."""
    tmp = GEMINI_HOME / "tmp"
    if not tmp.exists():
        return ""
    candidates: list[tuple[float, Path]] = []
    for chat_file in tmp.glob("*/chats/*.jsonl"):
        try:
            st = chat_file.stat()
        except OSError:
            continue
        if st.st_size < _MIN_SESSION_BYTES:
            continue
        candidates.append((st.st_mtime, chat_file))
    for chat_file in tmp.glob("*/chats/*.json"):
        try:
            st = chat_file.stat()
        except OSError:
            continue
        if st.st_size < _MIN_SESSION_BYTES:
            continue
        candidates.append((st.st_mtime, chat_file))

    candidates.sort(reverse=True)
    for _, path in candidates[:8]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        matches = _MODEL_PATTERN.findall(content)
        if matches:
            return matches[-1]
    return ""


# --- Probe logic ---

def _probe_model_alive(model: str) -> bool:
    """Liveness check: does `gemini -p ok -m <model>` return cleanly?"""
    cmd = ["gemini", "-p", "ok", "-m", model, "--yolo", *ISOLATION_FLAGS]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECS,
            env=_build_oauth_env(),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    if proc.returncode != 0:
        return False
    blob = (proc.stderr or "") + (proc.stdout or "")
    # Reject quota/permission errors
    for marker in ("Daily quota", "Per-minute quota", "RESOURCE_EXHAUSTED",
                   "QUOTA_EXHAUSTED", "PERMISSION_DENIED", "NOT_FOUND"):
        if marker in blob:
            return False
    return True


# --- Probe caching ---

def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _is_cache_fresh(entry: dict) -> bool:
    """Check if cache entry is still within TTL."""
    probed_at = entry.get("probed_at", 0)
    ttl = CACHE_TTL_ALIVE_SECS if entry.get("alive") else CACHE_TTL_DEAD_SECS
    return (time.time() - probed_at) < ttl


def probe_with_cache(model: str) -> bool:
    """Probe model with caching to avoid repeated 20s probes."""
    cache = _load_cache()
    if model in cache and _is_cache_fresh(cache[model]):
        _log(f"[select-model] cache hit: {model} → {'alive' if cache[model]['alive'] else 'dead'}")
        return cache[model]["alive"]

    _log(f"[select-model] probing {model} (timeout {PROBE_TIMEOUT_SECS}s)...")
    alive = _probe_model_alive(model)
    _log(f"[select-model]   {model} → {'OK' if alive else 'unavailable'}")

    cache[model] = {
        "alive": alive,
        "probed_at": time.time(),
    }
    _save_cache(cache)
    return alive


def invalidate_cache(model: str):
    """Remove model from cache (e.g., after quota exhaustion)."""
    cache = _load_cache()
    cache.pop(model, None)
    _save_cache(cache)


# --- Cascade logic ---

def strongest_available(exhausted: list[str] | None = None) -> str:
    """
    Pro1 → Pro2 → Flash1 cascade.
    Returns strongest alive model, skipping exhausted ones.
    """
    exhausted = exhausted or []
    history = discover_used_models()

    # Try Pro models first
    pros = rank_pro_candidates(history)
    _log(f"[select-model] Pro candidates: {pros}")
    for pro in pros[:2]:
        if pro in exhausted:
            _log(f"[select-model]   {pro} → skipped (exhausted)")
            continue
        if probe_with_cache(pro):
            return pro

    # Fall back to Flash
    flashes = rank_flash_candidates(history)
    _log(f"[select-model] Flash candidates: {flashes}")
    for flash in flashes:
        if flash in exhausted:
            _log(f"[select-model]   {flash} → skipped (exhausted)")
            continue
        if probe_with_cache(flash):
            return flash

    return ""


# --- Main detection ---

def detect_active_model(exhausted: list[str] | None = None) -> tuple[str, str]:
    """
    Resolve which model to use. Returns (model_name, source).
    Priority:
      1. GEMINI_MODEL env var
      2. strongest_available() cascade
      3. ~/.gemini/settings.json
      4. Recent session log
      5. "" (CLI default)
    """
    chosen = os.environ.get("GEMINI_MODEL", "").strip()
    source = "env GEMINI_MODEL"
    if chosen:
        return chosen, source

    chosen = strongest_available(exhausted)
    source = "strongest_pro_auto_detect"
    if chosen:
        return chosen, source

    chosen = _read_settings_model()
    source = "~/.gemini/settings.json"
    if chosen:
        return chosen, source

    chosen = _scan_recent_session_model()
    source = "recent_session"
    if chosen:
        return chosen, source

    return "", "cli_default"


# --- CLI ---

def main():
    global _quiet

    parser = argparse.ArgumentParser(description="Select strongest available Gemini model")
    parser.add_argument("--json", action="store_true", help="Output JSON with model + source")
    parser.add_argument("--quiet", action="store_true", help="Suppress diagnostic output")
    parser.add_argument("--exhausted", type=str, default="",
                        help="Comma-separated list of exhausted models to skip")
    args = parser.parse_args()

    _quiet = args.quiet
    exhausted = [m.strip() for m in args.exhausted.split(",") if m.strip()]

    model, source = detect_active_model(exhausted)

    if args.json:
        print(json.dumps({"model": model, "source": source}))
    else:
        print(model)


if __name__ == "__main__":
    main()
