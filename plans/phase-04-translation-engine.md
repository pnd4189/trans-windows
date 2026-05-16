---
phase: 4
title: "Translation Engine"
status: pending
priority: P1
effort: "4h"
dependencies: [1, 2, 3]
---

# Phase 4: Translation Engine

## Overview

Build the core translation engine: SKILL.md translation expertise, translation principles, and the `/resume` and `/validate` TOML commands. Uses direct prompt approach (no brief/response files). This phase brings together state management (Phase 1), hook loop (Phase 2), and glossary (Phase 3) into a working translation pipeline.

## Requirements

- Functional: Model translates chapters correctly, glossary applied as hints, bilingual output supported
- Non-functional: Translation quality consistent across chapters, context cleared between chapters

## Architecture

```
commands/
├── translate.toml             ← Main translation command (Phase 1)
├── resume.toml                ← Resume interrupted translation
└── validate.toml              ← Quality validation pass

skills/
└── novel-translator/
    └── SKILL.md               ← Translation expertise + glossary rules

references/
├── translation-principles.md  ← P1-P4 guidelines
├── pronoun-guide.md           ← Genre-specific pronouns
└── common-errors.md           ← Error cases to avoid

Approach: Direct prompt (no brief/response files).
translate.toml has all instructions inline. Model reads state.json via read_file.
```

### Translation Flow (Per Chapter)

```
1. Model reads state.json → find current chapter (start_line, end_line)
2. Model reads glossary via read_file
3. Model reads chapter N via read_file(start_line, end_line)
4. Model reads previous chapter output for context continuity (optional)
5. Model translates following SKILL.md principles (in GEMINI.md)
6. Model writes output to translations/chapter_NNN.txt
7. Model updates state.json (status: "completed")
8. Model outputs "CHAPTER_TRANSLATION_COMPLETE" marker in response
9. AfterAgent hook → detects marker → advance to next chapter
```

### Direct Prompt Approach

No brief/response files. translate.toml contains all instructions inline:
- Translation principles (P1-P4)
- Glossary usage (read via read_file, treat as HINT)
- Output format (one file per chapter)
- Completion marker (CHAPTER_TRANSLATION_COMPLETE)

## Related Code Files

- Create: `commands/resume.toml`
- Create: `commands/validate.toml`
- Create: `skills/novel-translator/SKILL.md`
- Create: `references/translation-principles.md`
- Create: `references/pronoun-guide.md`
- Create: `references/common-errors.md`

## Implementation Steps

### 4.1 Create skills/novel-translator/SKILL.md

Translation expertise document (auto-activated by Gemini CLI):

```markdown
---
name: novel-translator
version: 1.0.0
description: Chinese-to-Vietnamese novel translation with genre support
allowed-tools:
  - Read
  - Write
  - Bash
---

# Novel Translator

Professional Chinese-to-Vietnamese web novel translator.

## Translation Principles

### P1: Meaning Preservation
- Translate meaning, not words
- Preserve intent, emotion, and nuance
- Cultural adaptation over literal translation

### P2: Natural Vietnamese
- Use natural Vietnamese sentence structure
- Avoid Chinese-style Vietnamese (Chủ ngữ-Vị ngữ-Phụ ngữ)
- Read aloud test: if it sounds awkward, rewrite

### P3: Character Voice
- Each character has distinct speech patterns
- Formal/informal matches character personality
- Dialogue should feel like natural speech

### P4: Consistency
- Use glossary terms consistently
- Character names never change
- World-building terms stay consistent

## Genre Handling

### Tiên Hiệp (tienxia)
- Tone: Formal, ancient, spiritual
- Pronouns: hắn (male), nàng (female)
- Terms: tu luyện, cảnh giới, Kim Đan

### Kiếm Hiệp (wuxia)
- Tone: Action-packed, honor-focused
- Pronouns: y (male), nàng (female)
- Terms: kiếm pháp, nội công, khinh công

### Urban (urban)
- Tone: Modern, casual
- Pronouns: anh (male), cô ấy (female)
- Terms: Keep modern terms natural

## Glossary Usage

Glossary is HINT, not hard rule:
- Use as starting point for term translation
- Override when context demands
- Explain overrides in notes

## Common Errors to Avoid

1. **Pronoun leakage**: Don't use ngươi/ta in narrative (dialogue only)
2. **Compound corruption**: bạn X → bạn X (NOT ngươi X)
3. **Chinese residual**: No Chinese characters in output
4. **Register mismatch**: Formal text with casual pronouns
5. **Name inconsistency**: Same character, different names
```

### 4.2 Create references/translation-principles.md

Detailed P1-P4 guidelines with examples.

### 4.3 Create references/pronoun-guide.md

Genre-specific pronoun usage guide:
- When to use hắn vs y vs anh
- When to use nàng vs cô ấy
- Dialogue vs narrative pronouns
- Formal vs informal registers

### 4.4 Create references/common-errors.md

27 verified error cases from proofreader research:
- Pronoun leakage patterns
- Compound noun corruption
- Chinese character residual
- Register mismatches
- Name inconsistencies

### 4.5 Create commands/resume.toml

Resume command picks up from last completed chapter:

```
Resume the interrupted translation.

1. Read .translator/state.json
2. Find the first chapter with status != "completed"
3. Set current_chapter to that chapter
4. Continue translation from that chapter
5. Follow the same process as /translate

State file: {{args}}/.translator/state.json
```

### 4.6 Create commands/validate.toml

Validation command checks translation quality:

```
Validate the translation quality.

1. Read .translator/state.json
2. For each completed chapter:
   a. Read the translated file
   b. Check for Chinese characters (should be none)
   c. Check paragraph count matches source
   d. Check length ratio (0.5-2.0x of source)
   e. Check glossary terms applied
3. Report any issues found

State file: {{args}}/.translator/state.json
```

### 4.7 Integrate All Components

The translate.toml command now has full pipeline:
1. Read state.json (Phase 1)
2. Load glossary via glossary-loader.py (Phase 3)
3. Read chapter via read_file (Phase 1)
4. Translate using SKILL.md principles (Phase 4)
5. Write output (Phase 1)
6. Hook advances to next chapter (Phase 2)

## Success Criteria

- [ ] `SKILL.md` provides clear translation instructions
- [ ] `translation-principles.md` covers P1-P4 with examples
- [ ] `pronoun-guide.md` handles all 7 genres
- [ ] `common-errors.md` lists verified error cases
- [ ] `/resume` command picks up from last completed chapter
- [ ] `/validate` command checks translation quality
- [ ] Full pipeline works: state → glossary → chapter → translate → output → marker → hook → next

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| clearContext loses SKILL.md context | HIGH | SKILL.md loaded by Gemini CLI automatically, survives clearContext |
| Translation quality inconsistent | MEDIUM | Clear principles in SKILL.md, glossary hints |
| Brief protocol too complex | LOW | Simplified to 1 brief per chapter |
| Resume fails on corrupted state | MEDIUM | Validate state.json before resume |

## Security Considerations

- No user input in shell commands
- Translation output is local only
- Glossary files are read-only

## Next Steps

- Phase 5 depends on this: Validation checks translation output
- Phase 7 depends on this: Testing with real novels
