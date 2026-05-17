#!/usr/bin/env python3
"""Recover corrupted state.json by scanning the output directory for completed chapters."""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

def recover_state(state_file: str):
    state_path = Path(state_file)
    if not state_path.exists():
        # If state.json is missing, try .bak
        bak_path = state_path.with_suffix('.json.bak')
        if bak_path.exists():
            print(f"Recovering from backup: {bak_path}")
            state_path.write_text(bak_path.read_text(encoding='utf-8'), encoding='utf-8')
            return
        else:
            print(f"Error: No state file or backup found at {state_file}", file=sys.stderr)
            sys.exit(1)

    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except json.JSONDecodeError:
        # If JSON is corrupted, try .bak
        bak_path = state_path.with_suffix('.json.bak')
        if bak_path.exists():
            print(f"Corrupted state.json. Recovering from backup: {bak_path}")
            state_path.write_text(bak_path.read_text(encoding='utf-8'), encoding='utf-8')
            return
        else:
            print(f"Error: state.json is corrupted and no backup found.", file=sys.stderr)
            sys.exit(1)

    # Scan output directory
    output_dir = Path(state['output_dir'])
    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}", file=sys.stderr)
        return

    print(f"Scanning {output_dir} for completed chapters...")
    completed_count = 0
    for chapter in state['chapters']:
        chapter_id = chapter['id']
        expected_file = f"chapter_{chapter_id:03d}.txt"
        file_path = output_dir / expected_file
        
        if file_path.exists():
            if chapter['status'] != 'completed':
                print(f"Found completed chapter {chapter_id} ({expected_file})")
                chapter['status'] = 'completed'
                chapter['output_file'] = expected_file
                if not chapter['translated_at']:
                    chapter['translated_at'] = datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc).isoformat()
            completed_count += 1
        elif chapter['status'] == 'completed':
             # Missing file but marked as completed
             print(f"Warning: Chapter {chapter_id} marked as completed but {expected_file} is missing. Resetting to pending.")
             chapter['status'] = 'pending'
             chapter['output_file'] = None

    # Update counters
    state['chapters_completed'] = completed_count
    state['chapters_failed'] = sum(1 for ch in state['chapters'] if ch['status'] == 'failed')
    
    # Find next chapter
    next_chapter = 1
    for ch in state['chapters']:
        if ch['status'] == 'pending':
            next_chapter = ch['id']
            break
    else:
        # All chapters done
        next_chapter = state['total_chapters'] + 1
        state['active'] = False

    state['current_chapter'] = next_chapter
    state['last_updated'] = datetime.now(timezone.utc).isoformat()

    # Save recovered state
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    
    print(f"Recovery complete. Completed: {completed_count}/{state['total_chapters']}. Next: {next_chapter}")

if __name__ == '__main__':
    state_file = sys.argv[1] if len(sys.argv) > 1 else '.translator/state.json'
    recover_state(state_file)
