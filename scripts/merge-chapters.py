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


def _part_path_for(ch: dict, output_dir: Path) -> Path:
    """Resolve the chapter file path, tolerating legacy loop-id naming."""
    recorded = ch.get("output_file")
    if recorded:
        p = Path(recorded)
        if not p.is_absolute():
            p = output_dir / p
        if p.exists():
            return p
    display_id = ch.get("display_id", ch["id"])
    loop_id = ch["id"]
    for candidate in (
        output_dir / f"chapter_{display_id:03d}.txt",
        output_dir / f"chapter_{loop_id:03d}.txt",
    ):
        if candidate.exists():
            return candidate
    return output_dir / f"chapter_{display_id:03d}.txt"


def merge(state_path: Path) -> int:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    output_dir = Path(state["output_dir"])
    source_path = Path(state["source_file"])
    chapters = state.get("chapters", [])

    completed = [c for c in chapters if c.get("status") == "completed"]
    if not completed:
        print("No completed chapters to merge.", file=sys.stderr)
        return 1

    # Final merged file lives next to the source, not inside the per-novel cache.
    merged_path = source_path.parent / f"{source_path.stem}_vi.txt"

    parts = []
    missing = []
    used_paths = []
    for ch in completed:
        part_path = _part_path_for(ch, output_dir)
        if not part_path.exists():
            missing.append(part_path.name)
            continue
        body = part_path.read_text(encoding="utf-8").strip()
        parts.append(body)
        used_paths.append(part_path)

    if missing:
        print(f"Warning: {len(missing)} chapter file(s) missing: {missing}", file=sys.stderr)

    if not parts:
        print("No chapter files found to merge.", file=sys.stderr)
        return 1

    merged_path.write_text("\n\n\n".join(parts) + "\n", encoding="utf-8")

    deleted = 0
    for part_path in used_paths:
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
