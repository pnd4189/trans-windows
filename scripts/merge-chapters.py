#!/usr/bin/env python3
"""Merge translated chapter files into a single output file.

Reads state.json to determine completed chapters and source filename,
concatenates chapter files in order, writes a single merged file, and
deletes the individual chapter parts.

Usage:
    python3 merge-chapters.py <state_file_path>
"""
import json
import sys
from pathlib import Path


def merge(state_path: Path) -> int:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    output_dir = Path(state["output_dir"])
    source_path = Path(state["source_file"])
    chapters = state.get("chapters", [])

    completed = [c for c in chapters if c.get("status") == "completed"]
    if not completed:
        print("No completed chapters to merge.", file=sys.stderr)
        return 1

    merged_path = output_dir.parent / f"{source_path.stem}_vi.txt"

    parts = []
    missing = []
    for ch in completed:
        cid = ch["id"]
        part_path = output_dir / f"chapter_{cid:03d}.txt"
        if not part_path.exists():
            missing.append(part_path.name)
            continue
        body = part_path.read_text(encoding="utf-8").strip()
        parts.append(body)

    if missing:
        print(f"Warning: {len(missing)} chapter file(s) missing: {missing}", file=sys.stderr)

    if not parts:
        print("No chapter files found to merge.", file=sys.stderr)
        return 1

    merged_path.write_text("\n\n\n".join(parts) + "\n", encoding="utf-8")

    deleted = 0
    for ch in completed:
        part_path = output_dir / f"chapter_{ch['id']:03d}.txt"
        if part_path.exists():
            part_path.unlink()
            deleted += 1

    try:
        output_dir.rmdir()
    except OSError:
        pass

    print(f"Merged {len(parts)} chapters -> {merged_path}")
    print(f"Deleted {deleted} individual chapter file(s).")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: merge-chapters.py <state_file_path>", file=sys.stderr)
        return 2
    state_path = Path(sys.argv[1])
    if not state_path.exists():
        print(f"State file not found: {state_path}", file=sys.stderr)
        return 2
    return merge(state_path)


if __name__ == "__main__":
    sys.exit(main())
