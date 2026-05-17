#!/usr/bin/env python3
"""Initialize translation state for a novel file."""

import json
import os
import sys
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

# Import detect-chapters from same directory
_scripts_dir = str(Path(__file__).parent)
sys.path.insert(0, _scripts_dir)

_spec = importlib.util.spec_from_file_location("detect_chapters", f"{_scripts_dir}/detect-chapters.py")
if _spec is None or _spec.loader is None:
    print(f"Error: Could not load detect-chapters.py from {_scripts_dir}", file=sys.stderr)
    sys.exit(1)

_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
detect_chapters = _mod.detect_chapters


KNOWN_GENRES = {'tienxia', 'wuxia', 'urban', 'historical', 'gamelit', 'horror', 'fantasy'}


def init_translation(source_file: str, output_dir: str | None = None,
                     genre: str = 'fantasy', glossary_path: str = 'glossary/default.json') -> dict:
    """Create .translator/ directory and state.json."""
    source_path = Path(source_file).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    if not source_path.is_file():
        raise ValueError(f"Source path is not a file: {source_file}")

    # Idempotent: if state.json already exists and is active, skip re-init
    translator_dir = source_path.parent / '.translator'
    existing_state_file = translator_dir / 'state.json'
    if existing_state_file.exists():
        try:
            existing = json.loads(existing_state_file.read_text(encoding='utf-8'))
            if existing.get('active') and existing.get('source_file') == str(source_path):
                print(f"Translation already in progress: {existing['total_chapters']} chapters")
                print(f"State file: {existing_state_file}")
                print(f"Output dir: {existing.get('output_dir', 'translations')}")
                print(f"Progress: {existing.get('chapters_completed', 0)}/{existing['total_chapters']} completed")
                return existing
        except (json.JSONDecodeError, KeyError):
            pass  # corrupted state, re-initialize

    if genre not in KNOWN_GENRES:
        print(f"Warning: Unknown genre '{genre}'. Known: {', '.join(sorted(KNOWN_GENRES))}", file=sys.stderr)
        print("Falling back to 'fantasy'", file=sys.stderr)
        genre = 'fantasy'

    # Validate glossary path
    glossary_file = Path(glossary_path)
    if not glossary_file.exists():
        print(f"Warning: Glossary not found at {glossary_path}, using default", file=sys.stderr)
        glossary_path = 'glossary/default.json'

    # Defaults
    if not output_dir:
        output_dir = str(source_path.parent / 'translations')
    output_path = Path(output_dir)

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

    # Detect current model from env
    current_model = os.environ.get('GEMINI_MODEL', '').strip()

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
        'model': {
            'name': current_model,
            'source': 'env' if current_model else 'unknown',
            'selected_at': now,
        },
        'current_model': current_model,
        'exhausted_models': [],
        'quota_exhausted': False,
        'model_switch_history': [],
    }

    # Atomic write
    state_file = translator_dir / 'state.json'
    tmp_file = translator_dir / 'state.json.tmp'
    tmp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp_file.rename(state_file)

    # Write state file path to a known location for the hook to find
    # Uses /tmp so hook can locate it regardless of CWD or source file location
    state_path_file = Path('/tmp/.cli-tran-state-path')
    state_path_file.write_text(str(state_file), encoding='utf-8')

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

    try:
        init_translation(source_file, output_dir, genre, glossary_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
