# User Guide — cli-tran (Cross-Platform Novel Translator)

## Overview

cli-tran translates Chinese web novels to Vietnamese using AI backends (currently `agy` which uses Gemini via Antigravity CLI). It runs as an agy skill — no manual API key management needed.

## Quick Start

### 1. Install

```bash
python3 install.py
```

This sets up the VS Code extension, hooks, and config files. Run from the repo root.

### 2. Translate a Novel

In Claude Code, run:

```
/cli-tran <path-to-novel.txt>
```

Example:
```
/cli-tran ~/novels/my-novel.txt
```

The skill will:
1. Detect chapters automatically
2. Initialize translation state
3. Start translating chapter by chapter

### 3. Check Progress

```
/cli-tran --progress
```

Shows: chapters completed, ETA, current model, skipped chapters, CJK residue warnings.

### 4. Resume After Interruption

If translation stops (quota, crash, Ctrl+C):

```
/cli-tran --resume
```

Resumes from where it left off. State is preserved in `~/.cache/cli-tran/novels/<hash>/state.json`.

### 5. Redo Chapters

```
/cli-tran --redo <spec>
```

Specs:
- `5` — single chapter
- `5-10` — range
- `5,8,12` — list
- `failed` — all skipped chapters
- `all` — everything

### 6. Recover Corrupted State

If `state.json` gets corrupted:

```bash
python3 scripts/recover-state.py [path-to-state.json]
```

Scans output directory and rebuilds state from actual files.

## How It Works

### Translation Loop

```
init-translation.py  →  Creates state.json with chapter metadata
        ↓
auto-translate.py    →  Driver loop (runs outside agent context)
        ↓
select-cascade.py    →  Picks available backend (agy)
        ↓
translate-chapter.py →  Translates ONE chapter via agy subprocess
        ↓
advance-chapter.py   →  Validates output, updates state, handles retries
        ↓
(repeat until all chapters done)
```

### State Management

Each novel gets a hash-keyed cache directory:

```
~/.cache/cli-tran/novels/<hash>/
  state.json           — Translation state (chapters, progress, model info)
  state.json.bak       — Backup of state
  driver.log           — Driver execution log
  backend_cache.json   — Backend availability cache
  novel-glossary.json  — Learned character/term mappings
  chapter-output/      — Per-chapter translated text
  entities/            — Extracted entities per chapter
  debug/               — Raw output from failed translations
```

Hash = `sha256(absolute_path + first_1KB)`. Survives renames, distinguishes same-name files.

### State Pointer

A single pointer file at `/tmp/.cli-tran-state-path` (Linux) or `%TEMP%\cli-tran-state-path` (Windows) tells the driver which novel is active. Only one translation runs at a time per agy instance.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLI_TRAN_CACHE_ROOT` | `~/.cache/cli-tran` | Cache directory override |
| `CLI_TRAN_STATE_POINTER` | temp dir | State pointer file override |
| `CLI_TRAN_MAX_CHAPTERS` | `600` | Safety limit per run |
| `CLI_TRAN_MAX_RETRIES` | `5` | Retries per chapter before skip |
| `CLI_TRAN_COOLDOWN` | `2` | Seconds between chapters |
| `CLI_TRAN_FORCE_BACKEND` | (none) | Force specific backend |

### Model Selection

The model is configured in `~/.gemini/antigravity-cli/settings.json` — use the
strongest Flash model available (highest version number):

```json
{
  "model": "Gemini 3.5 Flash (High)"
}
```

Google updates model versions periodically. Always pick the latest Flash with the
highest version number in your agy settings.

### Genre Detection

cli-tran auto-detects genre from source content. Supported genres:
- `tienxia` — Tiên hiệp
- `wuxia` — Kiếm hiệp
- `urban` — Đô thị
- `historical` — Lịch sử
- `gamelit` — Game/System
- `horror` — Kinh dị
- `fantasy` — Fantasy (default fallback)

Override: `/cli-tran <file> --genre <genre>`

## Platform-Specific Notes

### Windows

- Cache: `%LOCALAPPDATA%\cli-tran`
- State pointer: `%TEMP%\cli-tran-state-path`
- File locking: `msvcrt.locking` (mandatory byte-range locks)
- Path separator: Uses `pathlib.Path` everywhere — no manual `/` or `\`

### Linux

- Cache: `~/.cache/cli-tran`
- State pointer: `/tmp/.cli-tran-state-path`
- File locking: `fcntl.flock` (advisory locks, auto-released on process death)

### macOS

- Cache: `~/Library/Caches/cli-tran`
- State pointer: `/tmp/.cli-tran-state-path`
- File locking: Same as Linux (`fcntl.flock`)

## Troubleshooting

### "All backends exhausted"

Backend quota hit. Wait for quota reset or switch model:
```
/model <different-model>
/cli-tran --resume
```

### "state file missing"

State was corrupted or deleted. Run recovery:
```bash
python3 scripts/recover-state.py
```

### Translation quality issues (CJK leak)

If translations contain Chinese characters (>5% CJK ratio), the chapter is auto-retried. Check `debug/` folder for raw output.

### Stale cache cleanup

Novel caches older than 24h (with `active=false`) are auto-cleaned on next init. Manual cleanup:
```bash
python3 scripts/lib/novel_cache.py --cleanup
```
