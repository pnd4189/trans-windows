---
phase: 1
title: "Cross-Platform Infrastructure"
status: pending
priority: P1
effort: "1.5h"
dependencies: []
---

# Phase 1: Cross-Platform Infrastructure

## Overview

Fix all hardcoded Unix paths (`/tmp`, `~/.cache/`) across 5 files. Create shared `platform-paths.py` helper. Audit all `Path.rename()` calls and replace with `Path.replace()` (atomic on Windows). Fix `python3` hardcodes to `sys.executable`.

## Requirements

- Functional: All path references resolve correctly on both Windows and Linux
- Non-functional: No external dependencies; `os.name` / `sys.platform` detection only

## Architecture

`scripts/lib/platform-paths.py` — 2 functions:
- `state_pointer_path()` → `Path(tempfile.gettempdir()).resolve() / ".cli-tran-state-path"` (env override via `CLI_TRAN_STATE_POINTER`)
- `cache_root()` → `%LOCALAPPDATA%\cli-tran` on Windows, `~/.cache/cli-tran` on Linux (env override via `CLI_TRAN_CACHE_ROOT`)

**Red team fix (C3):** Use `.resolve()` on `gettempdir()` to normalize 8.3 short names.

**Red team fix (C1):** Audit all `.rename()` → `.replace()` across all scripts. `Path.replace()` overwrites target on Windows; `Path.rename()` raises `FileExistsError` and fails cross-drive.

## Related Code Files

- Create: `scripts/lib/platform-paths.py`
- Modify: `scripts/advance-chapter.py` (line 98: `/tmp/...`)
- Modify: `scripts/init-translation.py` (line 262: `/tmp/...`, line 243: `python3`, lines 85,204: `.rename()`)
- Modify: `scripts/get-progress.py` (line 15: `/tmp/...`)
- Modify: `scripts/recover-state.py` (line 91: `/tmp/...`)
- Modify: `scripts/lib/novel_cache.py` (line 34: `~/.cache/...`)
- Modify: `scripts/redo-chapters.py` (line 102: `.rename()`)

## Implementation Steps

1. Create `scripts/lib/platform-paths.py` with `state_pointer_path()` and `cache_root()` functions
2. Update `novel_cache.py` — replace `CACHE_ROOT` with `from lib.platform_paths import cache_root; CACHE_ROOT = cache_root()`
3. Update `advance-chapter.py:98` — replace `Path("/tmp/.cli-tran-state-path")` with `state_pointer_path()`
4. Update `init-translation.py:262` — replace `Path('/tmp/...')` with `state_pointer_path()`
5. Update `init-translation.py:243` — replace `"python3"` with `sys.executable`
6. Update `get-progress.py:15` — replace `Path("/tmp/...")` with `state_pointer_path()`
7. Update `recover-state.py:91` — replace `Path("/tmp/...")` with `state_pointer_path()`
8. **Red team C1:** Audit ALL `.rename()` calls → `.replace()`:
   - `init-translation.py:85` — `.rename()` → `.replace()`
   - `init-translation.py:204` — `.rename()` → `.replace()`
   - `redo-chapters.py:102` — `.rename()` → `.replace()`
   - `advance-chapter.py:67` — already uses `.replace()` ✓

## Success Criteria

- [ ] `platform-paths.py` exists and exports `state_pointer_path()` + `cache_root()`
- [ ] No hardcoded `/tmp/` or `/dev/null` references remain in any Python file
- [ ] `grep -rn '"/tmp/' scripts/` returns 0 matches
- [ ] No `python3` string remains — `grep -rn 'python3' scripts/` returns 0 matches
- [ ] `novel_cache.py` uses `cache_root()` from `platform-paths.py`
- [ ] All `.rename()` calls replaced with `.replace()` — `grep -rn '\.rename(' scripts/` returns 0 matches
