# CLI Translator — Extension Context

Chinese-to-Vietnamese web novel translator. Chapter-by-chapter with automatic loop control.

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

## Genre System

| Genre | Code | Tone | Pronouns |
|-------|------|------|----------|
| Tiên Hiệp | tienxia | Formal, ancient, spiritual | hắn/nàng |
| Kiếm Hiệp | wuxia | Action-packed, honor-focused | y/nàng |
| Thành Thị | urban | Modern, casual | anh/cô ấy |
| Lịch Sử | historical | Formal, period-accurate | hắn/nàng |
| GameLit | gamelit | Technical, progression-focused | hắn/nàng |
| Kinh Dị | horror | Dark, eerie | hắn/nàng |
| Fantasy | fantasy | Epic, diverse | hắn/nàng |

## Glossary Usage

Glossary is HINT, not hard rule:
- Use as starting point for term translation
- Override when context demands it
- Explain overrides in translation notes

## Output Format

- One file per chapter: `chapter_NNN.txt`
- Chapter number zero-padded to 3 digits
- UTF-8 encoding
- No Chinese characters in output

## Completion Markers

After translating a chapter, output EXACTLY one of:
- `CHAPTER_TRANSLATION_COMPLETE` — success
- `CHAPTER_TRANSLATION_FAILED` — failure

These markers control the automated loop.

## Tool Usage

- Use `read_file` tool (NOT `@{file}`) — `@{file}` has 2000-line limit
- Use `write_file` for output (overwrite mode)
- Use `read_file(start_line, end_line)` for chapter extraction
