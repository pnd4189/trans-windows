---
phase: 7
title: "Testing + Polish"
status: pending
priority: P1
effort: "4h"
dependencies: [4, 5]
---

# Phase 7: Testing + Polish

## Overview

End-to-end testing with a real Chinese novel (50+ chapters), error handling hardening, hook reliability testing at scale, and README documentation. This phase validates the entire pipeline works in production conditions.

## Requirements

- Functional: Translate a real 50+ chapter novel end-to-end, resume works, validate catches errors
- Non-functional: Hook reliable at 50+ iterations, clearContext doesn't degrade quality, error messages clear

## Architecture

```
Testing scope:
1. Unit tests for each script
2. Integration test: full pipeline with sample novel
3. Stress test: 50+ chapter loop
4. Edge cases: empty chapters, very long chapters, missing glossary
5. Resume test: kill mid-translation, resume
6. Quality test: validate output of real translation
```

## Related Code Files

- Test: All scripts from Phases 1-6
- Create: `README.md`

## Implementation Steps

### 7.1 Unit Tests

**detect-chapters.py**
- Test Chinese chapter markers: 第一章, 第12章, 第一百零三章
- Test English markers: Chapter 1, Chapter XII
- Test Vietnamese markers: Chương 1
- Test mixed markers in same file
- Test no markers (fallback to paragraph count)
- Test volume markers (卷/册) are excluded

**init-translation.py**
- Test state.json creation with correct schema
- Test chapter array has correct start_line/end_line
- Test output directory creation
- Test genre parameter stored correctly

**glossary-loader.py**
- Test deep-merge: terms override
- Test deep-merge: protected_phrases append
- Test deep-merge: compound_context union
- Test deep-merge: pronoun_rules merge by `from`
- Test missing genre file (fallback to default only)

**validate-translation.py**
- Test Chinese residual detection
- Test paragraph count check (pass/fail)
- Test length ratio check (too short/long)
- Test pronoun leakage detection
- Test clean translation passes all checks

**epub2txt.py**
- Test EPUB extraction
- Test chapter structure preservation
- Test HTML text extraction
- Test missing TOC handling

### 7.2 Integration Test: Sample Novel

Use a short Chinese novel (5-10 chapters) for integration testing:

```
1. Create sample novel with known chapters
2. Run /translate sample.txt --genre tienxia
3. Verify:
   - state.json created correctly
   - Each chapter translated
   - Output files exist
   - Hook loop completed
   - No Chinese residual
   - Glossary terms applied
4. Run /validate
5. Verify all checks pass
```

### 7.3 Stress Test: 50+ Chapter Loop

Test hook reliability at scale:

```
1. Create synthetic novel with 50+ chapters
2. Run /translate
3. Monitor for:
   - Hook fires after each chapter
   - clearContext works (no context overflow)
   - State.json updates correctly each iteration
   - Progress display accurate
   - No hook timeout
4. Verify all 50 chapters completed
5. Check token usage (~200K expected)
```

### 7.4 clearContext + GEMINI.md Test (CRITICAL)

Test whether clearContext also clears GEMINI.md context:
```
1. Start translation of 3-chapter novel
2. After chapter 1, check if model still has GEMINI.md instructions
3. If GEMINI.md is cleared → add BeforeAgent hook to re-inject context
4. If GEMINI.md survives → no action needed
```

### 7.5 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Empty chapter (< 100 chars) | Skip, mark as skipped |
| Very long chapter (>20K chars) | Translate in single pass |
| Missing glossary file | Use default.json only |
| Corrupted state.json | Error, suggest manual recovery |
| No chapter markers | Treat as single chapter |
| Mixed language chapter | Translate Chinese, preserve other |
| DRM-protected EPUB | Error: cannot process |
| CHAPTER_TRANSLATION_COMPLETE not output | Hook marks as failed, advances to next |

### 7.6 Resume Test

```
1. Start translation of 10-chapter novel
2. Kill process after 3 chapters (Ctrl+C)
3. Verify state.json shows chapters 1-3 completed
4. Run /resume
5. Verify resumes from chapter 4
6. Verify chapters 4-10 translated correctly
```

### 7.7 Quality Test

Test with real novel, validate output:

```
1. Translate 10 chapters of real Chinese novel
2. Run /validate
3. Manual review of 3 chapters:
   - Meaning preserved?
   - Vietnamese natural?
   - Glossary terms consistent?
   - Pronouns correct for genre?
4. Document any quality issues found
```

### 7.8 Error Handling Hardening

Add error handling to all scripts:

- **File not found**: Clear error message with path
- **Permission denied**: Suggest chmod or sudo
- **JSON parse error**: Suggest manual recovery
- **Hook crash**: Graceful stop, state preserved
- **Disk full**: Catch write errors, save state

### 7.9 Create README.md

```markdown
# cli-translator

Gemini CLI extension for Chinese-to-Vietnamese novel translation.

## Installation

1. Install Gemini CLI
2. Clone this extension
3. Add to Gemini CLI extensions

## Usage

### Translate a Novel
```
/translate novel.txt --genre tienxia --bilingual
```

### Resume Interrupted Translation
```
/resume
```

### Validate Translation Quality
```
/validate
```

### Translate from EPUB
```
/translate novel.epub --genre tienxia
```

## Genre Support

| Genre | Code | Description |
|-------|------|-------------|
| Tiên Hiệp | tienxia | Cultivation novels |
| Kiếm Hiệp | wuxia | Martial arts novels |
| Thành Thị | urban | Urban fantasy |
| Lịch Sử | historical | Historical novels |
| GameLit | gamelit | Game system novels |
| Kinh Dị | horror | Horror novels |
| Fantasy | fantasy | Generic fantasy |

## Configuration

### Glossary
- `glossary/default.json` — Universal terms
- `glossary/genres/*.json` — Genre-specific overrides

### Translation Principles
See `references/translation-principles.md`

## Architecture

- TOML commands for Gemini CLI
- Python scripts for preprocessing
- AfterAgent hook for chapter loop
- State.json for progress tracking

## License

MIT
```

## Success Criteria

- [ ] All unit tests pass
- [ ] Integration test: 5-chapter novel translated end-to-end
- [ ] Stress test: 50-chapter loop completes without errors
- [ ] Resume test: picks up from last completed chapter
- [ ] Quality test: manual review passes for sample chapters
- [ ] Edge cases handled gracefully with clear error messages
- [ ] README.md complete with usage instructions
- [ ] No Chinese residual in output
- [ ] Glossary terms applied consistently
- [ ] Hook reliable at 50+ iterations

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Hook fails at 50+ iterations | HIGH | Test early, fallback to batch mode if needed |
| clearContext degrades quality | HIGH | Compare quality at chapter 1 vs chapter 50 |
| Real novel has edge cases | MEDIUM | Test with multiple novels |
| Gemini CLI version changes | MEDIUM | Pin tested version in README |

## Security Considerations

- No secrets in test data
- Test files are local only
- No network calls during testing

## Next Steps

- After this phase, extension is production-ready
- Consider adding to Gemini CLI extensions registry
