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

# Chapter number extractors — try each in order, first match wins. Returns int or None.
_CN_NUM_MAP = {
    '零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000, '壹': 1, '贰': 2, '叁': 3, '肆': 4, '伍': 5,
    '陆': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10,
}


def _parse_cn_number(s: str) -> int | None:
    """Parse a Chinese numeral string like '一', '十二', '百零五', '二百三十四'."""
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if any(c not in _CN_NUM_MAP for c in s):
        return None
    total = 0
    section = 0
    last = 0
    for ch in s:
        v = _CN_NUM_MAP[ch]
        if v >= 10:
            if last == 0:
                last = 1
            section += last * v
            last = 0
        else:
            last = v
    section += last
    total += section
    return total or None


def extract_chapter_number(title: str) -> int | None:
    """Extract the chapter number embedded in a title.

    Handles: '第011章', '第十二章', 'Chapter 12', 'Chương 12', '12.', '# Chapter 12'.
    Returns None for prologue/epilogue/non-numbered titles so caller can fall back.
    """
    s = title.strip()
    m = re.match(r'^第\s*(\d+)\s*章', s)
    if m:
        return int(m.group(1))
    m = re.match(r'^第\s*([零〇一二两三四五六七八九十百千壹贰叁肆伍陆柒捌玖拾]+)\s*章', s)
    if m:
        n = _parse_cn_number(m.group(1))
        if n is not None:
            return n
    m = re.match(r'^(?:Chapter|Chương)\s+(\d+)', s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.match(r'^(\d+)\.\s', s)
    if m:
        return int(m.group(1))
    m = re.match(r'^#{1,3}\s+(?:Chapter|Chương)?\s*(\d+)', s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None

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
        if line_count == 0:
            return []
        return [{
            'id': 1,
            'display_id': 1,
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

        parsed_id = extract_chapter_number(title)
        chapters.append({
            'id': idx + 1,
            'display_id': parsed_id if parsed_id is not None else idx + 1,
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
