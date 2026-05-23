"""Cross-platform exclusive file lock using stdlib only.

Linux:  fcntl.flock  (advisory, auto-released on process death)
Windows: msvcrt.locking (mandatory byte-range, auto-released on process death)
"""

import os
import sys


def acquire(lock_path: str, *, blocking: bool = True) -> int | None:
    """Acquire exclusive lock. Returns fd on success, None if non-blocking and busy."""
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        if sys.platform == "win32":
            import msvcrt
            size = os.fstat(fd).st_size
            if size == 0:
                os.write(fd, b"L")
                size = 1
            os.lseek(fd, 0, os.SEEK_SET)
            mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            msvcrt.locking(fd, mode, size)
        else:
            import fcntl
            flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, flags)
    except OSError:
        os.close(fd)
        return None
    return fd


def release(fd: int) -> None:
    """Release lock and close fd."""
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
