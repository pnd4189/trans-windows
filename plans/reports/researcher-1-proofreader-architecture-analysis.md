# Researcher Report: chinese-novel-proofreader Architecture Analysis

**Date:** 2026-05-16
**Source:** `/home/dung/.claude/skills/chinese-novel-proofreader/` (v3.4.0, 40 Python scripts)
**Target:** cli-translator (planned: 5 scripts + TOML commands)

---

## Executive Summary

The proofreader has 40 scripts implementing a 10-step pipeline with 5 brief/response AI interaction points, 5-tier glossary cascade, multi-round LLM-first review, and visual prompt generation. For a chapter-by-chapter Chinese-to-Vietnamese translator, **roughly 8-10 patterns are essential**, 15+ are proofreader-specific and unneeded, and the planned 5-script architecture **misses 3 critical patterns**: chapter loop state management, glossary-as-hint (not hard rule) architecture, and translation quality validation (distinct from proofreading QA).

---

## Pattern Matrix: Essential vs Non-Essential

### ESSENTIAL (must-have, even simplified)

| Pattern | Proofreader Script | Why Essential | Simplified Form |
|---------|-------------------|---------------|-----------------|
| **Glossary cascade** | `apply_glossary.py` | Term consistency across chapters | 2-tier OK (default + genre), but deep-merge logic and phrase protection needed |
| **Brief/Response protocol** | `_brief_protocol.py` | AI-in-the-loop for translation decisions | Single-file pattern per chapter, not 5 concurrent briefs |
| **Chinese detection** | `detect_chinese.py` | Identify untranslated segments | Reuse directly or thin wrapper |
| **Genre detection** | `detect_genre.py` | Tone/register for translation | Heuristic-only (no AI confirmation round needed) |
| **Text normalization** | `text_normalizer.py` | Clean input before translation | Reuse directly |
| **Dialogue detection** | `dialogue_detector.py` | Preserve dialogue register, translate differently | Core FSM, essential for quality |
| **IO utilities** | `_io_utils.py` | Atomic writes, crash safety | Reuse directly |
| **Regex patterns** | `_regexes.py` | Chinese/Pinyin/English detection | Reuse directly |

### VALUABLE (nice-to-have, adapt if time permits)

| Pattern | Proofreader Script | Value | Notes |
|---------|-------------------|-------|-------|
| **Character tracking** | `track_characters.py` | Name consistency across chapters | Useful but not blocking for v1 |
| **Chunk translation** | `chunk_translate.py` | AI translation with validation | Core concept needed, but 3000-char chunking + validation logic is the key part |
| **QA gate** | `qa_review.py` | Structural quality checks | Simplify to: Chinese residual + paragraph count + glossary consistency |
| **Translation cache** | `chunk_translate.py` (internal) | Avoid re-translating unchanged chunks | Content-hash caching by chunk is very valuable for resume |
| **Phrase protection** | `_phrase_protection.py` | Prevent glossary from corrupting compound nouns | Critical for quality, small module |

### NOT NEEDED (proofreader-specific)

| Pattern | Script | Why Not Needed |
|---------|--------|----------------|
| Pipeline orchestrator (10-step) | `pipeline_orchestrator.py` | Overkill. Chapter loop via AfterAgent hook is simpler |
| Multi-round comprehensive review | `comprehensive_review.py` | Proofreading concern, not translation |
| Comprehensive review detection | `comprehensive_review_detect.py` | Proofreading concern |
| Comprehensive review POV | `comprehensive_review_pov.py` | Proofreading concern |
| Polish loop | `polish_loop.py` | Deprecated even in proofreader v3.4 |
| Pronoun replacement | `replace_pronouns.py` | Proofreading-specific (anh→hắn etc.) |
| Visual prompt generation | `generate_visual_prompts.py` | Not part of translation |
| Scene extraction | `extract_scenes.py` | Visual prompt support |
| TTS formatting (VieNeu/Gwen) | `format_tts.py`, `_tts_*.py` | Post-processing, not translation |
| QA content review | `qa_content_review.py` | Proofreading-specific criteria |
| Final QA gate | `final_qa_gate.py` | Proofreading-specific gate |
| Final check | `final_check.py` | Proofreading-specific |
| Field completeness checker | `field_completeness_checker.py` | Visual prompt support |
| Narrative leak detector | `narrative_leak_detector.py` | Pronoun proofreading |
| Skill log | `skill_log.py` | Self-learning, not core |
| CLI summary | `cli_summary.py` | Nice output, not core |
| Audit glossary | `audit_glossary.py` | Safety check, not core |
| Update glossary | `update_glossary.py` | CLI tool, not core pipeline |
| Translate Chinese wrapper | `translate_chinese.py` | External API wrapper, cli-translator uses Gemini CLI |
| Paragraph-aligned chunker | `chunker_paragraph_aligned.py` | Used by comprehensive_review only |
| Pipeline steps helpers | `pipeline_steps.py` | Orchestrator-specific |

---

## Key Architecture Questions Answered

### 1. Brief/Response Protocol — Essential or Proofreader-Specific?

**Verdict: ESSENTIAL pattern, simplified form.**

The `_brief_protocol.py` (62 lines) is a thin wrapper: write brief JSON → Claude fills response JSON → pipeline applies. This pattern is the **core AI-in-the-loop mechanism** for any LLM-assisted tool.

For cli-translator, the pattern adapts to:
- **One brief per chapter** (not 5 concurrent briefs for different concerns)
- Brief contains: source text + glossary hints + genre tone + translation instructions
- Response contains: translated text + notes + quality flags
- Cache by content hash enables resume without re-translating

The proofreader runs 5 brief/response pairs (genre, translate, comprehensive_review, visual, final_qa). The translator needs **1 pair per chapter** with the loop managed by AfterAgent hook.

### 2. Pipeline Orchestrator — Overkill?

**Verdict: YES, overkill. Replace with chapter loop.**

The `pipeline_orchestrator.py` (600+ lines) manages a linear 10-step pipeline with complex state tracking, conditional imports, and multiple gate points. This is designed for **single-file batch processing**.

For chapter-by-chapter translation:
- **AfterAgent hook** handles the loop: translate chapter → check result → advance to next
- Each chapter is independent (own brief/response pair)
- State is filesystem-based: which chapters have translated files, which are pending
- No need for the orchestrator's complex conditional import chain

### 3. 5-Tier vs 2-Tier Glossary — Is 2-Tier Sufficient?

**Verdict: 2-tier is sufficient, but preserve the MERGE LOGIC.**

The proofreader's 5 tiers:
1. `default-glossary.json` (skill root)
2. `genre-profiles/<genre>.json`
3. `<novel-root>/glossary.json`
4. `<chapter-folder>/glossary.json`
5. CLI `--glossary` override

For cli-translator, 2 tiers (default + genre) covers the common case. But the **deep-merge logic** in `apply_glossary.py` (lines 35-121) is critical:
- Terms: override wins
- Characters: override wins
- Protected phrases: append (both preserved)
- Compound context: merge prefixes/suffixes
- Pronoun rules: merge by `from` key

**Key insight:** The proofreader's glossary is a HINT system, not hard rules. The `chunk_translate.py` instructions (line 197) explicitly say: "Glossary và examples là HINT, AI tự đọc ngữ cảnh để phán đoán." This philosophy should carry over to the translator.

### 4. Multi-Round Review — Needed for Translation Quality?

**Verdict: NOT needed for translation. Different quality model.**

The proofreader's multi-round review (up to 3 rounds per comprehensive_review) addresses:
- Pronoun consistency (ngươi/ta leak detection)
- Stylistic polish (stiff/literal passages)
- Dialogue register preservation

Translation quality is different:
- Accuracy of meaning
- Naturalness of target language
- Term consistency (handled by glossary)
- No untranslated segments (handled by Chinese detection)

**Translation quality can be validated in a single pass** via `validate-translation.py` checking: no Chinese residual, glossary terms applied, paragraph count preserved, length ratio reasonable (0.5-2.0x).

### 5. What Critical Patterns Does the 5-Script Plan MISS?

**3 critical gaps identified:**

#### Gap 1: Chapter Loop State Management
The 5 scripts have no mechanism to:
- Track which chapters are translated vs pending
- Resume after interruption
- Handle the "translate one chapter, then advance" loop

**Recommendation:** Add a `state.json` or use filesystem convention (translated chapters get `_translated.txt` suffix). The AfterAgent hook reads state to determine next chapter.

#### Gap 2: Glossary-as-Hint Architecture
The planned `init-translation.py` likely initializes glossary, but there's no pattern for:
- Passing glossary hints to the AI during translation
- Allowing AI to override glossary based on context
- Caching translation decisions by content hash

**Recommendation:** Adapt `chunk_translate.py`'s brief structure: embed glossary terms + genre tone + few-shot examples in the translation brief. Let AI decide contextually.

#### Gap 3: Translation Cache with Content Hashing
The proofreader's `chunk_translate.py` caches translations by `sha256(chunk_content) + glossary_version_hash`. This means:
- Unchanged chapters don't need re-translation
- Glossary changes invalidate only affected chunks
- Resume is fast (only translate new/changed chapters)

**Recommendation:** Each chapter's translated output includes a metadata header with content hash + glossary version. `get-progress.py` checks these to determine what needs re-translation.

---

## Script Dependency Map (Essential Only)

```
_brief_protocol.py  ← used by chunk translation
_io_utils.py        ← used everywhere (atomic writes)
_regexes.py         ← used by detection scripts
_phrase_protection.py ← used by glossary application
dialogue_detector.py ← used by chunk translation (narrative extraction)
detect_genre.py     ← reads genres.py, uses _brief_protocol
detect_chinese.py   ← uses _regexes
text_normalizer.py  ← standalone
apply_glossary.py   ← uses genres, _phrase_protection, _regexes
chunk_translate.py  ← uses dialogue_detector, _regexes, genres, _brief_protocol
```

**Minimum viable dependency set:** `_io_utils.py`, `_regexes.py`, `_brief_protocol.py`, `_phrase_protection.py`, `dialogue_detector.py` — these are pure utility modules with no pipeline coupling.

---

## Recommendations for cli-translator Architecture

### Keep (reuse or adapt)
1. `_brief_protocol.py` — reuse as-is (62 lines, pure utility)
2. `_io_utils.py` — reuse as-is (atomic writes)
3. `_regexes.py` — reuse as-is (Chinese/Pinyin/English patterns)
4. `_phrase_protection.py` — reuse as-is (compound noun protection)
5. `dialogue_detector.py` — reuse as-is (narrative/dialogue FSM)
6. `apply_glossary.py` — adapt: simplify to 2-tier, keep deep-merge logic
7. `detect_genre.py` — adapt: heuristic-only, skip AI confirmation round
8. `chunk_translate.py` — adapt: core chunking + validation + caching logic, simplified brief

### Add (missing from proofreader)
1. **Chapter state tracker** — filesystem-based or state.json
2. **Translation brief template** — genre-aware, glossary-hint, with few-shot examples
3. **Translation validator** — Chinese residual + paragraph count + length ratio (not proofreader QA)

### Skip (proofreader-specific)
- Pipeline orchestrator, comprehensive review, polish loop, pronoun replacement, visual prompts, TTS formatting, final QA gate, skill log, all visual/TTS modules

---

## Unresolved Questions

1. **TOML command structure** — How do `translate.toml` and `resume.toml` map to the brief/response cycle? Does Gemini CLI read TOML to know what to do, or does the Python script emit TOML?
2. **AfterAgent hook granularity** — Does it fire after each chapter translation, or after a batch? How does it pass the "which chapter next" context?
3. **Glossary source** — Is the glossary provided by the user upfront, or built incrementally as chapters are translated (like the proofreader's auto-save pattern)?
4. **Multi-chapter novels** — The proofreader processes one file containing multiple chapters. Does cli-translator expect one file per chapter, or does `epub2txt.py` split them?
