# Brainstorm: Windows Adaptation for cli-tran

## Problem Statement

cli-tran currently runs only on Ubuntu/Linux. Goal: adapt the entire codebase to work on Windows with full feature parity. Changes are confined to this repo only — no external tool modifications.

## User Decisions

| Decision | Choice |
|----------|--------|
| Backend | Only `agy` (remove `gemini` CLI cascade) |
| Script approach | Python rewrite (replace `.sh` with `.py`) |
| Install path | `%USERPROFILE%\.gemini\extensions\cli-tran\` (confirmed: agy/gemini-cli uses `os.homedir()/.gemini/`) |
| README | Full rewrite with Windows instructions |

## Research Findings

### Antigravity CLI Extension Path (Confirmed)

Source: `google-gemini/gemini-cli` → `packages/core/src/utils/paths.ts`:
```typescript
export const GEMINI_DIR = '.gemini';
export function homedir(): string {
  const envHome = process.env['GEMINI_CLI_HOME'];
  if (envHome) return envHome;
  return os.homedir();
}
```

- **Windows**: `%USERPROFILE%\.gemini\extensions\cli-tran\`
- **Override**: `GEMINI_CLI_HOME` env var (if set)
- Extension scan: `homedir()/.gemini/extensions/<name>/` — same pattern cross-platform

### Key Cross-Platform Mappings

| Linux | Windows | Python equiv |
|-------|---------|--------------|
| `~/.cache/cli-tran/` | `%LOCALAPPDATA%\cli-tran\` | `os.environ.get('LOCALAPPDATA', Path.home()) / 'cli-tran'` |
| `/tmp/` | `%TEMP%\` | `tempfile.gettempdir()` |
| `/dev/null` | `NUL` | `os.devnull` |
| `python3` | `python` | `sys.executable` |
| `fcntl.flock` | `msvcrt.locking` | platform-conditional |
| `ln -sfn` | `mklink` or copy | `shutil.copytree` / junction |
| `chmod +x` | N/A | skip on Windows |
| `sed` | N/A | Python string ops |
| `readlink -f` | N/A | `Path.resolve()` |
| `~/.gemini/` | `%USERPROFILE%\.gemini\` | `Path.home() / '.gemini'` |

## Unix-Specific Issues Catalog (6 Categories)

### C1: Hardcoded Unix paths (5 files)
- `advance-chapter.py:98` — `/tmp/.cli-tran-state-path`
- `init-translation.py:262` — `/tmp/.cli-tran-state-path`
- `get-progress.py:15` — `/tmp/.cli-tran-state-path`
- `recover-state.py:91` — `/tmp/.cli-tran-state-path`
- `auto-translate.sh:21` — `CLI_TRAN_STATE_POINTER` default

### C2: Unix-only imports (1 file)
- `advance-chapter.py:35` — `import fcntl` (no Windows stdlib equiv)

### C3: Cache dir convention (1 file)
- `novel_cache.py:34` — `~/.cache/cli-tran` (XDG convention, not Windows)

### C4: Bash scripts (2 files)
- `auto-translate.sh` — entire file is bash
- `install.sh` — uses `ln -sfn`, `chmod +x`, `sed`, `readlink`

### C5: `python3` hardcode (2 files)
- `init-translation.py:243` — `["python3", ...]`
- `auto-translate.sh:20` — `PYTHON="${PYTHON:-python3}"`

### C6: Backend cascade includes gemini CLI (2 files)
- `select-cascade.py` — `BACKENDS = ("gemini", "agy")` + `_probe_gemini()`
- `translate-chapter.py:170-171` — `cmd = ["gemini", ...]` path

## Proposed Solution: 10-File Change Set

### New Files (2)
1. **`scripts/auto-translate.py`** — Python rewrite of `auto-translate.sh`
   - Same loop logic, uses `subprocess.run()` instead of bash `$()`
   - Uses `tempfile.gettempdir()` for pointer path
   - Uses `sys.executable` for Python subprocess calls
   - No `/dev/null` — uses `os.devnull` or `subprocess.DEVNULL`

2. **`install.py`** — Cross-platform Python installer
   - Copies repo to a no-space staging dir under `%LOCALAPPDATA%\cli-tran-src` (Windows) or `~/.local/share/cli-tran-src` (Linux)
   - On Windows: no symlinks — direct copy (junction if needed for GEMINI.md)
   - Substitutes `__EXT_ROOT__` in SKILL.md/hooks.json via Python string replace
   - Runs `agy plugin import gemini` at the end
   - Idempotent (re-run safe)

### Modified Files (8)
3. **`scripts/advance-chapter.py`** — Replace `fcntl` with cross-platform locking
   - Add `_acquire_lock()` / `_release_lock()` with platform dispatch:
     - Unix: `fcntl.flock()` (existing)
     - Windows: `msvcrt.locking()` with `os.O_CREAT | os.O_RDWR`
   - Replace `/tmp/` with `tempfile.gettempdir()`

4. **`scripts/init-translation.py`** — Fix paths + python3
   - `Path('/tmp/...')` → `Path(tempfile.gettempdir()) / '.cli-tran-state-path'`
   - `["python3", ...]` → `[sys.executable, ...]`

5. **`scripts/get-progress.py`** — Fix temp path
   - `Path("/tmp/...")` → `Path(tempfile.gettempdir()) / '.cli-tran-state-path'`

6. **`scripts/recover-state.py`** — Fix temp path
   - Same as above

7. **`scripts/lib/novel_cache.py`** — Cross-platform cache root
   - On Windows: `%LOCALAPPDATA%\cli-tran`
   - On Linux: `~/.cache/cli-tran` (existing)
   - Detection: `os.name == 'nt'` or `sys.platform == 'win32'`

8. **`scripts/select-cascade.py`** — Remove gemini backend
   - `BACKENDS = ("agy",)` — single backend
   - Remove `_probe_gemini()`, `_API_KEY_STRIP`, `_oauth_env()`
   - Remove `PROBES["gemini"]` mapping
   - Simplify `pick()` to just probe agy

9. **`scripts/translate-chapter.py`** — Remove gemini backend path
   - Remove `"gemini"` from `choices` in argparse
   - Remove `if backend == "gemini":` branch in `_invoke_backend()`
   - Remove `GEMINI_PROBE_FLAGS`
   - Simplify to only agy path

10. **`skills/cli-tran/SKILL.md`** — Update for Python + agy-only
    - `python3` → `python`
    - `bash __EXT_ROOT__/scripts/auto-translate.sh` → `python __EXT_ROOT__/scripts/auto-translate.py`
    - Remove gemini CLI references
    - Update architecture description (no bash, single backend)

### Updated Config/Docs (3)
11. **`README.md`** — Full Windows-focused rewrite
    - Prerequisites: Python 3.10+, Antigravity CLI, agy in PATH
    - Install: `python install.py`
    - Usage: same `/cli-tran` commands
    - Architecture: updated for Python driver
    - Backend: agy only

12. **`GEMINI.md`** — Update for Windows conventions
    - Remove model cascade description
    - Update tool paths for Windows

13. **`scripts/lib/model_registry.py`** — Verify Path.home() works (no change expected)

### No Changes Needed
- `detect-chapters.py`, `merge-chapters.py`, `merge-entities.py`
- `glossary-loader.py`, `validate-translation.py`, `redo-chapters.py`
- `epub2txt.py`
- `gemini-extension.json`, `plugin.json`, `hooks/hooks.json`
- `glossary/`, `references/`

## Cross-Platform File Locking Design

```python
import os, sys, tempfile
from pathlib import Path

def _acquire_lock(lock_path: Path):
    """Return (lock_fd, lock_was_acquired). Platform-conditional."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        import msvcrt
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return fd, True
        except OSError:
            os.close(fd)
            return None, False
    else:
        import fcntl
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd, True
        except OSError:
            os.close(fd)
            return None, False

def _release_lock(fd):
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
```

## Cross-Platform Cache Root

```python
import os, sys
from pathlib import Path

def _cache_root() -> Path:
    env = os.environ.get("CLI_TRAN_CACHE_ROOT")
    if env:
        return Path(env)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "cli-tran"
    return Path.home() / ".cache" / "cli-tran"
```

## Cross-Platform State Pointer

```python
import tempfile
from pathlib import Path

def _state_pointer_path() -> Path:
    env = os.environ.get("CLI_TRAN_STATE_POINTER")
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / ".cli-tran-state-path"
```

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| `msvcrt.locking` byte-range limitations | Low — only one process locks at a time | Lock on dedicated `.lock` file, lock byte 0 only |
| Windows path spaces in repo dir | Medium — hooks tokenize on whitespace | `install.py` copies to no-space staging dir |
| `os.devnull` for NUL | None — Python stdlib handles it | Already cross-platform |
| `agy` not in PATH on Windows | Low — user installs agy first | install.py checks `shutil.which("agy")` before proceeding |
| Junction vs symlink for GEMINI.md | Low — can just copy | install.py copies, doesn't symlink |

## Success Criteria

1. `python install.py` succeeds on Windows (Python 3.10+)
2. `agy plugin list` shows `cli-tran` after install
3. `/cli-tran test.txt` initializes and translates a short test file
4. `/cli-tran --status` shows progress
5. `/cli-tran --resume` picks up from interrupted state
6. Ctrl+C is safe — state persists, resume works
7. No `import fcntl`, `bash`, `/tmp/`, `/dev/null`, `python3` in Windows execution path
