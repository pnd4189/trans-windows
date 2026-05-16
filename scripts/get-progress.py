#!/usr/bin/env python3
"""Display translation progress from state.json."""

import json
import sys
from pathlib import Path


def get_progress(state_file: str = '.translator/state.json') -> str:
    """Read state.json and return formatted progress summary."""
    path = Path(state_file)
    if not path.exists():
        return f"Error: State file not found: {state_file}"

    with open(path, 'r', encoding='utf-8') as f:
        state = json.load(f)

    total = state['total_chapters']
    completed = state['chapters_completed']
    failed = state['chapters_failed']
    current = state['current_chapter']
    active = state['active']

    pending = total - completed - failed
    pct = (completed / total * 100) if total > 0 else 0

    status = 'ACTIVE' if active else 'DONE'
    current_title = ''
    if active and current <= total:
        for ch in state['chapters']:
            if ch['id'] == current:
                current_title = ch['title']
                break

    lines = [
        f"Translation Progress [{status}]",
        f"  Total:     {total} chapters",
        f"  Completed: {completed}",
        f"  Failed:    {failed}",
        f"  Pending:   {pending}",
        f"  Progress:  {pct:.1f}%",
    ]

    if active and current <= total:
        lines.append(f"  Current:   Chapter {current} — {current_title}")

    # Show failed chapters
    failed_chapters = [ch for ch in state['chapters'] if ch['status'] == 'failed']
    if failed_chapters:
        ids = ', '.join(str(ch['id']) for ch in failed_chapters)
        lines.append(f"  Failed IDs: {ids}")

    return '\n'.join(lines)


def main():
    state_file = sys.argv[1] if len(sys.argv) > 1 else '.translator/state.json'
    print(get_progress(state_file))


if __name__ == '__main__':
    main()
