# Full Codebase Review — cli-translator

**Date:** 2026-05-16
**Reviewers:** 3 (Security, Code Quality, Architecture)
**Scope:** Full codebase (~550 LOC, 25+ files)
**Branch:** main

---

## Executive Summary

The cli-translator is a well-conceived Gemini CLI extension for Chinese-to-Vietnamese novel translation. The hook-based loop control pattern and 2-tier glossary system show thoughtful design. However, **4 critical issues** were found that could cause data loss or security breaches in production. All are straightforward fixes.

**Findings by severity:**
- **CRITICAL:** 4 (2 security, 2 reliability)
- **IMPORTANT:** 11 (3 security, 5 code quality, 3 architecture)
- **MODERATE:** 18 (across all areas)

---

## Critical Issues (Must Fix)

### 1. Zip path traversal in EPUB extraction — `epub2txt.py:90`

`epub.read(file_path)` uses unsanitized `href` from EPUB manifest. A malicious EPUB can read arbitrary files via `../` in manifest href.

**Impact:** Arbitrary file read (SSH keys, API tokens, /etc/shadow)
**Fix:** Sanitize href with `posixpath.normpath()`, reject paths starting with `..`
**Effort:** 10 min

### 2. Path traversal via state file — `validate-translation.py:115`

`Path(state['output_dir']) / ch['output_file']` joins unsanitized `output_file` from state.json. If state.json is tampered, arbitrary file read is possible.

**Impact:** Arbitrary file read via tampered state.json
**Fix:** Validate resolved path stays under `output_dir` using `is_relative_to()`
**Effort:** 10 min

### 3. Non-atomic state.json write — `translate-hook.sh:67`

`jq > tmp && cp tmp state` is not atomic. If process is killed mid-write, state.json is corrupted and all translation progress is lost.

**Impact:** Data loss at scale (50+ chapters)
**Fix:** Replace `cp` with `mv` (atomic rename on same filesystem). Add `.bak` backup before update.
**Effort:** 5 min

### 4. No state.json corruption recovery

If state.json becomes corrupt, there's no backup, no checksum, and no way to reconstruct state from output files.

**Impact:** Manual state reconstruction required
**Fix:** Keep rolling `.translator/state.json.bak`. Add `recover-state.py` script.
**Effort:** 30 min

---

## Important Issues (Should Fix)

### Security

| # | Finding | File:Line | Recommendation |
|---|---------|-----------|----------------|
| 5 | No path boundary validation on source file | init-translation.py:20 | Check source is regular file |
| 6 | No zip bomb protection in EPUB | epub2txt.py:50 | Check decompressed size before read |
| 7 | Non-atomic `cp` in shell hook | translate-hook.sh:67 | Use `mv` for atomic state update |

### Code Quality

| # | Finding | File:Line | Recommendation |
|---|---------|-----------|----------------|
| 8 | `sys.exit()` in library functions | init-translation.py:23, detect-chapters.py:40, glossary-loader.py:49 | Raise exceptions, let main() handle exit |
| 9 | Silent exception swallowing | epub2txt.py:105 | Log skipped items to stderr |
| 10 | Zero tests for 3 critical modules | init-translation.py, get-progress.py, translate-hook.sh | Add unit tests with tmp fixtures |
| 11 | Entire file loaded into memory | detect-chapters.py:43 | Iterate line-by-line for large files |
| 12 | Inconsistent error reporting | get-progress.py:13 | Use exceptions or None returns |

### Architecture

| # | Finding | File:Line | Recommendation |
|---|---------|-----------|----------------|
| 13 | Resume has no retry limit | resume.toml:3 | Add retry_count, skip after N failures |
| 14 | Prologue/epilogue not detected | detect-chapters.py:9-15 | Add 序章/序幕/楔子/Prologue/Epilogue patterns |
| 15 | Numbered-list pattern too broad | detect-chapters.py:13 | Add minimum line-count heuristic |

---

## Moderate Issues (Nice to Fix)

| # | Finding | File | Recommendation |
|---|---------|------|----------------|
| 16 | TOCTOU race in shell hook | translate-hook.sh:16-19 | Low risk, single-agent environment |
| 17 | KeyError risk in get-progress.py | get-progress.py:18-21 | Use .get() with defaults |
| 18 | Unbounded stdin read | translate-hook.sh:8 | Add size limit |
| 19 | Mixed type annotation styles | Multiple files | Standardize on builtins (Python 3.9+) |
| 20 | No structured logging | All scripts | Use logging module or stderr prefixes |
| 21 | Silent genre fallback | glossary-loader.py:78 | Print warning to stderr |
| 22 | deep_merge no type validation | glossary-loader.py:21-23 | Validate types before merge |
| 23 | State file keys not validated | get-progress.py:18-22 | Use .get() or schema validation |
| 24 | EPUB 100-char minimum drops content | epub2txt.py:96 | Log skipped items or make configurable |
| 25 | No integration tests | tests/ | Add init→detect→translate→validate flow |
| 26 | EPUB OPF namespace hardcoded | epub2txt.py:63 | Handle EPUB 2 and 3 namespaces |
| 27 | Relative path for STATE_FILE | translate-hook.sh:14 | Use $PWD/.translator/state.json |
| 28 | Context duplication across 4 files | GEMINI.md, translate.toml, SKILL.md | Single source of truth in GEMINI.md |
| 29 | No /progress command | commands/ | Add progress.toml |
| 30 | EPUB title extraction limited | epub2txt.py:100 | Check <title> and class-based patterns |
| 31 | epub2txt always prepends Chinese markers | epub2txt.py:127 | Make marker format configurable |
| 32 | glossary merge doesn't validate unknown keys | glossary-loader.py:35 | Add schema validation |
| 33 | glossary-loader uses relative path default | glossary-loader.py:43 | Use Path(__file__).parent.parent |

---

## Test Coverage

| Module | Unit Tests | Integration | Gaps |
|--------|-----------|-------------|------|
| detect-chapters.py | 7 tests | No | prologue, numbered lists, huge files |
| epub2txt.py | 6 tests | No | corrupt EPUB, DRM, no OPF |
| glossary-loader.py | 6 tests | No | missing genre file, corrupt JSON |
| validate-translation.py | 8 tests | No | empty source, binary file |
| **init-translation.py** | **0** | **No** | **All** |
| **get-progress.py** | **0** | **No** | **All** |
| **translate-hook.sh** | **0** | **No** | **All** |

---

## Top 5 Quick Wins (Highest Impact, Lowest Effort)

1. **Replace `cp` with `mv`** in translate-hook.sh:67 — 5 min, prevents data loss
2. **Add `.bak` backup** before state updates — 5 min, enables recovery
3. **Sanitize EPUB href** in epub2txt.py:90 — 10 min, prevents arbitrary file read
4. **Validate path in validate-translation.py:115** — 10 min, prevents arbitrary file read
5. **Add prologue/epilogue patterns** to detect-chapters.py — 10 min, fixes silent data corruption

---

## Positive Observations

- Shell hook uses `jq --arg`/`--argjson` for safe string interpolation — prevents injection
- `set -euo pipefail` in hook — fails fast on errors
- `mktemp` + trap pattern for temp files — proper cleanup
- Atomic write pattern in `init-translation.py` (rename-based)
- Proper UTF-8 encoding on all file I/O
- Good test fixtures for chapter detection
- Well-structured reference docs (pronoun-guide, common-errors, translation-principles)
- Volume marker exclusion in chapter detection

---

## Unresolved Questions

- Are there additional TOML commands beyond the three reviewed?
- Is the `.translator/` directory ever exposed to untrusted users?
- What's the expected novel file size range? (affects memory optimization priority)

---

## Individual Reports

- [Security Review](reviewer-1-security-review.md)
- [Code Quality Review](reviewer-2-code-quality-review.md)
- [Architecture Review](reviewer-3-architecture-review.md)
