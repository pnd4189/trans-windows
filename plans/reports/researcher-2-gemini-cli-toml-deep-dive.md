# Research Report: Gemini CLI TOML Command System Deep Dive

**Date:** 2026-05-16
**Researcher:** researcher-2
**Sources:** Gemini CLI source code (v0.4.x), Ralph extension, Conductor extension, Google API docs

---

## Executive Summary

Gemini CLI's TOML command system is a prompt-injection mechanism with 3 template variables (`{{args}}`, `!{shell}`, `@{file}`). The `@{file}` injection has hard limits (2000 lines, 20MB) making it unsuitable for novels. However, the model's built-in `read_file` tool supports `start_line`/`end_line` parameters with no per-call line limit, enabling reliable chunked reading of large files. `write_file` is overwrite-only (no append mode). Context management across 50+ sequential tool calls is handled by automatic compression at 50% of the 1M token limit, with Ralph's `clearContext: true` hook pattern proving the loop-control approach works. Rate limits are RPD-based (1000-2000/day) with per-minute throttling that returns retryable errors with server-suggested delays.

**Key finding: The `read_file` tool with `start_line`/`end_line` is reliable for 500+ page novels. The real constraint is RPD quota, not file reading capability.**

---

## 1. TOML Command Spec: Template Variables

### 1.1 Complete Template Variable List

Source: `packages/cli/src/services/prompt-processors/types.ts`

| Syntax | Processing Order | Purpose |
|--------|-----------------|---------|
| `@{path}` | 1st | Inject file/dir content into prompt |
| `!{shell command}` | 2nd | Execute shell, inject output |
| `{{args}}` | 3rd | User arguments injection |

### 1.2 `@{file}` Injection — Hard Limits

Source: `packages/core/src/utils/constants.ts`, `packages/core/src/utils/fileUtils.ts`

| Limit | Value | Impact on Novel Translation |
|-------|-------|----------------------------|
| Max file size | 20 MB | OK — 500-page novel ~200KB |
| Max lines | 2,000 lines | **BLOCKER** — novel has 6,000+ lines |
| Max line length | 2,000 chars | Minor — Chinese lines are shorter |
| Offset parameter | **NONE** | Cannot read beyond line 2000 |

**Processing pipeline** (`FileCommandLoader.ts`):
1. `AtFileProcessor` — calls `readPathFromWorkspace()` → `processSingleFileContent()`
2. `ShellProcessor` — executes shell commands, substitutes `{{args}}`
3. `DefaultArgumentProcessor` — if no `{{args}}`, appends raw user input

**Critical: `@{file}` has NO offset/limit parameters. It always reads from line 1. For a novel with 6,000+ lines, it silently truncates at line 2,000.**

### 1.3 `!{shell}` Execution

Source: `packages/cli/src/services/prompt-processors/shellProcessor.ts`

- Executes **ONCE** at TOML command invocation time (pre-processing, not runtime)
- `{{args}}` inside `!{...}` is shell-escaped automatically
- Output replaces the `!{...}` block in the prompt text
- Security: policy engine checks each command; user confirmation required unless allowlisted
- Exit codes: error output + `[Shell command exited with code N]` included

**Limitation:** Cannot write files from `!{}` — it's pre-processing only. The model can call `run_shell_command` tool later.

### 1.4 `{{args}}` Injection

- Outside `!{...}`: raw user input
- Inside `!{...}`: shell-escaped user input
- If no `{{args}}` in prompt: raw input appended as default argument

---

## 2. `read_file` Tool: Large File Handling

### 2.1 Implementation Details

Source: `packages/core/src/tools/read-file.ts`, `packages/core/src/utils/fileUtils.ts`

```typescript
interface ReadFileToolParams {
  file_path: string;
  start_line?: number;  // 1-based, optional
  end_line?: number;    // 1-based, inclusive, optional
}
```

**Key behavior from `processSingleFileContent()`:**

1. **With `start_line`/`end_line`:** Reads the specified range. If only `start_line` provided, reads `DEFAULT_MAX_LINES_TEXT_FILE` (2000) lines from that point.
2. **Without parameters:** Reads first 2000 lines (same as `@{file}`).
3. **Truncation detection:** Returns `isTruncated: true` with `linesShown: [start, end]` and `originalLineCount`.
4. **Helpful message:** When truncated, includes: `"To read more of the file, you can use the 'start_line' and 'end_line' parameters in a subsequent 'read_file' call. For example, to read the next section of the file, use start_line: ${end + 1}."`

### 2.2 Reliability for 500+ Page Novels

| Scenario | Behavior | Reliable? |
|----------|----------|-----------|
| 200KB novel (~6,000 lines) | `read_file(start_line=1, end_line=2000)` reads lines 1-2000 | YES |
| Continue reading | `read_file(start_line=2001, end_line=4000)` reads lines 2001-4000 | YES |
| Chapter of 2K-20K chars | Single `read_file` call handles it (well under 2000 lines) | YES |
| 50+ sequential reads | Each call is independent; no cumulative limit | YES |
| File size limit | 20MB — novel at 200KB is well under | YES |

**Verdict: `read_file` with `start_line`/`end_line` is reliable for large novels. The model can read any portion of the file by specifying line ranges.**

### 2.3 Line Length Truncation

Lines exceeding 2,000 characters get `... [truncated]` appended. For Chinese text, typical lines are 20-80 characters, so this is not a concern.

---

## 3. `write_file` Tool: Output Handling

### 3.1 Implementation Details

Source: `packages/core/src/tools/write-file.ts`

```typescript
interface WriteFileToolParams {
  file_path: string;
  content: string;
  modified_by_user?: boolean;
  ai_proposed_content?: string;
}
```

### 3.2 Key Characteristics

| Feature | Behavior |
|---------|----------|
| Mode | **Overwrite only** — no append mode |
| Size limit | None specified in code |
| Line ending | Preserves original file's line ending (CRLF/LF) |
| Directory creation | Auto-creates parent directories |
| Confirmation | Shows diff before writing (unless auto-approved) |
| Omission detection | Rejects content with placeholders like "rest of methods ..." |

### 3.3 Implications for Novel Translation

- **No append mode:** To add a translated chapter, the model must either:
  - Read existing output, append new chapter, write entire file (risky for large files)
  - Write each chapter to a separate file (recommended)
- **Overwrite risk:** If model writes partial content, previous content is lost
- **Recommendation:** Use separate output files per chapter, then `shell` to concatenate

---

## 4. Context Window Management

### 4.1 Token Limits

Source: `packages/core/src/core/tokenLimits.ts`

| Model | Token Limit |
|-------|-------------|
| Gemini 2.5 Pro | 1,048,576 (1M) |
| Gemini 2.5 Flash | 1,048,576 (1M) |
| Gemini 2.5 Flash Lite | 1,048,576 (1M) |
| Gemma 4 | 256,000 |

### 4.2 Automatic Context Compression

Source: `packages/core/src/context/chatCompressionService.ts`

- **Trigger:** When chat history exceeds 50% of model's token limit (`DEFAULT_COMPRESSION_TOKEN_THRESHOLD = 0.5`)
- **Preservation:** Keeps last 30% of chat history (`COMPRESSION_PRESERVE_THRESHOLD = 0.3`)
- **Function response budget:** 50,000 tokens for tool outputs in preserved history
- **Method:** LLM-based summarization of older context

### 4.3 Context Across 50+ Sequential Tool Calls

**How it works:**
1. Each tool call (read_file, write_file) adds to chat history
2. When history hits 50% of 1M tokens (~500K tokens), compression triggers
3. Older context is summarized; recent 30% preserved
4. Model continues with compressed context + recent history

**Practical implications for novel translation:**
- A chapter read (~5K chars = ~2K tokens) + translation (~5K chars = ~2K tokens) = ~4K tokens per chapter
- 50 chapters = ~200K tokens (well under 500K compression threshold)
- Compression unlikely to trigger during a single novel translation
- If it does, the model loses earlier chapter context but retains recent work

### 4.4 Ralph's `clearContext: true` Pattern

Source: `/tmp/ralph-research/hooks/stop-hook.sh`

```json
{
  "decision": "deny",
  "reason": "$ORIGINAL_PROMPT",
  "hookSpecificOutput": {
    "clearContext": true
  }
}
```

- `AfterAgent` hook returns `clearContext: true` to wipe conversation history
- Combined with `decision: "deny"` + `reason: "<original prompt>"` to re-inject the prompt
- Effectively resets context to zero while continuing the loop
- **Critical for long novels:** Prevents context overflow by clearing between iterations

---

## 5. Chapter Chunking Strategy

### 5.1 Optimal Chunk Size Analysis

| Factor | Consideration |
|--------|---------------|
| Context window | 1M tokens; each chapter ~2-4K tokens |
| Translation quality | Larger chunks = better narrative coherence |
| `read_file` limit | 2000 lines per call (but can chain calls) |
| Rate limits | Each chapter = 1 model request (RPD constraint) |
| Error recovery | Smaller chunks = less work lost on failure |

### 5.2 Recommended Chunking Approach

**Strategy: One chapter per loop iteration**

1. **Detect chapter boundaries** using `grep` (pattern: `第.*章` or `Chapter \d+`)
2. **Read chapter** via `read_file(start_line=X, end_line=Y)`
3. **Translate** in-context (model processes entire chapter)
4. **Write output** via `write_file` to separate chapter file
5. **Update state** via `shell` command
6. **Hook clears context** and re-enters loop

**Chunk size recommendation:** Natural chapter boundaries (2K-20K chars). Do NOT split chapters mid-paragraph.

### 5.3 Multi-Chapter Context (Optional)

For better translation consistency, the model can:
1. Read previous chapter's translation as context
2. Read glossary file
3. Read current chapter
4. Translate with awareness of prior context

This uses ~3 tool calls per chapter but maintains character/terminology consistency.

---

## 6. Rate Limiting Behavior

### 6.1 Daily Request Limits (RPD)

Source: `docs/resources/quota-and-pricing.md`, `https://developers.google.com/gemini-code-assist/resources/quotas`

| Authentication | Tier | RPD Limit |
|----------------|------|-----------|
| Google account | Individual (Free) | 1,000 |
| Google account | AI Pro | 1,500 |
| Google account | AI Ultra | 2,000 |
| API key | Free | 250 |
| API key | Pay-as-you-go | Varies |
| Workspace | Standard | 1,500 |
| Workspace | Enterprise | 2,000 |

### 6.2 Per-Minute Throttling (RPM)

**No explicit RPM numbers published.** From source code analysis:

- `googleQuotaErrors.ts` detects `PerMinute` quota violations
- Returns `RetryableQuotaError` with 60-second suggested delay
- `MAX_RETRYABLE_DELAY_SECONDS = 300` (5 min) — beyond this, treated as terminal
- Retry logic: exponential backoff starting at 5s, max 30s, up to 10 attempts

**Practical behavior:**
- Rapid sequential requests trigger 429 errors
- Gemini CLI auto-retries with server-suggested delay
- If delay > 5 minutes, treated as terminal quota error
- User sees fallback/credits flow for terminal errors

### 6.3 Burst Handling

From `retry.ts`:
```
initialDelayMs: 5000    // 5 seconds
maxDelayMs: 30000       // 30 seconds
maxAttempts: 10         // 10 retries
```

**Implication:** The CLI handles burst rate limits automatically. For a 50-chapter novel, sequential processing (1 chapter per request) should stay well within per-minute limits.

### 6.4 Quota Exhaustion Strategy

For a 50-chapter novel on Free tier (1,000 RPD):
- 50 chapters + 50 validation calls = 100 requests (10% of daily quota)
- Safe margin even with retries
- On API key free tier (250 RPD): still feasible but tighter

---

## 7. State Persistence Between Commands

### 7.1 Ralph's State File Pattern

Source: `/tmp/ralph-research/scripts/setup.sh`, `/tmp/ralph-research/hooks/stop-hook.sh`

**State file:** `.gemini/ralph/state.json`

```json
{
  "active": true,
  "current_iteration": 1,
  "max_iterations": 50,
  "completion_promise": "TRANSLATION_COMPLETE",
  "original_prompt": "/translate novel.txt --genre tienxia",
  "started_at": "2026-05-16T10:00:00Z"
}
```

### 7.2 Hook Cycle State Survival

**Flow:**
1. `loop.toml` runs `setup.sh` → creates `state.json`
2. Model executes task, writes output
3. `AfterAgent` hook (`stop-hook.sh`) fires:
   - Reads `state.json` from stdin (hook receives `prompt_response`)
   - Checks `completion_promise` in response
   - Increments `current_iteration`
   - If iterations remain: returns `decision: "deny"` + `clearContext: true`
   - If done: returns `decision: "allow"` + `continue: false`
4. Context cleared, original prompt re-injected
5. Model reads `state.json` to know current progress

**Key mechanisms:**
- State survives because it's on disk (`.gemini/ralph/state.json`)
- Hook reads state via `jq` from the file
- Model reads state via `read_file` tool at start of each iteration
- `clearContext: true` prevents context overflow

### 7.3 Adaptation for Novel Translation

**Translator state file:** `.translator/state.json`

```json
{
  "active": true,
  "source_file": "novel.txt",
  "output_dir": "translations/",
  "chapters": [
    {"id": 1, "start_line": 1, "end_line": 150, "status": "done"},
    {"id": 2, "start_line": 151, "end_line": 320, "status": "in_progress"},
    {"id": 3, "start_line": 321, "end_line": 480, "status": "pending"}
  ],
  "current_chapter": 2,
  "total_chapters": 50,
  "glossary_hash": "abc123",
  "started_at": "2026-05-16T10:00:00Z"
}
```

**Hook behavior:**
- After each chapter translation, hook checks state
- If `current_chapter < total_chapters`: increment, clear context, continue
- If all done: stop and report completion
- If error: stop and report failure

---

## 8. Capability Matrix

| Capability | @{file} | !{shell} | read_file tool | write_file tool |
|------------|---------|----------|----------------|-----------------|
| Read full novel | FAILS (2000 line limit) | FAILS (output too large) | WORKS (chunked) | N/A |
| Read chapter | WORKS (if < 2000 lines) | WORKS (sed/awk) | WORKS | N/A |
| Write translation | N/A | N/A | N/A | WORKS (overwrite) |
| Append to file | N/A | N/A | N/A | FAILS (no append) |
| State management | N/A | WORKS (jq) | WORKS (read JSON) | WORKS (write JSON) |
| Chapter detection | N/A | WORKS (grep) | WORKS (grep tool) | N/A |

---

## 9. Limitations & Risks

| Limitation | Severity | Mitigation |
|------------|----------|------------|
| `@{file}` 2000-line truncation | HIGH | Use `read_file` tool instead |
| `write_file` no append mode | MEDIUM | Write per-chapter files, concatenate later |
| RPD quota exhaustion | MEDIUM | 50 chapters << 1000 RPD limit |
| RPM throttling | LOW | Auto-retry with backoff |
| Context compression mid-translation | LOW | 50 chapters unlikely to trigger 50% threshold |
| Model attention degradation over long sessions | MEDIUM | Use `clearContext` between chapters |
| No cross-chapter consistency mechanism | MEDIUM | Read previous chapter + glossary as context |

---

## 10. Recommendations

### 10.1 Architecture: Ralph Loop + Chapter Files

```
cli-translator/
├── gemini-extension.json
├── commands/
│   └── translate.toml           # Main command
├── hooks/
│   ├── hooks.json               # AfterAgent hook
│   └── translate-hook.sh        # State management
├── scripts/
│   ├── detect-chapters.sh       # Find chapter boundaries
│   └── init-translation.sh      # Create state file
├── skills/
│   └── novel-translator/
│       └── SKILL.md             # Translation expertise
├── glossary/
│   └── default.json
└── GEMINI.md
```

### 10.2 Translation Loop

1. `init-translation.sh` detects chapters, creates `state.json`
2. `translate.toml` instructs model to:
   - Read `state.json` → find current chapter
   - Read chapter via `read_file(start_line, end_line)`
   - Read glossary via `read_file`
   - Translate chapter
   - Write to `output/chapter_N.txt`
   - Update `state.json` status
3. `translate-hook.sh` (AfterAgent):
   - Check completion promise
   - Increment chapter counter
   - Clear context if chapters remain
   - Stop if all done

### 10.3 Key Design Decisions

1. **Use `read_file` tool, NOT `@{file}`** — bypasses 2000-line limit
2. **One chapter per iteration** — manageable context, clean error recovery
3. **Separate output files** — avoids `write_file` overwrite risk
4. **Shell concatenation at end** — `cat translations/chapter_*.txt > novel_translated.txt`
5. **Glossary in `read_file`** — load on-demand, not in prompt (saves context)

---

## Unresolved Questions

1. **Actual RPM limit:** Google doesn't publish specific RPM numbers. Need empirical testing to determine safe request间隔.
2. **Context quality after `clearContext`:** Does the model maintain translation consistency when context is wiped between chapters? Needs testing with real novel.
3. **Hook reliability for 50+ iterations:** Ralph's pattern is proven but not tested at 50+ iterations. Potential issues: state file corruption, hook timeout.
4. **EPUB input handling:** Not covered in this research. Would need `shell` command with Python EPUB library.
5. **Translation quality vs chunk size:** Is per-chapter optimal, or would 2-3 chapter batches produce better translations?
