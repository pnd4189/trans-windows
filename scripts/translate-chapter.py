#!/usr/bin/env python3
"""
translate-chapter.py — Translate ONE chapter via agy -p subprocess.

This is the per-iteration unit that the auto-translate.py driver invokes.
It encapsulates prompt construction, subprocess call, response parsing, file
writes.

Args:
  --state <path>     per-novel state.json
  --chapter <id>     1-indexed chapter id (state.chapters[id-1])
  --backend <name>   "agy"
  --model <name>     model name (informational, agy uses its own config)

Exit codes:
  0   chapter translated and files written
  1   transient failure (driver retries)
  2   backend-level failure (quota/permission) -- driver should cascade
  3   fatal config error (missing source/glossary) -- driver should halt

Stdout: JSON object describing the outcome.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from lib.io_utils import atomic_write_json as _atomic_write_json, QUOTA_MARKERS

SUBPROCESS_TIMEOUT_SECS = 600

# Lines that the gemini/agy CLIs or skill-conflict warnings prepend before/after
# the real model output. We strip these as best-effort.
STDOUT_NOISE_PREFIXES = (
    "Loaded cached credentials",
    "Skill conflict detected",
    "YOLO mode is enabled",
    "Warning: ",
    "Ripgrep is not available",
    "Invalid hook event",
    "[INFO]",
    "[WARN]",
    "Data collection is disabled",
    "Tip: ",
)

# Preambles a chat model may add before the actual translation despite the
# "print only the translation" instruction. Stripped case-insensitively from
# the first non-empty line if it matches.
TRANSLATION_PREAMBLES = (
    "đây là bản dịch",
    "đây là phần dịch",
    "bản dịch:",
    "phần dịch:",
    "dịch:",
    "vietnamese translation:",
    "here is the translation",
    "here's the translation",
    "translation:",
    "translated text:",
)


def _clean_env() -> dict:
    """Strip API-key vars to prevent auth confusion in subprocess."""
    from lib.io_utils import API_KEY_STRIP
    env = os.environ.copy()
    for k in API_KEY_STRIP:
        env.pop(k, None)
    return env


def _read_source_chunk(path: Path, start: int, end: int) -> str:
    """Return lines [start, end] inclusive, 1-indexed."""
    from itertools import islice
    if start < 1:
        start = 1
    with path.open("r", encoding="utf-8", errors="replace") as f:
        chunk = list(islice(f, start - 1, end))
    return "".join(chunk)


def _load_glossary(repo_root: Path, genre: str, novel_glossary: Path | None) -> dict:
    _scripts = str(repo_root / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    try:
        from glossary_loader import load_glossary  # type: ignore
    except ImportError:
        import importlib.util
        loader_path = str(repo_root / "scripts" / "glossary-loader.py")
        spec = importlib.util.spec_from_file_location("glossary_loader", loader_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load glossary-loader.py from {loader_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        load_glossary = mod.load_glossary
    glossary_dir = repo_root / "glossary"
    return load_glossary(genre, glossary_dir, novel_glossary)


def _glossary_compact(glossary: dict) -> str:
    """Return a compact glossary snippet the model can apply."""
    keep = {}
    for cat in ("characters", "terms", "places", "pronouns"):
        block = glossary.get(cat) or {}
        if not isinstance(block, dict):
            continue
        compact = {k: v for k, v in block.items() if isinstance(k, str) and isinstance(v, str)}
        if compact:
            keep[cat] = compact
    return json.dumps(keep, ensure_ascii=False, indent=2)


def _build_prompt(meta: dict, source_text: str, glossary_json: str,
                  genre: str, source_lang: str, target_lang: str) -> str:
    chapter_label = meta.get("title") or f"Chapter {meta.get('id')}"
    lang_pair = f"{source_lang}->{target_lang}".upper()
    return f"""You are a professional literary novel translator ({lang_pair}).
This is a fictional novel; translate faithfully regardless of dramatic content.

Translate the chapter below into natural, fluent Vietnamese.
- Preserve paragraph structure.
- Never output Chinese/CJK characters.
- Apply the glossary mappings consistently (first-seen wins).
- Use natural Vietnamese sentence flow, not Chinese-style.

Genre: {genre}

Glossary (apply where matches occur):
{glossary_json}

Chapter title: {chapter_label}

OUTPUT FORMAT:
Print ONLY the Vietnamese translation, paragraphs preserved.
Do NOT include the chapter source.
Do NOT include any English/Chinese commentary, prefaces, or markers.
Do NOT wrap output in code fences.
Start directly with the translated first line.

Source chapter:
{source_text}
"""


def _invoke_backend(backend: str, model: str, prompt: str) -> tuple[int, str, str]:
    agy_path = shutil.which("agy") or "agy"
    cmd = [agy_path, "-p", prompt]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT_SECS, env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        return 124, "", "subprocess timeout"
    except FileNotFoundError as exc:
        return 127, "", f"backend not installed: {exc}"

    return proc.returncode, proc.stdout, proc.stderr


def _strip_preamble(text: str) -> str:
    """Drop one leading preamble line if it matches known chatty openers."""
    lines = text.split("\n", 1)
    if not lines:
        return text
    first = lines[0].strip().lower()
    if not first:
        return text
    for opener in TRANSLATION_PREAMBLES:
        if first.startswith(opener):
            return lines[1] if len(lines) > 1 else ""
    return text


def _clean_stdout(stdout: str) -> str:
    """Drop boilerplate prefix lines / code fences / ANSI noise."""
    # Strip ANSI sequences and gemini's <ctrl##> spinner placeholders
    stdout = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", stdout)
    stdout = re.sub(r"<ctrl\d+>", "", stdout)

    lines = stdout.splitlines()
    # Drop leading noise lines (skill conflicts, YOLO banners, etc).
    while lines and any(lines[0].lstrip().startswith(p) for p in STDOUT_NOISE_PREFIXES):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    text = "\n".join(lines).strip()
    # Strip surrounding code fences if the model added them
    text = re.sub(r"^```[a-zA-Z]*\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    # Strip a single chatty preamble line if present.
    text = _strip_preamble(text)
    return text.strip()


def _looks_like_translation(text: str) -> tuple[bool, str | None]:
    """Reject empty / CJK-leaked output before persisting."""
    if not text or len(text) < 50:
        return False, f"output too short ({len(text)} chars)"
    total = sum(1 for c in text if c.strip())
    if total == 0:
        return False, "no non-whitespace characters"
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    cjk_bp = int(cjk * 10000 / total)
    if cjk_bp > 500:
        return False, f"CJK leak {cjk_bp}bp (>500)"
    return True, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", required=True, type=Path)
    ap.add_argument("--chapter", required=True, type=int)
    ap.add_argument("--backend", required=True, choices=("agy",))
    ap.add_argument("--model", default="")
    args = ap.parse_args()

    started = time.time()
    repo_root = Path(__file__).resolve().parent.parent

    if not args.state.exists():
        print(json.dumps({"status": "fatal", "fail_reason": "state file missing"}))
        return 3

    state = json.loads(args.state.read_text(encoding="utf-8"))
    chapters = state.get("chapters", [])
    idx = args.chapter - 1
    if not 0 <= idx < len(chapters):
        print(json.dumps({"status": "fatal",
                          "fail_reason": f"chapter {args.chapter} out of range"}))
        return 3
    meta = chapters[idx]

    source_file = Path(state["source_file"])
    if not source_file.exists():
        print(json.dumps({"status": "fatal",
                          "fail_reason": f"source file missing: {source_file}"}))
        return 3
    novel_dir = Path(state["novel_cache_dir"])
    output_dir = Path(state["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    entities_dir = novel_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)

    display_id = int(meta.get("display_id") or meta.get("id") or args.chapter)
    output_file = output_dir / f"chapter_{display_id:03d}.txt"
    entities_file = entities_dir / f"chapter_{args.chapter:03d}.json"

    # Build glossary + prompt
    source_text = _read_source_chunk(
        source_file, int(meta["start_line"]), int(meta["end_line"])
    )
    novel_glossary = novel_dir / "novel-glossary.json"
    try:
        glossary = _load_glossary(repo_root, state.get("genre", "fantasy"),
                                  novel_glossary if novel_glossary.exists() else None)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "fatal",
                          "fail_reason": f"glossary load failed: {exc}"}))
        return 3
    glossary_json = _glossary_compact(glossary)
    prompt = _build_prompt(
        meta, source_text, glossary_json,
        state.get("genre", "fantasy"),
        state.get("source_lang", "zh"),
        state.get("target_lang", "vi"),
    )

    rc, stdout, stderr = _invoke_backend(args.backend, args.model, prompt)
    elapsed = round(time.time() - started, 2)
    blob = (stdout or "") + (stderr or "")

    # Detect quota / cascade conditions
    for marker in QUOTA_MARKERS:
        if marker in blob:
            print(json.dumps({
                "status": "cascade",
                "fail_reason": f"backend quota: {marker}",
                "backend": args.backend,
                "model": args.model,
                "elapsed_secs": elapsed,
            }))
            return 2

    if rc != 0:
        print(json.dumps({
            "status": "retry",
            "fail_reason": f"backend exit {rc}: {stderr.strip()[:300]}",
            "backend": args.backend,
            "model": args.model,
            "elapsed_secs": elapsed,
        }))
        return 1

    translation = _clean_stdout(stdout)
    ok, reject_reason = _looks_like_translation(translation)
    if not ok:
        # Dump raw output to a debug file so the driver log can pinpoint the issue.
        debug_dir = novel_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"chapter_{args.chapter:03d}_raw.log"
        debug_path.write_text(
            f"--- STDOUT ({len(stdout)} bytes) ---\n{stdout}\n"
            f"--- STDERR ({len(stderr)} bytes) ---\n{stderr}\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "retry",
            "fail_reason": reject_reason,
            "backend": args.backend,
            "model": args.model,
            "elapsed_secs": elapsed,
            "debug_file": str(debug_path),
        }))
        return 1

    # Persist translation atomically. Entity extraction happens in a separate
    # pass via extract-entities.py (cheaper, can run on completed Vietnamese).
    tmp = output_file.with_suffix(".txt.tmp")
    tmp.write_text(translation + "\n", encoding="utf-8")
    try:
        tmp.replace(output_file)
    except OSError:
        shutil.copy2(tmp, output_file)
        tmp.unlink(missing_ok=True)

    print(json.dumps({
        "status": "ok",
        "output_file": str(output_file),
        "entities_file": str(entities_file),
        "backend": args.backend,
        "model": args.model,
        "elapsed_secs": elapsed,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
