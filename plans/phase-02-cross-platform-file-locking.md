---
phase: 2
title: "Cross-Platform File Locking"
status: pending
priority: P1
effort: "1h"
dependencies: [1]
---

# Phase 2: Cross-Platform File Locking

## Overview

Replace Unix-only `fcntl.flock` in `advance-chapter.py` with cross-platform locking. Extract to `scripts/lib/file-lock.py`. **Red team fix (C2):** Lock entire file on Windows, not just 1 byte.

## Requirements

- Functional: Exclusive, non-blocking file lock works on both Windows and Linux
- Non-functional: stdlib only (no `portalocker` or `filelock`)
- Lock must auto-release on process crash (OS-level, not application-level)

## Architecture

```
scripts/lib/file-lock.py
  ├── acquire_lock(lock_path, blocking=True) -> fd | None
  ├── release_lock(fd, lock_path) -> None
  └── platform dispatch:
        Linux: fcntl.LOCK_EX | fcntl.LOCK_NB on os.open() fd
        Windows: msvcrt.locking(fd, msvcrt.LK_NBLCK, <file_size>) on full range
```

**Red team fix (C2):** `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` only locks byte 0. A second process locking byte 1 would succeed. Fix: write a known byte at position 0, then lock `max(file_size, 1)` bytes. Better: always lock from position 0 for `os.path.getsize(lock_path) or 1` bytes. Since the lock file is small (just a placeholder), write a single byte and lock it.

## Related Code Files

- Create: `scripts/lib/file-lock.py`
- Modify: `scripts/advance-chapter.py` (lines 35, 291-298)

## Implementation Steps

1. Create `scripts/lib/file-lock.py`:
   - `acquire_lock(lock_path, blocking=True)`:
     - `fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)`
     - Write 1 byte at position 0 to establish file size
     - Linux: `fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))`
     - Windows: `msvcrt.locking(fd, msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)`
     - On failure: close fd, return `None`
   - `release_lock(fd)`:
     - Windows: `os.lseek(fd, 0, os.SEEK_SET)` then `msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)`
     - Linux: `fcntl.flock(fd, fcntl.LOCK_UN)`
     - Then `os.close(fd)`
2. Update `advance-chapter.py`:
   - Remove `import fcntl` (line 35) and `import errno` (line 34)
   - Add `from lib.file_lock import acquire_lock, release_lock`
   - Replace lines 291-298 with `acquire_lock`/`release_lock` pattern
3. Verify: `grep -rn 'import fcntl' scripts/` returns 0 matches

## Success Criteria

- [ ] `file-lock.py` exists and exports `acquire_lock()` + `release_lock()`
- [ ] `grep -rn 'import fcntl' scripts/` returns 0 matches
- [ ] Lock acquires exclusively on Linux (existing behavior preserved)
- [ ] Lock acquires exclusively on Windows (msvcrt, full file range)
- [ ] Lock auto-releases on process crash (OS handles fd close)
