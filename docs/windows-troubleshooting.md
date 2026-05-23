# Windows Troubleshooting Guide — For AI Agents

When diagnosing cli-tran crashes on Windows, follow this decision tree.

## Quick Diagnosis

```bash
# 1. Check Python version (need 3.10+)
python --version

# 2. Check if scripts compile
python -m py_compile scripts\auto-translate.py
python -m py_compile scripts\translate-chapter.py
python -m py_compile scripts\advance-chapter.py

# 3. Check cache directory exists
dir %LOCALAPPDATA%\cli-tran

# 4. Check state pointer
type %TEMP%\cli-tran-state-path
```

## Error → Fix Table

| Error Message | Root Cause | Fix |
|---------------|------------|-----|
| `ModuleNotFoundError: lib` | `sys.path` not set | Scripts auto-guard with `if _scripts not in sys.path`. Check the guard exists. |
| `PermissionError: [WinError 32]` | File locked by another process | Wait for other cli-tran instance to finish, or kill stale Python processes. |
| `OSError: [WinError 17]` | Cross-drive atomic write | `atomic_write_json` handles this with `shutil.copy2` fallback. Check disk space. |
| `UnicodeDecodeError` | Source file not UTF-8 | All reads use `errors="replace"`. If source is GBK/GB2312, convert to UTF-8 first. |
| `FileNotFoundError` | Path with spaces or wrong separator | Use `pathlib.Path` everywhere. Never concatenate raw strings for paths. |
| `subprocess.TimeoutExpired` | agy hung (>600s) | Check network. Increase `SUBPROCESS_TIMEOUT_SECS` if needed. |
| `msvcrt.locking error` | Lock file corrupted | Delete `.state.lock` in novel cache dir. Auto-recovery should work on next run. |
| `ImportError: Cannot load glossary-loader.py` | File missing or syntax error | Check `scripts\glossary-loader.py` exists and compiles. |
| `JSONDecodeError` in state.json | State file corrupted | Run `python scripts\recover-state.py` |

## File Lock Deep Dive (Windows)

Windows uses `msvcrt.locking` — mandatory byte-range locks:

```python
# lib/file_lock.py Windows path:
fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
size = os.fstat(fd).st_size
if size == 0:
    os.write(fd, b"L")  # Write a byte so we have something to lock
    size = 1
os.lseek(fd, 0, os.SEEK_SET)  # Seek back to start
msvcrt.locking(fd, msvcrt.LK_LOCK, size)  # Lock
```

**Key differences from Linux:**
- Mandatory (not advisory) — other processes CAN'T bypass
- Byte-range based — locks specific bytes, not whole file
- Auto-released on process crash (same as Linux)
- `LK_LOCK` retries every 1 second for 10 attempts, then raises `OSError`

**If lock hangs:**
1. Check for zombie Python processes: `tasklist | findstr python`
2. Kill stale processes: `taskkill /PID <pid> /F`
3. Delete `.state.lock` file
4. Re-run

## Path Handling

All scripts use `pathlib.Path`. If you see raw string path manipulation:

```python
# WRONG (breaks on Windows):
path = basedir + "/" + filename

# RIGHT:
path = Path(basedir) / filename
```

**Common pitfall:** `Path.replace()` works cross-drive on Windows, but `Path.rename()` does NOT. Always use `replace()`.

## Subprocess Invocation

```python
# All scripts use this pattern:
subprocess.run(
    [sys.executable, str(script_path)] + args,
    capture_output=True, text=True, timeout=600,
)
```

**Windows notes:**
- `sys.executable` resolves to the correct Python interpreter
- `capture_output=True` handles encoding automatically
- `text=True` enables string mode (not bytes)
- Scripts output JSON to stdout, human text to stderr

## Cache Directory

| OS | Location |
|----|----------|
| Windows | `%LOCALAPPDATA%\cli-tran\novels\<hash>\` |
| Linux | `~/.cache/cli-tran/novels/<hash>\` |
| macOS | `~/Library/Caches/cli-tran/novels/<hash>\` |

Override: `set CLI_TRAN_CACHE_ROOT=C:\my-cache`

## Debug Checklist

When a Windows crash is reported:

1. **Read the error message** — Python tracebacks are precise
2. **Check file existence** — `state.json`, source file, output dir
3. **Check permissions** — Can Python write to cache dir?
4. **Check disk space** — `dir %LOCALAPPDATA%\cli-tran`
5. **Check for stale locks** — `.state.lock` file age
6. **Check encoding** — Source file encoding
7. **Check paths** — No hardcoded `/`, use `Path`
8. **Check imports** — `sys.path` guard exists
9. **Check subprocess** — `agy` is in PATH
10. **Check network** — Can reach API endpoints

## Recovery Commands

```bash
# Recover corrupted state
python scripts\recover-state.py %LOCALAPPDATA%\cli-tran\novels\<hash>\state.json

# Redo failed chapters
python scripts\redo-chapters.py %LOCALAPPDATA%\cli-tran\novels\<hash>\state.json failed

# Check progress
python scripts\get-progress.py %LOCALAPPDATA%\cli-tran\novels\<hash>\state.json

# Clean stale caches
python scripts\lib\novel_cache.py --cleanup

# Check hash for a source file
python scripts\lib\novel_cache.py --hash C:\path\to\novel.txt
```
