# Architecture Audit Synthesis — cli-translator

**Date:** 2026-05-16
**Status:** Architecture VALIDATED with 3 critical gaps identified
**Researchers:** 3 parallel (proofreader patterns, Gemini CLI TOML, hook loop control)

---

## Verdict: Architecture is SOUND but INCOMPLETE

The locked architecture (Pure TOML + Python Scripts + Gemini CLI Built-in Tools, NO MCP) is **correct**. All 3 researchers confirmed MCP is unnecessary. However, the planned 5-script design has **3 critical gaps** that must be addressed before implementation.

---

## Cross-Researcher Findings Matrix

| Finding | Researcher 1 (Proofreader) | Researcher 2 (Gemini CLI) | Researcher 3 (Hook Loop) | Consensus |
|---------|---------------------------|--------------------------|-------------------------|-----------|
| MCP unnecessary | Confirmed | Confirmed | N/A | **UNANIMOUS** |
| `@{file}` blocked for novels | N/A | Confirmed (2000-line limit) | N/A | **CONFIRMED** |
| `read_file` reliable for novels | N/A | Confirmed (start_line/end_line) | N/A | **CONFIRMED** |
| AfterAgent hook viable | N/A | N/A | Confirmed (Ralph pattern) | **CONFIRMED** |
| clearContext needed | N/A | Confirmed (50% threshold) | Confirmed (prevents overflow) | **CONFIRMED** |
| 5 scripts insufficient | Confirmed (3 gaps) | Partially (needs hook script) | Confirmed (needs state mgmt) | **UNANIMOUS** |
| 2-tier glossary sufficient | Confirmed (keep merge logic) | N/A | N/A | **CONFIRMED** |
| Brief/response essential | Confirmed | N/A | N/A | **CONFIRMED** |

---

## 3 Critical Gaps in Current Plan

### Gap 1: Chapter Loop State Management (MISSING)

**Impact:** Without state tracking, the translator cannot:
- Know which chapters are translated vs pending
- Resume after interruption
- Display progress

**Solution:** Add `state.json` with chapter array:
```json
{
  "active": true,
  "source_file": "novel.txt",
  "output_dir": "translations/",
  "total_chapters": 50,
  "current_chapter": 1,
  "chapters": [
    {"id": 1, "start_line": 1, "end_line": 142, "status": "completed", "output_file": "chapter_001.txt"},
    {"id": 2, "start_line": 143, "end_line": 287, "status": "pending"}
  ]
}
```

**Source:** Researcher 3's Ralph pattern analysis + Researcher 1's pipeline state insight.

### Gap 2: Hook Script for Loop Control (MISSING)

**Impact:** No mechanism to continue translation loop after each chapter.

**Solution:** Add `hooks/translate-hook.sh` (AfterAgent hook):
- Reads state.json via `jq`
- Checks if all chapters done
- Returns `deny + clearContext: true` to continue
- Returns `allow + continue: false` when done

**Source:** Researcher 3's verified Ralph hook protocol.

### Gap 3: Glossary-as-Hint Architecture (MISSING)

**Impact:** Without this pattern, glossary becomes hard rules that corrupt compound nouns.

**Solution:** Adapt proofreader's brief/response protocol:
- One brief per chapter (not 5 concurrent)
- Brief contains: source text + glossary hints + genre tone
- Response contains: translated text + notes
- AI decides contextually, not mechanically

**Source:** Researcher 1's analysis of `_brief_protocol.py` and `chunk_translate.py`.

---

## Revised Script Count: 8 (not 5)

| # | Script | Purpose | Status |
|---|--------|---------|--------|
| 1 | `detect-chapters.py` | Chapter boundary detection (regex) | **EXISTING PLAN** |
| 2 | `init-translation.py` | Create state.json + output directory | **EXISTING PLAN** (enhanced with state schema) |
| 3 | `get-progress.py` | Read state, return progress | **EXISTING PLAN** |
| 4 | `validate-translation.py` | Paragraph count, length ratio, CJK residual | **EXISTING PLAN** |
| 5 | `epub2txt.py` | EPUB extraction (optional, Phase 3) | **EXISTING PLAN** |
| 6 | `translate-hook.sh` | AfterAgent hook for chapter loop | **NEW — Gap 2** |
| 7 | `brief-protocol.py` | Brief/response JSON handler | **NEW — Gap 3** (adapt from proofreader's `_brief_protocol.py`, 62 lines) |
| 8 | `glossary-loader.py` | 2-tier glossary deep-merge | **NEW — Gap 1** (adapt from proofreader's `apply_glossary.py`, simplified) |

---

## What's CONFIRMED from Original Plan

| Decision | Status | Evidence |
|----------|--------|----------|
| No MCP server | **VALIDATED** | All 3 researchers confirmed |
| TOML commands (translate, resume, validate) | **VALIDATED** | Researcher 2 verified TOML spec |
| AfterAgent hook pattern | **VALIDATED** | Researcher 3 verified Ralph protocol |
| 2-tier glossary (default + genre) | **VALIDATED** | Researcher 1 confirmed, keep merge logic |
| Chapter-by-chapter translation | **VALIDATED** | Researcher 2 confirmed read_file reliability |
| Genre system (7 profiles) | **VALIDATED** | Researcher 1 confirmed heuristic detection |
| Bilingual output mode | **VALIDATED** | No research contradicts |

---

## What's CHANGED from Original Plan

| Original Plan | Revised | Reason |
|---------------|---------|--------|
| 5 Python scripts | 8 scripts (5 Python + 1 shell + 1 Python + 1 Python) | 3 critical gaps |
| `init-translation.py` creates basic state | Enhanced with chapter array + status tracking | Resume capability |
| No hook script | `translate-hook.sh` added | Loop control |
| No brief protocol | `brief-protocol.py` added | AI-in-the-loop quality |
| No glossary loader | `glossary-loader.py` added | Deep-merge logic |

---

## What's DROPPED (Confirmed Unnecessary)

From proofreader's 34 scripts, these are NOT needed:
- Pipeline orchestrator (replaced by hook loop)
- Multi-round comprehensive review (proofreading concern)
- Polish loop (deprecated)
- Pronoun replacement (proofreading-specific)
- Visual prompt generation (not translation)
- TTS formatting (post-processing)
- Final QA gate (proofreading-specific)
- Skill log (self-learning, not core)
- ~20 other proofreader-specific scripts

---

## Open Questions (Prioritized)

| # | Question | Priority | Impact |
|---|----------|----------|--------|
| 1 | Does clearContext also clear GEMINI.md context? | **HIGH** | If yes, agent loses translation instructions between chapters |
| 2 | Ralph's prompt mismatch detection — will dynamic chapter numbers trigger it? | **HIGH** | May kill the loop if prompt changes per chapter |
| 3 | Actual RPM limits (not published) | **MEDIUM** | Affects speed, not correctness |
| 4 | Translation quality after 50+ clearContext cycles | **MEDIUM** | May degrade consistency |
| 5 | Hook timeout for large chapters (20K chars) | **LOW** | Hook itself is fast, translation happens in agent turn |
| 6 | State file locking for concurrent sessions | **LOW** | Edge case, can add advisory locking later |

---

## Implementation Priority

### Phase 1: Core (Must-have)
1. `gemini-extension.json` manifest
2. `translate.toml` with full translation instructions
3. `detect-chapters.py` — chapter boundary detection
4. `init-translation.py` — create state.json with chapter array
5. `translate-hook.sh` — AfterAgent loop control
6. `GEMINI.md` — extension context

### Phase 2: Translation Engine
7. `brief-protocol.py` — brief/response handler
8. `glossary-loader.py` — 2-tier deep-merge
9. `default.json` — universal glossary
10. 7 genre profiles with pronoun sets

### Phase 3: Quality & Resume
11. `validate-translation.py` — quality checks
12. `get-progress.py` — progress display
13. `resume.toml` — resume command
14. `validate.toml` — validation command

### Phase 4: Polish
15. `translation-principles.md` — P1-P4 guidelines
16. `pronoun-guide.md` — genre-specific pronouns
17. `common-errors.md` — error cases
18. `epub2txt.py` — EPUB support (optional)

---

## Sources

| Report | File |
|--------|------|
| Researcher 1 | `plans/reports/researcher-1-proofreader-architecture-analysis.md` |
| Researcher 2 | `plans/reports/researcher-2-gemini-cli-toml-deep-dive.md` |
| Researcher 3 | `plans/reports/researcher-3-hook-loop-state-management.md` |
| Prior research | `plans/reports/research-summary-mcp-necessity.md` |
| Prior research | `plans/reports/260516-2000-researcher-1-gemini-cli-without-mcp.md` |
| Prior research | `plans/reports/260516-1945-researcher-3-real-world-extension-patterns.md` |
