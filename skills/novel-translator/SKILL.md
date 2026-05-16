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

### Thành Thị (urban)
- Tone: Modern, casual
- Pronouns: anh (male), cô ấy (female)
- Terms: Keep modern terms natural

### Lịch Sử (historical)
- Tone: Formal, period-accurate
- Pronouns: hắn (male), nàng (female)

### GameLit (gamelit)
- Tone: Technical, progression-focused
- Pronouns: hắn (male), nàng (female)

### Kinh Dị (horror)
- Tone: Dark, eerie, atmosphere-driven
- Pronouns: hắn (male), nàng (female)

### Fantasy (fantasy)
- Tone: Epic, diverse
- Pronouns: hắn (male), nàng (female)

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
