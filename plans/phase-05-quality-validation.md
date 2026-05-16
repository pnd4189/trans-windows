---
phase: 5
title: "Quality & Validation"
status: pending
priority: P2
effort: "2h"
dependencies: [4]
---

# Phase 5: Quality & Validation

## Overview

Implement translation quality validation: Chinese character residual detection, paragraph count verification, length ratio checks, and glossary consistency validation. This phase ensures translation output meets quality standards.

## Requirements

- Functional: Detect Chinese residual, verify paragraph count, check length ratio, validate glossary
- Non-functional: Validation runs in <5s per chapter, clear error messages

## Architecture

```
scripts/
└── validate-translation.py    ← Quality validation script

Checks:
1. Chinese character residual (should be 0)
2. Paragraph count (should match source ±10%)
3. Length ratio (0.5-2.0x of source length)
4. Glossary consistency (key terms applied)
5. Pronoun leakage (ngươi/ta in narrative = error)
```

## Related Code Files

- Create: `scripts/validate-translation.py`
- Read: `.translator/state.json`
- Read: `translations/chapter_*.txt`

## Implementation Steps

### 5.1 Create scripts/validate-translation.py

```python
#!/usr/bin/env python3
"""Translation quality validation."""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any

# Chinese character detection
CJK_RANGE = r'[一-鿿㐀-䶿]'
CHINESE_PATTERN = re.compile(CJK_RANGE)

# Pronoun leakage in narrative
PRONOUN_LEAKAGE = re.compile(r'(?<!["“])(?:ngươi|ta)(?!["”])')

class ValidationResult:
    """Validation result for a chapter."""
    
    def __init__(self, chapter_id: int):
        self.chapter_id = chapter_id
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def add_error(self, msg: str):
        self.passed = False
        self.errors.append(msg)
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def to_dict(self) -> dict:
        return {
            "chapter_id": self.chapter_id,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings
        }

def count_chinese_chars(text: str) -> int:
    """Count Chinese characters in text."""
    return len(CHINESE_PATTERN.findall(text))

def count_paragraphs(text: str) -> int:
    """Count non-empty paragraphs."""
    return len([p for p in text.split('\n') if p.strip()])

def check_chinese_residual(translated: str) -> List[str]:
    """Check for Chinese characters in translation."""
    errors = []
    chinese_count = count_chinese_chars(translated)
    if chinese_count > 0:
        # Find specific locations
        lines = translated.split('\n')
        for i, line in enumerate(lines, 1):
            chinese = CHINESE_PATTERN.findall(line)
            if chinese:
                errors.append(f"Line {i}: Chinese characters found: {''.join(chinese[:5])}")
                if len(errors) >= 5:  # Limit to 5 examples
                    break
    return errors

def check_paragraph_count(source: str, translated: str, tolerance: float = 0.1) -> List[str]:
    """Check paragraph count matches source."""
    errors = []
    source_count = count_paragraphs(source)
    translated_count = count_paragraphs(translated)
    
    if source_count == 0:
        return errors
    
    diff = abs(source_count - translated_count) / source_count
    if diff > tolerance:
        errors.append(
            f"Paragraph count mismatch: source={source_count}, "
            f"translated={translated_count} ({diff:.0%} difference)"
        )
    return errors

def check_length_ratio(source: str, translated: str, min_ratio: float = 0.5, max_ratio: float = 2.0) -> List[str]:
    """Check translation length is reasonable."""
    errors = []
    source_len = len(source)
    translated_len = len(translated)
    
    if source_len == 0:
        return errors
    
    ratio = translated_len / source_len
    if ratio < min_ratio:
        errors.append(f"Translation too short: {ratio:.2f}x (min {min_ratio}x)")
    elif ratio > max_ratio:
        errors.append(f"Translation too long: {ratio:.2f}x (max {max_ratio}x)")
    return errors

def check_pronoun_leakage(translated: str) -> List[str]:
    """Check for ngươi/ta leakage in narrative."""
    errors = []
    lines = translated.split('\n')
    for i, line in enumerate(lines, 1):
        # Skip dialogue (text in quotes)
        narrative = re.sub(r'["“].*?["”]', '', line)
        leaks = PRONOUN_LEAKAGE.findall(narrative)
        if leaks:
            errors.append(f"Line {i}: Pronoun leakage: {', '.join(leaks[:3])}")
            if len(errors) >= 3:
                break
    return errors

def validate_chapter(source_file: str, translated_file: str, chapter_id: int) -> ValidationResult:
    """Validate a single chapter translation."""
    result = ValidationResult(chapter_id)
    
    # Read files
    try:
        source = Path(source_file).read_text(encoding='utf-8')
        translated = Path(translated_file).read_text(encoding='utf-8')
    except FileNotFoundError as e:
        result.add_error(f"File not found: {e}")
        return result
    
    # Run checks
    chinese_errors = check_chinese_residual(translated)
    for err in chinese_errors:
        result.add_error(f"Chinese residual: {err}")
    
    para_errors = check_paragraph_count(source, translated)
    for err in para_errors:
        result.add_warning(f"Paragraph: {err}")
    
    length_errors = check_length_ratio(source, translated)
    for err in length_errors:
        result.add_warning(f"Length: {err}")
    
    pronoun_errors = check_pronoun_leakage(translated)
    for err in pronoun_errors:
        result.add_error(f"Pronoun: {err}")
    
    return result

def validate_all(state_file: str) -> List[ValidationResult]:
    """Validate all completed chapters."""
    with open(state_file, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    results = []
    for chapter in state['chapters']:
        if chapter['status'] == 'completed' and chapter['output_file']:
            source_path = state['source_file']
            translated_path = Path(state['output_dir']) / chapter['output_file']
            result = validate_chapter(source_path, str(translated_path), chapter['id'])
            results.append(result)
    
    return results

def print_report(results: List[ValidationResult]):
    """Print validation report."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    
    print(f"\n{'='*60}")
    print(f"VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"Total chapters: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"{'='*60}\n")
    
    for result in results:
        if not result.passed:
            print(f"Chapter {result.chapter_id}: FAILED")
            for error in result.errors:
                print(f"  ERROR: {error}")
            for warning in result.warnings:
                print(f"  WARN: {warning}")
    
    if failed == 0:
        print("All chapters passed validation!")

if __name__ == '__main__':
    state_file = sys.argv[1] if len(sys.argv) > 1 else '.translator/state.json'
    results = validate_all(state_file)
    print_report(results)
    sys.exit(0 if all(r.passed for r in results) else 1)
```

### 5.2 Validation Criteria Summary

| Check | Severity | Threshold |
|-------|----------|-----------|
| Chinese character residual | ERROR | 0 characters |
| Pronoun leakage (ngươi/ta) | ERROR | 0 in narrative |
| Paragraph count | WARNING | ±10% of source |
| Length ratio | WARNING | 0.5-2.0x of source |
| Glossary consistency | WARNING | Key terms applied |

### 5.3 Integration with validate.toml

The `/validate` command runs `validate-translation.py` and reports results.

## Success Criteria

- [ ] `validate-translation.py` detects Chinese character residual
- [ ] Paragraph count verification works with ±10% tolerance
- [ ] Length ratio checks work (0.5-2.0x)
- [ ] Pronoun leakage detection works for ngươi/ta in narrative
- [ ] Clear error messages with line numbers
- [ ] Validation report summarizes pass/fail counts
- [ ] Exit code 0 for pass, 1 for fail (CI integration)

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| False positive Chinese detection | MEDIUM | Exclude proper nouns that use Chinese characters |
| Paragraph count off for short chapters | LOW | Use absolute difference for <10 paragraphs |
| Pronoun leakage regex too aggressive | MEDIUM | Test with real dialogue-heavy chapters |

## Security Considerations

- Read-only validation (no file modifications)
- No user input in shell commands

## Next Steps

- Phase 7 uses this: Validation runs as part of testing
