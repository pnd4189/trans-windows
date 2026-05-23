---
title: "Windows Adaptation for cli-tran"
description: "Adapt cli-tran codebase to run on Windows with full feature parity. Replace bash with Python, remove gemini CLI backend, fix Unix-only paths and imports. All changes confined to this repo."
status: pending
priority: P1
branch: "main"
tags: [windows, cross-platform, python-rewrite, agy-only]
blockedBy: []
blocks: []
created: "2026-05-22T15:22:55.470Z"
createdBy: "ck:plan"
source: skill
brainstorm: "plans/reports/260522-brainstorm-windows-adaptation.md"
red-team: "plans/reports/260522-red-team-windows-adaptation.md"
---

# Windows Adaptation for cli-tran

## Overview

Adapt the cli-tran (Chinese-to-Vietnamese novel translator) codebase from Ubuntu-only to Windows-compatible. Key changes: replace bash scripts with Python, remove gemini CLI backend cascade (agy only), fix Unix-only paths (`/tmp`, `~/.cache/`, `fcntl`), create Python cross-platform installer. All changes confined to this repo — no external modifications.

**Brainstorm report**: `plans/reports/260522-brainstorm-windows-adaptation.md`

## Phases

| Phase | Name | Status | Effort | Priority |
|-------|------|--------|--------|----------|
| 1 | [Cross-Platform Infrastructure](./phase-01-cross-platform-infrastructure.md) | Pending | 1.5h | P1 |
| 2 | [Cross-Platform File Locking](./phase-02-cross-platform-file-locking.md) | Pending | 1h | P1 |
| 3 | [Backend Simplification](./phase-05-backend-simplification.md) | Pending | 1h | P1 |
| 4 | [Python Driver Rewrite](./phase-03-python-driver-rewrite.md) | Pending | 2.5h | P1 |
| 5 | [Installer Rewrite](./phase-04-installer-rewrite.md) | Pending | 2h | P1 |
| 6 | [SKILL and Config Updates](./phase-06-skill-and-config-updates.md) | Pending | 1h | P1 |
| 7 | [README and Documentation](./phase-07-readme-and-documentation.md) | Pending | 1h | P2 |

## Dependencies

```
Phase 1 (Infrastructure) ──→ all other phases
Phase 2 (Locking) ──→ Phase 4 (Driver rewrite uses locking)
Phase 3 (Backend) ──→ Phase 4 (Driver rewrite assumes agy-only)
Phase 3 (Backend) ──→ Phase 6 (SKILL.md references agy-only)
Phase 4 (Driver) ──→ Phase 5 (Installer deploys .py not .sh)
Phase 5 (Installer) ──→ Phase 6 (SKILL.md references install.py)
Phase 6 (SKILL/Config) ──→ Phase 7 (README reflects final state)
```

## Key Design Decisions (from brainstorm)

1. **agy-only backend** — remove `gemini` CLI cascade entirely
2. **Python rewrite** — all `.sh` → `.py` (auto-translate.sh → auto-translate.py)
3. **Extension path**: `%USERPROFILE%\.gemini\extensions\cli-tran\` (confirmed from gemini-cli source)
4. **Cache path**: `%LOCALAPPDATA%\cli-tran\` on Windows, `~/.cache/cli-tran` on Linux
5. **State pointer**: `tempfile.gettempdir() / .cli-tran-state-path` (cross-platform)
6. **File locking**: platform-conditional `fcntl`/`msvcrt` in stdlib, lock entire file
7. **Installer**: Python script with direct copy (no symlinks on Windows)
8. **Atomic writes**: `Path.replace()` everywhere (not `Path.rename()` — fails cross-drive on Windows)
9. **Backend simplification before driver rewrite** — avoids porting dead gemini-specific code

## Red Team Fixes Applied

| Finding | Severity | Fix |
|---------|----------|-----|
| `Path.rename()` not atomic on Windows cross-drive | CRITICAL | Audit all `.rename()` → `.replace()` in Phase 1 |
| `msvcrt.locking` only locks 1 byte | CRITICAL | Lock entire file via `os.path.getsize()` in Phase 2 |
| `tempfile.gettempdir()` returns 8.3 short names | CRITICAL | Use `.resolve()` in `state_pointer_path()` |
| Windows long path limit (260 chars) | CRITICAL | Document in README; keep cache paths short |
| Phase order: backend simplification before driver rewrite | HIGH | Phase 3 (was 5) now before Phase 4 (was 3) |
| `shutil.copytree` copies `.git/` | HIGH | Add `ignore=shutil.ignore_patterns(...)` in Phase 5 |
| `_strip_env()` removal may affect agy auth | HIGH | Keep env stripping for agy safety in Phase 3 |
| `/dev/null` as file path arg | MEDIUM | Use `None` sentinel instead of `os.devnull` |
| `python3` grep misses unquoted instances | MEDIUM | Use `grep -n 'python3' scripts/` (no quotes) |

## Cross-Platform Path Map

| Concept | Linux | Windows |
|---------|-------|---------|
| Extension dir | `~/.gemini/extensions/cli-tran/` | `%USERPROFILE%\.gemini\extensions\cli-tran\` |
| Cache root | `~/.cache/cli-tran/` | `%LOCALAPPDATA%\cli-tran\` |
| State pointer | `/tmp/.cli-tran-state-path` | `%TEMP%\.cli-tran-state-path` |
| Staging dir | `~/.local/share/cli-tran-src` | `%LOCALAPPDATA%\cli-tran-src` |
| Python binary | `python3` / `sys.executable` | `python` / `sys.executable` |
