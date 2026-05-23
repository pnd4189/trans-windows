# Codebase Review: trans-windows — Optimization Analysis

**Date:** 2026-05-23
**Reviewers:** 3 parallel (code-quality, performance, architecture)
**Scope:** 12 Python files (2158 LOC), extension skill, plans, README

---

## Cross-Reviewer Deduplicated Findings

### CRITICAL (3 unique)

| # | Finding | Evidence | Reviewer |
|---|---------|----------|----------|
| C1 | **`exec()` code injection risk** — loads glossary-loader.py via `exec(compile(...))` | `translate-chapter.py:106` | Q1, A2 |
| C2 | **recover-state.py mutates state.json without file lock** — concurrent driver corrupts state | `recover-state.py:84-92` | Q1, A5 |
| C3 | **Atomic write logic duplicated 6 times** — bug fix requires 6 identical changes | 6 files (see Q1-I1) | Q1, A1 |

### IMPORTANT (12 unique, deduplicated)

| # | Finding | Evidence | Impact |
|---|---------|----------|--------|
| I1 | Redundant state.json reads in driver loop (2-3 parses/iteration) | `auto-translate.py:52-82,139-144` | ~1000 wasted JSON parses for 500 chapters |
| I2 | `_read_source_chunk` loads entire file then slices | `translate-chapter.py:88-95` | 10MB+ allocation for small range |
| I3 | `sys.path.insert` repeated 8 times across all scripts | 8 files | Fragile, breaks if imported as module |
| I4 | `sys.path` grows unboundedly (insert per chapter) | `translate-chapter.py:99` | 500 duplicate entries after full run |
| I5 | Driver log file opened/closed on every `log()` call | `auto-translate.py:35-42` | ~2000 open/close cycles for 500 chapters |
| I6 | API-key strip list duplicated across 3 files | `select-cascade.py`, `translate-chapter.py`, `auto-translate.py` | DRY violation |
| I7 | `QUOTA_MARKERS` duplicated in 2 files | `select-cascade.py:92-96`, `translate-chapter.py:38-42` | DRY violation |
| I8 | `_parse_iso` duplicated in 2 files | `get-progress.py:26-32`, `novel_cache.py:95-102` | DRY violation |
| I9 | 4 files exceed 200-line target | advance-chapter (311), init-translation (302), translate-chapter (355), auto-translate (257) | Readability/maintainability |
| I10 | `_read_state_field` is over-engineered dot-path accessor used once | `auto-translate.py:52-66` | Unnecessary complexity |
| I11 | README lists `platform-paths.py` but file is `platform_paths.py` | `README.md:109` | Doc accuracy |
| I12 | `model_registry.py` is dead code — never imported | `scripts/lib/model_registry.py` | Dead weight |

### MODERATE (8 unique, deduplicated)

| # | Finding | Evidence |
|---|---------|----------|
| M1 | Hash recomputed on every cache accessor (no memoization) | `novel_cache.py:44-64` |
| M2 | CJK ratio iterates text twice (single-pass possible) | `advance-chapter.py:52-58` |
| M3 | 3 subprocess spawns per chapter (~75-150s overhead) | `auto-translate.py:159-241` |
| M4 | Backend cache file re-read per chapter in same process | `select-cascade.py:52-111` |
| M5 | `novel_cache.py` computes CACHE_ROOT at import time (stale if env changes) | `novel_cache.py:39-40` |
| M6 | `platform_paths.py` macOS falls through to `~/.cache` instead of `~/Library/Caches/` | `platform_paths.py` |
| M7 | `install.py` no rollback on partial failure | `install.py` |
| M8 | Plan numbering chaos — 14 phase files for 7 phases | `plans/` directory |

---

## Highest Impact Fixes (Priority Order)

### 1. Merge state.json reads in driver loop
**Files:** `auto-translate.py`
**Effort:** Low
**Impact:** ~50% I/O reduction in translation hot path
Read state.json once per iteration, pass dict to both `_read_state_field` and `_find_next_pending`.

### 2. Extract `atomic_write_json()` to `lib/`
**Files:** New `scripts/lib/io_utils.py`, update 6 consumers
**Effort:** Low
**Impact:** Single fix point for all atomic writes, eliminates 6x duplication

### 3. Replace `exec()` with `importlib.util` (or rename files)
**Files:** `translate-chapter.py:104-107`
**Effort:** Low
**Impact:** Security fix, pattern already exists in `init-translation.py`

### 4. Add file locking to `recover-state.py`
**Files:** `recover-state.py:84-92`
**Effort:** Low
**Impact:** Prevents state corruption during concurrent runs

### 5. Stream `_read_source_chunk` with `itertools.islice`
**Files:** `translate-chapter.py:88-95`
**Effort:** Low
**Impact:** Eliminates full-file load for small range extraction

### 6. Open driver log once, pass handle through
**Files:** `auto-translate.py:35-42`
**Effort:** Low
**Impact:** Eliminates ~2000 file open/close cycles

### 7. Extract shared constants to `lib/`
**Files:** New or existing `lib/` module, update 3-5 consumers
**Effort:** Low
**Impact:** `_API_KEY_STRIP`, `QUOTA_MARKERS`, `_parse_iso` — single source of truth

### 8. Memoize `compute_novel_hash` with `@lru_cache`
**Files:** `novel_cache.py:44-56`
**Effort:** Trivial
**Impact:** Eliminates redundant hash recomputation

---

## Architecture Verdict

**Design: SOUND.** Clean module boundaries, correct cross-platform abstractions, good state management, stdlib-only file locking, proper atomic writes.

**Main risk: MAINTENANCE from code duplication.** The atomic-write pattern (6x), sys.path insertion (8x), and constant duplication create a surface where bugs must be fixed in multiple places.

**No security vulnerabilities** found (aside from the `exec()` usage). **No race conditions** in normal operation. **No deadlocks** in file locking.

---

## Metrics

| Metric | Value |
|--------|-------|
| Total findings | 23 (3 critical, 12 important, 8 moderate) |
| DRY violations | 6 distinct patterns, ~15 instances |
| Files over 200 LOC | 4 of 12 (33%) |
| Security concerns | 1 (exec usage) |
| Race conditions | 0 |
| Dead code | 1 file (model_registry.py) |
| Doc mismatches | 1 (filename in README) |

---

## Unresolved Questions

1. Should hyphenated filenames (`glossary-loader.py`, `detect-chapters.py`) be renamed to underscores for standard imports?
2. Is `model_registry.py` intended for future use or truly dead?
3. Is the 3-spawn-per-chapter architecture (select+translate+advance) worth optimizing to 1-spawn, or is process isolation more valuable?
4. Should Pass 1 plan files be archived or deleted?

---

## Source Reports

- `plans/reports/reviewer-1-260523-code-quality.md` — Code Quality & Maintainability
- `plans/reports/reviewer-2-260523-performance.md` — Performance & Resource Optimization
- `plans/reports/reviewer-3-260523-architecture.md` — Architecture & Cross-Platform Design
