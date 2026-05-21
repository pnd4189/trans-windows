#!/usr/bin/env python3
"""
novel_cache.py — Per-novel ephemeral cache layout.

Each novel gets its own hash-keyed directory under ~/.cache/cli-tran/novels/<hash>/
so character/place/setting/pronoun memory never leaks between novels.

Hash key = sha256(absolute_source_path + first 1KB of file content)
  - Survives content renames if the source file moves but stays the same content
  - Distinguishes same-name files in different folders

Layout:
  ~/.cache/cli-tran/novels/<hash>/
    state.json, state.json.bak
    novel-glossary.json
    entities/chapter_NNN.json
    chapter-output/chapter_NNN.txt
    hook.log
    glossary-conflicts.log

TTL cleanup: a novel dir is eligible for deletion if state.active == false AND
state.last_updated is older than 24h. In-progress translations (active=true)
are always preserved regardless of age — user may pause for days.
"""

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE_ROOT = Path(os.environ.get("CLI_TRAN_CACHE_ROOT", str(Path.home() / ".cache" / "cli-tran")))
NOVELS_DIR = CACHE_ROOT / "novels"
TTL_SECS = 24 * 3600  # 24h after novel completion


def compute_novel_hash(source_path: Path) -> str:
    """sha256(absolute_source_path + first 1KB of content) — 16 hex chars."""
    abs_path = str(source_path.resolve()).encode("utf-8")
    try:
        with open(source_path, "rb") as f:
            head = f.read(1024)
    except OSError:
        head = b""
    h = hashlib.sha256()
    h.update(abs_path)
    h.update(b"\x00")
    h.update(head)
    return h.hexdigest()[:16]


def novel_cache_dir(source_path: Path) -> Path:
    """Return per-novel cache dir, creating parent dirs."""
    nhash = compute_novel_hash(source_path)
    d = NOVELS_DIR / nhash
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_file_for(source_path: Path) -> Path:
    return novel_cache_dir(source_path) / "state.json"


def chapter_output_dir(source_path: Path) -> Path:
    d = novel_cache_dir(source_path) / "chapter-output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def entities_dir(source_path: Path) -> Path:
    d = novel_cache_dir(source_path) / "entities"
    d.mkdir(parents=True, exist_ok=True)
    return d


def novel_glossary_path(source_path: Path) -> Path:
    return novel_cache_dir(source_path) / "novel-glossary.json"


def hook_log_path(source_path: Path) -> Path:
    return novel_cache_dir(source_path) / "hook.log"


def conflicts_log_path(source_path: Path) -> Path:
    return novel_cache_dir(source_path) / "glossary-conflicts.log"


def _parse_iso(ts: str) -> float:
    """Parse ISO timestamp to epoch seconds; return 0.0 on failure."""
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def cleanup_stale_novels(now: float | None = None) -> list[str]:
    """
    Delete novel cache dirs where state.active == false AND
    last_updated > TTL_SECS ago. Preserve in-progress novels.

    Returns list of deleted hash dirs.
    """
    if now is None:
        now = time.time()
    if not NOVELS_DIR.exists():
        return []

    deleted = []
    for novel_dir in NOVELS_DIR.iterdir():
        if not novel_dir.is_dir():
            continue
        state_file = novel_dir / "state.json"
        if not state_file.exists():
            # Orphaned dir with no state — leave it alone (could be partial init)
            continue
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # NEVER delete in-progress translations
        if state.get("active", True):
            continue

        last_updated = _parse_iso(state.get("last_updated", ""))
        if last_updated == 0.0:
            continue  # missing timestamp — be conservative

        if (now - last_updated) > TTL_SECS:
            try:
                shutil.rmtree(novel_dir)
                deleted.append(novel_dir.name)
            except OSError:
                pass

    return deleted


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Per-novel cache helper")
    parser.add_argument("--hash", type=str, help="Print hash for source file")
    parser.add_argument("--state-path", type=str, help="Print state.json path for source file")
    parser.add_argument("--cleanup", action="store_true", help="Run TTL cleanup")
    args = parser.parse_args()

    if args.hash:
        print(compute_novel_hash(Path(args.hash)))
    elif args.state_path:
        print(state_file_for(Path(args.state_path)))
    elif args.cleanup:
        deleted = cleanup_stale_novels()
        if deleted:
            print(f"Deleted {len(deleted)} stale novel cache(s): {', '.join(deleted)}")
        else:
            print("No stale novel caches.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
