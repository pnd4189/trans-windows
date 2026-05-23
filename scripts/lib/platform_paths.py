"""Cross-platform path helpers for cli-tran."""

import os
import sys
import tempfile
from pathlib import Path


def state_pointer_path() -> Path:
    """Return the state pointer file path (cross-platform).

    On Linux: /tmp/.cli-tran-state-path
    On Windows: %TEMP%\\cli-tran-state-path
    Override: CLI_TRAN_STATE_POINTER env var
    """
    env = os.environ.get("CLI_TRAN_STATE_POINTER")
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()).resolve() / ".cli-tran-state-path"


def cache_root() -> Path:
    """Return the cache root directory (cross-platform).

    On Linux: ~/.cache/cli-tran
    On macOS: ~/Library/Caches/cli-tran
    On Windows: %LOCALAPPDATA%\\cli-tran
    Override: CLI_TRAN_CACHE_ROOT env var
    """
    env = os.environ.get("CLI_TRAN_CACHE_ROOT")
    if env:
        return Path(env)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "cli-tran"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "cli-tran"
    return Path.home() / ".cache" / "cli-tran"
