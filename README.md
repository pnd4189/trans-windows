# cli-tran

Antigravity CLI skill for automated Chinese-to-Vietnamese novel translation.
One command translates a full novel (~500 chapters) without manual intervention.

## Requirements

- [Antigravity CLI](https://github.com/google-antigravity/antigravity-cli) (`agy`) — in PATH
- Python 3.10+ — `python` command must work in your terminal

## Installation

```bash
git clone https://github.com/pnd4189/trans-windows
cd trans-windows
python install.py
```

`install.py` copies files to a staging directory, deploys the extension to
`~/.gemini/extensions/cli-tran/`, and registers the plugin via
`agy plugin import gemini`. Restart Antigravity CLI after install.

## Usage

```
/cli-tran /path/to/novel.txt           # init + translate full file
/cli-tran --resume                     # continue an interrupted run
/cli-tran --status                     # show progress
/cli-tran --redo 3,7,11-15             # reset specific chapters to pending
```

The skill runs a Python driver that translates each chapter as an
independent subprocess. It continues until every chapter is `completed` or
`skipped`, then writes a single `*_vi.txt` file next to the source.

## Architecture

```
/cli-tran <file>
  │
  ├─ scripts/init-translation.py     # detect chapters, create state.json
  │
  └─ scripts/auto-translate.py       # Python driver loop — runs to completion
       ├─ scripts/select-cascade.py       # pick agy backend
       ├─ scripts/translate-chapter.py    # one subprocess per chapter
       └─ scripts/advance-chapter.py      # validate output + update state
            └─ scripts/merge-chapters.py  # final merge once all chapters done
```

Per-novel state lives in a platform-dependent cache directory:
- **Linux/macOS**: `~/.cache/cli-tran/novels/<hash>/state.json`
- **Windows**: `%LOCALAPPDATA%\cli-tran\novels\<hash>\state.json`

Safe to Ctrl+C at any point — `/cli-tran --resume` picks up from the last
completed chapter.

## Backend

| Priority | Backend | Model |
|----------|---------|-------|
| 1 | agy subprocess | Configured in Antigravity settings |

The driver checks agy binary availability (no live subprocess probe).
A 5-minute negative cache prevents repeated dead checks; a 1-hour positive
cache short-circuits on the happy path. When the backend is exhausted the
driver halts cleanly and tells you to resume later with `/cli-tran --resume`.

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
├── install.py                  # Cross-platform install + agy plugin registration
├── gemini-extension.json       # Extension manifest (read by Antigravity)
├── plugin.json                 # Plugin metadata
├── GEMINI.md                   # Context file loaded by the skill
├── hooks/
│   └── hooks.json              # Empty — driver architecture needs no hooks
├── skills/
│   └── cli-tran/
│       └── SKILL.md            # Slash-command definition (thin delegator)
├── scripts/
│   ├── auto-translate.py       # Python driver loop
│   ├── translate-chapter.py    # Per-chapter subprocess translator
│   ├── select-cascade.py       # Backend probe + cache logic
│   ├── advance-chapter.py      # Validate output + mutate state.json
│   ├── init-translation.py     # Initialize per-novel cache + state
│   ├── detect-chapters.py      # Chapter boundary detection
│   ├── merge-chapters.py       # Merge chapter files into final output
│   ├── merge-entities.py       # Accumulate glossary entities
│   ├── redo-chapters.py        # Reset chapters to pending
│   ├── get-progress.py         # Progress display
│   ├── recover-state.py        # State recovery utility
│   ├── validate-translation.py # Quality validation
│   ├── epub2txt.py             # EPUB to text conversion
│   └── lib/
│       ├── platform-paths.py   # Cross-platform path helpers
│       ├── file-lock.py        # Cross-platform file locking
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
- **Atomic writes**: chapter files and state.json are written via temp + replace
  to prevent corruption on interrupt.
- **Cross-platform file lock**: `advance-chapter.py` takes an exclusive lock
  before mutating state so parallel invocations cannot corrupt it.

## Windows notes

- **Python in PATH**: ensure `python --version` works in your terminal. If only
  the `py` launcher is available, add Python to your PATH or use `py` instead.
- **Long paths**: if your Windows username is very long and cache paths exceed
  260 characters, either enable the `LongPathsEnabled` registry key or set
  `CLI_TRAN_CACHE_ROOT` to a shorter path.
- **State migration**: cache data from Linux cannot be used on Windows — start
  a fresh translation on the new machine.

## License

MIT
