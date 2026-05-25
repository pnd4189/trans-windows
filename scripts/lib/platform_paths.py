"""Cross-platform path helpers for cli-tran."""

import os
import shutil
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


def find_agy() -> str:
    """Locate the agy binary with Windows fallback search.

    Search order: shutil.which → LOCALAPPDATA/agy/bin/agy.exe →
    APPDATA/npm/agy.cmd. Exits if not found.
    """
    agy = shutil.which("agy")
    if agy:
        return agy
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            agy_exe = Path(local_app) / "agy" / "bin" / "agy.exe"
            if agy_exe.exists():
                return str(agy_exe)
        appdata = os.environ.get("APPDATA")
        if appdata:
            npm_bin = Path(appdata) / "npm" / "agy.cmd"
            if npm_bin.exists():
                return str(npm_bin)
    return "agy"
