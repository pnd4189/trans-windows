#!/usr/bin/env python3
"""Initialize translation state for a novel file."""

import json
import os
import shutil
import sys
import uuid
import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Import detect-chapters from same directory
_scripts_dir = str(Path(__file__).parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_spec = importlib.util.spec_from_file_location("detect_chapters", str(Path(_scripts_dir) / "detect-chapters.py"))
if _spec is None or _spec.loader is None:
    print(f"Error: Could not load detect-chapters.py from {_scripts_dir}", file=sys.stderr)
    sys.exit(1)

_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
detect_chapters = _mod.detect_chapters

from lib.novel_cache import (
    state_file_for,
    chapter_output_dir,
    entities_dir,
    cleanup_stale_novels,
)
from lib.file_lock import acquire as _acquire_lock, release as _release_lock
from lib.platform_paths import state_pointer_path as _state_pointer_path

MAX_RETRIES_PER_CHAPTER = 5


def _atomic_write_state(state_file: Path, data: dict) -> None:
    """Write state.json atomically under file lock."""
    lock_path = state_file.parent / ".state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = _acquire_lock(str(lock_path), blocking=True)
    try:
        from lib.io_utils import atomic_write_json
        atomic_write_json(state_file, data)
    finally:
        if fd is not None:
            _release_lock(fd)


KNOWN_GENRES = {'tienxia', 'wuxia', 'urban', 'historical', 'gamelit', 'horror', 'fantasy'}


def init_translation(source_file: str, output_dir: str | None = None,
                     genre: str = 'fantasy', glossary_path: str = 'glossary/default.json') -> dict:
    """Create per-novel cache dir and state.json under ~/.cache/cli-tran/novels/<hash>/."""
    source_path = Path(source_file).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    if not source_path.is_file():
        raise ValueError(f"Source path is not a file: {source_file}")

    active_state = _active_pointer_state()
    if active_state and active_state.get('source_file') != str(source_path):
        raise RuntimeError(
            "Another cli-tran translation is active. Run /cli-tran --status or "
            "/cli-tran --resume, or stop it before starting a different source."
        )

    # TTL cleanup: drop completed novels older than 24h before initializing a new one.
    deleted = cleanup_stale_novels()
    if deleted:
        print(f"Cleaned up {len(deleted)} stale novel cache(s).", file=sys.stderr)

    # Resolve per-novel paths (hash-keyed under ~/.cache/cli-tran/novels/<hash>/)
    existing_state_file = state_file_for(source_path)

    # Idempotent: if state.json already exists and is active, skip re-init
    if existing_state_file.exists():
        try:
            existing = json.loads(existing_state_file.read_text(encoding='utf-8'))
            if existing.get('active') and existing.get('source_file') == str(source_path):
                # Cascade reset: clear exhausted_models if last RPD hit was >12h ago
                # (RPD resets at midnight Pacific Time, so 12h covers worst-case offset)
                mutated = False
                last_rpd = existing.get('last_rpd_hit_at') or existing.get('last_updated', '')
                try:
                    last_ts = datetime.fromisoformat(last_rpd.replace('Z', '+00:00'))
                    if (datetime.now(timezone.utc) - last_ts) > timedelta(hours=12):
                        if existing.get('exhausted_models'):
                            existing['exhausted_models'] = []
                            existing['quota_exhausted'] = False
                            mutated = True
                            print("Cleared exhausted_models (last RPD hit >12h ago)", file=sys.stderr)
                except (ValueError, TypeError):
                    pass
                # Reset RPM streak on every resume
                if existing.get('rpm_consecutive', 0) > 0:
                    existing['rpm_consecutive'] = 0
                    mutated = True
                # Rotate session_id every resume so hook gate can validate ownership
                existing['session_id'] = uuid.uuid4().hex[:12]
                existing['last_updated'] = datetime.now(timezone.utc).isoformat()
                mutated = True
                if mutated:
                    _atomic_write_state(existing_state_file, existing)

                print(f"Translation already in progress: {existing['total_chapters']} chapters")
                print(f"State file: {existing_state_file}")
                print(f"Output dir: {existing.get('output_dir', 'translations')}")
                print(f"Progress: {existing.get('chapters_completed', 0)}/{existing['total_chapters']} completed")
                _write_state_pointer(existing_state_file)

                # Idempotent merge recovery: if all chapters done but no merged _vi.txt, run merge
                if existing.get('chapters_completed', 0) + existing.get('chapters_failed', 0) >= existing.get('total_chapters', 0):
                    merged_file = source_path.parent / f"{source_path.stem}_vi.txt"
                    if not merged_file.exists():
                        print("All chapters processed but merged output missing — triggering merge", file=sys.stderr)
                        _trigger_merge(existing_state_file)
                return existing
        except (json.JSONDecodeError, KeyError):
            pass  # corrupted state, re-initialize

    # Auto-detect genre when caller passed default 'fantasy' (signals "no preference")
    if genre == 'fantasy':
        detected = _auto_detect_genre(source_path)
        if detected and detected != 'fantasy':
            print(f"Auto-detected genre: {detected}", file=sys.stderr)
            genre = detected

    if genre not in KNOWN_GENRES:
        print(f"Warning: Unknown genre '{genre}'. Known: {', '.join(sorted(KNOWN_GENRES))}", file=sys.stderr)
        print("Falling back to 'fantasy'", file=sys.stderr)
        genre = 'fantasy'

    # Validate glossary path
    glossary_file = Path(glossary_path)
    if not glossary_file.exists():
        print(f"Warning: Glossary not found at {glossary_path}, using default", file=sys.stderr)
        glossary_path = 'glossary/default.json'

    # Per-chapter output goes into per-novel cache dir; output_dir arg is ignored
    # for the per-chapter scratch (it would leak between runs). Final merged
    # *_vi.txt still lands next to the source file via merge-chapters.py.
    output_path = chapter_output_dir(source_path)
    entities_path = entities_dir(source_path)  # pre-create so AI write_file doesn't fail
    if output_dir:
        print(f"Note: --output-dir is ignored — per-chapter output goes to {output_path}", file=sys.stderr)

    # Detect chapters
    chapters_raw = detect_chapters(str(source_path))
    now = datetime.now(timezone.utc).isoformat()

    # Build chapters array
    chapters = []
    for ch in chapters_raw:
        chapters.append({
            'id': ch['id'],
            'display_id': ch.get('display_id', ch['id']),
            'title': ch['title'],
            'start_line': ch['start_line'],
            'end_line': ch['end_line'],
            'status': 'pending',
            'output_file': None,
            'char_count': None,
            'translated_at': None,
            'retry_count': 0,
            'max_retries': MAX_RETRIES_PER_CHAPTER,
            'skip_reason': None,
        })

    # Determine source language (Chinese novels)
    source_lang = 'zh'

    # Detect current model: env first (Gemini-CLI legacy), then Antigravity settings file.
    current_model = os.environ.get('GEMINI_MODEL', '').strip()
    model_source = 'env' if current_model else 'unknown'
    if not current_model:
        antigravity_settings = Path.home() / '.gemini' / 'antigravity-cli' / 'settings.json'
        if antigravity_settings.exists():
            try:
                data = json.loads(antigravity_settings.read_text(encoding='utf-8'))
                m = data.get('model')
                if isinstance(m, str) and m.strip():
                    current_model = m.strip()
                    model_source = 'antigravity-settings'
            except (json.JSONDecodeError, OSError):
                pass

    state = {
        'active': True,
        'version': 2,
        'session_id': uuid.uuid4().hex[:12],
        'source_file': str(source_path),
        'novel_cache_dir': str(output_path.parent),
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
        'last_rpd_hit_at': None,
        'rpm_consecutive': 0,
        'model': {
            'name': current_model,
            'source': model_source,
            'selected_at': now,
        },
        'current_model': current_model,
        'exhausted_models': [],
        'quota_exhausted': False,
        'model_switch_history': [],
    }

    # Atomic write (under file lock)
    state_file = existing_state_file
    _atomic_write_state(state_file, state)

    _write_state_pointer(state_file)

    print(f"Translation initialized: {len(chapters)} chapters detected")
    print(f"State file: {state_file}")
    print(f"Output dir: {output_path}")
    return state


def _auto_detect_genre(source_path: Path) -> str | None:
    """Sample first ~8KB of source and run keyword-based genre detection."""
    try:
        with open(source_path, encoding='utf-8', errors='ignore') as f:
            sample = f.read(8192)
    except OSError:
        return None
    try:
        _gl_spec = importlib.util.spec_from_file_location(
            "glossary_loader", str(Path(_scripts_dir) / "glossary-loader.py")
        )
        if _gl_spec is None or _gl_spec.loader is None:
            return None
        _gl_mod = importlib.util.module_from_spec(_gl_spec)
        _gl_spec.loader.exec_module(_gl_mod)
        return _gl_mod.detect_genre(sample)
    except Exception:
        return None


def _trigger_merge(state_file: Path) -> None:
    """Run merge-chapters.py to produce final _vi.txt next to source."""
    import subprocess
    merge_script = Path(__file__).parent / "merge-chapters.py"
    if not merge_script.exists():
        return
    try:
        result = subprocess.run(
            [sys.executable, str(merge_script), str(state_file)],
            capture_output=True, text=True, timeout=120,
        )
        if result.stdout:
            print(result.stdout.strip(), file=sys.stderr)
        if result.returncode != 0 and result.stderr:
            print(f"Merge stderr: {result.stderr.strip()}", file=sys.stderr)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"Merge trigger failed: {e}", file=sys.stderr)


def _write_state_pointer(state_file: Path) -> None:
    """Write a single pointer file so the Stop hook can locate state.json.

    Per-PID keying was tried earlier but is unworkable under Antigravity: the
    bash-tool process that runs init-translation.py and the agy process that
    spawns the Stop hook are siblings, so their PPIDs do not match. A single
    unsuffixed pointer is sufficient because only one /cli-tran session runs
    per agy instance.
    """
    _state_pointer_path().write_text(str(state_file), encoding='utf-8')


def _active_pointer_state() -> dict | None:
    pointer = _state_pointer_path()
    if not pointer.exists():
        return None
    try:
        pointed_state = Path(pointer.read_text(encoding='utf-8').strip())
        if not pointed_state.exists():
            return None
        state = json.loads(pointed_state.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return state if state.get('active') else None


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
