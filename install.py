#!/usr/bin/env python3
"""Cross-platform installer for cli-tran Antigravity CLI extension."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_NAME = "cli-tran"

IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git", "plans", "tests", "__pycache__", "*.pyc", ".gitignore",
)


def _is_windows() -> bool:
    return sys.platform == "win32"


def _staging_dir() -> Path:
    if _is_windows():
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local:
            base = Path(local)
        else:
            base = Path.home() / "AppData" / "Local"
    else:
        base = Path.home() / ".local" / "share"
    return base / "cli-tran-src"


def _ext_dir() -> Path:
    home = Path(os.environ.get("GEMINI_CLI_HOME", Path.home()))
    return home / ".gemini" / "extensions" / PLUGIN_NAME


def _find_agy() -> str:
    agy = shutil.which("agy")
    if agy:
        return agy
    if _is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            npm_bin = Path(appdata) / "npm" / "agy.cmd"
            if npm_bin.exists():
                return str(npm_bin)
    print("ERROR: agy not found in PATH. Install Antigravity CLI first.", file=sys.stderr)
    sys.exit(1)


def _stale_paths() -> list[Path]:
    home = Path.home()
    return [
        home / ".gemini" / "skills" / "cli-tran",
        home / ".gemini" / "antigravity-cli" / "plugins" / "cli-translator",
        home / ".gemini" / "extensions" / "cli-translator",
    ]


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    staging = _staging_dir()
    ext_dir = _ext_dir()
    agy_bin = _find_agy()

    if not (repo_root / "gemini-extension.json").exists():
        print(f"ERROR: gemini-extension.json missing in {repo_root}", file=sys.stderr)
        return 1

    print(f"Repo:     {repo_root}")
    print(f"Staging:  {staging}")
    print(f"ExtDir:   {ext_dir}")
    print(f"agy:      {agy_bin}")

    # 1. Copy repo to staging (no-space path, excludes .git etc.)
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(repo_root, staging, ignore=IGNORE_PATTERNS)

    if " " in str(staging):
        print(f"WARNING: staging path contains spaces: {staging}")
        print("Hook commands may break. Consider moving repo to a no-space path.")

    staging_root = str(staging).replace("\\", "/")

    # 2. Build extension directory
    if ext_dir.exists():
        shutil.rmtree(ext_dir)
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / "skills" / PLUGIN_NAME).mkdir(parents=True)

    shutil.copy2(staging / "gemini-extension.json", ext_dir / "gemini-extension.json")

    # 3. Substitute __EXT_ROOT__ in SKILL.md
    skill_src = staging / "skills" / PLUGIN_NAME / "SKILL.md"
    skill_dst = ext_dir / "skills" / PLUGIN_NAME / "SKILL.md"
    skill_dst.write_text(
        skill_src.read_text(encoding="utf-8").replace("__EXT_ROOT__", staging_root),
        encoding="utf-8",
    )

    # 4. Hooks (if non-empty)
    hooks_src = staging / "hooks" / "hooks.json"
    if hooks_src.exists():
        try:
            hooks_data = json.loads(hooks_src.read_text(encoding="utf-8"))
            if hooks_data.get("hooks"):
                hooks_dst = ext_dir / "hooks"
                hooks_dst.mkdir(exist_ok=True)
                content = hooks_src.read_text(encoding="utf-8").replace(
                    "__EXT_ROOT__", staging_root
                )
                (hooks_dst / "hooks.json").write_text(content, encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass

    # 5. GEMINI.md
    gemini_md_src = staging / "GEMINI.md"
    if gemini_md_src.exists():
        dst = ext_dir / "GEMINI.md"
        if _is_windows():
            shutil.copy2(gemini_md_src, dst)
        else:
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            os.symlink(gemini_md_src, dst)

    # 6. Clean stale legacy dirs
    for stale in _stale_paths():
        if stale.is_symlink() or stale.is_dir():
            print(f"Removing stale: {stale}")
            shutil.rmtree(stale, ignore_errors=True)

    # 7. Uninstall stale entry, then import
    subprocess.run([agy_bin, "plugin", "uninstall", PLUGIN_NAME],
                   capture_output=True)

    print("\nImporting via agy...")
    result = subprocess.run([agy_bin, "plugin", "import", "gemini"],
                           capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: agy plugin import failed:\n{result.stderr}", file=sys.stderr)
        return 1

    # 8. Verify
    print("\nVerifying registration:")
    check = subprocess.run([agy_bin, "plugin", "list"], capture_output=True, text=True)
    if PLUGIN_NAME not in check.stdout:
        print(f"ERROR: {PLUGIN_NAME} did not appear in agy plugin list", file=sys.stderr)
        return 1

    print(f"\nInstalled. Restart Antigravity CLI to load the extension.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
