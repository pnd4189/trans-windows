# Brainstorm Progress Update — cli-translator

**Updated:** 2026-05-16
**Status:** Architecture AUDITED & VALIDATED — ready for implementation planning

---

## Architecture Decision (LOCKED)

**Pure TOML + Python Scripts + Gemini CLI Built-in Tools. NO MCP Server.**

Rationale: 3 independent researchers confirmed MCP is over-engineering. Evidence:
- Conductor extension (3,559 stars): complex multi-file workflow, zero MCP
- Ralph extension (318 stars): batch loop + state management via shell scripts + hooks
- Gemini CLI built-in tools (`read_file`, `write_file`, `grep`, `shell`) cover all needs
- MCP adds ~90K tokens overhead/novel, tool name conflict risk, double rate-limiting
- chinese-novel-proofreader v3.3: same domain, TOML + 34 Python scripts, no MCP

---

## Architecture Audit (2026-05-16) — VALIDATED

3 parallel researchers investigated: proofreader patterns, Gemini CLI TOML system, hook loop control.

**Verdict:** Architecture is **SOUND** but has **3 critical gaps**. Revised from 5 → 8 scripts.

### Key Technical Findings

| Finding | Source | Impact |
|---------|--------|--------|
| `@{file}` BLOCKED for novels (2000-line hard limit) | Researcher 2 | Must use `read_file` tool with `start_line`/`end_line` |
| `read_file` IS reliable for 500+ page novels | Researcher 2 | Confirmed: no per-call line limit, can chain calls |
| `write_file` is overwrite-only (no append) | Researcher 2 | Must write per-chapter files, concatenate at end |
| AfterAgent hook protocol verified from source | Researcher 3 | Ralph pattern: `deny + clearContext: true` continues loop |
| clearContext fully wipes LLM memory | Researcher 3 | Must reload glossary each turn via `read_file` |
| 50+ iterations architecturally sound | Researcher 3 | Ralph proven, main risk is operational not technical |
| Rate limits safe: 50 chapters ≈ 100 requests vs 1000-2000 RPD | Researcher 2 | Well within limits |
| Glossary-as-hint (not hard rules) essential | Researcher 1 | Proofreader pattern: AI decides contextually |
| Brief/response protocol essential (simplified) | Researcher 1 | One brief per chapter, not 5 concurrent |
| 2-tier glossary sufficient (keep deep-merge logic) | Researcher 1 | Override + append + compound merge |

### 3 Critical Gaps in Original 5-Script Plan

1. **Chapter Loop State Management** — no mechanism to track/resume chapters → add `state.json` with chapter array
2. **Hook Script** — no loop control → add `translate-hook.sh` (AfterAgent, Ralph pattern)
3. **Glossary-as-Hint Architecture** — glossary becomes hard rules → add `brief-protocol.py` (adapt from proofreader's `_brief_protocol.py`, 62 lines)

### Revised Project Structure (8 scripts)

```
cli-translator/
├── gemini-extension.json          # name + version + contextFileName (NO mcpServers)
├── commands/
│   ├── translate.toml             # Main translation command (~300 lines prompt)
│   ├── resume.toml                # Resume interrupted translation
│   └── validate.toml              # Quality validation pass
├── scripts/
│   ├── detect-chapters.py         # Chapter boundary detection (regex)
│   ├── init-translation.py        # Create state.json + output directory [ENHANCED: chapter array]
│   ├── get-progress.py            # Read state, return progress
│   ├── validate-translation.py    # Paragraph count, length ratio, CJK residual
│   ├── epub2txt.py                # EPUB extraction (optional, Phase 3)
│   ├── translate-hook.sh          # [NEW] AfterAgent hook for chapter loop (Ralph pattern)
│   ├── brief-protocol.py          # [NEW] Brief/response JSON handler (adapt from proofreader)
│   └── glossary-loader.py         # [NEW] 2-tier glossary deep-merge (adapt from proofreader)
├── skills/
│   └── novel-translator/
│       └── SKILL.md               # Translation expertise + glossary rules
├── glossary/
│   ├── default.json               # Universal terms (Tier 1)
│   └── genres/                    # Genre-specific overrides (Tier 2)
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
│   └── hooks.json                 # AfterAgent hook config
└── GEMINI.md                      # Extension context
```

### State.json Schema (NEW)

```json
{
  "active": true,
  "source_file": "novel.txt",
  "output_dir": "translations/",
  "source_lang": "zh",
  "target_lang": "vi",
  "genre": "tienxia",
  "glossary_path": "glossary/default.json",
  "total_chapters": 50,
  "current_chapter": 1,
  "chapters": [
    {"id": 1, "start_line": 1, "end_line": 142, "status": "completed", "output_file": "chapter_001.txt", "char_count": 5230},
    {"id": 2, "start_line": 143, "end_line": 287, "status": "pending"}
  ],
  "chapters_completed": 0,
  "chapters_failed": 0,
  "started_at": "2026-05-16T12:00:00Z"
}
```

Status values: `pending`, `in_progress`, `completed`, `failed`, `skipped`

### Translation Loop (Verified)

```
1. init-translation.py → detect chapters, create state.json
2. translate.toml instructs model:
   ├─ read_file(state.json) → find current chapter
   ├─ read_file(novel.txt, start_line, end_line) → read chapter
   ├─ read_file(glossary.json) → load glossary hints
   ├─ Model translates with context
   ├─ write_file(output/chapter_N.txt) → save translation
   └─ update state.json status
3. translate-hook.sh (AfterAgent):
   ├─ Read state.json via jq
   ├─ If current_chapter < total_chapters → deny + clearContext → continue
   └─ If all done → allow + continue:false → stop
4. /resume picks up from last completed chapter
```

---

## Key Technical Decisions

### 1. TOML Command Processing (Source-Verified)
- `@{file}` truncates at **2000 lines** — DO NOT use for novels
- Model uses `read_file` with `start_line`/`end_line` instead
- `!{shell}` runs Python scripts pre-processing
- `{{args}}` injects user arguments

### 2. Chapter Loop Control (Ralph Pattern)
- `AfterAgent` hook checks `state.json` after each chapter
- Hook returns `deny` + `clearContext: true` to continue loop
- Hook returns `allow` when all chapters done
- `/resume` command picks up from last completed chapter

### 3. Translation Workflow
```
User: /translate novel.txt --genre tienxia --bilingual
  │
  ├─ 1. init-translation.py → detect chapters, create state.json
  ├─ 2. Model reads state.json → knows current chapter
  ├─ 3. Model reads glossary JSON via read_file
  ├─ 4. For each chapter:
  │     ├─ read_file(novel.txt, start_line, end_line)
  │     ├─ read_file(previous output) → context continuity
  │     ├─ Model translates with full context
  │     └─ write_file(output) → save translation
  ├─ 5. AfterAgent hook → continue or stop
  └─ 6. /resume picks up from last chapter
```

### 4. What's KEPT from Original Brainstorm
- Translation principles (4 core points from reference image) ✓
- Genre system (7 profiles with pronoun sets) ✓
- Glossary cascade (4-tier, temp per file) ✓
- Chapter detection patterns (Chinese, Vietnamese, English, numbered) ✓
- Bilingual output mode ✓
- SKILL.md auto-activation ✓
- Context continuity between chapters ✓
- EPUB support (Phase 3) ✓

### 5. What's DROPPED
- Entire MCP server (TypeScript + @modelcontextprotocol/sdk) ✗
- 9 MCP tools → replaced by Python scripts + built-in tools ✗
- MCP rate limiter → Gemini CLI handles natively ✗
- node_modules / TypeScript build / npm deps ✗

---

## Research Reports (Completed)

### Phase 1: MCP Necessity Research (2026-05-16)

| # | File | Topic |
|---|------|-------|
| 1 | `260516-2000-researcher-1-gemini-cli-without-mcp.md` | TOML capabilities, `@{file}` limits, built-in tools |
| 2 | `researcher-2-mcp-overhead-vs-value.md` | Token overhead, conflict risks, double-throttle analysis |
| 3 | `260516-1945-researcher-3-real-world-extension-patterns.md` | Conductor/Ralph/code-review patterns, MCP elimination map |
| 4 | `research-summary-mcp-necessity.md` | Cross-validated synthesis + architecture recommendation |
| 5 | `brainstorm-gemini-cli-translator.md` | Original brainstorm (ARCHIVED — architecture section outdated) |

### Phase 2: Architecture Audit (2026-05-16)

| # | File | Topic |
|---|------|-------|
| 6 | `researcher-1-proofreader-architecture-analysis.md` | chinese-novel-proofreader patterns: essential vs overkill, 3 critical gaps |
| 7 | `researcher-2-gemini-cli-toml-deep-dive.md` | TOML spec, `read_file` reliability, `write_file` limits, rate limits, context management |
| 8 | `researcher-3-hook-loop-state-management.md` | AfterAgent hook protocol, state.json schema, 50+ iteration viability, error recovery |
| 9 | `architecture-audit-synthesis.md` | Cross-researcher synthesis: revised 8-script architecture |

---

## Open Questions (Post-Audit)

| # | Question | Priority | Status |
|---|----------|----------|--------|
| 1 | Does clearContext also clear GEMINI.md context? | **HIGH** | Untested — if yes, agent loses translation instructions |
| 2 | Ralph's prompt mismatch detection — dynamic chapter numbers trigger it? | **HIGH** | Need static prompt or disable mismatch detection |
| 3 | Actual RPM limits (not published by Google) | **MEDIUM** | Empirical testing needed |
| 4 | Translation quality after 50+ clearContext cycles | **MEDIUM** | Test with real novel |
| 5 | Hook timeout for large chapters (20K chars) | **LOW** | Hook is fast, translation in agent turn |
| 6 | State file locking for concurrent sessions | **LOW** | Edge case, add advisory locking later |

### Resolved from Original Questions

| Original Question | Resolution |
|-------------------|------------|
| Chunking strategy | **One chapter per iteration** — natural boundaries, don't split mid-paragraph |
| Context quality degradation | **clearContext prevents this** — fresh context each turn, reload glossary via read_file |
| Glossary format | **JSON via read_file** — structured, model reads on-demand, not embedded in prompt |
| Rate limit behavior | **Safe** — 50 chapters ≈ 100 requests, well under 1000-2000 RPD limit |
| Hook reliability | **Architecturally sound** — Ralph proven, 50+ iterations untested but no technical blockers |

---

## Implementation Phases (Post-Audit)

### Phase 1: Core Extension + State Management
- Create `gemini-extension.json` manifest
- Write `translate.toml` with full translation instructions (use `read_file`, NOT `@{file}`)
- Write `resume.toml` and `validate.toml`
- Create `GEMINI.md` extension context
- Python: `detect-chapters.py` — chapter boundary detection (regex)
- Python: `init-translation.py` — create state.json with chapter array (ENHANCED)
- Python: `get-progress.py` — read state, return progress

### Phase 2: Hook Loop Control
- Shell: `translate-hook.sh` — AfterAgent hook (Ralph pattern)
- Create `hooks/hooks.json` — hook configuration
- State file management (create/read/update/advance)
- Resume capability via state.json
- Test with 5-chapter sample novel

### Phase 3: Glossary & Genre System
- Python: `glossary-loader.py` — 2-tier deep-merge (adapt from proofreader)
- Create `default.json` universal terms
- Create 7 genre profiles with pronoun sets
- Test glossary loading via `read_file`

### Phase 4: Translation Engine
- Python: `brief-protocol.py` — brief/response JSON handler (adapt from proofreader)
- Create `SKILL.md` for novel-translator skill
- Write `translation-principles.md` (P1-P4 guidelines)
- Write `pronoun-guide.md` (genre-specific pronouns)
- Write `common-errors.md` (error cases)

### Phase 5: Quality & Validation
- Python: `validate-translation.py` — paragraph count, length ratio, CJK residual
- Quality checks: Chinese residual + glossary consistency
- Progress display

### Phase 6: EPUB Support (Optional)
- Python: `epub2txt.py` script
- Preserve chapter structure from EPUB TOC

### Phase 7: Testing + Polish
- Test with real Chinese novel (50+ chapters)
- Error handling + edge cases
- Hook reliability at 50+ iterations
- clearContext quality impact assessment
- README

---

## Reference Links
- Gemini CLI: https://github.com/google-gemini/gemini-cli
- Conductor extension: https://github.com/gemini-cli-extensions/conductor
- Ralph extension: https://github.com/gemini-cli-extensions/ralph
- Immersive Translate: https://github.com/immersive-translate/immersive-translate
- Gemini CLI quotas: https://developers.google.com/gemini-code-assist/resources/quotas?hl=vi
- Reference image (translation principles): `/home/dung/cloud/gdrive/KHÁC/Linh tinh/photo_2026-05-15_14-43-08.jpg`
