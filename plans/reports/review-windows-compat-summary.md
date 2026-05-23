# Review Summary: Windows Compatibility + Model Switching

**Date:** 2026-05-22
**Reviewers:** 3 (parallel code-reviewer agents)
**Scope:** Full cli-tran codebase for Windows compatibility and Flash→Opus model switching

---

## Executive Summary

**10 CRITICAL, 15 IMPORTANT, 16 MODERATE** findings across 3 review angles.

The codebase has solid foundations (atomic writes, serial execution, clean exit codes, cross-platform path helpers) but has **zero model switching capability** today. agy exposes no `--model` flag — the only control surface is mutating `~/.gemini/antigravity-cli/settings.json`. Additionally, several Windows-specific bugs exist that would crash the driver on Windows.

---

## CRITICAL Findings (must fix)

### Windows Runtime

| ID | Finding | File | Impact |
|----|---------|------|--------|
| W-C1 | File lock only locks 1 byte on Windows — entire state.json unprotected | `lib/file_lock.py:17-21` | Concurrent state corruption |
| W-C2 | `Path.replace()` cross-drive failure — no fallback | 6+ files | Crash on systems where TEMP and cache are on different drives |
| W-C3 | `agy` subprocess missing `.cmd` extension on Windows | `translate-chapter.py:156` | `FileNotFoundError` on every chapter |

### Model Switching

| ID | Finding | File | Impact |
|----|---------|------|--------|
| M-F1 | No mechanism to switch agy models between subprocess calls | `translate-chapter.py` | Flash→Opus switching impossible |
| M-F2 | select-cascade.py operates at backend-level, not model-level | `select-cascade.py:31` | Single "agy" entry, no model awareness |
| M-F3 | No 30-minute recovery timer when both models exhausted | `auto-translate.py:170` | Driver halts permanently |

### Quota Resilience

| ID | Finding | File | Impact |
|----|---------|------|--------|
| Q-C1 | recover-state.py uses wrong filename pattern (`chapter_id` vs `display_id`) | `recover-state.py:49` | Recovery misses completed chapters |
| Q-C2 | recover-state.py counts status `"failed"` but code sets `"skipped"` | `recover-state.py:68` | chapters_failed always 0 after recovery |
| Q-C3 | Duplicate of M-F3 — no 30-min retry on total exhaustion | `auto-translate.py:170` | — |
| Q-C4 | Quota failures count toward 5-retry budget → chapters get skipped | `auto-translate.py:210-228` | Permanent chapter loss on quota exhaustion |

---

## IMPORTANT Findings

| ID | Finding | Source |
|----|---------|--------|
| W-I3 | f-string path concat instead of `Path()` | init-translation.py:16 |
| W-I4 | SKILL.md uses `python` — may not be on PATH on Windows | SKILL.md |
| W-I5 | No file lock in init-translation.py or redo-chapters.py | init/redo |
| M-F4 | State.json model fields initialized but never used — dead schema | init-translation.py |
| M-F5 | Probe "OK" may not trigger quota error until real translation | select-cascade.py:76 |
| M-F6 | init-translation.py reads model but never configures it | init-translation.py:154 |
| M-F7 | No Claude Opus display name anywhere in codebase | — |
| Q-I2 | No SIGTERM handler — Windows taskkill won't clean up | auto-translate.py |
| Q-I3 | backend_cache.json not atomically written | select-cascade.py:63 |
| Q-I4 | QUOTA_MARKERS missing generic patterns (rate_limit, 429) | translate-chapter.py |
| Q-I5 | Probe quota markers inconsistent with translate-chapter.py | select-cascade.py |
| Q-I6 | select-cascade.py missing "Per-minute quota" marker | select-cascade.py |

---

## Recommended Implementation Path

### Phase 1: Windows Fixes (must do first)
1. Fix file lock to cover entire file on Windows (`os.path.getsize()`)
2. Add `shutil.which("agy")` in `translate-chapter.py:_invoke_backend`
3. Add `shutil.copy2` fallback for cross-drive `Path.replace()`
4. Fix path concat in `init-translation.py` → use `Path() /`
5. Add file lock to `init-translation.py` and `redo-chapters.py`

### Phase 2: Model Switching Infrastructure
1. **Discover agy display names** for Flash and Opus (manual step: set model in agy, read settings.json)
2. Add `mutate_agy_model()` helper — writes model to `~/.gemini/antigravity-cli/settings.json`
3. Restructure `select-cascade.py` from backend-level to model-level cascade:
   - `MODELS = {"flash": "<display_name>", "opus": "<display_name>"}`
   - `MODEL_PREFERENCE = ["flash", "opus"]` (Flash always first)
   - Each model gets its own cache entry in `backend_cache.json`
   - `pick()` returns `(model_name, reason)` instead of `(backend_name, reason)`
4. Wire model name through `translate-chapter.py` JSON output
5. Update `init-translation.py` to define `MODELS` constant

### Phase 3: Quota Recovery Loop
1. Add 30-min recovery loop in `auto-translate.py` when both models exhausted:
   ```
   while both exhausted:
     log("Both models exhausted, waiting 30 min...")
     time.sleep(1800)
     clear dead cache entries
     re-probe both models
     if either alive: break
   ```
2. Add `--quota-fail` flag to `advance-chapter.py` — quota failures don't count toward retry budget
3. Add SIGTERM handler in `auto-translate.py`
4. Make `backend_cache.json` writes atomic
5. Unify `QUOTA_MARKERS` across files (shared module or same tuple)
6. Fix `recover-state.py` filename pattern and status counting

### Phase 4: Documentation
1. Update `GEMINI.md` — describe Flash/Opus cascade
2. Update `SKILL.md` — document model switching behavior
3. Update `README.md` — Windows notes + model switching docs

---

## Positive Foundations

1. Serial execution makes settings.json mutation safe for model switching
2. Atomic writes (tmp+replace) consistently used across all state mutations
3. Clean exit code taxonomy (0/1/2/3) maps well to model cascade
4. `--model` arg plumbing already exists in translate-chapter.py
5. `backend_cache.json` mechanism ready for extension to model-level
6. `sys.executable` used consistently in all subprocess calls
7. Platform branching localized to 3 files
8. Environment variable overrides allow user workarounds

---

## Unresolved Questions

1. What is the exact agy display name for Claude Opus in settings.json? (Must discover manually)
2. Does agy respect settings.json changes mid-session, or does it cache model at startup?
3. Should the 30-min wait be configurable via env var?
4. Should `exhausted_models` in state.json be wired to the actual cascade logic or removed?
