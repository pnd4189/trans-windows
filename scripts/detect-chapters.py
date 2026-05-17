#!/usr/bin/env python3
"""Detect chapter boundaries in a novel file using regex patterns."""

import json
import re
import sys
from pathlib import Path

CHAPTER_PATTERNS = [
    (r'^第.{1,10}章', 'zh'),       # Chinese: 第一章, 第12章
    (r'^序[章幕]', 'zh'),          # Chinese: 序章, 序幕
    (r'^楔子', 'zh'),              # Chinese: 楔子
    (r'^尾声', 'zh'),              # Chinese: 尾声
    (r'^Chapter\s+\d+', 'en'),      # English: Chapter 1
    (r'^Prologue', 'en'),           # English: Prologue
    (r'^Epilogue', 'en'),           # English: Epilogue
    (r'^Chương\s+\d+', 'vi'),      # Vietnamese: Chương 1
    (r'^Lời\s+nói\s+đầu', 'vi'),   # Vietnamese: Lời nói đầu
    (r'^Lời\s+kết', 'vi'),         # Vietnamese: Lời kết
    (r'^\d+\.\s', 'num'),           # Numbered: 1. Introduction
    (r'^#{1,3}\s+', 'md'),          # Markdown: ## Chapter 1
]

# Warn when chapter exceeds this many lines (risk of context overflow in LLM)
MAX_CHAPTER_LINES = 5000

# Volume markers to exclude
VOLUME_PATTERNS = [
    r'^第.{1,10}卷',
    r'^第.{1,10}册',
    r'^Volume\s+\d+',
    r'^卷',
]


def is_volume_marker(line: str) -> bool:
    return any(re.match(p, line.strip()) for p in VOLUME_PATTERNS)


def detect_chapters(file_path: str) -> list:
    """Detect chapter boundaries in a file.

    Returns list of {id, title, start_line, end_line} dicts.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Find chapter boundaries by iterating line-by-line (efficient for large files)
    boundaries = []
    line_count = 0
    with open(path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            line_count += 1
            stripped = line.strip()
            if not stripped:
                continue
            if is_volume_marker(stripped):
                continue
            for pattern, lang in CHAPTER_PATTERNS:
                if re.match(pattern, stripped):
                    boundaries.append((i + 1, stripped))  # 1-indexed line
                    break

    # No markers found — treat entire file as single chapter
    if not boundaries:
        return [{
            'id': 1,
            'title': '全文',
            'start_line': 1,
            'end_line': line_count,
        }]

    # Build chapter list
    chapters = []
    for idx, (start_line, title) in enumerate(boundaries):
        end_line = boundaries[idx + 1][0] - 1 if idx + 1 < len(boundaries) else line_count
        ch_line_count = end_line - start_line + 1

        if ch_line_count > MAX_CHAPTER_LINES:
            print(f"Warning: Chapter {idx + 1} has {ch_line_count} lines (>{MAX_CHAPTER_LINES}). "
                  f"May cause context overflow during translation.", file=sys.stderr)

        chapters.append({
            'id': idx + 1,
            'title': title,
            'start_line': start_line,
            'end_line': end_line,
        })

    return chapters


def main():
    if len(sys.argv) < 2:
        print("Usage: detect-chapters.py <file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    try:
        chapters = detect_chapters(file_path)
        print(json.dumps(chapters, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
