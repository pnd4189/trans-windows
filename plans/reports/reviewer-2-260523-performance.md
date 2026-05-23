# Performance & Resource Optimization Review

**Date:** 2026-05-23
**Scope:** All Python scripts (scripts/, scripts/lib/), install.py, skills/cli-tran/SKILL.md
**Focus:** Caching, file I/O, memory, subprocess management, file locking, startup overhead

---

## IMPORTANT Findings

### 1. Redundant state.json reads in auto-translate main loop

**File:** `scripts/auto-translate.py:52-66,69-82,139-144`

`_read_state_field` and `_find_next_pending` both independently read and parse the full state.json. In the main loop, both are called per iteration (lines 139-144), meaning 2 full JSON parses per chapter. For a 500-chapter novel, that's ~1000 redundant file reads and JSON parses.

**Recommendation:** Read state.json once per loop iteration, pass the parsed dict to both functions, or merge them into a single `_read_loop_state` that returns both `active` and `next_pending`.

### 2. Full file load for line-range extraction

**File:** `scripts/translate-chapter.py:88-95`

```python
def _read_source_chunk(path: Path, start: int, end: int) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    ...
    return "".join(lines[start - 1:end])
```

`f.readlines()` loads the entire source file into memory, then slices a small range. For a 10MB+ novel file, this allocates a large list of strings just to use a fraction of them.

**Recommendation:** Use `itertools.islice` on the file iterator to read only the needed lines:
```python
from itertools import islice
with path.open("r", encoding="utf-8", errors="replace") as f:
    chunk = list(islice(f, start - 1, end))
return "".join(chunk)
```

### 3. sys.path pollution on every chapter

**File:** `scripts/translate-chapter.py:99`

```python
def _load_glossary(repo_root: Path, genre: str, novel_glossary: Path | None) -> dict:
    sys.path.insert(0, str(repo_root / "scripts"))
```

`sys.path.insert(0, ...)` prepends on every call. Since `_load_glossary` is called once per chapter translation, the path grows unboundedly. For 500 chapters, `sys.path` has 500 duplicate entries.

**Recommendation:** Guard with a check:
```python
_scripts = str(repo_root / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
```

### 4. Driver log file opened/closed on every message

**File:** `scripts/auto-translate.py:35-42`

```python
def log(msg: str, driver_log: Path | None = None) -> None:
    ...
    if driver_log:
        with driver_log.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
```

Every `log()` call opens, writes, and closes the file. The main loop calls `log` 3-5 times per chapter iteration (start, cascade result, advance result, etc.). For 500 chapters, that's ~2000 file open/close cycles on the same file.

**Recommendation:** Accept an already-open file handle, or open once at the start of `main()` and pass it through. Flush after each write if durability is needed.

---

## MODERATE Findings

### 5. Hash recomputation on every cache accessor call

**File:** `scripts/lib/novel_cache.py:44-56,59-64`

`compute_novel_hash` reads 1KB from disk and computes SHA-256 every time it's called. `novel_cache_dir` calls it, and every accessor (`state_file_for`, `chapter_output_dir`, `entities_dir`, `novel_glossary_path`, etc.) calls `novel_cache_dir`. If a script calls multiple accessors for the same source file (e.g., init-translation.py lines 142-143), the hash is recomputed and the file re-read each time.

**Recommendation:** Add `@functools.lru_cache` to `compute_novel_hash` or `novel_cache_dir` since the hash is deterministic for a given path.

### 6. Double character iteration in CJK ratio

**File:** `scripts/advance-chapter.py:52-58`

```python
def _cjk_ratio_bp(text: str) -> int:
    total = sum(1 for c in text if c.strip())
    if total == 0:
        return 0
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return int(cjk * 10000 / total)
```

Iterates over the entire text twice: once for `total`, once for `cjk`. Also in `translate-chapter.py:216-221` (`_looks_like_translation`).

**Recommendation:** Single pass:
```python
total = 0
cjk = 0
for c in text:
    if c.strip():
        total += 1
        if "一" <= c <= "鿿":
            cjk += 1
```

### 7. Three subprocess spawns per chapter iteration

**File:** `scripts/auto-translate.py:159-241`

Each chapter iteration spawns 3 Python subprocesses: `select-cascade.py`, `translate-chapter.py`, `advance-chapter.py`. Each has Python interpreter startup cost (~50-100ms). For 500 chapters, that's 1500 subprocess spawns, adding ~75-150 seconds of pure startup overhead.

This is by design (process isolation for the agy subprocess), but the overhead is non-trivial.

**Recommendation:** Consider inlining `select-cascade` and `advance-chapter` as function calls within the driver loop, keeping only `translate-chapter` as a subprocess (since it spawns `agy`). This would reduce spawns from 3 to 1 per chapter.

### 8. Backend cache file read per chapter

**File:** `scripts/select-cascade.py:52-58,103-111`

`_load_cache` reads and parses `backend_cache.json` on every `_check_backend` call. In the auto-translate loop, this happens once per chapter. The cache file is small, but the read+parse is unnecessary when the cache hasn't changed since the last read (within the same driver process).

**Recommendation:** Cache the parsed dict in memory within the driver process, or pass the cache state through function calls.

### 9. cleanup_stale_novels reads all state files

**File:** `scripts/lib/novel_cache.py:105-145`

Iterates every directory under `novels/`, reads each `state.json`. For a machine with many cached novels, this is O(n) file reads at init time. Not a hot path, but could slow down `init-translation.py` startup.

**Recommendation:** Acceptable for typical use (< 20 novels). Consider adding a limit or making cleanup async if it becomes a bottleneck.

### 10. install.py copies entire repo twice

**File:** `install.py:78-80`

```python
shutil.copytree(repo_root, staging, ignore=IGNORE_PATTERNS)
```

The full repo is copied to staging, then key files are copied again to `ext_dir`. The staging copy exists to provide a no-space path, but the double-copy doubles disk I/O and storage.

**Recommendation:** If the repo path has no spaces, skip the staging copy entirely and work directly from `repo_root`.

---

## LOW Findings

### 11. importlib.util for hyphenated module names

**File:** `scripts/init-translation.py:17-24,237-247`

Uses `importlib.util.spec_from_file_location` to load `detect-chapters.py` and `glossary-loader.py` (hyphenated names). This is a workaround for Python's import system. Done once per init, so not a performance concern.

### 12. regex compilation on every call

**File:** `scripts/translate-chapter.py:191-193,205-206`

`re.sub` with string patterns is called in `_clean_stdout`. Python caches compiled regexes internally (up to 512), so this is fine in practice, but pre-compiling would be cleaner.

---

## Summary

| Severity | Count | Key Theme |
|----------|-------|-----------|
| IMPORTANT | 4 | Redundant I/O in hot loop, memory waste, path pollution |
| MODERATE | 6 | Hash recomputation, subprocess overhead, double iteration |
| LOW | 2 | Minor code patterns |

**Highest impact fix:** Merging the two state.json reads in the auto-translate main loop (finding #1) and switching to streaming line reads in `_read_source_chunk` (finding #2). These two changes alone would reduce I/O by ~50% in the translation hot path.

**Subprocess overhead** (finding #7) is the largest architectural performance cost but requires a design change beyond a simple fix.
