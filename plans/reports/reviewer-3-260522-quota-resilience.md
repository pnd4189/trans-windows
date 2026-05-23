# Code Review: Quota Recovery, Resilience, and Correctness

**Reviewer:** reviewer-3 (code-reviewer)
**Date:** 2026-05-22
**Scope:** scripts/{auto-translate,translate-chapter,select-cascade,advance-chapter,init-translation,recover-state}.py + scripts/lib/{file_lock,platform_paths,novel_cache}.py
**Focus:** Quota recovery, error resilience, state integrity, race conditions, signal handling

---

## CRITICAL

### C1. recover-state.py uses wrong filename pattern — will never find chapters

**Evidence:** `translate-chapter.py:258-259` writes output as `chapter_{display_id:03d}.txt`, but `recover-state.py:49` looks for `chapter_{chapter_id:03d}.txt`. When `display_id != id` (e.g., prologue chapter with display_id=0 but id=1), recovery will miss the file and reset the chapter to `pending`, causing re-translation of already-completed work.

**Recommendation:** `recover-state.py:49` must use the same naming logic:
```python
display_id = int(chapter.get("display_id") or chapter.get("id") or chapter_id)
expected_file = f"chapter_{display_id:03d}.txt"
```

### C2. recover-state.py counts wrong status — chapters_failed always 0

**Evidence:** `advance-chapter.py:232` sets `ch["status"] = "skipped"` on max-retry exhaustion. But `recover-state.py:68` counts `ch['status'] == 'failed'` — a status value that no code path ever sets. This means `chapters_failed` is always 0 after recovery, making the "All chapters processed" check in `init-translation.py:94` unreliable.

**Recommendation:** Change `recover-state.py:68` to:
```python
state['chapters_failed'] = sum(1 for ch in state['chapters'] if ch['status'] == 'skipped')
```

### C3. No 30-minute wait/retry when ALL backends exhausted

**Evidence:** `auto-translate.py:170` — when `select-cascade.py` returns empty backend, the driver logs `"All backends exhausted; halting"` and `break`s out of the loop. The user requirement is: wait 30 minutes, re-check, continue if backend is alive again. The current code exits immediately, requiring manual re-invocation via `/cli-tran --resume`.

**Recommendation:** Add a sleep-retry loop at the exhaustion point:
```python
if not backend:
    exhaustion_count += 1
    wait_mins = min(30 * exhaustion_count, 120)  # backoff cap
    log(f"All backends exhausted; waiting {wait_mins} min (attempt {exhaustion_count})", driver_log)
    time.sleep(wait_mins * 60)
    # Clear dead cache so select-cascade re-probes
    _run_python(SCRIPT_DIR / "select-cascade.py",
                ["--state", str(state_file), "--clear-cache"])
    continue
```

### C4. Quota failures count toward the 5-retry budget — chapters get skipped on quota exhaustion

**Evidence:** `auto-translate.py:210-228` — on `status == "cascade"`, the driver calls `select-cascade.py --mark-fail` then `continue`s (no retry increment). This is correct for the cascade case. BUT when the cascaded backend ALSO returns cascade, the loop hits `backend == ""` and halts (see C3). If the user resumes and quota is still exhausted, the chapter gets translated via `advance-chapter.py` with `--fail-reason` which DOES increment retry_count. After 5 quota-related failures, the chapter is permanently skipped.

**Recommendation:** In `auto-translate.py`, when calling `advance-chapter.py` for a cascade/quota failure, pass a flag (e.g., `--quota-fail`) so `advance-chapter.py` can skip incrementing `retry_count` for quota-related failures. Alternatively, the driver should not call `advance-chapter.py` on cascade at all (currently it only calls it on `status == "retry"`, which is correct — but the cascade path at line 218 does `continue` without advancing state, meaning the same chapter retries indefinitely on the same state, which is the correct behavior). The real risk is in C3: if the driver halts and resumes, the stale retry_count from previous non-cascade failures may combine with new quota failures to trigger a skip.

---

## IMPORTANT

### I1. auto-translate.py reads state.json without file lock — potential TOCTOU race

**Evidence:** `auto-translate.py:54,71,87` all call `state_file.read_text()` directly. Only `advance-chapter.py:291-299` acquires the file lock. If a human or another process (e.g., manual `advance-chapter.py` invocation) writes state.json while the driver is reading, the driver could parse a half-written JSON (if `.tmp.replace()` is mid-flight on a non-atomic filesystem like NTFS without proper flush).

**Mitigating factor:** `_atomic_write_json` uses write-to-tmp + `replace()`, which is atomic on most POSIX and NTFS. The real risk is on FAT32 or network drives. Low practical severity but worth noting.

**Recommendation:** If running on exotic filesystems is planned, wrap driver state reads in a shared (read) lock. For the current single-driver-per-novel model, this is acceptable.

### I2. No SIGTERM handler — Windows `taskkill` or Ctrl+Break will not clean up state

**Evidence:** Only `KeyboardInterrupt` (SIGINT/Ctrl+C) is caught at `auto-translate.py:246`. On Windows, `taskkill` sends SIGTERM, which is unhandled. The process dies mid-iteration, potentially after `translate-chapter.py` wrote output but before `advance-chapter.py` updated state. State will be inconsistent but `--resume` can recover (the chapter will retry since state was not advanced).

**Recommendation:** Add a SIGTERM handler:
```python
import signal
def _graceful_shutdown(signum, frame):
    raise KeyboardInterrupt("SIGTERM received")
signal.signal(signal.SIGTERM, _graceful_shutdown)
```
Note: `signal.SIGTERM` is available on Windows (Python 3.x).

### I3. backend_cache.json is not atomically written

**Evidence:** `select-cascade.py:63-64` — `_save_cache` writes directly via `p.write_text()` without tmp+replace. If the process is interrupted mid-write, the cache file can be corrupted (truncated JSON), causing `_load_cache` to return `{}` (safe fallback) but losing the dead-backend cache, causing unnecessary re-probes of exhausted backends.

**Recommendation:** Use the same tmp+replace pattern as `_atomic_write_json` in advance-chapter.py.

### I4. QUOTA_MARKERS may miss Claude-specific error messages

**Evidence:** `translate-chapter.py:37-40` has markers covering Gemini patterns (RESOURCE_EXHAUSTED, QUOTA_EXHAUSTED, Daily/Per-minute quota). The current backend is `agy` only (single backend). However, if a future backend wraps Claude API, the markers miss: `"overloaded"`, `"rate_limit"`, `"capacity"`, Anthropic-specific 529 status messages. This is defensive — currently only agy is supported.

**Recommendation:** Add generic fallback markers: `"rate_limit"`, `"too many requests"`, `"429"`. These cover most HTTP-rate-limit responses regardless of provider.

### I5. _probe_agy only checks stdout+stderr for quota markers — return code 0 with quota error possible

**Evidence:** `select-cascade.py:73-89` — the probe runs `agy -p "OK"` and checks stdout+stderr for quota markers. But if agy returns exit code 0 with a "quota exceeded" message buried in JSON output (not matching the exact strings), the probe reports alive=true while the backend is actually dead. The translate-chapter.py QUOTA_MARKERS check is more robust since it runs on the full output, but this means the driver will keep selecting the dead backend, getting cascade errors, marking it dead, waiting 5 min, then re-probing — a cycle that wastes one translation attempt every 5 minutes.

**Recommendation:** Add a more robust check: if the probe response does not contain "OK" (the expected output), consider it suspicious.

### I6. select-cascade.py probe check for quota is duplicated but inconsistent with translate-chapter.py

**Evidence:** `select-cascade.py:85-88` checks a subset of `QUOTA_MARKERS` (RESOURCE_EXHAUSTED, QUOTA_EXHAUSTED, PERMISSION_DENIED, "quota exhausted", "Daily quota") — missing "Per-minute quota" that translate-chapter.py catches. This means the probe can report alive while translate-chapter.py will immediately get a cascade error for per-minute quota limits.

**Recommendation:** Extract QUOTA_MARKERS to a shared module or use the same tuple in both files.

---

## MODERATE

### M1. 5-min dead cache TTL may be too aggressive for RPD (daily) quota exhaustion

**Evidence:** `select-cascade.py:29` — `CACHE_TTL_DEAD = 300` (5 minutes). For per-minute quota (RPM), 5 min is reasonable. But for daily quota (RPD), the backend remains dead for hours while the cache refreshes every 5 minutes, causing a probe every 5 minutes against an exhausted endpoint. This is wasteful but not harmful.

**Recommendation:** Differentiate RPM vs RPD exhaustion in the cache entry and use different TTLs (5 min for RPM, 1 hour for RPD).

### M2. 2-second cooldown may be insufficient for RPM rate limits on large chapters

**Evidence:** `auto-translate.py:32` — `CHAPTER_COOLDOWN_SECS = 2`. If each chapter takes 60+ seconds of model inference, 2 seconds between chapters is fine. But if chapters are very short (sub-second inference), 2 seconds may not be enough for models with 15 RPM free-tier limits (1 request per 4 seconds). The cooldown should be configurable per-model.

**Recommendation:** Make cooldown configurable via state.json per-model, or use a minimum of `max(2, 60/rpm_limit)` seconds.

### M3. init-translation.py resume path writes state.json without file lock

**Evidence:** `init-translation.py:83-85` — the idempotent resume path writes state.json via tmp+replace but does not acquire the file lock. If the driver is actively running while someone runs `init-translation.py --resume`, both processes write state.json concurrently. The last writer wins; one update is lost.

**Recommendation:** Acquire the same `.state.lock` file before writing in the resume path.

### M4. recover-state.py does not update chapters_failed correctly when mixing completed and failed

**Evidence:** `recover-state.py:67-68` — `chapters_completed` counts chapters with existing files regardless of their `status` field. A chapter could have `status="skipped"` but still have a file on disk (from a previous successful translation before it was retried and the file was deleted). The recovery would mark it completed incorrectly.

**Recommendation:** Add a validation check: if the chapter was previously skipped, verify the file is not stale.

### M5. file_lock.py on Windows writes a byte "0" on every acquire — file grows unbounded

**Evidence:** `file_lock.py:18` — `os.write(fd, b"0")` writes one byte on every `acquire()` call. The lock file grows by 1 byte per lock acquisition. Over a 600-chapter novel, this is 600 bytes — negligible. But the intent seems to be ensuring the file has content for `msvcrt.locking`, and the write always appends.

**Recommendation:** Use `os.ftruncate(fd, 0)` before writing to reset the file, or use `os.SEEK_SET` before write:
```python
os.lseek(fd, 0, os.SEEK_SET)
os.ftruncate(fd, 0)
os.write(fd, b"0")
```

### M6. Driver does not log backend_cache.json state on exhaustion

**Evidence:** `auto-translate.py:170` logs `"All backends exhausted"` with the cascade_json but does not dump the backend_cache.json contents. When debugging why a backend is considered dead, the operator must manually read the cache file.

**Recommendation:** Log the cache file contents on exhaustion for debugging.

---

## POSITIVE OBSERVATIONS

1. **Atomic writes:** `_atomic_write_json` uses tmp+replace pattern consistently in advance-chapter.py and recover-state.py.
2. **Exit code protocol:** translate-chapter.py has well-defined exit codes (0/1/2/3) with clear semantic meaning for the driver.
3. **File locking:** advance-chapter.py correctly uses acquire/release in try/finally, ensuring the lock is released even on exceptions.
4. **Quota detection in translate-chapter.py:** The blob-combine approach (stdout+stderr) is robust against output channel variation.
5. **State recovery:** recover-state.py handles both missing-file and corrupted-JSON cases with .bak fallback.
6. **Clean KeyboardInterrupt:** Driver logs a helpful message pointing to `--resume`.
7. **Environment stripping:** Both translate-chapter.py and select-cascade.py strip API-key env vars to prevent auth confusion.

---

## UNRESOLVED QUESTIONS

1. Should the driver support a configurable wait time for total-backend-exhaustion (C3) instead of a hardcoded 30 minutes?
2. Should `exhausted_models` tracking in state.json be used by select-cascade.py? Currently it is set by init-translation.py but never read by the selector.
3. Is there a plan to support multiple backends (not just `agy`) in `BACKENDS` tuple? The cascade infrastructure is built but only one backend exists.
