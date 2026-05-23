"""Shared I/O utilities for cli-tran scripts."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Env vars stripped from subprocess env to prevent auth confusion.
API_KEY_STRIP = (
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_GCA",
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
    "VERTEXAI_PROJECT", "VERTEXAI_LOCATION",
)

# Strings that indicate backend quota exhaustion.
QUOTA_MARKERS = (
    "RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED", "Daily quota",
    "Per-minute quota", "quota exhausted", "PERMISSION_DENIED",
    "rate_limit", "429",
)


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically with cross-drive fallback."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.replace(path)
    except OSError:
        shutil.copy2(tmp, path)
        tmp.unlink(missing_ok=True)


def parse_iso(ts: str | None) -> float:
    """Parse ISO timestamp to epoch seconds; return 0.0 on failure."""
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def parse_iso_dt(ts: str | None) -> datetime | None:
    """Parse ISO timestamp to datetime; return None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
