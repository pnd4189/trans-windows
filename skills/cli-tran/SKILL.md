---
name: cli-tran
description: Translate a Chinese novel file to Vietnamese. Driven by an external Python loop (auto-translate.py) so it auto-handles long novels (~500 chapters) without manual continue/resume.
---

You orchestrate Chinese→Vietnamese novel translation by delegating to a
self-running Python driver. The driver runs Antigravity CLI (`agy -p`) as
separate subprocesses, one per chapter, until every chapter is `completed` or
`skipped`. The agent's job is to launch the driver and surface its output —
**do not translate chapters yourself in this turn**.

<user-request>
{{args}}
</user-request>

## Architecture (read before doing anything)

```
user types  /cli-tran <flags>
   |
   v
this skill        --(python)-->  scripts/init-translation.py     (init mode only)
   |
   v
scripts/auto-translate.py      (runs as a subprocess in the user's terminal)
   |
   |  loop while pending chapters exist:
   |    scripts/select-cascade.py   -> pick agy backend
   |    scripts/translate-chapter.py -> one subprocess call per chapter
   |    scripts/advance-chapter.py   -> validate + mutate state.json
   v
final summary line to user
```

Per-novel state lives under a platform-dependent cache directory:
- Linux/macOS: `~/.cache/cli-tran/novels/<hash>/state.json`
- Windows: `%LOCALAPPDATA%\cli-tran\novels\<hash>\state.json`

The init script writes the active path to a state pointer file (temp dir);
the driver reads it from there. Driver run log: `<novel_dir>/driver.log`.

## Flag dispatch

Parse `{{args}}` and pick exactly ONE mode. Default = init + run.

- **No flag** or **source file path** — init a new translation, then run the driver.
- `--resume` — driver only (state must already exist).
- `--status` — print progress, do not translate.
- `--redo <spec>` — reset chapters to pending, do not translate.
- `--validate` — quality check, do not translate.

## Mode: DEFAULT (init + run)

1. Run `python __EXT_ROOT__/scripts/init-translation.py <source_file>`
   - Detects chapters, creates per-novel cache dir, writes state.json.
   - Idempotent: re-using a source file resumes the existing state.
2. Run `python __EXT_ROOT__/scripts/auto-translate.py`
   - Streams driver log to stdout. May take many minutes for long novels.
   - Returns a single summary line: `Translation complete|paused: X/Y ...`
3. Surface the summary line to the user. If the driver paused (all
   backends exhausted), tell the user to retry later with `/cli-tran --resume`.

## Mode: --resume

1. Run `python __EXT_ROOT__/scripts/auto-translate.py` directly.
2. Surface its final summary.

## Mode: --status

1. Run `python __EXT_ROOT__/scripts/get-progress.py`.
2. Print the output. Do not invoke the driver.

## Mode: --redo

1. Read state path via:
   `python -c "import sys; sys.path.insert(0, '__EXT_ROOT__/scripts'); from lib.platform_paths import state_pointer_path; print(state_pointer_path())"`
2. Run `python __EXT_ROOT__/scripts/redo-chapters.py <state_path> <spec>`.
3. Tell the user: "Reset done. Run `/cli-tran --resume` to translate the
   reset chapters." Do not invoke the driver in this turn.

## Mode: --validate

1. Read state path via the same method as --redo.
2. Run `python __EXT_ROOT__/scripts/validate-translation.py <state_path>`.
3. Surface the report.

## Driver tuning (env vars)

You normally never set these. Documented for emergencies:
- `CLI_TRAN_MAX_CHAPTERS=600` — safety cap (chapters per driver run).
- `CLI_TRAN_COOLDOWN=2` — seconds between subprocess calls.
- `CLI_TRAN_MAX_RETRIES=5` — retry budget per chapter (also held in state).

## What the driver does and does NOT do

**Does:**
- Iterates over pending chapters in state.json order.
- Picks agy backend each iteration.
- Calls one `agy -p` subprocess per chapter with a bounded prompt
  (glossary + chapter source).
- Writes Vietnamese output to `<novel_dir>/chapter-output/chapter_NNN.txt`.
- Validates output: rejects empty / CJK-leaked translations and retries.
- On backend quota errors, marks that backend as exhausted (5-min negative
  cache) and retries after cooldown.
- Persists state after every chapter — safe to Ctrl+C and resume.

**Does not:**
- Mutate state.json or output files outside of the helper scripts.
- Use the agent's context window for actual translation (so 500-chapter
  novels do not blow the parent session).
- Require any Stop/AfterAgent hook to fire — independent of agy hook gating.

## Important constraints

- Never produce Chinese characters in the Vietnamese output (driver rejects
  output with >5% CJK).
- First-seen wins for glossary terms: once `李明 → Lý Minh` is recorded in
  `<novel_dir>/novel-glossary.json`, never re-translate it.
- Output files are zero-padded to 3 digits using `display_id` (original
  novel chapter number), e.g. `chapter_023.txt` for the 3rd loop chapter
  when the source covers chapters 21-30.
