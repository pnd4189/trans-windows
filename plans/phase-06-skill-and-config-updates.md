---
phase: 6
title: "SKILL and Config Updates"
status: pending
priority: P1
effort: "1h"
dependencies: [3, 5]
---

# Phase 6: SKILL and Config Updates

## Overview

Update `SKILL.md` and `GEMINI.md` to reflect: Python driver, agy-only backend, Windows-compatible paths. **Red team fix (M5):** Provide concrete command for reading state pointer instead of abstract description.

## Requirements

- Functional: SKILL.md commands use `python` not `bash` / `python3`
- Functional: All references to gemini CLI backend removed
- Functional: Concrete command for reading state pointer (not hardcoded path)
- Non-functional: Clear, concise — no stale references

## Architecture

**SKILL.md** key changes:
- Remove all "bash" and "python3" references
- Replace `bash __EXT_ROOT__/scripts/auto-translate.sh` → `python __EXT_ROOT__/scripts/auto-translate.py`
- Replace `python3` → `python` in all commands
- Update architecture diagram for Python driver + agy-only
- Remove gemini CLI backend references
- **Red team fix (M5):** State pointer access: use `python -c "import sys; sys.path.insert(0, '__EXT_ROOT__/scripts'); from lib.platform_paths import state_pointer_path; print(state_pointer_path())"` instead of hardcoded `/tmp/...`

**GEMINI.md** key changes:
- Remove model cascade (Pro1→Pro2→Flash)
- Remove `GEMINI_MODEL` env var reference
- Remove `./translate novel.txt` stale reference (line 83)
- Update "Model Selection" section: agy uses its own model config

## Related Code Files

- Modify: `skills/cli-tran/SKILL.md`
- Modify: `GEMINI.md`

## Implementation Steps

1. Edit `SKILL.md`:
   - Frontmatter `description` — remove "bash"
   - Architecture diagram: `auto-translate.sh` → `auto-translate.py`, `bash` → `python subprocess`
   - All `python3` → `python`
   - All `bash __EXT_ROOT__/scripts/auto-translate.sh` → `python __EXT_ROOT__/scripts/auto-translate.py`
   - Remove "Gemini Flash (primary)" and "gemini -p" references
   - Backend: "agy only, uses model from Antigravity settings"
   - State pointer: concrete `python -c "..."` command, not hardcoded path
   - Cache path: mention cross-platform locations
   - Update "What the driver does" section — agy-only
2. Edit `GEMINI.md`:
   - Remove model cascade section
   - Remove `GEMINI_MODEL=...` env var reference
   - Remove `./translate novel.txt` stale reference
   - Keep: translation principles, genre system, glossary, output format, completion markers

## Success Criteria

- [ ] No `bash` command references in SKILL.md
- [ ] No `python3` references in SKILL.md
- [ ] No `auto-translate.sh` references in SKILL.md
- [ ] No `gemini -p` or gemini CLI references in SKILL.md
- [ ] No model cascade in GEMINI.md
- [ ] No `GEMINI_MODEL` or `./translate` in GEMINI.md
- [ ] State pointer uses concrete python command, not hardcoded path
- [ ] Architecture diagram shows `auto-translate.py`
