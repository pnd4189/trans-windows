# Code Quality Review — cli-translator

## Scope
- Files: 6 Python scripts, 1 bash hook, 4 test files
- Focus: Code quality, error handling, maintainability, edge cases
- All scripts under 200 lines (modularity OK)

## Findings

### CRITICAL

- **[CRITICAL] Path traversal in EPUB extraction** -- `epub2txt.py:90` -- `file_path = f"{base_path}/{href}"` concatenates OPF href without sanitizing `..` components. A crafted EPUB can read arbitrary files from the archive. Fix: validate that resolved path stays within the EPUB root, or use `zipfile.Path` for safe resolution.

- **[CRITICAL] Race condition in shell hook state update** -- `translate-hook.sh:67` -- `jq ... > "$TMP" && cp "$TMP" "$STATE_FILE"` is not atomic. A concurrent read (e.g., `get-progress.py`) can see partial state. `init-translation.py:89` uses `tmp_file.rename()` which IS atomic. Fix: use `mv` instead of `cp` in the hook.

### IMPORTANT

- **[IMPORTANT] `sys.exit()` in library functions** -- `init-translation.py:23`, `detect-chapters.py:40`, `glossary-loader.py:49` -- Functions that should be importable call `sys.exit(1)` on error. This makes them untestable as library functions and causes silent interpreter exit when imported. Fix: raise exceptions (`ValueError`, `FileNotFoundError`) and let `main()` handle exit.

- **[IMPORTANT] Silent exception swallowing in EPUB processing** -- `epub2txt.py:105` -- `except (KeyError, UnicodeDecodeError): continue` discards errors with zero logging. Corrupt or non-UTF-8 EPUB content vanishes silently. Fix: log skipped items with `print(..., file=sys.stderr)`.

- **[IMPORTANT] No test coverage for 3 modules** -- `init-translation.py`, `get-progress.py`, `translate-hook.sh` have zero tests. The init module creates filesystem state and is the entry point — untested init means untested state schema. Fix: add unit tests with tmp directory fixtures.

- **[IMPORTANT] Hyphenated script filenames violate PEP 8** -- All scripts (`detect-chapters.py`, `epub2txt.py`, etc.) use hyphens, making them non-importable. Tests work around this with `importlib.util.spec_from_file_location` boilerplate. Fix: rename to `detect_chapters.py` etc., or keep hyphens but accept the import cost.

- **[IMPORTANT] Entire file loaded into memory** -- `detect-chapters.py:43` -- `path.read_text().splitlines()` loads full file. For a 50MB+ novel, this causes high memory usage. Fix: iterate line-by-line with `open()`.

- **[IMPORTANT] Inconsistent error reporting** -- `get-progress.py:13` returns error string `"Error: State file not found"` as normal return value. Other scripts use `print(..., file=sys.stderr); sys.exit(1)`. Callers can't distinguish success from error. Fix: raise exception or return `None`.

### MODERATE

- **[MODERATE] Mixed type annotation styles** -- `epub2txt.py:10` uses `from typing import List, Tuple` while `init-translation.py` uses `list[str]` builtins. Pick one style. Since Python 3.9+ is assumed (given `list[str]` usage), drop `typing` imports.

- **[MODERATE] No structured logging** -- All scripts use bare `print()`. No timestamps, no log levels, no structured format. For a multi-step translation pipeline, debugging requires correlating output across scripts. Fix: use `logging` module or at minimum add script name prefixes.

- **[MODERATE] `detect_genre` silent fallback** -- `glossary-loader.py:78` -- `if max(scores.values()) == 0: return 'fantasy'` silently defaults with no warning. Empty or non-Chinese text gets fantasy glossary without user knowing. Fix: print warning to stderr.

- **[MODERATE] `deep_merge` no type validation** -- `glossary-loader.py:21-23` -- If `terms` or `characters` value in override is not a dict, `{**result[key], **value}` raises `TypeError` with no useful message. Fix: validate types before merge.

- **[MODERATE] State file keys not validated** -- `get-progress.py:18-22` -- Direct `state['total_chapters']` access with no key existence check. Corrupt or schema-migrated state file causes unhandled `KeyError`. Fix: use `.get()` with defaults or validate schema on load.

- **[MODERATE] EPUB 100-char minimum silently drops content** -- `epub2txt.py:96` -- `if len(text.strip()) > 100` skips short spine items. Short chapters (e.g., interludes, author notes) are silently excluded. Fix: log skipped items or make threshold configurable.

- **[MODERATE] No integration tests** -- All tests are unit-level. No test covers the init -> detect -> translate -> validate workflow end-to-end. State schema compatibility between modules is untested.

- **[MODERATE] EPUB OPF namespace hardcoded** -- `epub2txt.py:63` -- `ns = {'opf': 'http://www.idpf.org/2007/opf'}` only handles one namespace. EPUB 3 uses `xmlns:opf` which may differ. Fix: also try without namespace or parse from root element.

### LOW

- **[LOW] `__pycache__` in working tree** -- `scripts/__pycache__/`, `tests/__pycache__/` present. Should be in `.gitignore`.

- **[LOW] Unused `typing.List` import** -- `validate-translation.py:8` -- `from typing import List` used only in type hints; could use `list` builtin.

- **[LOW] No `__all__` exports** -- No script defines `__all__`. When imported as module, all top-level names are exposed.

## Positive Observations

- Atomic write pattern in `init-translation.py:86-89` (rename-based)
- Proper UTF-8 encoding specified on all file I/O
- `translate-hook.sh` uses `jq --arg` to prevent shell injection via chapter titles
- Good test fixtures for chapter detection (empty, mixed, volumes, etc.)
- `ValidationResult` class provides structured error/warning reporting
- Genre detection is simple keyword-based, appropriate for v1
- Glossary deep-merge logic handles each key type correctly

## Test Coverage Summary

| Module | Tests | Coverage |
|--------|-------|----------|
| detect-chapters.py | 7 tests | Good |
| epub2txt.py | 6 tests | HTML extraction only, no EPUB file tests |
| validate-translation.py | 8 tests | Good unit coverage |
| glossary-loader.py | 6 tests | Good |
| init-translation.py | 0 | None |
| get-progress.py | 0 | None |
| translate-hook.sh | 0 | None |

## Recommended Actions (Priority Order)

1. Fix EPUB path traversal (CRITICAL)
2. Fix shell hook race condition — use `mv` not `cp` (CRITICAL)
3. Replace `sys.exit()` with exceptions in library functions (IMPORTANT)
4. Add error logging for skipped EPUB content (IMPORTANT)
5. Add tests for init-translation.py and get-progress.py (IMPORTANT)
6. Rename scripts to use underscores for importability (IMPORTANT)
7. Add state file schema validation (MODERATE)
8. Add integration tests (MODERATE)
