#!/usr/bin/env python3
"""Display translation progress from state.json with ETA, model, and cascade info."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from lib.platform_paths import state_pointer_path as _pointer_path
from lib.io_utils import parse_iso_dt as _parse_iso


def _resolve_state_file(arg: str | None) -> Path | None:
    if arg:
        p = Path(arg)
        if p.exists():
            return p
    pointer = _pointer_path()
    if pointer.exists():
        target = Path(pointer.read_text(encoding="utf-8").strip())
        if target.exists():
            return target
    return None


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def _progress_bar(pct: float, width: int = 30) -> str:
    filled = int(pct / 100 * width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {pct:5.1f}%"


def get_progress(state_file: str | None = None) -> str:
    path = _resolve_state_file(state_file)
    if path is None:
        return f"Error: state file not found: {state_file or '(no pointer)'}"

    state = json.loads(path.read_text(encoding="utf-8"))

    total = state['total_chapters']
    completed = state['chapters_completed']
    failed = state.get('chapters_failed', 0)
    current = state['current_chapter']
    active = state.get('active', False)
    pending = total - completed - failed
    pct = (completed / total * 100) if total > 0 else 0

    status_label = 'ACTIVE' if active else ('DONE' if completed + failed >= total else 'PAUSED')

    # ETA from started_at + completed count
    started_at = _parse_iso(state.get('started_at'))
    eta_str = ""
    if started_at and completed > 0 and active and pending > 0:
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        if elapsed > 0:
            sec_per_chapter = elapsed / completed
            eta_seconds = sec_per_chapter * pending
            eta_str = f"  ETA:       ~{_format_duration(eta_seconds)} ({_format_duration(sec_per_chapter)}/chapter)"

    current_title = ''
    if active and 1 <= current <= total:
        for ch in state['chapters']:
            if ch['id'] == current:
                current_title = ch.get('title', '')
                break

    lines = [
        f"Translation Progress [{status_label}]  {state.get('source_file', '')}",
        f"  {_progress_bar(pct)}",
        f"  Total:     {total} chapters",
        f"  Completed: {completed}",
        f"  Skipped:   {failed}",
        f"  Pending:   {pending}",
    ]
    if eta_str:
        lines.append(eta_str)

    if active and 1 <= current <= total:
        lines.append(f"  Current:   ch.{current} — {current_title}")

    cur_model = state.get('current_model') or state.get('model', {}).get('name') or '(unknown)'
    exhausted = state.get('exhausted_models', [])
    lines.append(f"  Model:     {cur_model}")
    if exhausted:
        lines.append(f"  Exhausted: {', '.join(exhausted)}")
    if state.get('quota_exhausted'):
        lines.append("  Quota:     RPD exhausted — switch /model then re-run /cli-tran")
    rpm = state.get('rpm_consecutive', 0)
    if rpm > 0:
        lines.append(f"  RPM streak: {rpm} (circuit breaker at 10)")

    skipped = [ch for ch in state['chapters'] if ch.get('status') == 'skipped']
    if skipped:
        ids = ', '.join(str(c['id']) for c in skipped[:20])
        more = f" (+{len(skipped) - 20} more)" if len(skipped) > 20 else ""
        lines.append(f"  Skipped IDs: {ids}{more}")

    # CJK residue warnings
    cjk_warn = [c for c in state['chapters'] if (c.get('cjk_bp') or 0) > 100]
    if cjk_warn:
        ids = ', '.join(f"{c['id']}({c['cjk_bp']}bp)" for c in cjk_warn[:10])
        more = f" (+{len(cjk_warn) - 10} more)" if len(cjk_warn) > 10 else ""
        lines.append(f"  CJK residue: {ids}{more}")

    return '\n'.join(lines)


def main():
    state_file = sys.argv[1] if len(sys.argv) > 1 else None
    print(get_progress(state_file))


if __name__ == '__main__':
    main()
