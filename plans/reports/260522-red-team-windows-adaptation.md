# Red Team Review: Windows Adaptation Plan

## CRITICAL

| ID | Issue | Fix Applied |
|----|-------|-------------|
| C1 | `Path.rename()` NOT atomic on Windows cross-drive; `init-translation.py:85,204`, `redo-chapters.py:102` use `.rename()` while `advance-chapter.py:67` uses `.replace()` | Phase 1: audit all `.rename()` → `.replace()` |
| C2 | `msvcrt.locking()` locks byte RANGES — locking 1 byte lets second process lock a different range | Phase 2: lock entire file via `os.path.getsize()` |
| C3 | `tempfile.gettempdir()` may return 8.3 short names on Windows | Phase 1: use `.resolve()` in `state_pointer_path()` |
| C4 | Windows 260-char path limit may break cache paths | Phase 7: document in README prerequisites |

## HIGH

| ID | Issue | Fix Applied |
|----|-------|-------------|
| H1 | `grep '"python3"'` (with quotes) misses unquoted instances like `["python3", ...]` | Phase 1: use `grep -n 'python3' scripts/` |
| H2 | `model_registry.py` uses `Path.home() / ".gemini"` but not listed in plan | Accepted: Path.home() works cross-platform, no fix needed |
| H3 | `shutil.copytree` copies `.git/` (read-only pack files) | Phase 5: add `ignore=shutil.ignore_patterns(...)` |
| H4 | Backend simplification should come BEFORE driver rewrite to avoid porting dead code | Reordered: Phase 3 is now Backend, Phase 4 is Driver |
| H5 | Removing `_strip_env()` may cause agy to use wrong auth via GEMINI_API_KEY | Phase 3: keep env stripping for agy too |
| H6 | Windows Ctrl+C kills subprocess via TerminateProcess (no cleanup); no KeyboardInterrupt in blocking subprocess.run | Phase 4: add try/except KeyboardInterrupt + state persist |
| H7 | No state migration for Linux→Windows users (absolute paths in state.json) | Accepted: document as unsupported |

## MEDIUM

| ID | Issue | Fix Applied |
|----|-------|-------------|
| M1 | `.rename()` vs `.replace()` inconsistency not fully audited | Merged into C1 fix |
| M3 | `/dev/null` passed as file path arg to `advance-chapter.py` — `Path("NUL").exists()` returns False | Phase 4: use `None` sentinel, not `os.devnull` |
| M5 | SKILL.md needs concrete command to read state pointer, not abstract description | Phase 6: add `python -c "..."` one-liner |
| M7 | No testing strategy for Windows | Phase 7: add Windows test checklist |

## LOW

| ID | Issue | Fix Applied |
|----|-------|-------------|
| L1 | `python` may not be in PATH on Windows (only `py` launcher) | Phase 7: document `python` in PATH as prerequisite |
| L2 | Extension dir parent dirs may not exist on fresh install | Phase 5: ensure `mkdir(parents=True)` |
