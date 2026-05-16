---
title: "cli-translator Implementation"
description: "Gemini CLI extension for Chinese-to-Vietnamese novel translation. Pure TOML + Python + Built-in Tools (NO MCP). Chapter-by-chapter with AfterAgent hook loop."
status: done
priority: P1
branch: "main"
tags: [gemini-cli, translation, extension, chinese-novel]
blockedBy: []
blocks: []
created: "2026-05-16T14:27:15.708Z"
createdBy: "ck:plan"
source: skill
---

# cli-translator Implementation

## Overview

Gemini CLI extension that translates Chinese web novels to Vietnamese, chapter by chapter. Architecture validated by 3 parallel researchers: TOML commands + Python scripts + Gemini CLI built-in tools. No MCP server. Uses Ralph's AfterAgent hook pattern for chapter loop control. Direct prompt approach (no brief/response files).

## Architecture Summary

```
User: /translate novel.txt --genre tienxia --bilingual
  │
  ├─ init-translation.py → detect chapters, create state.json
  ├─ translate.toml → model reads state, translates chapter N
  ├─ translate-hook.sh → deny + clearContext → loop to next chapter
  ├─ ... repeat until all chapters done ...
  └─ /resume picks up from last completed chapter
```

## Phases

| Phase | Name | Status | Effort | Priority |
|-------|------|--------|--------|----------|
| 1 | [Core Extension + State Management](./phase-01-core-extension-state-management.md) | Done | 4h | P1 |
| 2 | [Hook Loop Control](./phase-02-hook-loop-control.md) | Done | 3h | P1 |
| 3 | [Glossary & Genre System](./phase-03-glossary-genre-system.md) | Done | 3h | P1 |
| 4 | [Translation Engine](./phase-04-translation-engine.md) | Done | 4h | P1 |
| 5 | [Quality & Validation](./phase-05-quality-validation.md) | Done | 2h | P2 |
| 6 | [EPUB Support](./phase-06-epub-support.md) | Done | 2h | P3 |
| 7 | [Testing + Polish](./phase-07-testing-polish.md) | Done | 4h | P1 |

## Dependencies

```
Phase 1 (Core) ──→ Phase 2 (Hook) ──→ Phase 4 (Translation Engine)
                  ──→ Phase 3 (Glossary) ──→ Phase 4
Phase 4 ──→ Phase 5 (Quality)
Phase 1 ──→ Phase 6 (EPUB)
Phase 4 + Phase 5 ──→ Phase 7 (Testing)
```

## Key Design Decisions (Locked)

1. **No MCP server** — 3 researchers confirmed over-engineering
2. **`read_file` not `@{file}`** — 2000-line hard limit blocks novels
3. **One chapter per iteration** — manageable context, clean error recovery
4. **Separate output files** — `write_file` is overwrite-only
5. **clearContext between chapters** — prevents context overflow
6. **Glossary as HINT** — AI decides contextually, not mechanically
7. **2-tier glossary** — default + genre (keep deep-merge logic from proofreader)

## Reference Reports

- `plans/reports/architecture-audit-synthesis.md` — cross-researcher synthesis
- `plans/reports/researcher-1-proofreader-architecture-analysis.md` — proofreader patterns
- `plans/reports/researcher-2-gemini-cli-toml-deep-dive.md` — TOML capabilities
- `plans/reports/researcher-3-hook-loop-state-management.md` — hook protocol
