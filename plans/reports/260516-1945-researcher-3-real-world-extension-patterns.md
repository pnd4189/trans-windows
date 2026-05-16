# Research: Real-World Gemini CLI Extension Patterns for File Processing

**Researcher:** researcher-3
**Date:** 2026-05-16
**Status:** Complete

---

## Executive Summary

Analyzed 20+ real Gemini CLI extensions, the full official extension API docs, and the immersive-translate architecture. **Key finding: the most successful file-processing extensions use ZERO MCP servers.** They rely on TOML commands + shell scripts + GEMINI.md context. The brainstorm's 9-MCP-tool architecture is massively over-engineered. A TOML+shell+skill architecture is both simpler and proven at scale.

**Recommendation: Pure TOML + Shell Scripts + Agent Skill. No MCP needed.**

---

## Case Studies: Real Extensions

### 1. Conductor (3,559 stars) — Complex Multi-File Workflow

- **Architecture:** TOML commands + GEMINI.md + skills. ZERO MCP servers.
- **Manifest:** Only `name`, `version`, `contextFileName`, `plan.directory`. No `mcpServers`.
- **Commands:** 6 TOML files (`setup`, `newTrack`, `implement`, `review`, `revert`, `status`)
- **Pattern:** Each TOML command is a detailed prompt (~200+ lines) that instructs the model to use built-in tools (`read_file`, `write_file`, `replace`, `run_shell_command`, `ask_user`) to orchestrate complex multi-file workflows.
- **Key insight:** The `implement.toml` command is ~300 lines of structured protocol. It reads project specs, creates plans, executes tasks, updates status files — all using Gemini's built-in file tools. No MCP needed for any of this.
- **Complexity handled:** Project scaffolding, multi-track planning, file creation/editing, git commits, user interaction via `ask_user`.

### 2. Ralph (318 stars) — Persistent Loop with State Management

- **Architecture:** TOML command + shell scripts + hooks. ZERO MCP servers.
- **Manifest:** Only `name` and `version`.
- **Mechanism:**
  1. `loop.toml` runs `setup.sh` to create `.gemini/ralph/state.json` with iteration tracking
  2. `AfterAgent` hook (`stop-hook.sh`) fires after each agent turn
  3. Hook reads state, increments iteration, and either continues loop (`decision: "deny"` + `clearContext: true`) or stops
  4. Supports `--max-iterations` and `--completion-promise` flags
- **Key insight:** State management via shell scripts + JSON files. Loop control via hooks. The model reads state files to know where it is. This is the pattern for any "process N items with resume" workflow.
- **Relevance to translator:** This exact pattern (state.json + AfterAgent hook) could handle chapter-by-chapter translation with progress tracking and resume.

### 3. Code Review (507 stars) — Pure Context Extension

- **Architecture:** GEMINI.md context only. ZERO commands, ZERO MCP servers.
- **Manifest:** Only `name`, `version`, `contextFileName`.
- **Pattern:** The entire extension is a GEMINI.md file that gives the model expertise in code review. The model uses its built-in tools to read diffs, analyze code, and write reviews.
- **Key insight:** For knowledge-heavy tasks, a well-crafted context file may be sufficient. The model already has file reading/writing capabilities.

### 4. ru-text (extension) — 1,044 Rules for Text Quality

- **Architecture:** Pure context file with rules. ZERO MCP servers.
- **Pattern:** Loads ~1,044 typography/editorial rules into context. Model applies rules to text using built-in tools.
- **Relevance:** Similar pattern to a translation glossary — load domain rules into context, let the model apply them.

### 5. Packet Buddy — Hybrid RAG + MCP

- **Architecture:** MCP server (bash script) + GEMINI.md + TOML commands.
- **Pattern:** MCP server wraps a Python script for packet capture analysis (RAG). Custom commands provide slash shortcuts.
- **Why MCP here:** Packet capture parsing requires specialized binary format handling (pcap files) that can't be done with built-in tools. Legitimate use case for MCP.
- **Contrast:** TXT file chapter detection and glossary lookup do NOT require MCP — they're simple text operations.

### 6. Security Extension (777 stars) — MCP for External Tools

- **Architecture:** 2 MCP servers (custom Node.js + osv-scanner binary).
- **Why MCP:** Integrates external security scanning tools (OSV vulnerability database). These are genuine external services.
- **Contrast:** A translator needs no external services beyond Gemini itself.

### 7. SRT Subtitle Translator (browser tool) — Non-CLI Translation Pattern

- **Architecture:** Browser app + CLIProxyAPI + validation engine.
- **Translation pattern:**
  - "Translate" mode: single-pass for small files (~800-900 subtitle indexes)
  - "Batch Translate": chunks for larger files to avoid context cutoffs
  - "Standalone Validate": post-translation validation pass
  - Validation: timestamp sync, script/character validation, auto-correction
- **Key insight:** Even a dedicated translation tool uses batch/chunk approach for large files, validates output, and auto-corrects. All doable with Gemini CLI built-in tools.
- **Progress tracking:** Browser tab title shows status. In Gemini CLI, state files serve this purpose.

---

## Architecture Comparison

| Dimension | (A) Pure TOML Prompt | (B) TOML + MCP | (C) TOML + Shell Scripts |
|---|---|---|---|
| **Complexity** | Very Low | High (Node.js server, deps, build) | Low (bash + jq) |
| **Setup** | Create .toml file | npm install, build, configure | Create .sh + .toml |
| **File I/O** | Built-in `read_file`, `write_file` | MCP tools wrap same ops | `!{cat}`, `!{tee}`, shell pipes |
| **Chapter Detection** | Model reads file, detects patterns | MCP tool with regex | Shell script with awk/sed |
| **Glossary Loading** | `@{glossary.json}` in TOML | MCP tool returns glossary | Shell script outputs glossary |
| **Progress/Resume** | Not natively (manual state) | MCP can track state | State file (like Ralph) |
| **Dependencies** | Zero | Node.js, MCP SDK, possibly more | bash, jq (standard on Linux/Mac) |
| **Maintenance** | Edit text file | Debug server, handle crashes, deps | Edit shell scripts |
| **Token Efficiency** | Moderate (glossary in prompt) | Better (on-demand via MCP) | Same as A |
| **Error Recovery** | Model self-corrects | MCP tool error handling | Shell error handling + state |
| **Proven at Scale** | Conductor (3.5k stars) | Security ext (777 stars) | Ralph (318 stars) |

---

## Key Research Findings

### 1. TOML Commands Can Execute Shell Commands

The `!{...}` syntax runs any shell command and injects output into the prompt. The `@{...}` syntax injects file contents directly. Combined, these can:
- Read files: `@{novel.txt}`
- Run text processing: `!{grep -n "^第.*章" novel.txt}`
- Get word counts: `!{wc -l novel.txt}`
- Extract chapters: `!{sed -n '100,200p' novel.txt}`

### 2. Built-in File Tools Are Powerful

Gemini CLI provides `read_file`, `write_file`, `replace`, `glob`, `grep_search`, `list_directory`. The model can use ALL of these within a TOML command session. A TOML command is just a prompt — once activated, the model has full tool access.

### 3. Ralph's Loop Pattern Solves Progress/Resume

The Ralph extension proves that state management + iteration control is achievable with:
- Shell script creates `state.json` (current chapter, total chapters, status)
- TOML command reads state and instructs model accordingly
- `AfterAgent` hook checks state, decides whether to continue or stop
- `clearContext: true` prevents context overflow on long runs

### 4. No Translation-Specific Gemini CLI Extensions Exist

Searched GitHub extensively. No Gemini CLI extension for text translation exists. The closest is the SRT Subtitle Translator, which is a browser tool using CLIProxyAPI. This is a greenfield opportunity.

### 5. Conductor's Pattern Handles Multi-Step Pipelines

Conductor's `implement.toml` demonstrates a multi-step pipeline (plan → execute → validate → commit) purely through prompt engineering. Each step reads files, makes decisions, uses tools. This is exactly what a translation pipeline needs.

### 6. TOML Commands Cannot Be Chained

No mechanism to chain TOML commands. Each `/command` invocation is independent. However, a single TOML command prompt can instruct the model to perform multiple sequential operations using built-in tools. Conductor's implement.toml is one command that performs ~20 sequential operations.

### 7. Skills Provide On-Demand Expertise

The Agent Skills system loads specialized knowledge only when needed. A translation skill could contain glossary rules, genre guides, and translation methodology — loaded only when the translate command runs.

### 8. Shell Script + State File Pattern for Batch Processing

```
# setup.sh creates state
echo '{"chapter": 1, "total": 50, "status": "translating"}' > state.json

# TOML command reads state
# Model translates chapter N, writes output
# Hook increments state, re-runs if not done
```

This is the simplest viable batch processing architecture.

---

## Minimal Viable Architecture

### Architecture: TOML Command + Shell Scripts + Agent Skill

```
cli-translator/
├── gemini-extension.json          # name + version + contextFileName
├── commands/
│   ├── translate.toml             # Main translation command
│   ├── resume.toml                # Resume interrupted translation
│   └── validate.toml              # Validate translation quality
├── scripts/
│   ├── detect-chapters.sh         # Find chapter boundaries
│   ├── get-progress.sh            # Read state.json, return progress
│   └── init-translation.sh        # Create state file + output dir
├── skills/
│   └── novel-translator/
│       └── SKILL.md               # Translation expertise + glossary rules
├── glossary/
│   ├── default.json               # Universal terms
│   └── genres/                    # Genre-specific overrides
├── hooks/
│   └── hooks.json                 # AfterAgent hook for batch control
└── GEMINI.md                      # Extension context
```

### How It Works

1. User runs `/translate novel.txt --genre tienxia --bilingual`
2. TOML command runs `init-translation.sh` which:
   - Detects chapters via `detect-chapters.sh` (grep/awk patterns)
   - Creates `.translator/state.json` with chapter list + progress
3. TOML prompt instructs model to:
   - Read `state.json` to find current chapter
   - Read chapter text via `read_file` (with offset/limit)
   - Load glossary via `@{glossary/default.json}`
   - Translate using built-in tools
   - Write output via `write_file`
   - Update state via `run_shell_command`
4. AfterAgent hook checks state:
   - If chapters remaining: continue with next chapter
   - If done: stop and report completion
5. User can `/resume` to pick up where they left off

### Why No MCP

- Chapter detection: `grep -nE "^第.{1,10}章" file` — one shell command
- Glossary loading: `@{glossary/default.json}` — built-in file injection
- File reading: built-in `read_file` with offset/limit
- File writing: built-in `write_file`
- Progress tracking: state.json + shell script (proven by Ralph)
- Validation: model validates during translation, can run separate `/validate` command

Each MCP tool from the brainstorm maps to a simpler alternative:
| MCP Tool | Simpler Alternative |
|---|---|
| detect_chapters | `!{grep -nE "^第.{1,10}章" {{args}}}` in TOML |
| get_glossary | `@{glossary/tienxia.json}` in TOML |
| get_genre_guide | `@{guides/tienxia.md}` in TOML |
| save_translation | Built-in `write_file` tool |
| validate_translation | `/validate` TOML command |
| get_cache | State file check via shell |
| epub_reader | `!{python3 scripts/epub2txt.py {{args}}}` |

---

## Immersive Translate Architecture Reference

Immersive Translate (browser extension, millions of users) handles translation via:
- **Chunking:** Splits content by paragraph/element boundaries
- **Batch processing:** Translates chunks in parallel where possible
- **Context injection:** Passes surrounding paragraphs as context for each chunk
- **Validation:** Post-translation quality checks
- **Caching:** Content-addressed cache (hash of source text → translated text)

All of these patterns are achievable without MCP in Gemini CLI:
- Chunking: shell scripts split by chapter markers
- Context: model has full context window (1M tokens)
- Validation: model can self-validate or run `/validate`
- Caching: state.json tracks which chapters are done

---

## Unresolved Questions

1. **Context window practical limits:** A 50-chapter novel may exceed 1M tokens. Need to test actual token counts for typical Chinese web novels. The Ralph pattern (clear context between chapters) handles this.
2. **Shell script portability:** bash + jq are standard on Linux/Mac but not Windows. May need PowerShell equivalents or Python fallbacks.
3. **Hook reliability for long runs:** Ralph's AfterAgent hook pattern is new (v1.0.1). Stability for 50+ iterations untested.
4. **Glossary size vs context efficiency:** Large glossaries may consume too much context. Skills system (on-demand loading) mitigates this.

---

## Sources

- Gemini CLI official docs: extension writing, custom commands, tools, hooks, skills, subagents (github.com/google-gemini/gemini-cli/docs/)
- Conductor extension: github.com/gemini-cli-extensions/conductor (3,559 stars)
- Ralph extension: github.com/gemini-cli-extensions/ralph (318 stars)
- Code Review extension: github.com/gemini-cli-extensions/code-review (507 stars)
- Security extension: github.com/gemini-cli-extensions/security (777 stars)
- ru-text extension: github.com/talkstream/ru-text
- SRT Subtitle Translator: github.com/VjayC/SRT-Subtitle-Translator-Validator
- Packet Buddy extension: github.com/automateyournetwork/GeminiCLI_Packet_Buddy_Extension
- Awesome Gemini CLI: github.com/Piebald-AI/awesome-gemini-cli (450 stars)
- Gemini Flow: github.com/clduab11/gemini-flow (383 stars)
- Immersive Translate: github.com/immersive-translate/immersive-translate
