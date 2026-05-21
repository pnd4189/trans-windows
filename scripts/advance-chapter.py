#!/usr/bin/env python3
"""
advance-chapter.py — per-chapter state mutation for the auto_translate driver.

Ports the validation/advance logic that previously lived in
hooks/translate-hook.sh. Called by the external bash driver after each
subprocess returns. Stdout is JSON describing the next action so the driver
can branch without re-parsing state.json itself.

Args:
  --state <path>        path to per-novel state.json
  --chapter <id>        chapter id being advanced (state.chapters[id-1])
  --output-file <path>  the file the subprocess was supposed to write
  --fail-reason <msg>   pre-known failure reason (skip validation, force retry)

Stdout (one JSON object):
  {
    "action": "advance"|"retry"|"skip"|"done",
    "chapter_id": N,
    "display_id": N,
    "next_chapter": N|null,
    "retry_count": N,
    "max_retries": N,
    "cjk_bp": N,
    "fail_reason": "..."|null
  }

Exit code 0 always; caller inspects JSON.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CJK_FATAL_BP = 500   # >5% Chinese chars => fail and retry
CJK_WARN_BP = 100    # 1-5% => warn but accept
MIN_OUTPUT_BYTES = 200  # arbitrary floor for "non-empty"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cjk_ratio_bp(text: str) -> int:
    """Return Chinese character ratio in basis points (1 bp = 0.01%)."""
    total = sum(1 for c in text if c.strip())
    if total == 0:
        return 0
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return int(cjk * 10000 / total)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _merge_entities(state_file: Path, chapter_id: int, log_path: Path) -> None:
    """Best-effort entity merge. Errors are logged but never fatal."""
    script = Path(__file__).resolve().parent / "merge-entities.py"
    if not script.exists():
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script), str(state_file), str(chapter_id)],
            capture_output=True, text=True, timeout=30,
        )
        line = proc.stdout.strip() or proc.stderr.strip() or "no output"
    except Exception as exc:  # noqa: BLE001
        line = f"merge-entities error: {exc}"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{_now_iso()}] Chapter {chapter_id} entity merge: {line}\n")


def _finalize_if_done(state: dict, state_file: Path, log_path: Path) -> bool:
    """Mark novel inactive + run merge-chapters if every chapter terminal."""
    chapters = state.get("chapters", [])
    if not all(ch.get("status") in {"completed", "skipped"} for ch in chapters):
        return False
    state["active"] = False
    state["last_updated"] = _now_iso()
    _atomic_write_json(state_file, state)

    # Drop the global pointer so future hook fires no-op.
    try:
        Path("/tmp/.cli-tran-state-path").unlink(missing_ok=True)
    except OSError:
        pass

    merge_script = Path(__file__).resolve().parent / "merge-chapters.py"
    if merge_script.exists():
        try:
            proc = subprocess.run(
                [sys.executable, str(merge_script), str(state_file)],
                capture_output=True, text=True, timeout=60,
            )
            line = proc.stdout.strip() or proc.stderr.strip() or "no output"
        except Exception as exc:  # noqa: BLE001
            line = f"merge-chapters error: {exc}"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{_now_iso()}] Merge result: {line}\n")
    return True


def advance(state_file: Path, chapter_id: int, output_file: Path,
            fail_reason: str | None) -> dict:
    state = _read_json(state_file)
    chapters = state.get("chapters", [])
    idx = chapter_id - 1
    if not 0 <= idx < len(chapters):
        return {
            "action": "done",
            "chapter_id": chapter_id,
            "fail_reason": f"chapter {chapter_id} out of range (total {len(chapters)})",
        }

    ch = chapters[idx]
    display_id = ch.get("display_id") or ch.get("id") or chapter_id
    novel_dir = Path(state.get("novel_cache_dir") or state_file.parent)
    log_path = novel_dir / "hook.log"

    # 1. Validate output file
    cjk_bp = 0
    file_ok = False
    detected_fail: str | None = fail_reason

    if detected_fail is None:
        if not output_file.exists() or output_file.stat().st_size < MIN_OUTPUT_BYTES:
            detected_fail = f"output file missing or too small: {output_file}"
        else:
            try:
                text = output_file.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                detected_fail = f"cannot read output file: {exc}"
                text = ""
            if not detected_fail:
                cjk_bp = _cjk_ratio_bp(text)
                if cjk_bp > CJK_FATAL_BP:
                    detected_fail = f"CJK leak {cjk_bp}bp (>{CJK_FATAL_BP})"
                    try:
                        output_file.unlink()
                    except OSError:
                        pass
                else:
                    file_ok = True

    now = _now_iso()

    if file_ok:
        ch["status"] = "completed"
        ch["translated_at"] = now
        ch["output_file"] = str(output_file)
        ch["retry_count"] = 0
        ch["cjk_bp"] = cjk_bp
        state["chapters_completed"] = state.get("chapters_completed", 0) + 1
        state["last_updated"] = now

        # Advance pointer to next pending chapter
        next_chapter = None
        for j in range(idx + 1, len(chapters)):
            if chapters[j].get("status") not in {"completed", "skipped"}:
                next_chapter = chapters[j].get("id")
                break
        state["current_chapter"] = next_chapter or (len(chapters) + 1)

        _atomic_write_json(state_file, state)
        _merge_entities(state_file, chapter_id, log_path)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{now}] Chapter {chapter_id}: file OK -> completed (cjk={cjk_bp}bp).\n")

        if _finalize_if_done(state, state_file, log_path):
            return {
                "action": "done",
                "chapter_id": chapter_id,
                "display_id": display_id,
                "next_chapter": None,
                "retry_count": 0,
                "max_retries": ch.get("max_retries", 5),
                "cjk_bp": cjk_bp,
                "fail_reason": None,
            }

        return {
            "action": "advance",
            "chapter_id": chapter_id,
            "display_id": display_id,
            "next_chapter": next_chapter,
            "retry_count": 0,
            "max_retries": ch.get("max_retries", 5),
            "cjk_bp": cjk_bp,
            "fail_reason": None,
        }

    # Failure path
    retry_count = int(ch.get("retry_count", 0)) + 1
    max_retries = int(ch.get("max_retries", 5))
    ch["retry_count"] = retry_count
    state["last_updated"] = now

    if retry_count <= max_retries:
        _atomic_write_json(state_file, state)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                f"[{now}] Chapter {chapter_id}: FAILED ({detected_fail}). "
                f"Retry {retry_count}/{max_retries}.\n"
            )
        return {
            "action": "retry",
            "chapter_id": chapter_id,
            "display_id": display_id,
            "next_chapter": chapter_id,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "cjk_bp": cjk_bp,
            "fail_reason": detected_fail,
        }

    # Skip path
    ch["status"] = "skipped"
    ch["skip_reason"] = detected_fail
    ch["translated_at"] = now
    state["chapters_failed"] = state.get("chapters_failed", 0) + 1

    next_chapter = None
    for j in range(idx + 1, len(chapters)):
        if chapters[j].get("status") not in {"completed", "skipped"}:
            next_chapter = chapters[j].get("id")
            break
    state["current_chapter"] = next_chapter or (len(chapters) + 1)

    _atomic_write_json(state_file, state)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(
            f"[{now}] Chapter {chapter_id}: SKIPPED after {max_retries} retries "
            f"({detected_fail}).\n"
        )

    if _finalize_if_done(state, state_file, log_path):
        return {
            "action": "done",
            "chapter_id": chapter_id,
            "display_id": display_id,
            "next_chapter": None,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "cjk_bp": cjk_bp,
            "fail_reason": detected_fail,
        }

    return {
        "action": "skip",
        "chapter_id": chapter_id,
        "display_id": display_id,
        "next_chapter": next_chapter,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "cjk_bp": cjk_bp,
        "fail_reason": detected_fail,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", required=True, type=Path)
    ap.add_argument("--chapter", required=True, type=int)
    ap.add_argument("--output-file", required=True, type=Path)
    ap.add_argument("--fail-reason", default=None)
    args = ap.parse_args()

    if not args.state.exists():
        print(json.dumps({"action": "done", "fail_reason": "state file missing"}))
        return 2

    novel_dir = args.state.parent
    lock_path = novel_dir / ".state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Exclusive lock for the duration of the mutation; matches translate-hook.sh.
    with lock_path.open("w") as lock_fp:
        try:
            fcntl.flock(lock_fp, fcntl.LOCK_EX)
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EACCES):
                raise
        result = advance(args.state, args.chapter, args.output_file, args.fail_reason)
        fcntl.flock(lock_fp, fcntl.LOCK_UN)

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
