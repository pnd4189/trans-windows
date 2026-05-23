# Architecture & Cross-Platform Design Review

**Reviewer:** code-reviewer (task #3)
**Date:** 2026-05-23
**Scope:** Full project structure — scripts/, scripts/lib/, skills/cli-tran/, install.py, plans/, README.md

---

## CRITICAL Issues

### C1. Duplicate atomic-write logic across 6 files

The `tmp.write_text() → tmp.replace() → shutil.copy2 fallback` pattern is independently implemented in:
- `advance-chapter.py:65-73` (`_atomic_write_json`)
- `merge-entities.py:46` (`_atomic_write_json`)
- `init-translation.py:37-52` (`_atomic_write_state`)
- `recover-state.py:85-92` (inline)
- `redo-chapters.py:108-115` (inline)
- `select-cascade.py:64-71` (inline)

Any bug fix (e.g., encoding, error handling, cross-drive behavior) must be applied 6 times. This is a maintenance hazard.

**Recommendation:** Extract `atomic_write_json(path, data)` into `scripts/lib/io_utils.py`. All scripts import from one place.

### C2. `sys.path.insert` repeated in every script (8 occurrences)

Every entry-point script repeats `sys.path.insert(0, str(Path(__file__).resolve().parent))` to resolve `lib.*` imports:
- `advance-chapter.py:40`
- `auto-translate.py:25`
- `get-progress.py:9`
- `init-translation.py:15` (and again at line 279)
- `recover-state.py:9`
- `redo-chapters.py:26`
- `translate-chapter.py:99`

Fragile — depends on exact invocation directory. Breaks if a script is imported as a module rather than run directly.

**Recommendation:** Add `scripts/__init__.py` and use relative imports, or add `scripts/` to `sys.path` via a sitecustomize or entry-point shim. At minimum, extract to a one-liner `_setup_path()` in `lib/__init__.py`.

---

## IMPORTANT Issues

### I1. Plan numbering chaos — 14 phase files for 7 phases

Two separate planning passes produced overlapping files:
- **Pass 1 (original):** `phase-01-core-extension-state-management.md`, `phase-02-hook-loop-control.md`, `phase-03-glossary-genre-system.md`, `phase-04-translation-engine.md`, `phase-05-quality-validation.md`, `phase-06-epub-support.md`, `phase-07-testing-polish.md`
- **Pass 2 (cross-platform):** `phase-01-cross-platform-infrastructure.md`, `phase-02-cross-platform-file-locking.md`, `phase-03-python-driver-rewrite.md`, `phase-04-installer-rewrite.md`, `phase-05-backend-simplification.md`, `phase-06-skill-and-config-updates.md`, `phase-07-readme-and-documentation.md`

The `plan.md` only references Pass 2 files, but Pass 1 files remain. Phase numbers in `plan.md` don't match file numbers (e.g., "Phase 3" links to `phase-05-backend-simplification.md`).

**Recommendation:** Archive Pass 1 files to `plans/archive/` or delete them. Keep only the active plan's files.

### I2. README project structure lists wrong filename

`README.md:109` lists `platform-paths.py` (hyphen). Actual file is `platform_paths.py` (underscore). Same mismatch in `plans/phase-01-cross-platform-infrastructure.md` (lines 14, 23, 33, 43, 58, 62).

**Recommendation:** Update README and plan to match actual filename `platform_paths.py`.

### I3. Dead code: `model_registry.py` never imported

`scripts/lib/model_registry.py` exists but is never imported by any script in the codebase. `grep -rn 'model_registry' scripts/` returns only the file's own docstring.

**Recommendation:** Delete if truly unused, or document its purpose if it's a future feature.

### I4. `novel_cache.py` module-level side effect

```python
CACHE_ROOT = _cache_root()  # line 39
NOVELS_DIR = CACHE_ROOT / "novels"  # line 40
```

These execute at import time. If `CLI_TRAN_CACHE_ROOT` is set after the module is imported (e.g., in tests or multi-tenant scenarios), the paths are stale.

**Recommendation:** Make `CACHE_ROOT` and `NOVELS_DIR` lazy (function calls or `functools.cache`).

### I5. `file_lock.py` Windows edge case — empty file race

```python
size = os.fstat(fd).st_size
if size == 0:
    os.write(fd, b"L")
    size = 1
```

If two processes open the same lock file simultaneously and both see `size == 0`, both write "L" and then both try `msvcrt.locking(fd, LK_LOCK, 1)`. The second lock attempt will block (correct behavior), but the file now contains "LL" instead of "L". Functionally harmless since `msvcrt.locking` locks byte ranges, but the intent is unclear — `msvcrt.locking` locks `size` bytes starting from the current seek position.

**Recommendation:** Use `os.lseek(fd, 0, os.SEEK_SET)` before locking to ensure consistent behavior, or document that the byte content doesn't matter.

### I6. `platform_paths.py` macOS falls through to Linux path

```python
def cache_root() -> Path:
    if sys.platform == "win32":
        ...
    return Path.home() / ".cache" / "cli-tran"
```

On macOS, `~/.cache` is not the XDG convention. macOS uses `~/Library/Caches/`. While `~/.cache` works, it's non-standard.

**Recommendation:** Add `elif sys.platform == "darwin": return Path.home() / "Library" / "Caches" / "cli-tran"` or document the intentional deviation.

### I7. `install.py` — no rollback on partial failure

If `install.py` fails at step 4 (hooks) or step 5 (GEMINI.md), the staging directory and partial extension directory are left behind. Re-running works (staging is deleted first), but the user sees confusing partial state.

**Recommendation:** Wrap in try/except, clean up on failure, or document that re-running is safe.

---

## MODERATE Issues

### M1. `advance-chapter.py` deferred import of `file_lock`

```python
# line 296 (inside main())
from lib.file_lock import acquire, release
```

All other scripts import at module level. This inconsistency suggests the import was moved to avoid a circular dep that doesn't actually exist.

**Recommendation:** Move to module-level import for consistency.

### M2. `translate-chapter.py:104` — `exec()` for glossary loader

```python
loader_src = (repo_root / "scripts" / "glossary-loader.py").read_text(encoding="utf-8")
ns: dict = {}
exec(compile(loader_src, "glossary-loader.py", "exec"), ns)
```

Uses `exec()` to load a module with a hyphenated filename. This is fragile (no error context if the file has syntax errors) and a security smell.

**Recommendation:** Rename `glossary-loader.py` to `glossary_loader.py` and use standard imports.

### M3. `init-translation.py:17-24` — `importlib.util` for detect-chapters

```python
_spec = importlib.util.spec_from_file_location("detect_chapters", ...)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
```

Same hyphenated-filename workaround. Verbose and error-prone.

**Recommendation:** Rename `detect-chapters.py` to `detect_chapters.py` and use standard imports.

### M4. `auto-translate.py` re-reads state.json on every iteration

`_find_next_pending()` (line 69-82) reads and parses the full state.json every loop iteration. For a 500-chapter novel, this is 500+ JSON parses of a growing file (each chapter adds metadata).

**Impact:** Low (JSON parse is fast for ~100KB files), but wasteful.

**Recommendation:** Cache the state in memory and re-read only after `advance-chapter.py` modifies it.

### M5. `recover-state.py` does not take file lock

`recover-state.py` writes state.json (line 85-92) without acquiring the `.state.lock`. If the driver is running concurrently, state corruption is possible.

**Recommendation:** Acquire lock before writing, consistent with other scripts.

### M6. Plan phase dependencies not reflected in file ordering

`plan.md` says Phase 3 = Backend Simplification, but `phase-05-backend-simplification.md` has file number 5. Phase 4 = Python Driver Rewrite maps to `phase-03-python-driver-rewrite.md`. The semantic ordering and file numbering are decoupled.

**Recommendation:** Either renumber files to match plan order, or use descriptive names without numbers.

---

## Positive Observations

1. **Clean separation of concerns** — each script does one thing: translate, advance, select, init, recover, redo, progress. No god-modules.

2. **Platform branching is localized** — `sys.platform == "win32"` checks exist only in `platform_paths.py`, `file_lock.py`, and `install.py`. No platform checks scattered across business logic.

3. **Atomic writes are correct** — `Path.replace()` is used everywhere (not `Path.rename()`), which is the right cross-platform choice. The `shutil.copy2` fallback handles cross-drive edge cases.

4. **State pointer pattern is sound** — the temp-dir pointer file allows loose coupling between init and driver without PID-based fragile matching.

5. **Driver subprocess architecture** — each chapter runs as an isolated subprocess, preventing context window blowup and enabling clean Ctrl+C recovery.

6. **Cross-platform file lock uses stdlib only** — no `portalocker` or `filelock` dependency. `fcntl`/`msvcrt` with auto-release on process death is correct.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| IMPORTANT | 7 |
| MODERATE | 6 |

The architecture is sound in design — clean module boundaries, correct cross-platform abstractions, good state management. The main risks are maintenance hazards from code duplication (atomic writes, sys.path.insert) and plan/document drift (stale phase files, wrong filenames in docs). No security vulnerabilities found. No race conditions in normal operation (file lock usage is correct). The `exec()` workaround for hyphenated filenames is the most actionable code smell.
