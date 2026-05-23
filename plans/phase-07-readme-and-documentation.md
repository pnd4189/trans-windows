---
phase: 7
title: "README and Documentation"
status: pending
priority: P2
effort: "1h"
dependencies: [6]
---

# Phase 7: README and Documentation

## Overview

Full rewrite of `README.md` for Windows-focused audience. Document Windows prerequisites, updated architecture, and testing checklist.

## Requirements

- Functional: Clear Windows installation instructions
- Functional: Accurate architecture (Python driver, agy-only)
- Functional: Windows-specific prerequisites documented
- Non-functional: Professional, concise, no AI references

## Architecture

README sections:
1. **Header** — updated description
2. **Requirements** — Python 3.10+, Antigravity CLI (`agy`), `python` in PATH
3. **Installation** — `python install.py`
4. **Usage** — same `/cli-tran` commands
5. **Architecture** — Python driver, agy-only
6. **Backend** — single table: agy only
7. **Genre support** — unchanged
8. **Project structure** — updated file list
9. **Quality controls** — cross-platform locking
10. **Windows notes** — long paths, PATH setup
11. **License** — MIT

**Red team fixes applied:**
- (C4) Document Windows long path limit
- (L1) Document `python` must be in PATH (not just `py` launcher)
- (H7) State migration from Linux is unsupported
- (M7) Include Windows test checklist

## Related Code Files

- Modify: `README.md`

## Implementation Steps

1. Rewrite `README.md`:
   - **Requirements**: Python 3.10+, Antigravity CLI (`agy` in PATH). No gemini CLI. `python` command must work in terminal.
   - **Installation**: `git clone` → `cd` → `python install.py` → restart agy
   - **Usage**: Same `/cli-tran` commands — unchanged
   - **Architecture**: Updated diagram with `auto-translate.py`, `install.py`, agy-only
   - **Backend**: Single row — agy, model from Antigravity settings
   - **Cache location**: Linux `~/.cache/cli-tran/`, Windows `%LOCALAPPDATA%\cli-tran\`
   - **Project structure**: `install.py`, `auto-translate.py` (no `.sh` files)
   - **Quality controls**: "cross-platform file lock" instead of "flock guard"
   - **Windows notes**:
     - Python must be in PATH (verify with `python --version`)
     - Windows long path support: if cache paths exceed 260 chars, enable LongPathsEnabled registry key or move cache via `CLI_TRAN_CACHE_ROOT` env var
     - State migration from Linux is not supported — start fresh on Windows
   - Remove `CLI_TRAN_FORCE_BACKEND=agy` example (no longer needed)
2. Include test checklist for Windows verification

## Success Criteria

- [ ] Windows-compatible installation instructions
- [ ] No `bash` or `.sh` references
- [ ] No gemini CLI references
- [ ] Architecture shows `.py` files
- [ ] Backend table: agy only
- [ ] Cache path documents both OS locations
- [ ] Windows prerequisites documented (Python in PATH, long paths)
- [ ] State migration noted as unsupported
- [ ] Windows test checklist included
