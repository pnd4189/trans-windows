---
phase: 1
title: "Core Extension + State Management"
status: pending
priority: P1
effort: "4h"
dependencies: []
---

# Phase 1: Core Extension + State Management

## Overview

Create the Gemini CLI extension manifest, TOML translation command, and Python scripts for chapter detection and state management. This is the foundation that all other phases depend on.

## Requirements

- Functional: Extension loads in Gemini CLI, `/translate` command works, chapters detected, state tracked
- Non-functional: State file survives crashes, chapter detection handles Chinese/Vietnamese/English patterns

## Architecture

```
gemini-extension.json          ← Extension manifest (name, version, contextFileName)
commands/translate.toml        ← Main translation prompt (~300 lines)
scripts/detect-chapters.py     ← Regex chapter boundary detection
scripts/init-translation.py    ← Create state.json with chapter array
scripts/get-progress.py        ← Read state, return progress summary
GEMINI.md                      ← Extension context (loaded every session)
```

### State.json Schema

```json
{
  "active": true,
  "version": 1,
  "source_file": "/path/to/novel.txt",
  "output_dir": "/path/to/output/",
  "source_lang": "zh",
  "target_lang": "vi",
  "genre": "tienxia",
  "glossary_path": "glossary/default.json",
  "total_chapters": 50,
  "current_chapter": 1,
  "chapters": [
    {
      "id": 1,
      "title": "第一章",
      "start_line": 1,
      "end_line": 142,
      "status": "completed",
      "output_file": "chapter_001.txt",
      "char_count": 5230,
      "translated_at": "2026-05-16T12:05:00Z"
    },
    {
      "id": 2,
      "title": "第二章",
      "start_line": 143,
      "end_line": 287,
      "status": "pending",
      "output_file": null,
      "char_count": null,
      "translated_at": null
    }
  ],
  "chapters_completed": 0,
  "chapters_failed": 0,
  "started_at": "2026-05-16T12:00:00Z",
  "last_updated": "2026-05-16T12:00:00Z"
}
```

Status values: `pending`, `in_progress`, `completed`, `failed`, `skipped`

## Related Code Files

- Create: `gemini-extension.json`
- Create: `commands/translate.toml`
- Create: `scripts/detect-chapters.py`
- Create: `scripts/init-translation.py`
- Create: `scripts/get-progress.py`
- Create: `GEMINI.md`

## Implementation Steps

### 1.1 Create gemini-extension.json

```json
{
  "name": "cli-translator",
  "version": "1.0.0",
  "contextFileName": "GEMINI.md"
}
```

No `mcpServers` field — pure TOML + built-in tools.

### 1.2 Create GEMINI.md

Extension context file loaded every session. Contains:
- Translation principles (P1-P4)
- Genre system overview
- Glossary usage instructions
- Output format specifications
- Error handling guidelines

### 1.3 Create commands/translate.toml

Main translation command. Key sections:
- **Prompt template**: Instructions for the model to translate one chapter
- **State reading**: Model reads `state.json` via `read_file` to find current chapter
- **Chapter reading**: Model reads chapter via `read_file(start_line, end_line)`
- **Glossary loading**: Model reads glossary via `read_file`
- **Output writing**: Model writes translated chapter via `write_file`
- **State update**: Model updates state.json status after translation

Critical: Use `read_file` tool, NOT `@{file}` (2000-line limit blocks novels).

Template structure:
```
You are a professional Chinese-to-Vietnamese novel translator.

## Current Task
1. Read the translation state file at {{args}}/.translator/state.json to find the current chapter (current_chapter field).
2. Read the source file chapter using read_file with the start_line and end_line from state.
3. Read the glossary file at the path specified in state.json (glossary_path field).
4. Translate the chapter following the principles in GEMINI.md.
5. Write the translation to the output directory as chapter_NNN.txt.
6. Update the state.json to mark the chapter as completed (status: "completed", translated_at: timestamp).
7. Output EXACTLY this marker at the end of your response: CHAPTER_TRANSLATION_COMPLETE

## Translation Principles
{embedded from GEMINI.md or references/translation-principles.md}

## Important
- Use read_file tool, NOT @{file} (2000-line limit)
- Use write_file for output (overwrite mode, one file per chapter)
- Output CHAPTER_TRANSLATION_COMPLETE marker when done — this signals the hook to continue
- If translation fails, output CHAPTER_TRANSLATION_FAILED instead
```

### 1.4 Create scripts/detect-chapters.py

Chapter boundary detection using regex patterns:

```python
# Patterns by language
CHAPTER_PATTERNS = [
    r'^第.{1,10}章',           # Chinese: 第一章, 第12章
    r'^Chapter\s+\d+',          # English: Chapter 1
    r'^Chương\s+\d+',          # Vietnamese: Chương 1
    r'^\d+\.\s',                # Numbered: 1. Introduction
    r'^#{1,3}\s+',              # Markdown: ## Chapter 1
]

# Edge cases:
# - Volume markers (卷/册) are NOT chapter markers — filter out
# - Prologue/Epilogue → chapter 0 and chapter N+1
# - No markers → treat entire file as single chapter
```

Input: file path
Output: JSON array of `{id, title, start_line, end_line}`

### 1.5 Create scripts/init-translation.py

Creates `.translator/` directory and `state.json`:
1. Call `detect-chapters.py` to get chapter list
2. Build chapters array with `status: "pending"`
3. Write state.json with all required fields
4. Create output directory

Input: source_file path, output_dir, genre, glossary_path
Output: state.json file

### 1.6 Create scripts/get-progress.py

Reads state.json and returns progress summary:
- Total chapters, completed, failed, pending
- Current chapter info
- Percentage complete
- Estimated time remaining (based on average chapter time)

Input: state.json path (optional, defaults to `.translator/state.json`)
Output: formatted progress text

## Success Criteria

- [ ] `gemini-extension.json` loads in Gemini CLI without errors
- [ ] `/translate novel.txt --genre tienxia` command recognized
- [ ] `detect-chapters.py` correctly identifies chapter boundaries in sample Chinese novel
- [ ] `init-translation.py` creates valid state.json with all chapters
- [ ] `get-progress.py` displays accurate progress
- [ ] `GEMINI.md` provides clear translation instructions to the model
- [ ] `translate.toml` instructs model to use `read_file` (not `@{file}`)
- [ ] `translate.toml` instructs model to output `CHAPTER_TRANSLATION_COMPLETE` marker

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `@{file}` used accidentally in TOML | HIGH | Document clearly: use `read_file` tool only |
| Chapter detection misses patterns | MEDIUM | Support multiple regex patterns, fallback to paragraph count |
| State.json corruption | MEDIUM | Atomic writes (write tmp, mv) |
| translate.toml prompt too long | LOW | Keep under 300 lines, reference GEMINI.md for details |

## Security Considerations

- No user input in shell commands (no injection risk)
- State.json is local only (no network exposure)
- Glossary files are read-only

## Next Steps

- Phase 2 depends on this: Hook script reads state.json created here
- Phase 3 depends on this: Glossary loaded via `read_file` in translate.toml
