# Skill Architecture — cli-tran

This document describes the internal architecture of the cli-tran skill for AI agents that need to debug, fix, or extend it. Read this before modifying any script.

## Directory Structure

```
trans-windows/
├── scripts/
│   ├── lib/
│   │   ├── __init__.py
│   │   ├── io_utils.py          # Shared I/O: atomic_write_json, constants, ISO parsing
│   │   ├── file_lock.py         # Cross-platform exclusive file lock (fcntl/msvcrt)
│   │   ├── novel_cache.py       # Per-novel hash-keyed cache directory management
│   │   ├── platform_paths.py    # Cross-platform path resolution (cache, state pointer)
│   │   └── model_registry.py    # (unused) Model registry placeholder
│   ├── auto-translate.py        # DRIVER: main translation loop
│   ├── translate-chapter.py     # Translate ONE chapter via agy subprocess
│   ├── advance-chapter.py       # Validate output + advance state pointer
│   ├── select-cascade.py        # Pick available backend (probe + cache)
│   ├── init-translation.py      # Initialize state.json for a novel
│   ├── recover-state.py         # Rebuild state.json from output files
│   ├── redo-chapters.py         # Reset chapters to pending
│   ├── get-progress.py          # Display progress bar + ETA
│   ├── merge-chapters.py        # Merge per-chapter files into single _vi.txt
│   ├── merge-entities.py        # Merge entity JSONs
│   ├── extract-entities.py      # Extract entities from translated text
│   ├── detect-chapters.py       # Auto-detect chapter boundaries
│   └── glossary-loader.py       # Load/merge glossary files
├── skills/
│   └── cli-tran/
│       └── SKILL.md             # Claude Code skill definition
├── install.py                   # Cross-platform installer
└── glossary/                    # Default glossary files
```

## Data Flow

```
User: /cli-tran <file>
  │
  ▼
SKILL.md (Claude Code reads this)
  │
  ▼
init-translation.py
  ├─ detect-chapters.py → chapter boundaries
  ├─ novel_cache.py → hash-keyed cache dir
  ├─ lib/io_utils.py → atomic_write_json
  └─ state.json created
  │
  ▼
auto-translate.py (driver loop)
  │
  ├─► select-cascade.py
  │     ├─ Probe agy availability
  │     └─ Cache result in backend_cache.json
  │
  ├─► translate-chapter.py
  │     ├─ Read source lines (islice, not full load)
  │     ├─ Load glossary (importlib.util for hyphenated files)
  │     ├─ Build prompt
  │     ├─ Invoke agy subprocess
  │     ├─ Clean stdout (strip ANSI, code fences, preambles)
  │     ├─ Validate (length, CJK ratio)
  │     └─ Write output atomically
  │
  ├─► advance-chapter.py
  │     ├─ Validate output file (size, CJK)
  │     ├─ Update state (completed/retry/skip)
  │     ├─ Write state atomically (under file lock)
  │     └─ Merge entities if done
  │
  └─ Loop until all chapters done or quota hit
```

## Key Design Decisions

### 1. Subprocess Isolation

Each chapter runs as a separate Python subprocess (`translate-chapter.py`). This:
- Prevents context window blowup in the agent
- Enables clean Ctrl+C recovery (state is saved before each chapter)
- Bounds memory usage per chapter
- Allows the driver to run outside the agent's turn context

**Cost:** ~50-100ms Python startup per chapter. For 500 chapters = ~75-150s overhead. Acceptable trade-off.

### 2. Atomic Writes

All state mutations use `lib/io_utils.atomic_write_json()`:
```python
def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ...), encoding="utf-8")
    try:
        tmp.replace(path)
    except OSError:
        shutil.copy2(tmp, path)  # cross-drive fallback
        tmp.unlink(missing_ok=True)
```

**Why:** `Path.replace()` is atomic on same filesystem. The `shutil.copy2` fallback handles cross-drive edge cases (Windows temp on different volume).

**Where used:** state.json, backend_cache.json, all state-mutating scripts.

### 3. File Locking

State mutations that run concurrently (advance-chapter, recover-state, redo-chapters) use `lib/file_lock.py`:

- **Linux/macOS:** `fcntl.flock(fd, LOCK_EX)` — advisory lock, auto-released on process death
- **Windows:** `msvcrt.locking(fd, LK_LOCK, 1)` — mandatory byte-range lock, auto-released on process death

**Critical:** Always acquire lock BEFORE writing state. The lock file is `.state.lock` in the novel cache directory.

### 4. Cross-Platform Paths

`lib/platform_paths.py` resolves paths per OS:

| Path | Linux | macOS | Windows |
|------|-------|-------|---------|
| Cache | `~/.cache/cli-tran` | `~/Library/Caches/cli-tran` | `%LOCALAPPDATA%\cli-tran` |
| State pointer | `/tmp/.cli-tran-state-path` | `/tmp/.cli-tran-state-path` | `%TEMP%\cli-tran-state-path` |

Override with `CLI_TRAN_CACHE_ROOT` and `CLI_TRAN_STATE_POINTER` env vars.

### 5. Hyphenated File Imports

Some scripts have hyphenated names (`glossary-loader.py`, `detect-chapters.py`) because they're invoked as CLI tools. Python can't import these directly.

**Solution:** Use `importlib.util.spec_from_file_location()`:
```python
import importlib.util
spec = importlib.util.spec_from_file_location("module_name", "/path/to/file.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
```

**NEVER use `exec()` for this** — it's a code injection risk (fixed in C1).

### 6. State Pointer Pattern

A single file (`/tmp/.cli-tran-state-path`) points to the active novel's `state.json`. This:
- Allows the Stop hook to find the active translation
- Enables `--resume` without specifying the state file
- Only one translation per agy instance (no PID matching needed)

## Common Failure Modes (Windows)

### 1. File Lock Contention

**Symptom:** "lock contention" in driver output
**Cause:** Another cli-tran instance is running, or a previous crash left a stale lock
**Fix:** `fcntl.flock` and `msvcrt.locking` auto-release on process death. If stale lock persists, delete `.state.lock` manually.

### 2. Cross-Drive Atomic Write Failure

**Symptom:** `OSError` during `tmp.replace()`
**Cause:** Temp directory on different drive than cache directory
**Fix:** Already handled — `atomic_write_json` falls back to `shutil.copy2`. If this fails too, check disk space and permissions.

### 3. Path Separator Issues

**Symptom:** `FileNotFoundError` on Windows
**Cause:** Hardcoded `/` in path strings
**Fix:** All paths use `pathlib.Path`. If you find raw string paths, convert to `Path`.

### 4. Encoding Issues

**Symptom:** `UnicodeDecodeError` or garbled text
**Cause:** Source file encoding not UTF-8
**Fix:** All file reads use `encoding="utf-8", errors="replace"`. Source files should be UTF-8.

### 5. Subprocess Timeout

**Symptom:** Chapter stuck for 10+ minutes
**Cause:** agy subprocess hanging (network issue, model timeout)
**Fix:** `translate-chapter.py` has `SUBPROCESS_TIMEOUT_SECS = 900` (15 min). Driver will retry on timeout.

## Shared Constants (lib/io_utils.py)

All duplicated constants are consolidated here:

| Constant | Purpose | Used by |
|----------|---------|---------|
| `API_KEY_STRIP` | Env vars to strip from subprocess env | select-cascade, translate-chapter |
| `QUOTA_MARKERS` | Strings indicating quota exhaustion | select-cascade, translate-chapter |
| `atomic_write_json()` | Atomic JSON write with cross-drive fallback | 6 scripts |
| `parse_iso()` | ISO timestamp → epoch seconds | novel_cache, get-progress |
| `parse_iso_dt()` | ISO timestamp → datetime | get-progress |

## Adding a New Backend

1. Add probe function in `select-cascade.py`:
   ```python
   def _probe_newbackend() -> tuple[bool, str]:
       # Return (alive, reason)
   ```

2. Add to `PROBES` dict:
   ```python
   PROBES = {"agy": _probe_agy, "newbackend": _probe_newbackend}
   ```

3. Add to `BACKENDS` tuple:
   ```python
   BACKENDS = ("agy", "newbackend")
   ```

4. Update `translate-chapter.py` to handle the new backend's CLI.

## Testing Changes

```bash
# Syntax check all scripts
python3 -m py_compile scripts/*.py scripts/lib/*.py

# Test a single chapter translation
python3 scripts/translate-chapter.py --state <state.json> --chapter 1 --backend agy --model ""

# Test state recovery
python3 scripts/recover-state.py <state.json>

# Test progress display
python3 scripts/get-progress.py <state.json>
```

## Conventions

- **Imports:** `sys.path.insert` guarded with `if _scripts not in sys.path`
- **File writes:** Always via `atomic_write_json()` or atomic tmp+replace pattern
- **State mutations:** Always under file lock (`lib/file_lock.acquire`)
- **Error handling:** At boundaries only (subprocess, file I/O, JSON parse). Trust internal calls.
- **Output:** JSON to stdout for machine consumption, human-readable to stderr
- **Naming:** kebab-case for scripts, snake_case for Python functions
