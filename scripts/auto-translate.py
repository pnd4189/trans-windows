#!/usr/bin/env python3
"""auto-translate.py — External driver for cli-translator.

Lifecycle:
  1. Read state pointer from tempfile
  2. While the novel has pending chapters:
       a. select-cascade.py picks agy backend
       b. translate-chapter.py runs ONE subprocess per chapter
       c. advance-chapter.py validates output and advances state
       d. on backend quota errors, mark backend dead and re-pick
  3. Emit a final summary line for the calling skill to surface.

The driver is invoked from the cli-tran slash command. It runs entirely
outside the agent's turn context: every agy call is a separate subprocess
with its own bounded prompt.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from lib.platform_paths import state_pointer_path as _pointer_path

SCRIPT_DIR = Path(__file__).resolve().parent

MAX_TOTAL_CHAPTERS = int(os.environ.get("CLI_TRAN_MAX_CHAPTERS", "600"))
MAX_RETRIES_PER_CHAPTER = int(os.environ.get("CLI_TRAN_MAX_RETRIES", "5"))
CHAPTER_COOLDOWN_SECS = float(os.environ.get("CLI_TRAN_COOLDOWN", "2"))
CHILD_TIMEOUT_SECS = int(os.environ.get("CLI_TRAN_CHILD_TIMEOUT", "1020"))


def log(msg: str, driver_log: Path | None = None, _log_fh=None) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()
    elif driver_log:
        with driver_log.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _run_python(script: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True, text=True, timeout=CHILD_TIMEOUT_SECS,
    )


def _read_loop_state(state_file: Path) -> tuple[bool, dict | None]:
    """Read state.json once; return (is_active, next_pending_chapter_or_None)."""
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return False, None
    active = state.get("active") is True
    next_ch = None
    for ch in state.get("chapters", []):
        if ch.get("status") not in {"completed", "skipped"}:
            next_ch = {
                "id": ch["id"],
                "display_id": ch.get("display_id", ch["id"]),
                "title": ch.get("title", ""),
                "retry_count": ch.get("retry_count", 0),
            }
            break
    return active, next_ch


def _final_summary(state_file: Path) -> str:
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        total = state.get("total_chapters", 0)
        done = state.get("chapters_completed", 0)
        fail = state.get("chapters_failed", 0)
        active = state.get("active", False)
        pending = sum(
            1 for ch in state.get("chapters", [])
            if ch.get("status") not in {"completed", "skipped"}
        )
        d = {"total": total, "completed": done, "skipped": fail,
             "pending": pending, "active": active}
        status = "complete" if not d["active"] else "paused"
        return (f"Translation {status}: {d['completed']}/{d['total']} chapters done, "
                f"{d['skipped']} skipped, {d['pending']} pending. "
                f"Log: {state_file.parent / 'driver.log'}")
    except Exception as exc:
        return f"Driver done (summary error: {exc})"


def main() -> int:
    pointer = _pointer_path()
    if not pointer.exists():
        print(f"FATAL: no active translation (pointer {pointer} missing). "
              "Run /cli-tran <file> first.", file=sys.stderr)
        return 1

    state_file_str = pointer.read_text(encoding="utf-8").strip()
    state_file = Path(state_file_str)
    if not state_file.exists():
        print(f"FATAL: state file from {pointer} is not readable: {state_file}",
              file=sys.stderr)
        return 1

    novel_dir = state_file.parent
    driver_log = novel_dir / "driver.log"
    novel_dir.mkdir(parents=True, exist_ok=True)

    log_fh = driver_log.open("a", encoding="utf-8")
    try:
        def _log(msg: str) -> None:
            log(msg, _log_fh=log_fh)

        _log(f"Driver start. State={state_file}")

        active, next_meta = _read_loop_state(state_file)
        if not active:
            _log("Novel state.active=false. Nothing to do.")
            return 0

        processed_count = 0

        try:
            while True:
                if not state_file.exists():
                    _log(f"FATAL: state file vanished mid-run: {state_file}")
                    return 1

                if next_meta is None:
                    active, next_meta = _read_loop_state(state_file)
                    if not active:
                        _log("Novel marked inactive. Loop ends.")
                        break
                    if next_meta is None:
                        _log("All chapters terminal. Loop complete.")
                        break

                chapter_id = next_meta["id"]
                display_id = next_meta["display_id"]
                title = next_meta["title"]

                if processed_count >= MAX_TOTAL_CHAPTERS:
                    _log(f"Hit MAX_TOTAL_CHAPTERS={MAX_TOTAL_CHAPTERS}; halting safety stop.")
                    break

                # Pick backend
                cascade_result = _run_python(
                    SCRIPT_DIR / "select-cascade.py",
                    ["--state", str(state_file), "--json"],
                )
                try:
                    cascade_json = json.loads(cascade_result.stdout.strip()) if cascade_result.stdout else {}
                except json.JSONDecodeError:
                    cascade_json = {"backend": "", "reason": "selector error"}

                backend = cascade_json.get("backend", "")
                if not backend:
                    _log(f"All backends exhausted; halting. Detail: {cascade_json}")
                    break

                _log(f"Chapter {chapter_id} (display {display_id}) [{title}] via {backend}")

                # Translate
                translate_result = _run_python(
                    SCRIPT_DIR / "translate-chapter.py",
                    ["--state", str(state_file), "--chapter", str(chapter_id),
                     "--backend", backend, "--model", ""],
                )
                translate_stdout = translate_result.stdout.strip() if translate_result.stdout else ""

                if not translate_stdout:
                    translate_stdout = '{"status":"retry","fail_reason":"empty translator stdout"}'

                try:
                    tr = json.loads(translate_stdout)
                except json.JSONDecodeError:
                    tr = {"status": "unknown", "fail_reason": f"non-json output: {translate_stdout[:200]}"}

                status = tr.get("status", "")
                fail_reason = tr.get("fail_reason", "")
                output_file = tr.get("output_file", "")

                if status == "ok":
                    _log("  -> translated, validating...")
                    adv_result = _run_python(
                        SCRIPT_DIR / "advance-chapter.py",
                        ["--state", str(state_file), "--chapter", str(chapter_id),
                         "--output-file", output_file],
                    )
                    try:
                        adv = json.loads(adv_result.stdout.strip()) if adv_result.stdout else {}
                        action = adv.get("action", "")
                    except json.JSONDecodeError:
                        action = "parse-error"
                    _log(f"  advance action={action}")

                elif status == "cascade":
                    _log(f"  -> backend {backend} exhausted: {fail_reason}. Marking + retrying.")
                    _run_python(
                        SCRIPT_DIR / "select-cascade.py",
                        ["--state", str(state_file), "--mark-fail", backend],
                    )
                    time.sleep(CHAPTER_COOLDOWN_SECS)
                    next_meta = None  # re-read state after cascade
                    continue

                elif status == "retry":
                    _log(f"  -> transient failure: {fail_reason}. Advancing retry counter.")
                    _run_python(
                        SCRIPT_DIR / "advance-chapter.py",
                        ["--state", str(state_file), "--chapter", str(chapter_id),
                         "--output-file", output_file or "",
                         "--fail-reason", fail_reason],
                    )

                elif status == "fatal":
                    _log(f"  -> fatal: {fail_reason}. Halting.")
                    break

                else:
                    _log(f"  -> unknown status='{status}' result={translate_stdout[:200]}")
                    _run_python(
                        SCRIPT_DIR / "advance-chapter.py",
                        ["--state", str(state_file), "--chapter", str(chapter_id),
                         "--output-file", "", "--fail-reason", "unknown translator status"],
                    )

                processed_count += 1
                next_meta = None  # re-read state after each chapter
                time.sleep(CHAPTER_COOLDOWN_SECS)

        except KeyboardInterrupt:
            _log("Interrupted by user. State preserved — run /cli-tran --resume to continue.")

    finally:
        log_fh.close()

    summary = _final_summary(state_file)
    log(f"Driver done. {summary}", driver_log)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
