#!/usr/bin/env python3
"""
model_registry.py — Discover Gemini models the user has actually invoked.

Scans the user's Gemini CLI session logs (~/.gemini/tmp/<project>/chats/*.jsonl)
and extracts every distinct model id that appears — those are demonstrably
available to this OAuth account.

Ordered most-recently-used first so prompts surface familiar choices on top.

Adapted from pdf-convert project.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

GEMINI_HOME = Path(os.environ.get("GEMINI_HOME", str(Path.home() / ".gemini")))
_MODEL_PATTERN = re.compile(r'"model"\s*:\s*"(gemini-[A-Za-z0-9.\-]+)"')


def discover_used_models() -> List[str]:
    """Return distinct gemini-* model ids found in CLI session logs, recent first."""
    tmp = GEMINI_HOME / "tmp"
    if not tmp.exists():
        return []

    files: list[tuple[float, Path]] = []
    for pattern in ("*/chats/*.jsonl", "*/chats/*.json"):
        for f in tmp.glob(pattern):
            try:
                files.append((f.stat().st_mtime, f))
            except OSError:
                continue
    files.sort(reverse=True)

    ordered: list[str] = []
    for _, path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for model_id in _MODEL_PATTERN.findall(content):
            if model_id not in ordered:
                ordered.append(model_id)
    return ordered


# --- Tier / version classifier ---------------------------------------------
# Pattern-based so any future Gemini family member is classified without a
# code change. "lite" must be checked before "flash" because lite ids are a
# superset (e.g. "gemini-2.5-flash-lite" contains "flash").

_TIER_PATTERNS = (
    ("lite",  ("flash-lite", "flash-8b")),
    ("flash", ("flash",)),
    ("ultra", ("ultra",)),
    ("pro",   ("pro",)),
)

_VERSION_RE = re.compile(r"gemini-(\d+)(?:\.(\d+))?")


def model_tier(name: str) -> str:
    """Classify into pro|flash|lite|ultra|unknown by substring match."""
    n = (name or "").lower()
    for tier, markers in _TIER_PATTERNS:
        if any(m in n for m in markers):
            return tier
    return "unknown"


def model_version(name: str) -> Tuple[int, int]:
    """Return (major, minor); (0, 0) if not parseable."""
    m = _VERSION_RE.search((name or "").lower())
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))


def is_preview(name: str) -> bool:
    """True for preview/experimental builds — used to throttle harder."""
    n = (name or "").lower()
    return "preview" in n or "-exp" in n or "experimental" in n


def rank_pro_candidates(candidates: List[str]) -> List[str]:
    """Sort Pro models by descending strength: version desc, GA before preview."""
    pros = [c for c in candidates if model_tier(c) == "pro"]
    return sorted(pros, key=lambda m: (
        -model_version(m)[0],
        -model_version(m)[1],
        1 if is_preview(m) else 0,
    ))


def rank_flash_candidates(candidates: List[str]) -> List[str]:
    """Sort Flash models by descending strength: version desc, GA before preview."""
    flashes = [c for c in candidates if model_tier(c) == "flash"]
    return sorted(flashes, key=lambda m: (
        -model_version(m)[0],
        -model_version(m)[1],
        1 if is_preview(m) else 0,
    ))
