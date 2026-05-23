---
phase: 4
title: "Python Driver Rewrite"
status: pending
priority: P1
effort: "2.5h"
dependencies: [1, 2, 3]
---

# Phase 4: Python Driver Rewrite

## Overview

Rewrite `scripts/auto-translate.sh` (211 lines bash) as `scripts/auto-translate.py`. Written agy-only (Phase 3 already removed gemini). Includes cross-platform signal handling.

## Requirements

- Functional: Identical loop behavior — iterate pending chapters, translate, validate, advance
- Functional: Same env var support (`CLI_TRAN_MAX_CHAPTERS`, `CLI_TRAN_COOLDOWN`, etc.)
- Functional: Same stdout output format (final summary line)
- Functional: Graceful shutdown on Ctrl+C (persist state before exit)
- Non-functional: No bash dependency; `subprocess.run()` for all external calls

## Architecture

```
auto-translate.py (replaces auto-translate.sh)
  │
  ├── _read_json(path) -> dict
  ├── _find_next_pending(state_file) -> dict | None
  ├── _final_summary(state_file) -> str
  └── main()
        ├── resolve state pointer via state_pointer_path()
        ├── while loop: find next pending chapter
        ├── select-cascade.py via subprocess (agy only)
        ├── translate-chapter.py via subprocess (agy only)
        ├── advance-chapter.py via subprocess
        ├── status routing: ok/retry/cascade/fatal
        └── KeyboardInterrupt → persist state, clean exit
```

**Red team fix (M3):** Replace `/dev/null` as `--output-file` argument with `None` sentinel. On Windows, `Path("NUL").exists()` returns `False` which triggers wrong failure path. Pass empty string or skip `--output-file` when no output.

**Red team fix (H6):** Wrap main loop with `try/except KeyboardInterrupt` to persist state. On Windows, Ctrl+C sends `CTRL_C_EVENT` to subprocess; parent receives `KeyboardInterrupt` after subprocess terminates.

## Related Code Files

- Create: `scripts/auto-translate.py`
- Delete: `scripts/auto-translate.sh`
- Reference: `scripts/auto-translate.sh` (source for rewrite)

## Implementation Steps

1. Create `scripts/auto-translate.py`:
   - Import `sys`, `json`, `subprocess`, `time`, `os`, `signal` from pathlib
   - Import `state_pointer_path` from `lib.platform_paths`
   - Resolve state file from pointer
   - Main while loop (agy-only — no gemini code paths):
     - Find next pending → `select-cascade.py` → `translate-chapter.py` → `advance-chapter.py`
     - Status routing: `ok` → advance, `cascade` → mark fail + continue, `retry` → advance with fail, `fatal` → break
   - `KeyboardInterrupt` handler: log to driver.log, break cleanly
   - Safety limits: `MAX_TOTAL_CHAPTERS`, `CHAPTER_COOLDOWN_SECS`
   - Final summary to stdout
2. Key differences from bash:
   - `subprocess.run([sys.executable, script, ...])` instead of `"$PYTHON"`
   - `json.loads()` for parsing stdout instead of inline python
   - `time.sleep()` instead of `sleep`
   - `None` sentinel for missing output file (not `/dev/null` or `NUL`)
   - `subprocess.DEVNULL` for stderr suppression where needed
3. Delete `scripts/auto-translate.sh`

## Success Criteria

- [ ] `auto-translate.py` runs with `python auto-translate.py`
- [ ] `auto-translate.sh` deleted
- [ ] All env vars respected
- [ ] No `/dev/null` or `NUL` file path arguments (use `None`/empty sentinel)
- [ ] `KeyboardInterrupt` caught and state persisted
- [ ] `grep -rn 'auto-translate.sh' .` returns 0 matches
