# Code Quality & Maintainability Review

**Date:** 2026-05-23
**Scope:** 12 files (2158 LOC total)
**Focus:** Code structure, readability, error handling, Python best practices, DRY, file size

---

## File Size Summary

| File | Lines | Target | Status |
|------|-------|--------|--------|
| advance-chapter.py | 311 | <200 | OVER |
| get-progress.py | 132 | <200 | OK |
| init-translation.py | 302 | <200 | OVER |
| recover-state.py | 105 | <200 | OK |
| redo-chapters.py | 126 | <200 | OK |
| select-cascade.py | 159 | <200 | OK |
| translate-chapter.py | 355 | <200 | OVER |
| auto-translate.py | 257 | <200 | OVER |
| novel_cache.py | 171 | <200 | OK |
| file_lock.py | 45 | <200 | OK |
| platform_paths.py | 36 | <200 | OK |
| install.py | 159 | <200 | OK |

---

## Findings

### CRITICAL

**C1. `exec()` used to load glossary-loader.py** -- `translate-chapter.py:106` -- The fallback uses `exec(compile(loader_src, ...))` to load a hyphenated filename. This is a code injection vector if `glossary-loader.py` is ever tampered with. Use `importlib.util.spec_from_file_location()` (same pattern already used in `init-translation.py:17-24` for `detect-chapters.py`).

```python
# Current (unsafe):
loader_src = (repo_root / "scripts" / "glossary-loader.py").read_text(encoding="utf-8")
ns: dict = {}
exec(compile(loader_src, "glossary-loader.py", "exec"), ns)
load_glossary = ns["load_glossary"]

# Fix:
import importlib.util
spec = importlib.util.spec_from_file_location("glossary_loader", str(repo_root / "scripts" / "glossary-loader.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
load_glossary = mod.load_glossary
```

**C2. recover-state.py has no file locking during state mutation** -- `recover-state.py:84-92` -- The recovery script reads state, mutates it, and writes it back without acquiring a file lock. If the auto-translate driver is running concurrently, this corrupts state.json. Every other state-mutating script (advance-chapter, redo-chapters, init-translation) uses `file_lock.acquire` before writing. This one does not.

---

### IMPORTANT

**I1. DRY: Atomic write + cross-drive fallback duplicated 6 times** -- `advance-chapter.py:65-73`, `init-translation.py:37-52`, `recover-state.py:84-92`, `redo-chapters.py:107-115`, `select-cascade.py:62-71`, `translate-chapter.py:335-341` -- The pattern `write tmp -> try replace -> except OSError: shutil.copy2 + unlink` is copy-pasted in every file. Extract to `lib/atomic_write.py` or add to `lib/file_lock.py`. The `init-translation.py` variant wraps this under a lock; the others should too or at minimum share the write primitive.

**I2. DRY: API-key strip list duplicated across 3 files** -- `advance-chapter.py` (not present, but `select-cascade.py:33-38` and `translate-chapter.py:76-84` and `auto-translate.py` indirectly) -- `_API_KEY_STRIP` / `_clean_env` / `_oauth_env` all define the same 8 env var names. One canonical list should live in `lib/` (e.g., `platform_paths.py` or a new `lib/env.py`).

**I3. DRY: QUOTA_MARKERS duplicated** -- `select-cascade.py:92-96` and `translate-chapter.py:38-42` -- Same list of quota detection strings in two files. Extract to a shared constant.

**I4. DRY: "find next pending chapter" loop duplicated** -- `advance-chapter.py:178-182` and `advance-chapter.py:243-247` -- Identical loop within the same file. Extract to a helper function.

**I5. DRY: `_parse_iso` duplicated** -- `get-progress.py:26-32` and `novel_cache.py:95-102` -- Nearly identical ISO timestamp parsing. Extract to `lib/platform_paths.py` or a shared utility.

**I6. `advance-chapter.py` exceeds 200-line target (311 lines)** -- The `advance()` function (lines 123-277) is 155 lines with deeply nested if/else. The success path, failure path, and skip path each build nearly identical JSON dicts. Extract the "find next chapter" helper, consolidate the return dict construction, and consider splitting `advance()` into `_handle_success()` / `_handle_retry()` / `_handle_skip()`.

**I7. `init-translation.py` exceeds 200-line target (302 lines)** -- `init_translation()` is 170 lines (58-227). The idempotent-resume block (76-119) is 44 lines of nested logic. The auto-detect genre + model detection + chapter building adds up. Split into `_resume_existing()`, `_build_initial_state()`, and keep `init_translation` as orchestrator.

**I8. `translate-chapter.py` exceeds 200-line target (355 lines)** -- `main()` alone is 130 lines. The file mixes prompt construction, subprocess invocation, stdout cleaning, and file I/O in one function. Extract `_build_prompt` call sequence and the post-translate validation/persist block into helpers.

**I9. `auto-translate.py` exceeds 200-line target (257 lines)** -- The main loop (133-248) is 115 lines with 6 levels of nesting. The translate/advance/cascade/retry branching is hard to follow. Extract `_handle_translate_result()` to contain the status switch.

**I10. `_read_state_field` is over-engineered** -- `auto-translate.py:52-66` -- A generic dot-path accessor with digit-index support, used only for `_read_state_field(state_file, "active")`. Replace with a direct `state.get("active")` read or a simple `_is_active(state_file) -> bool` helper. The generic accessor adds complexity for a single use case.

**I11. Multiple redundant state.json reads per iteration** -- `auto-translate.py` -- In the main loop, `_read_state_field(state_file, "active")` reads the file (line 139), then `_find_next_pending(state_file)` reads it again (line 144). Each iteration parses state.json 2-3 times. Read once and pass the dict through.

**I12. Lazy `import shutil` inside functions** -- `advance-chapter.py:72`, `recover-state.py:91`, `redo-chapters.py:114` -- `shutil` is a stdlib module with negligible import cost. Importing it inside `except OSError` blocks is unnecessary deferral and hurts readability. Import at the top of the file.

---

### MODERATE

**M1. `_write_state_pointer` re-inserts sys.path unnecessarily** -- `init-translation.py:279` -- `sys.path.insert(0, _scripts_dir)` is already done at line 15. The duplicate insert is harmless but confusing.

**M2. Inconsistent indentation in recover-state.py** -- `recover-state.py:61-62` -- The comment and code under `elif chapter['status'] == 'completed':` uses 6-space indent instead of the surrounding 4-space indent. This is a style inconsistency (not a syntax error since Python allows it, but it's misleading).

**M3. `subprocess` imported at top level but only used in one function** -- `advance-chapter.py:35` -- `subprocess` is only used in `_merge_entities` and `_finalize_if_done`. This is fine for clarity but the import could be local since those are optional best-effort calls. Minor; not worth changing.

**M4. `importlib.util` used for dynamic loading in two files with different patterns** -- `init-translation.py:17-24` uses `spec_from_file_location` correctly; `translate-chapter.py:104-107` uses `exec()` (flagged as C1). After fixing C1, both will use the same pattern -- consider extracting a `_load_hyphen_module(path)` helper in `lib/` since hyphenated filenames are a recurring issue.

**M5. Magic number 12 in session_id** -- `init-translation.py:99,190` -- `uuid.uuid4().hex[:12]` truncates to 12 chars. The choice of 12 is unexplained. If this is for collision resistance, document the rationale. If arbitrary, consider full UUID.

**M6. `auto_translate.py` line 127: string comparison for boolean** -- `active not in (True, "True", "true")` -- The state.json stores `active` as a JSON boolean, but this code also accepts string "True"/"true". This suggests a past or feared serialization bug. If state.json is always valid JSON, `active is not True` suffices. If there's a real concern, document why.

**M7. `_auto_detect_genre` catches all exceptions silently** -- `init-translation.py:246` -- `except Exception: return None` swallows everything including `KeyboardInterrupt` (in Python <3.11 this is not an issue since `KeyboardInterrupt` inherits from `BaseException`, but `SystemExit` would be caught). Use `except (OSError, ImportError, AttributeError)` for the specific failure modes.

**M8. No type hints on several functions** -- `recover-state.py:12` (`recover_state`), `get-progress.py:126` (`main`), `novel_cache.py:148` (`main`) -- Public functions lack return type annotations. The codebase generally uses type hints well; these are outliers.

---

## Positive Observations

1. **Consistent atomic write pattern** -- Every state mutation writes to `.tmp` then replaces. Good defensive practice.
2. **file_lock.py is clean and minimal** -- 46 lines, correct cross-platform behavior, auto-release on process death.
3. **platform_paths.py is well-designed** -- Env-var overrides, platform detection, 37 lines total.
4. **CJK detection in basis points** -- Creative and precise approach to detecting translation quality regressions.
5. **Good use of pathlib throughout** -- No raw string path manipulation except where interfacing with subprocess args.
6. **Idempotent init** -- `init-translation.py` correctly handles resume on already-active translations without re-initializing.
7. **Clean CLI interfaces** -- All scripts use argparse or sys.argv consistently, output JSON for machine consumption, print human-readable to stderr.

---

## Recommended Actions (Priority Order)

1. **Fix C1** -- Replace `exec()` with `importlib.util` in `translate-chapter.py:104-107`. Security risk.
2. **Fix C2** -- Add file locking to `recover-state.py`. Data corruption risk.
3. **Extract shared `atomic_write_json()`** to `lib/` -- Eliminates 6x duplication of the write-tmp-replace-fallback pattern.
4. **Extract shared constants** -- `_API_KEY_STRIP`, `QUOTA_MARKERS`, `_parse_iso` to a single `lib/` module.
5. **Split oversized files** -- advance-chapter.py, init-translation.py, translate-chapter.py, auto-translate.py all exceed 200 lines. Extract helpers per recommendations above.
6. **Fix M2** -- Normalize indentation in recover-state.py.
7. **Address I10-I11** -- Simplify state reading in auto-translate.py to reduce redundant file I/O.

---

## Metrics

- **Files over 200 LOC:** 4 of 12 (33%)
- **DRY violations (duplicate logic):** 6 distinct patterns, ~15 instances total
- **Security concerns:** 1 (exec() usage)
- **Missing error handling:** 1 (recover-state.py no locking)
- **Type hint coverage:** ~85% (missing on a few public functions)
- **Unused imports:** 0 found
- **Dead code:** 0 found

## Unresolved Questions

1. Should `_API_KEY_STRIP` be the canonical list in `lib/`, or should each file maintain its own subset? (Recommend: single source.)
2. The `_read_state_field` dot-path accessor in auto-translate.py supports array indexing (`parts.isdigit()`) -- is this used anywhere or dead generality?
3. `init-translation.py:9` imports `uuid` -- is the session_id used for anything beyond the single-pointer note in `_write_state_pointer`? If not, the uuid import adds no value beyond the `session_id` field in state.json.
