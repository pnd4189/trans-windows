---
phase: 5
title: "Installer Rewrite"
status: pending
priority: P1
effort: "2h"
dependencies: [4]
---

# Phase 5: Installer Rewrite

## Overview

Rewrite `install.sh` as `install.py`. Cross-platform Python installer: copy to staging, substitute `__EXT_ROOT__`, register with agy. **Red team fix (H3):** Exclude `.git/`, `plans/`, etc. from copy.

## Requirements

- Functional: Installs cli-tran as agy extension on both Windows and Linux
- Functional: Idempotent — safe to re-run
- Functional: Verifies `agy` is in PATH before proceeding
- Non-functional: No bash dependency; pure Python 3.10+
- Non-functional: No symlinks on Windows (copy instead)

## Architecture

```
install.py (replaces install.sh)
  ├── _staging_dir() → %LOCALAPPDATA%\cli-tran-src (Win) or ~/.local/share/cli-tran-src (Linux)
  ├── _ext_dir() → ~/.gemini/extensions/cli-tran/
  ├── main():
      1. shutil.which("agy") — verify in PATH
      2. shutil.copytree(repo_root, staging, ignore=.git,plans,tests,__pycache__)
      3. Substitute __EXT_ROOT__ in SKILL.md + hooks.json
      4. Deploy to ext_dir (mkdir parents=True)
      5. Copy GEMINI.md (symlink on Linux, copy on Windows)
      6. Clean stale legacy dirs
      7. agy plugin uninstall (idempotent)
      8. agy plugin import gemini
      9. Verify with agy plugin list
```

**Red team fix (H3):** `shutil.copytree` must use `ignore=shutil.ignore_patterns('.git', 'plans', 'tests', '__pycache__', '*.pyc')` to avoid copying read-only `.git/objects/pack/` files and non-runtime directories.

**Red team fix (L2):** Ensure `ext_dir.mkdir(parents=True, exist_ok=True)` for fresh installs where `~/.gemini/extensions/` doesn't exist.

## Related Code Files

- Create: `install.py`
- Delete: `install.sh`
- Reference: `skills/cli-tran/SKILL.md` (contains `__EXT_ROOT__`)
- Reference: `hooks/hooks.json` (contains `__EXT_ROOT__`)

## Implementation Steps

1. Create `install.py` at repo root:
   - `_find_repo_root()` — `Path(__file__).resolve().parent`
   - `_staging_dir()` — platform-conditional no-space path
   - `_ext_dir()` — `Path.home() / ".gemini" / "extensions" / "cli-tran"`
   - Verify agy: `shutil.which("agy")`, check common Windows npm path as fallback
   - Copy to staging with ignore patterns
   - If staging path has spaces: print warning
   - Substitute `__EXT_ROOT__` via Python `.replace()` (use forward slashes in templates)
   - Deploy: `gemini-extension.json`, substituted SKILL.md, hooks.json (if non-empty), GEMINI.md
   - GEMINI.md: symlink on Linux, copy on Windows
   - Clean stale dirs (same list as install.sh)
   - `subprocess.run(["agy", "plugin", "uninstall", "cli-tran"], capture_output=True)` — ignore errors
   - `subprocess.run(["agy", "plugin", "import", "gemini"])` — must succeed
   - Verify: `agy plugin list` contains `cli-tran`
2. Delete `install.sh`

## Success Criteria

- [ ] `install.py` exists at repo root
- [ ] `python install.py` registers cli-tran with agy
- [ ] `agy plugin list` shows cli-tran after install
- [ ] Idempotent: re-run does not error
- [ ] `install.sh` deleted
- [ ] `.git/` and `plans/` excluded from staging copy
- [ ] `__EXT_ROOT__` substituted with forward-slash path
- [ ] Extension dir parents created (`mkdir(parents=True)`)
