#!/usr/bin/env python3
"""Initialize translation state for a novel file."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import detect-chapters from same directory
sys.path.insert(0, str(Path(__file__).parent))
from detect_chapters import detect_chapters


def init_translation(source_file: str, output_dir: str = None,
                     genre: str = 'fantasy', glossary_path: str = 'glossary/default.json') -> dict:
    """Create .translator/ directory and state.json."""
    source_path = Path(source_file).resolve()
    if not source_path.exists():
        print(f"Error: Source file not found: {source_file}", file=sys.stderr)
        sys.exit(1)

    # Defaults
    if not output_dir:
        output_dir = str(source_path.parent / 'translations')
    output_path = Path(output_dir)
    translator_dir = source_path.parent / '.translator'

    # Create directories
    translator_dir.mkdir(exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    # Detect chapters
    chapters_raw = detect_chapters(str(source_path))
    now = datetime.now(timezone.utc).isoformat()

    # Build chapters array
    chapters = []
    for ch in chapters_raw:
        chapters.append({
            'id': ch['id'],
            'title': ch['title'],
            'start_line': ch['start_line'],
            'end_line': ch['end_line'],
            'status': 'pending',
            'output_file': None,
            'char_count': None,
            'translated_at': None,
        })

    # Determine source language (Chinese novels)
    source_lang = 'zh'

    state = {
        'active': True,
        'version': 1,
        'source_file': str(source_path),
        'output_dir': str(output_path),
        'source_lang': source_lang,
        'target_lang': 'vi',
        'genre': genre,
        'glossary_path': glossary_path,
        'total_chapters': len(chapters),
        'current_chapter': 1,
        'chapters': chapters,
        'chapters_completed': 0,
        'chapters_failed': 0,
        'started_at': now,
        'last_updated': now,
    }

    # Atomic write
    state_file = translator_dir / 'state.json'
    tmp_file = translator_dir / 'state.json.tmp'
    tmp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp_file.rename(state_file)

    print(f"Translation initialized: {len(chapters)} chapters detected")
    print(f"State file: {state_file}")
    print(f"Output dir: {output_dir}")
    return state


def main():
    if len(sys.argv) < 2:
        print("Usage: init-translation.py <source_file> [output_dir] [genre] [glossary_path]", file=sys.stderr)
        sys.exit(1)

    source_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    genre = sys.argv[3] if len(sys.argv) > 3 else 'fantasy'
    glossary_path = sys.argv[4] if len(sys.argv) > 4 else 'glossary/default.json'

    init_translation(source_file, output_dir, genre, glossary_path)


if __name__ == '__main__':
    main()
