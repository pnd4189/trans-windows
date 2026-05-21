#!/usr/bin/env python3
"""
redo-chapters.py — Reset chapter status to 'pending' so the loop re-translates.

Usage:
  python3 redo-chapters.py <state_file> <spec>

<spec> forms:
  "5"       — single chapter
  "5-10"    — inclusive range
  "5,8,12"  — explicit list
  "failed"  — every chapter currently 'skipped'
  "all"     — every non-pending chapter

The script clears: status, retry_count, output_file, translated_at, skip_reason.
It also rewinds current_chapter to the lowest reset chapter so the loop picks
up there on next /cli-tran <file>.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_spec(spec: str, total: int) -> list[int]:
    spec = spec.strip().lower()
    if spec == "all":
        return list(range(1, total + 1))
    if spec == "failed":
        return []  # caller handles
    if "," in spec:
        return [int(x) for x in spec.split(",") if x.strip().isdigit()]
    m = re.match(r"^(\d+)-(\d+)$", spec)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return list(range(min(a, b), max(a, b) + 1))
    if spec.isdigit():
        return [int(spec)]
    raise ValueError(f"Unrecognized spec: {spec!r}")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: redo-chapters.py <state_file> <spec>", file=sys.stderr)
        return 2

    state_file = Path(sys.argv[1])
    spec = sys.argv[2]

    if not state_file.exists():
        print(f"State file not found: {state_file}", file=sys.stderr)
        return 2

    state = json.loads(state_file.read_text(encoding="utf-8"))
    total = state.get("total_chapters", 0)

    if spec.strip().lower() == "failed":
        targets = [c["id"] for c in state["chapters"] if c.get("status") == "skipped"]
    else:
        try:
            targets = parse_spec(spec, total)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

    targets = [t for t in targets if 1 <= t <= total]
    if not targets:
        print("No matching chapters to reset.")
        return 0

    target_set = set(targets)
    now = datetime.now(timezone.utc).isoformat()
    reset_count = 0
    completed_decrement = 0
    failed_decrement = 0

    for ch in state["chapters"]:
        if ch["id"] in target_set:
            prev_status = ch.get("status", "pending")
            if prev_status == "completed":
                completed_decrement += 1
            elif prev_status == "skipped":
                failed_decrement += 1
            ch["status"] = "pending"
            ch["retry_count"] = 0
            ch["output_file"] = None
            ch["translated_at"] = None
            ch["skip_reason"] = None
            ch.pop("cjk_bp", None)
            reset_count += 1

    state["chapters_completed"] = max(0, state.get("chapters_completed", 0) - completed_decrement)
    state["chapters_failed"] = max(0, state.get("chapters_failed", 0) - failed_decrement)
    state["current_chapter"] = min(targets)
    state["active"] = True
    state["last_updated"] = now

    tmp = state_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(state_file)

    print(f"Reset {reset_count} chapter(s): {sorted(target_set)}")
    print(f"current_chapter rewound to {min(targets)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
