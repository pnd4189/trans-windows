# cli-translator

Gemini CLI extension for Chinese-to-Vietnamese novel translation. Chapter-by-chapter with automatic loop control.

## Installation

1. Install Gemini CLI
2. Clone this extension
3. Add to Gemini CLI extensions directory

## Usage

### Translate with Auto Model Selection (Recommended)
```bash
./translate novel.txt
./translate novel.epub
```

The supervisor script automatically:
- Selects the strongest available Gemini Pro model
- Handles quota exhaustion (Pro1 → Pro2 → Flash cascade)
- Resumes from last completed chapter on restart

### Translate Directly (Manual Model)
```bash
gemini
/cli-tran novel.txt
/cli-tran novel.epub
```

### Resume Interrupted Translation
```
/resume
```

### Validate Translation Quality
```
/validate
```

## Genre Support

| Genre | Code | Description |
|-------|------|-------------|
| Tiên Hiệp | tienxia | Cultivation novels |
| Kiếm Hiệp | wuxia | Martial arts novels |
| Thành Thị | urban | Urban fantasy |
| Lịch Sử | historical | Historical novels |
| GameLit | gamelit | Game system novels |
| Kinh Dị | horror | Horror novels |
| Fantasy | fantasy | Generic fantasy |

## Architecture

```
User: ./translate novel.txt
  ├─ select-model.py → detect strongest Pro model
  ├─ export GEMINI_MODEL=<model>
  ├─ gemini session starts
  │   ├─ /cli-tran novel.txt → init + translate chapter 1
  │   ├─ translate-hook.sh → deny + clearContext → loop
  │   ├─ ... repeat until all chapters done ...
  │   └─ if quota exhausted → hook stops session
  ├─ supervisor detects quota → cascade to next model
  └─ restart session with new model → resume
```

## Model Selection

The `translate` supervisor script implements automatic model cascade:

| Priority | Model | When Used |
|----------|-------|-----------|
| 1 | Pro (strongest) | Default — auto-detected from CLI history |
| 2 | Pro (2nd strongest) | When Pro1 daily quota exhausted |
| 3 | Flash (strongest) | When both Pro models exhausted |

### Override Model
```bash
GEMINI_MODEL=gemini-2.5-pro ./translate novel.txt
```

### Probe Caching
Model availability is cached in `~/.gemini/cli-translator/model_cache.json` (1h TTL) to avoid repeated 20s probes.

## Project Structure

```
├── translate                   # Supervisor script (auto model selection)
├── gemini-extension.json       # Extension manifest
├── GEMINI.md                   # Extension context (loaded every session)
├── commands/
│   ├── cli-tran.toml           # All-in-one: init + translate
│   ├── resume.toml             # Resume interrupted translation
│   └── validate.toml           # Quality validation command
├── hooks/
│   ├── hooks.json              # Hook registration
│   └── translate-hook.sh       # AfterAgent chapter loop hook + quota detection
├── scripts/
│   ├── lib/
│   │   ├── __init__.py
│   │   └── model_registry.py   # Model discovery + classification
│   ├── select-model.py         # Model selection CLI (Pro → Pro → Flash cascade)
│   ├── detect-chapters.py      # Chapter boundary detection
│   ├── init-translation.py     # Initialize translation state
│   ├── get-progress.py         # Display progress summary
│   ├── glossary-loader.py      # 2-tier glossary merge
│   ├── validate-translation.py # Quality validation
│   └── epub2txt.py             # EPUB to TXT converter
├── glossary/
│   ├── default.json            # Universal terms
│   └── genres/                 # Genre-specific overrides
├── skills/
│   └── novel-translator/
│       └── SKILL.md            # Translation expertise
├── references/
│   ├── translation-principles.md
│   ├── pronoun-guide.md
│   └── common-errors.md
└── tests/                      # Unit tests
```

## Configuration

### Glossary
- `glossary/default.json` — Universal terms for all genres
- `glossary/genres/*.json` — Genre-specific overrides

### Translation Principles
See `references/translation-principles.md`

## Key Design Decisions

1. **No MCP server** — TOML commands + Python scripts + built-in tools
2. **`read_file` not `@{file}`** — 2000-line hard limit blocks novels
3. **One chapter per iteration** — manageable context, clean error recovery
4. **clearContext between chapters** — prevents context overflow
5. **Glossary as HINT** — AI decides contextually, not mechanically
6. **Pro → Pro → Flash cascade** — quality first, Flash as fallback
7. **Supervisor pattern** — automated model switching on quota exhaustion

## License

MIT
