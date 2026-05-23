# Reviewer-1: Windows Compatibility Review

**Date:** 2026-05-22
**Scope:** scripts/lib/{platform_paths,file_lock,novel_cache}.py, scripts/{auto-translate,translate-chapter,init-translation,advance-chapter}.py, install.py
**Platform target:** Windows 10/11, Python 3.10+

---

## CRITICAL

### C1. File lock only locks 1 byte on Windows -- concurrent mutation race
**File:** `scripts/lib/file_lock.py:17-21`
**Evidence:** `msvcrt.locking(fd, mode, 1)` locks exactly 1 byte. A second process writing state.json can read partial/inconsistent data because the lock does not cover the file's content region. The Linux path uses `fcntl.flock()` which locks the entire file. Only `advance-chapter.py` acquires the lock, but `init-translation.py:83-85` and `redo-chapters.py:100-102` write state.json without any lock.
**Impact:** On Windows, two concurrent driver processes (or init + driver) can corrupt state.json. The 1-byte lock provides no mutual exclusion for the actual file content.
**Recommendation:** Change `msvcrt.locking` to lock the full file size:
```python
size = os.path.getsize(lock_path)
if size == 0:
    os.write(fd, b"0")
    size = 1
os.lseek(fd, 0, os.SEEK_SET)
mssvcrt.locking(fd, mode, size)
```
Also acquire the lock in `init-translation.py` and `redo-chapters.py` before writing state.json.

### C2. Path.replace() can fail cross-drive on Windows (atomic writes)
**Files:** `scripts/translate-chapter.py:334`, `scripts/advance-chapter.py:68`, `scripts/init-translation.py:85,204`, `scripts/redo-chapters.py:102`, `scripts/recover-state.py:87`, `scripts/merge-entities.py:49`
**Evidence:** All atomic writes use the pattern `tmp = path.with_suffix(...); tmp.write_text(...); tmp.replace(path)`. On Windows, if `%TEMP%` (used by tempfile) and `%LOCALAPPDATA%` (cache root) are on different drives (common with RAM disks, mapped drives, or redirected folders), `Path.replace()` raises `OSError` because it cannot do an atomic rename across drives.
**Impact:** Translation driver crashes on every chapter write on systems where temp dir and cache dir are on different drives/partitions.
**Recommendation:** Place the `.tmp` file in the **same directory** as the target (which the code already does for most cases -- the `.tmp` is created via `path.with_suffix()`). This is already correct for all callers except `translate-chapter.py:332-334` where `output_file.with_suffix(".txt.tmp")` is used -- this is fine because it stays in the same dir. The real risk is minimal for these specific patterns since they all write temp files adjacent to the target. However, add a defensive fallback:
```python
try:
    tmp.replace(target)
except OSError:
    shutil.copy2(tmp, target)
    tmp.unlink(missing_ok=True)
```

### C3. `agy` subprocess invocation may fail on Windows without `.cmd` extension
**Files:** `scripts/translate-chapter.py:156`, `scripts/select-cascade.py:76`
**Evidence:** Both call `subprocess.run(["agy", "-p", ...])` directly. On Windows, `shutil.which("agy")` (used in `select-cascade.py:74` and `install.py:36`) resolves to `agy.cmd` in npm global bin. But `translate-chapter.py:_invoke_backend` does NOT use `shutil.which` -- it passes `"agy"` directly to `subprocess.run`. On Windows, `subprocess.run` without `shell=True` requires the exact executable name including extension.
**Impact:** translate-chapter.py fails with `FileNotFoundError` on Windows because `"agy"` has no `.cmd` extension in the subprocess call.
**Recommendation:** Resolve the agy binary path once at module level or pass it through:
```python
def _invoke_backend(backend: str, model: str, prompt: str) -> tuple[int, str, str]:
    agy_path = shutil.which("agy") or "agy"
    cmd = [agy_path, "-p", prompt]
```

---

## IMPORTANT

### I1. `os.open()` with `0o644` mode on Windows -- silent permission issue
**File:** `scripts/lib/file_lock.py:13`
**Evidence:** `os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)` -- on Windows, the mode argument is ignored (Windows uses ACLs, not Unix permissions). The file will be created with whatever the inherited ACL is. Not a crash risk, but `0o644` is misleading -- any file created will be writable by the current user regardless. No fix needed for functionality, but the comment should note this.
**Recommendation:** No code change required. Add a comment: `# Note: mode arg is ignored on Windows (ACL-based permissions)`.

### I2. `os.unlink(missing_ok=True)` requires Python 3.8+ -- not a version issue but worth noting
**File:** `scripts/advance-chapter.py:99`
**Evidence:** `_pointer_path().unlink(missing_ok=True)` -- `missing_ok` was added in Python 3.8. Since the minimum target is 3.10+ (per docstring annotation `int | None`), this is fine.
**Recommendation:** No action needed.

### I3. `importlib.util.spec_from_file_location` with forward-slash path concatenation
**File:** `scripts/init-translation.py:16`
**Evidence:** `f"{_scripts_dir}/detect-chapters.py"` -- on Windows, `_scripts_dir` will contain backslashes but the concatenation uses forward slash. While Python's `importlib` handles mixed separators, this is fragile and inconsistent.
**Recommendation:** Use `Path(_scripts_dir) / "detect-chapters.py"`:
```python
_spec = importlib.util.spec_from_file_location(
    "detect_chapters", str(Path(_scripts_dir) / "detect-chapters.py"))
```
Same fix for line 223 (`glossary-loader.py`).

### I4. SKILL.md uses `python` not `sys.executable` -- agent may invoke wrong binary
**File:** `skills/cli-tran/SKILL.md:54,57,65,70,76,77,84`
**Evidence:** All invocations in SKILL.md say `python __EXT_ROOT__/scripts/...`. On Windows, the Antigravity CLI (agy) agent runs bash commands via its tool. The `python` command may not be on PATH if only `python3` or the Python launcher (`py`) is installed. Conversely, on some Windows setups `python` works but `python3` does not.
**Impact:** The AI agent following SKILL.md instructions may fail to find the `python` command on Windows.
**Recommendation:** The SKILL.md should note: `On Windows, use 'py' or 'python' (whichever is on PATH)`. Alternatively, the install script could create a small wrapper that the SKILL.md invokes. Or use `python3` on Unix and `py` on Windows via a conditional note.

### I5. No file locking in `init-translation.py` or `redo-chapters.py` -- state corruption on concurrent access
**Files:** `scripts/init-translation.py:83-85,202-204`, `scripts/redo-chapters.py:100-102`
**Evidence:** These scripts write state.json atomically (tmp + replace) but do NOT acquire the `.state.lock` file. Only `advance-chapter.py:292` acquires the lock. If the user runs `init-translation.py` (via `/cli-tran <file>`) while the driver is running, state corruption is possible.
**Impact:** Race condition on both Linux and Windows, but more acute on Windows where the 1-byte lock (C1) is already weak.
**Recommendation:** Acquire `.state.lock` in both `init-translation.py` and `redo-chapters.py` before writing state.json.

---

## MODERATE

### M1. `install.py:40` -- APPDATA fallback with empty string creates invalid path
**File:** `install.py:40`
**Evidence:** `Path(os.environ.get("APPDATA", "")) / "npm" / "agy.cmd"` -- if `APPDATA` is not set, `os.environ.get("APPDATA", "")` returns `""`, and `Path("") / "npm" / "agy.cmd"` produces `npm/agy.cmd` (a relative path). This will never exist, so the fallback silently fails.
**Recommendation:** Guard against empty string:
```python
appdata = os.environ.get("APPDATA")
if appdata:
    npm_bin = Path(appdata) / "npm" / "agy.cmd"
    if npm_bin.exists():
        return str(npm_bin)
```

### M2. `install.py:24` -- LOCALAPPDATA fallback to hardcoded `AppData\Local` may not exist
**File:** `install.py:24`
**Evidence:** `Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))` -- on some Windows configurations (e.g., roaming profiles), `LOCALAPPDATA` may not be set and `~/AppData/Local` may not exist or may have different casing.
**Recommendation:** Use `os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA", "")` with a final fallback to `Path.home() / "AppData" / "Local"`.

### M3. `install.py:122` -- `os.symlink` on Windows requires developer mode or admin privileges
**File:** `install.py:117-122`
**Evidence:** The code already has a conditional: symlink on Linux, copy on Windows. This is correct. However, the `else` branch (Linux) still has `dst.unlink()` before symlink creation, which is fine.
**Recommendation:** No action needed -- already handled.

### M4. Long path support (>260 chars) not addressed
**Files:** `scripts/lib/platform_paths.py`, `scripts/lib/novel_cache.py`
**Evidence:** Windows has a 260-character path limit by default. If the user's home directory is deep (e.g., `C:\Users\Very Long Username\...`), cache paths like `%LOCALAPPDATA%\cli-tran\novels\<16-char-hash>\chapter-output\chapter_999.txt` could exceed 260 chars. The `\\?\` prefix is not used anywhere.
**Impact:** Path operations fail with `FileNotFoundError` or `OSError` on deep paths.
**Recommendation:** For Python 3.10+, long paths are handled automatically when the OS has long-path support enabled (registry + manifest). For safety, the code could use `Path.resolve()` which on Windows returns extended-length paths when needed. This is already done in `state_pointer_path()` (line 19) but NOT in `cache_root()`. Add `.resolve()` to the cache_root return value.

### M5. `install.py:80` -- Backslash-to-forward-slash conversion may break JSON escaping
**File:** `install.py:80`
**Evidence:** `staging_root = str(staging).replace("\\", "/")` -- this is used to substitute `__EXT_ROOT__` in SKILL.md and hooks.json. On Windows, a path like `C:\Users\foo\AppData\Local\cli-tran-src` becomes `C:/Users/foo/AppData/Local/cli-tran-src`. This works for shell commands in the AI agent's bash tool, but could break if the path is used inside JSON strings without proper escaping (e.g., `C:/Users/foo/...` is fine in JSON, but if any downstream code re-escapes, it could double-escape).
**Recommendation:** Current approach is correct for the AI agent's bash tool. No action needed, but add a comment noting this is intentional for cross-platform bash compatibility.

### M6. `file_lock.py:18` -- Writing `b"0"` to lock file corrupts file content
**File:** `scripts/lib/file_lock.py:18`
**Evidence:** `os.write(fd, b"0")` writes a byte to the lock file every time `acquire()` is called. This means the lock file grows by 1 byte on each acquisition (since `O_RDWR` appends at the current seek position, which starts at 0 -- but `os.write` at position 0 overwrites the first byte, so the file stays at 1 byte). However, the lseek + write pattern is: open -> write "0" -> lseek to 0 -> lock 1 byte. This is functionally correct but semantically confusing.
**Recommendation:** Use `os.ftruncate(fd, 1)` or seek to end before write to make intent clearer. Alternatively, check size first:
```python
if os.fstat(fd).st_size == 0:
    os.write(fd, b"0")
```

### M7. Temp directory in `platform_paths.py` may use 8.3 short names on Windows
**File:** `scripts/lib/platform_paths.py:19`
**Evidence:** `Path(tempfile.gettempdir()).resolve()` -- on Windows, `tempfile.gettempdir()` may return a path with 8.3 short names (e.g., `C:\Users\LONGNA~1\AppData\Local\Temp`). The `.resolve()` call helps, but if the 8.3 name is the only name available (unlikely but possible on some FAT32 setups), state pointer paths stored in the file will use short names. Downstream code comparing paths by string equality could fail.
**Recommendation:** Low risk (NTFS always has long names). No action needed unless users report issues.

---

## Edge Cases Found by Scout

1. **`select-cascade.py` calls `shutil.which("agy")` but `translate-chapter.py` does not** -- inconsistent binary resolution. If agy is installed in a non-standard location, select-cascade finds it but translate-chapter does not. (Covered in C3.)

2. **No `.state.lock` in `recover-state.py`** -- same race condition as I5, but recovery is typically run manually, so risk is lower.

3. **`os.O_CREAT | os.O_RDWR` on Windows** -- works correctly. Windows does not support `O_EXCL` well, but the code does not use it.

4. **Shebangs `#!/usr/bin/env python3`** -- on Windows, shebangs are ignored (scripts are invoked via `sys.executable`). Not an issue for the driver architecture, but direct script execution from cmd.exe would need `python script.py` or `py script.py`.

5. **`shutil.rmtree` on Windows** -- `shutil.rmtree(staging, ignore_errors=True)` in install.py may fail if any file is locked by another process (common on Windows with file handles). The `ignore_errors=True` handles this silently.

---

## Positive Observations

1. **`sys.executable` used consistently** in all subprocess calls within Python scripts -- no hardcoded `python3` in actual code (only in SKILL.md instructions and docstrings).
2. **Platform branching is clean** -- `sys.platform == "win32"` checks are localized to `platform_paths.py`, `file_lock.py`, and `install.py`.
3. **Atomic write pattern** (tmp + replace) is used consistently across all state mutations.
4. **`install.py` handles Windows symlink fallback** correctly (copy instead of symlink).
5. **Environment variable overrides** (`CLI_TRAN_STATE_POINTER`, `CLI_TRAN_CACHE_ROOT`) allow users to work around path issues.

---

## Recommended Actions (Priority Order)

1. **[C1]** Fix file lock to cover entire file on Windows -- race condition risk.
2. **[C3]** Add `shutil.which("agy")` in `translate-chapter.py:_invoke_backend` -- crash on Windows.
3. **[I3]** Fix path concatenation in `init-translation.py` -- use `Path()` instead of f-string with `/`.
4. **[I5]** Add file locking to `init-translation.py` and `redo-chapters.py`.
5. **[C2]** Add `shutil.copy2` fallback for cross-drive `Path.replace()`.
6. **[M1]** Guard against empty `APPDATA` in `install.py`.
7. **[M4]** Add `.resolve()` to `cache_root()` for long path support.
8. **[I4]** Update SKILL.md with Windows-specific `python` invocation notes.

---

## Metrics

- **Type Coverage:** N/A (Python, no static typing enforcement)
- **Test Coverage:** No automated tests found for these files
- **Linting Issues:** Not run (Linux-only environment)

---

## Unresolved Questions

1. What is the minimum supported Python version on Windows? Code uses `int | None` syntax (3.10+).
2. Is agy CLI officially supported on Windows? The install script handles it, but subprocess invocation patterns may need platform-specific testing.
3. Should the SKILL.md `python` references be changed to `py` (Windows Python launcher) conditionally?
