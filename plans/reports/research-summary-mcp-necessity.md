# Research Summary: MCP Necessity for Gemini CLI Novel Translator

**Date:** 2026-05-16
**Verdict: KHÔNG CẦN MCP. Pure TOML + Python/Shell là kiến trúc đúng.**

---

## Executive Summary

3 researchers điều tra độc lập, tất cả đồng nhất: **MCP server là over-engineering cho use case này.** Evidence:

1. **Conductor (3,559 stars)** — complex multi-file workflow, ZERO MCP, 6 TOML commands
2. **Ralph (318 stars)** — batch loop + state management, ZERO MCP, shell scripts + hooks
3. **Gemini CLI source code v0.42.0** — model có built-in `read_file`, `write_file`, `grep`, `shell` tools
4. **chinese-novel-proofreader v3.3** — cùng domain, TOML + 34 Python scripts, NO MCP

---

## Key Findings (Cross-Validated)

### 1. MCP Overhead là THỰC SỰ, không phải lý thuyết

| Metric | MCP (9 tools) | TOML (0 tools) |
|--------|---------------|----------------|
| Token overhead/novel 25 chapters | ~90,000 tokens (9%) | 0 tokens |
| Latency overhead/novel 25 chapters | 3.75-11.25 min extra | 0 min |
| Tool call round-trips | 225 calls | 0 calls |
| Dependencies | Node.js + MCP SDK + Zod | Python stdlib |
| Build step | `tsc` compilation | None |
| Crash surfaces | MCP server process + SDK + transport | None |

### 2. Tool Name Conflict Risk — HIGH

Gemini CLI dùng flat tool registry. MCP tools + built-in tools đều gửi đến Gemini API. Risk:
- `save_translation` vs `WriteFileTool` → model bối rối chọn tool nào
- `get_chapter` vs `ReadFileTool` → same
- Model phải quyết định tool trên MỖI operation → confusion

### 3. Double Rate Limiting

Gemini CLI có `RetryableQuotaError` riêng. MCP rate limiter thêm layer nữa:
- MCP reject → model thấy error → retry → Gemini CLI count retry against quota
- Double quota consumption

### 4. Mỗi MCP Tool Có Replacement Đơn Giản Hơn

| MCP Tool | Replacement | Chi phí |
|----------|------------|---------|
| detect_chapters | `grep -nE "^第.{1,10}章"` / Python script | 1 shell command |
| get_glossary | `read_file` on JSON / `@{file}` injection | Built-in |
| get_genre_guide | SKILL.md / GEMINI.md references | Built-in |
| save_translation | `write_file` built-in tool | Built-in |
| validate_translation | Python script via `shell` | 1 script |
| get_cache | State file (JSON) via `shell` | Ralph pattern |
| auto_detect_characters | Model intelligence + Python | 1 script |
| get_previous_translation | `read_file` on output file | Built-in |
| epub_reader | `python3 scripts/epub2txt.py` | 1 script |

### 5. TOML Command Processing Pipeline (Source-Verified)

```
1. AtFileProcessor:  @{file} → inject file content (max 2000 lines!)
2. ShellProcessor:   !{cmd} → execute shell, inject output
3. DefaultArgument:  {{args}} → inject user arguments
```

**CRITICAL: `@{file}` truncates at 2000 lines.** For novels, use model's `read_file` tool with `start_line`/`end_line` params instead.

---

## Recommended Architecture: Pure TOML + Python Scripts

```
cli-translator/
├── gemini-extension.json          # name + version + contextFileName (NO mcpServers)
├── commands/
│   ├── translate.toml             # Main translation command (~300 lines prompt)
│   ├── resume.toml                # Resume interrupted translation
│   └── validate.toml              # Quality validation pass
├── scripts/
│   ├── detect-chapters.py         # Chapter boundary detection (regex)
│   ├── init-translation.py        # Create state.json + output directory
│   ├── get-progress.py            # Read state, return progress
│   ├── validate-translation.py    # Paragraph count, length ratio, CJK residual
│   └── epub2txt.py                # EPUB extraction (optional)
├── skills/
│   └── novel-translator/
│       └── SKILL.md               # Translation expertise + glossary rules
├── glossary/
│   ├── default.json               # Universal terms
│   └── genres/
│       ├── tienxia.json
│       ├── wuxia.json
│       ├── urban.json
│       ├── historical.json
│       ├── gamelit.json
│       ├── horror.json
│       └── fantasy.json
├── references/
│   ├── translation-principles.md  # Flexible P1-P4 guidelines
│   ├── pronoun-guide.md           # Genre-specific pronouns
│   └── common-errors.md           # 27 verified error cases
├── hooks/
│   └── hooks.json                 # AfterAgent hook for chapter loop (Ralph pattern)
└── GEMINI.md                      # Extension context
```

### Workflow

```
User: /translate novel.txt --genre tienxia --bilingual
  │
  ├─ 1. TOML prompt triggers Python: init-translation.py
  │     → detect chapters, create .translator/state.json
  │
  ├─ 2. Model reads state.json via read_file
  │     → knows current chapter position
  │
  ├─ 3. Model reads glossary via read_file (glossary/tienxia.json)
  │     → loads terms, pronouns, genre notes
  │
  ├─ 4. For each chapter:
  │     ├─ read_file(novel.txt, start_line, end_line) → chapter text
  │     ├─ read_file(previous output) → context continuity
  │     ├─ Model translates with full context
  │     └─ write_file(output) → save translation
  │
  ├─ 5. AfterAgent hook checks state.json
  │     → chapters remaining? continue. Done? stop.
  │
  └─ 6. /resume picks up from last completed chapter
```

---

## What Gets KEPT from Brainstorm

- Translation principles (4 điểm từ ảnh tham khảo) ✓
- Genre system (7 profiles) ✓
- Glossary cascade (4-tier, temp per file) ✓
- Chapter detection patterns ✓
- Bilingual output ✓
- SKILL.md auto-activation ✓
- Context continuity between chapters ✓

## What Gets DROPPED

- Entire MCP server (TypeScript + @modelcontextprotocol/sdk) ✗
- 9 MCP tools → replaced by Python scripts + built-in tools ✗
- MCP rate limiter → Gemini CLI handles rate limiting natively ✗
- node_modules / build step / npm deps ✗

## What Gets ADDED

- Python scripts for deterministic operations (chapter detection, validation, init)
- AfterAgent hook pattern (from Ralph) for chapter loop control
- State file (state.json) for progress tracking + resume
- Separate `/resume` and `/validate` commands

---

## Open Questions (Low Priority)

1. **Context quality degradation** — Does model quality drop after 25+ sequential tool calls? Needs testing.
2. **Shell portability** — bash+jq standard on Linux/Mac, Python scripts more portable.
3. **Hook reliability** — Ralph's AfterAgent pattern is new (v1.0.1), untested at 50+ iterations.
4. **Glossary format** — JSON (structured, model reads via `read_file`) vs embedded in SKILL.md (immediate context). Test both.

---

## Action Recommendation

1. **Proceed with Pure TOML + Python architecture**
2. **Do NOT implement MCP server** — over-engineering with proven simpler alternative
3. **Use Ralph's hook pattern** for chapter loop control
4. **Use Conductor's prompt pattern** for complex multi-step workflow in single TOML command
5. **Test with real novel** early to validate context quality over long sessions
