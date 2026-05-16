# Research Report: Gemini CLI Extension Without MCP — Pure TOML Capabilities

**Date:** 2026-05-16
**Researcher:** researcher-1
**Sources:** Gemini CLI source code (github.com/google-gemini/gemini-cli), official docs, source code analysis

---

## Executive Summary

Gemini CLI TOML commands have 3 template variables (`{{args}}`, `!{shell}`, `@{file}`) and a built-in model with 1M+ context window. **The model also has access to built-in tools (write_file, edit, read_file, shell, etc.) during execution.** This means TOML commands can do file I/O, chapter detection, and translation WITHOUT MCP — the model uses its own tools during the conversation.

**Verdict: MCP is NOT strictly necessary for this use case.** The model can handle file reading, chapter detection, translation, and file writing using its built-in tools, guided by the TOML prompt. MCP adds value only for deterministic/reusable logic (glossary loading, caching, validation) — not for core functionality.

---

## Key Findings

### 1. Template Variables — Complete List

Only 3 template variables exist. Confirmed from source code (`packages/cli/src/services/prompt-processors/types.ts`):

| Syntax | Purpose | Processing Order |
|--------|---------|------------------|
| `{{args}}` | User arguments injection | 3rd (after @{file} and !{shell}) |
| `!{shell command}` | Execute shell, inject output | 2nd (after @{file}) |
| `@{path}` | Inject file/dir content into prompt | 1st (before everything) |

**No other template variables exist.** No `{{model}}`, `{{date}}`, `{{env}}`, or similar.

Processing pipeline (from `FileCommandLoader.ts`):
1. `AtFileProcessor` — injects file contents
2. `ShellProcessor` — executes shell commands, substitutes `{{args}}`
3. `DefaultArgumentProcessor` — if no `{{args}}` in prompt, appends raw user input

### 2. Shell Commands (`!{shell}`) — Full I/O Capable

**Source:** `packages/cli/src/services/prompt-processors/shellProcessor.ts`

- `!{shell command}` executes BEFORE the prompt is sent to the model
- Output replaces the `!{...}` block in the prompt text
- `{{args}}` inside `!{...}` is shell-escaped automatically
- Security: user confirmation required for shell execution (unless allowlisted)
- Exit codes: error output + `[Shell command exited with code N]` included
- **Can read files:** `!{cat novel.txt}` works
- **Cannot write files from prompt expansion** — `!{}` is pre-processing, not runtime
- Shell commands are synchronous — output must complete before prompt is sent

**Limitation:** Shell commands run ONCE at invocation time, not during model execution. The model itself can call `run_shell_command` tool later, but TOML `!{}` is a one-shot pre-processing step.

### 3. File Injection (`@{file}`) — Has Hard Limits

**Source:** `packages/core/src/utils/pathReader.ts`, `packages/core/src/utils/fileUtils.ts`, `packages/core/src/utils/constants.ts`

`@{path}` uses `readPathFromWorkspace()` which calls `processSingleFileContent()`:

| Limit | Value | Source |
|-------|-------|--------|
| Max file size | **20 MB** | `MAX_FILE_SIZE_MB = 20` |
| Max lines (default) | **2,000 lines** | `DEFAULT_MAX_LINES_TEXT_FILE = 2000` |
| Max line length | **2,000 chars** | `MAX_LINE_LENGTH_TEXT_FILE = 2000` |
| Truncation behavior | Lines truncated beyond 2000 | Lines > 2000 chars get `... [truncated]` |

**Critical for novel translation:**
- A 500K char novel at ~80 chars/line = ~6,250 lines. `@{file}` would only inject the first 2,000 lines (~160K chars)
- `@{file}` has NO offset parameter — cannot inject "the rest" of a large file
- Binary files are skipped gracefully
- Directory injection: recursively injects ALL files (also subject to per-file limits)
- Respects `.gitignore` and `.geminiignore`
- Workspace-scoped: absolute paths must be within workspace

**Verdict: `@{file}` is unsuitable for large novels. Would truncate at 2000 lines.**

### 4. Built-in Tools Available to Model During Execution

**Source:** `packages/core/src/tools/tool-names.ts`

When the TOML command prompt is sent to the model, the model retains access to ALL built-in tools:

| Tool | Name | Relevance |
|------|------|-----------|
| Read file | `read_file` | Read novel chapters, supports `start_line`/`end_line` params |
| Write file | `write_file` | Save translated output |
| Edit file | `edit` | Edit files in-place |
| Shell | `run_shell_command` | Any shell operation |
| Grep | `grep` | Search for chapter patterns |
| Glob | `glob` | Find files |
| List dir | `ls` | Directory listing |
| Read many files | `read_many_files` | Batch file reading |
| Web search | `web_search` | (not needed here) |
| Web fetch | `web_fetch` | (not needed here) |
| Ask user | `ask_user` | Interactive prompts |
| Activate skill | `activate_skill` | Activate bundled skills |

**This is the key insight: the model can use `read_file` with `start_line`/`end_line` to read any portion of a large file, bypassing the `@{file}` 2000-line limit.**

### 5. SKILL.md Capabilities — Rich Context Without MCP

**Source:** `docs/cli/creating-skills.md`, `docs/cli/skills.md`

Skills provide:
- **SKILL.md body** — full instructions injected when activated
- **references/** — static docs the model can read
- **scripts/** — executable scripts the model can run via shell tool
- **assets/** — templates and other resources
- Progressive disclosure: only name+description loaded initially, full content on activation
- Discovery: auto-scanned from `.gemini/skills/` and `~/.gemini/skills/`

**For translator:** SKILL.md can contain genre guides, glossary references (as file paths the model reads via `read_file`), translation principles, and pronoun rules — all without MCP.

### 6. Chapter Detection — Pure Prompt Capability

The model can detect chapters using built-in tools:
1. `read_file` with `start_line=1, end_line=100` to scan for patterns
2. `grep` with pattern `第.*章` or `Chapter \d+` to find chapter markers
3. Model intelligence to identify non-standard chapter breaks

**No MCP needed for chapter detection.** The model can grep/read and identify patterns.

### 7. Large File Handling Strategy (Without MCP)

For a 500K+ char novel:

| Approach | How | Limitation |
|----------|-----|------------|
| `@{file}` | Inject entire file | **FAILS** — truncated at 2000 lines |
| `!{cat file}` | Shell inject | **FAILS** — same output, no offset |
| Model `read_file` tool | Model reads chunks | **WORKS** — supports `start_line`/`end_line` |
| Model `grep` tool | Find chapter positions | **WORKS** — pattern matching |
| Model `write_file` tool | Save output | **WORKS** — no size limit on write |

**Optimal no-MCP approach:**
1. TOML prompt instructs model to translate
2. Model uses `grep` to find chapter boundaries
3. Model uses `read_file` with line ranges to read each chapter
4. Model translates chapter by chapter
5. Model uses `write_file` to save translated output
6. Model uses `shell` for any additional processing

### 8. GEMINI.md as Persistent Context

**Source:** Extension docs, writing-extensions guide

`GEMINI.md` in the extension root is loaded into model context at session start. Can contain:
- Translation principles
- Genre-specific guidance
- Pronoun rules
- Common error patterns

This replaces the need for MCP tools like `get-genre-guide` and `get-translation-principles`.

---

## Capabilities Matrix: With vs Without MCP

| Capability | Without MCP | With MCP | MCP Value |
|------------|-------------|----------|-----------|
| Read novel file | `read_file` tool (chunked) | MCP `get-chapter` tool | LOW — built-in works |
| Chapter detection | `grep` tool + model intelligence | MCP `detect-chapters` | LOW — grep suffices |
| Genre guide | SKILL.md / GEMINI.md references | MCP `get-genre-guide` | NONE — static content |
| Glossary loading | `read_file` on JSON files | MCP `get-glossary` | LOW — model can read JSON |
| Translation | Model intelligence | Model intelligence | SAME — model does the work |
| Save output | `write_file` tool | MCP `save-translation` | NONE — built-in works |
| Validation | Model asks `shell` for word count | MCP `validate-translation` | MEDIUM — deterministic check |
| Caching | `shell` + file-based cache | MCP `get-cache` | MEDIUM — MCP cleaner |
| Rate limiting | Not possible in prompt | MCP `rate-limiter` | HIGH — can't do without MCP or external |
| Character detection | Model reads file + identifies | MCP `auto-detect-characters` | LOW — model can do this |
| Progress display | Model prints progress text | MCP progress reporting | NONE — model can report |
| EPUB reading | `shell` (python/epublib) | MCP `epub-reader` | MEDIUM — MCP simpler |

---

## Concrete Recommendation

**Ranked choice: Start WITHOUT MCP. Add MCP only if proven necessary.**

### Phase 1: Pure TOML + SKILL (Recommended Start)

```
cli-translator/
├── gemini-extension.json          # Extension manifest (no mcpServers)
├── commands/
│   └── translate.toml             # Slash command
├── skills/
│   └── novel-translator/
│       └── SKILL.md               # Translation expertise
├── glossary/
│   ├── default.json               # Universal terms
│   └── genres/
│       └── tienxia.json           # Genre-specific
├── references/
│   ├── translation-principles.md
│   ├── pronoun-guide.md
│   └── common-errors.md
└── GEMINI.md                      # Extension context
```

**translate.toml prompt instructs model to:**
1. Use `grep` to find chapter markers in the input file
2. Use `read_file` to read each chapter (with line ranges)
3. Use `read_file` to load glossary JSON files
4. Translate chapter by chapter
5. Use `write_file` to save output
6. Report progress

### Phase 2: Add MCP Only For (if needed)
- **Caching** (SHA-256 content-addressed cache, skip re-translation)
- **Rate limiting** (token bucket, exponential backoff)
- **Deterministic validation** (paragraph count, length ratio, CJK residual detection)

### Why This Approach
- YAGNI: Don't build MCP server until pure prompt approach is tested
- KISS: TOML prompt + built-in tools is dramatically simpler
- The 1M context window means the model can hold multiple chapters + glossary + genre guide simultaneously
- Built-in `read_file` with `start_line`/`end_line` bypasses the `@{file}` 2000-line limit
- The model is smart enough to do chapter detection, glossary application, and validation

---

## Adoption Risk

| Risk | Severity | Mitigation |
|------|----------|------------|
| Model might not follow instructions perfectly for chapter-by-chapter | MEDIUM | Detailed prompt with explicit steps |
| No rate limiting → quota exhaustion on long novels | HIGH | Add delay between chapters via `shell` tool (e.g., `sleep 2`) |
| No caching → re-translates from scratch on retry | MEDIUM | Accept for v1; add MCP caching in phase 2 |
| `@{file}` truncation at 2000 lines | HIGH | Don't use `@{file}` for novels; use model `read_file` tool |
| Model context overflow on very long chapters | LOW | 1M context is huge; instruct model to process chapters individually |

---

## Limitations of This Research

1. Did not test actual model behavior with translation prompts — findings based on source code analysis and docs
2. Rate limit quotas (2,000 req/day for Ultra) may still be the binding constraint regardless of MCP
3. EPUB handling via shell (python -c "import epub...") was not tested
4. Actual translation quality comparison (with vs without MCP glossary) not evaluated

---

## Unresolved Questions

1. **Can the model reliably process 25+ sequential `read_file` + `write_file` calls in one session?** — Needs testing. Context window supports it, but model attention may degrade.
2. **Is there a practical session token limit before quality degrades?** — 1M input tokens but quality may drop before hitting the limit.
3. **Should glossary be in JSON (read by model) or embedded in SKILL.md?** — JSON is more structured but model must parse it; embedded text is immediately available.
