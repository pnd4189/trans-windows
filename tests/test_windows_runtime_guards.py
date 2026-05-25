"""Tests for Windows runtime safety guards."""

import importlib.util
import json
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _load_script(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_long_windows_prompt_uses_temp_file(monkeypatch):
    mod = _load_script("translate_chapter", "translate-chapter.py")
    monkeypatch.setattr(mod.sys, "platform", "win32")

    command, prompt_file = mod._prompt_command("agy", "x" * (mod.WINDOWS_PROMPT_ARG_LIMIT + 1))

    try:
        assert command[:3] == ["agy", "--add-dir", str(prompt_file.parent)]
        assert command[3] == "-p"
        assert prompt_file.read_text(encoding="utf-8").startswith("xxx")
        assert len(command[-1]) < 1000
    finally:
        prompt_file.unlink(missing_ok=True)


def test_advance_completed_chapter_is_idempotent(tmp_path):
    mod = _load_script("advance_chapter", "advance-chapter.py")
    output_file = tmp_path / "chapter_001.txt"
    output_file.write_text("a" * mod.MIN_OUTPUT_BYTES, encoding="utf-8")
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "active": True,
        "novel_cache_dir": str(tmp_path),
        "output_dir": str(tmp_path),
        "source_file": str(tmp_path / "novel.txt"),
        "chapters_completed": 0,
        "chapters_failed": 0,
        "chapters": [{
            "id": 1,
            "display_id": 1,
            "status": "pending",
            "retry_count": 0,
            "max_retries": 5,
        }],
    }), encoding="utf-8")

    mod.advance(state_file, 1, output_file, None)
    mod.advance(state_file, 1, output_file, None)

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["chapters_completed"] == 1
    assert state["chapters"][0]["status"] == "completed"
