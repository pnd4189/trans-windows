# cli-tran

Antigravity CLI skill for automated Chinese-to-Vietnamese novel translation.
One command translates a full novel (~500 chapters) without manual intervention.

## Requirements

- [Antigravity CLI](https://github.com/nicepkg/antigravity-cli) (`agy`)
- `gemini` CLI (optional — used as the primary backend; falls back to `agy` when quota exhausted)

## Installation

```bash
git clone https://github.com/pnd4189/cli-translator
cd cli-translator
./install.sh
```

`install.sh` creates a no-space symlink, copies files into
`~/.gemini/extensions/cli-tran/`, and registers the plugin via
`agy plugin import gemini`. Restart Antigravity CLI after install.

## Usage

```
/cli-tran /path/to/novel.txt           # init + translate full file
/cli-tran --resume                     # continue an interrupted run
/cli-tran --status                     # show progress
/cli-tran --redo 3,7,11-15             # reset specific chapters to pending
```

The skill runs an external bash driver that translates each chapter as an
independent subprocess. It continues until every chapter is `completed` or
`skipped`, then writes a single `*_vi.txt` file next to the source.

## Architecture

```
/cli-tran <file>
  │
  ├─ scripts/init-translation.py     # detect chapters, create state.json
  │
  └─ scripts/auto-translate.sh       # driver loop — runs to completion
       ├─ scripts/select-cascade.py       # pick backend (Flash → Claude Opus)
       ├─ scripts/translate-chapter.py    # one subprocess per chapter
       └─ scripts/advance-chapter.py      # validate output + update state
            └─ scripts/merge-chapters.py  # final merge once all chapters done
```

Per-novel state lives at `~/.cache/cli-tran/novels/<hash>/state.json`.
Safe to Ctrl+C at any point — `/cli-tran --resume` picks up from the last
completed chapter.

## Backend cascade

| Priority | Backend | Model |
|----------|---------|-------|
| 1 | `gemini -p` | gemini-2.5-flash |
| 2 | `agy -p` | Claude Opus (configured in Antigravity settings) |

The driver probes each backend before each chapter run. A 5-minute negative
cache prevents repeated dead probes; a 1-hour positive cache skips probes on
the happy path. When all backends are exhausted the driver halts cleanly and
tells you to resume later with `/cli-tran --resume`.

Force a specific backend for testing:
```bash
CLI_TRAN_FORCE_BACKEND=agy /cli-tran /path/to/novel.txt
```

## Genre support

| Genre code | Description |
|------------|-------------|
| `tienxia`  | Cultivation / Tiên Hiệp |
| `wuxia`    | Martial arts / Kiếm Hiệp |
| `urban`    | Urban fantasy / Thành Thị |
| `historical` | Historical / Lịch Sử |
| `gamelit`  | Game-system novels |
| `horror`   | Horror / Kinh Dị |
| `fantasy`  | Generic fantasy (default) |

Genre is auto-detected from the first 8KB of the source file.

## Project structure

```
├── install.sh                  # One-step install + agy plugin registration
├── gemini-extension.json       # Extension manifest (read by Antigravity)
├── plugin.json                 # Plugin metadata
├── GEMINI.md                   # Context file loaded by the skill
├── hooks/
│   └── hooks.json              # Empty — driver architecture needs no hooks
├── skills/
│   └── cli-tran/
│       └── SKILL.md            # Slash-command definition (thin delegator)
├── scripts/
│   ├── auto-translate.sh       # Bash driver loop
│   ├── translate-chapter.py    # Per-chapter subprocess translator
│   ├── select-cascade.py       # Backend probe + cascade logic
│   ├── advance-chapter.py      # Validate output + mutate state.json
│   ├── init-translation.py     # Initialize per-novel cache + state
│   ├── detect-chapters.py      # Chapter boundary detection
│   ├── merge-chapters.py       # Merge chapter files into final output
│   ├── merge-entities.py       # Accumulate glossary entities
│   ├── redo-chapters.py        # Reset chapters to pending
│   ├── get-progress.py         # Progress display
│   ├── recover-state.py        # State recovery utility
│   ├── validate-translation.py # Quality validation
│   └── lib/
│       └── novel_cache.py      # Cache directory helpers
├── glossary/
│   ├── default.json            # Universal terms
│   └── genres/                 # Genre-specific overrides
└── references/                 # Translation principles + pronoun guide
```

## Quality controls

- **CJK leak guard**: output with >5% Chinese characters is rejected and
  retried automatically (5 retries per chapter before skip).
- **First-seen-wins glossary**: once `李明 → Lý Minh` is recorded in
  `novel-glossary.json` it is applied consistently to all subsequent chapters.
- **Atomic writes**: chapter files and state.json are written via temp + rename
  to prevent corruption on interrupt.
- **flock guard**: `advance-chapter.py` takes an exclusive lock before
  mutating state so parallel invocations cannot corrupt it.

## License

MIT
