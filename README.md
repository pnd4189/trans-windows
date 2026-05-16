# cli-translator

Gemini CLI extension for Chinese-to-Vietnamese novel translation. Chapter-by-chapter with automatic loop control.

## Installation

1. Install Gemini CLI
2. Clone this extension
3. Add to Gemini CLI extensions directory

## Usage

### Translate a Novel (All-in-One)
```
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
User: /cli-tran novel.txt
  ├─ cli-tran.toml → runs init-translation.py + translates chapter 1
  ├─ translate-hook.sh → deny + clearContext → loop to next chapter
  ├─ ... repeat until all chapters done ...
  └─ /resume picks up from last completed chapter
```

## Project Structure

```
├── gemini-extension.json       # Extension manifest
├── GEMINI.md                   # Extension context (loaded every session)
├── commands/
│   ├── cli-tran.toml           # All-in-one: init + translate
│   ├── resume.toml             # Resume interrupted translation
│   └── validate.toml           # Quality validation command
├── hooks/
│   ├── hooks.json              # Hook registration
│   └── translate-hook.sh       # AfterAgent chapter loop hook
├── scripts/
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

## License

MIT
