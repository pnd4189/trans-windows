#!/usr/bin/env python3
"""
merge-entities.py — Merge per-chapter entities into novel-glossary.json.

Policy: FIRST-SEEN WINS. When a Chinese term has been seen in an earlier
chapter, its translation is locked. Conflicting later translations are NOT
applied — they are written to glossary-conflicts.log so the user can audit.

This is the consistency mechanism that prevents AI drift across 1000+
chapters: once "李明 -> Lý Minh" is established in chapter 5, the same
mapping is force-fed back to the AI via the merged glossary in every
subsequent chapter.

Schema (per-chapter entities-NNN.json and merged novel-glossary.json):
  {
    "characters": { "中文": "Tiếng Việt", ... },
    "places":     { ... },
    "terms":      { ... },
    "pronouns":   { ... }
  }

The merged novel-glossary.json is shaped so glossary-loader.py's deep_merge
can pull it into the "characters"/"terms" buckets it already knows about.

Usage:
  python3 merge-entities.py <state_file> <chapter_id>
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ENTITY_CATEGORIES = ("characters", "places", "terms", "pronouns")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def merge_chapter_entities(novel_cache_dir: Path, chapter_id: int) -> dict:
    """Merge entities-NNN.json into novel-glossary.json with first-seen-wins."""
    entities_file = novel_cache_dir / "entities" / f"chapter_{chapter_id:03d}.json"
    if not entities_file.exists():
        return {"merged": 0, "conflicts": 0, "skipped": "no entities file"}

    chapter_entities = _read_json(entities_file)
    if not chapter_entities:
        return {"merged": 0, "conflicts": 0, "skipped": "empty entities file"}

    glossary_path = novel_cache_dir / "novel-glossary.json"
    conflicts_log = novel_cache_dir / "glossary-conflicts.log"

    glossary = _read_json(glossary_path)
    merged_count = 0
    conflict_count = 0
    conflict_lines: list[str] = []

    now = datetime.now(timezone.utc).isoformat()

    for category in ENTITY_CATEGORIES:
        if category not in chapter_entities:
            continue
        glossary.setdefault(category, {})

        for zh, vi in chapter_entities[category].items():
            if not zh or not vi:
                continue
            existing = glossary[category].get(zh)
            if existing is None:
                glossary[category][zh] = vi
                merged_count += 1
            elif existing != vi:
                conflict_count += 1
                conflict_lines.append(
                    f"[{now}] chapter {chapter_id} {category}: "
                    f"'{zh}' kept='{existing}' (first-seen) vs new='{vi}' — rejected"
                )

    _atomic_write_json(glossary_path, glossary)

    if conflict_lines:
        with conflicts_log.open("a", encoding="utf-8") as f:
            for line in conflict_lines:
                f.write(line + "\n")

    # Periodic snapshot every 50 chapters so corruption is recoverable
    snapshot_path = None
    if chapter_id > 0 and chapter_id % 50 == 0:
        snapshots_dir = novel_cache_dir / "glossary-snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        snapshot_path = snapshots_dir / f"novel-glossary.v{chapter_id:04d}.json"
        _atomic_write_json(snapshot_path, glossary)

    result = {"merged": merged_count, "conflicts": conflict_count}
    if snapshot_path:
        result["snapshot"] = str(snapshot_path)
    return result


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: merge-entities.py <state_file> <chapter_id>", file=sys.stderr)
        return 2

    state_file = Path(sys.argv[1])
    try:
        chapter_id = int(sys.argv[2])
    except ValueError:
        print(f"Invalid chapter_id: {sys.argv[2]}", file=sys.stderr)
        return 2

    if not state_file.exists():
        print(f"State file not found: {state_file}", file=sys.stderr)
        return 2

    state = json.loads(state_file.read_text(encoding="utf-8"))
    novel_cache_dir = Path(state.get("novel_cache_dir") or state_file.parent)

    result = merge_chapter_entities(novel_cache_dir, chapter_id)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
