#!/usr/bin/env python3
"""Translation quality validation: Chinese residual, paragraph count, length ratio, pronoun leakage."""

import json
import re
import sys
from pathlib import Path
from typing import List

CHINESE_PATTERN = re.compile(r'[一-鿿㐀-䶿]')
PRONOUN_LEAKAGE = re.compile(r'(?<![""“])(?:ngươi|ta)(?![""”])')


class ValidationResult:
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


def count_chinese_chars(text: str) -> int:
    return len(CHINESE_PATTERN.findall(text))


def count_paragraphs(text: str) -> int:
    return len([p for p in text.split('\n') if p.strip()])


def check_chinese_residual(translated: str) -> List[str]:
    errors = []
    lines = translated.split('\n')
    for i, line in enumerate(lines, 1):
        chinese = CHINESE_PATTERN.findall(line)
        if chinese:
            errors.append(f"Line {i}: Chinese chars: {''.join(chinese[:5])}")
            if len(errors) >= 5:
                break
    return errors


def check_paragraph_count(source: str, translated: str, tolerance: float = 0.1) -> List[str]:
    errors = []
    src_count = count_paragraphs(source)
    tr_count = count_paragraphs(translated)
    if src_count == 0:
        return errors
    diff = abs(src_count - tr_count) / src_count
    if diff > tolerance:
        errors.append(f"Paragraph mismatch: source={src_count}, translated={tr_count} ({diff:.0%} diff)")
    return errors


def check_length_ratio(source: str, translated: str, min_r: float = 0.5, max_r: float = 2.0) -> List[str]:
    errors = []
    src_len = len(source)
    if src_len == 0:
        return errors
    ratio = len(translated) / src_len
    if ratio < min_r:
        errors.append(f"Too short: {ratio:.2f}x (min {min_r}x)")
    elif ratio > max_r:
        errors.append(f"Too long: {ratio:.2f}x (max {max_r}x)")
    return errors


def check_pronoun_leakage(translated: str) -> List[str]:
    errors = []
    lines = translated.split('\n')
    for i, line in enumerate(lines, 1):
        narrative = re.sub(r'[""“].*?[""”]', '', line)
        leaks = PRONOUN_LEAKAGE.findall(narrative)
        if leaks:
            errors.append(f"Line {i}: Pronoun leakage: {', '.join(leaks[:3])}")
            if len(errors) >= 3:
                break
    return errors


def validate_chapter(source_file: str, translated_file: str, chapter_id: int) -> ValidationResult:
    result = ValidationResult(chapter_id)
    try:
        source = Path(source_file).read_text(encoding='utf-8')
        translated = Path(translated_file).read_text(encoding='utf-8')
    except FileNotFoundError as e:
        result.add_error(f"File not found: {e}")
        return result

    for err in check_chinese_residual(translated):
        result.add_error(f"Chinese residual: {err}")
    for err in check_paragraph_count(source, translated):
        result.add_warning(f"Paragraph: {err}")
    for err in check_length_ratio(source, translated):
        result.add_warning(f"Length: {err}")
    for err in check_pronoun_leakage(translated):
        result.add_error(f"Pronoun: {err}")
    return result


def validate_all(state_file: str) -> List[ValidationResult]:
    with open(state_file, 'r', encoding='utf-8') as f:
        state = json.load(f)

    results = []
    for ch in state['chapters']:
        if ch['status'] == 'completed' and ch['output_file']:
            src = state['source_file']
            tr = str(Path(state['output_dir']) / ch['output_file'])
            results.append(validate_chapter(src, tr, ch['id']))
    return results


def print_report(results: List[ValidationResult]):
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print(f"\n{'='*60}")
    print("VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print(f"{'='*60}\n")

    for r in results:
        if not r.passed:
            print(f"Chapter {r.chapter_id}: FAILED")
            for e in r.errors:
                print(f"  ERROR: {e}")
            for w in r.warnings:
                print(f"  WARN: {w}")

    if failed == 0:
        print("All chapters passed validation!")


def main():
    state_file = sys.argv[1] if len(sys.argv) > 1 else '.translator/state.json'
    results = validate_all(state_file)
    print_report(results)
    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == '__main__':
    main()
