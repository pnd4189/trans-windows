# Research Report: MCP Overhead vs Value Assessment for CLI Translator

**Date:** 2026-05-16
**Researcher:** researcher-2
**Status:** Complete
**Verdict:** MCP adds disproportionate overhead for this use case. Pure TOML + Python is the better architecture.

---

## Executive Summary

After analyzing the MCP protocol, Gemini CLI v0.42.0 source (bundled), existing MCP-based extensions (security, maestro, Stitch), and the proven TOML+Python approach (chinese-novel-proofreader v3.3), **MCP is not justified for a translation tool**. The core operation is "read file -> translate -> write file" which Gemini CLI handles natively via built-in Bash/ReadFile/WriteFile tools. MCP adds ~1800 tokens of tool definitions per request, 225+ round-trip tool calls for a 25-chapter novel, and multiple failure modes that a TOML+Python approach avoids entirely.

**Recommendation:** Pure TOML command + Python scripts (proven pattern from chinese-novel-proofreader). No MCP server.

---

## 1. MCP Tool Call Overhead Analysis

### 1.1 Token Cost

| Component | MCP (9 tools) | TOML (0 tools) |
|-----------|---------------|----------------|
| Tool definitions per request | ~1800 tokens | 0 tokens |
| Tool call round-trips per chapter | ~9 calls * ~200 tokens = ~1800 | 0 |
| Total per-chapter overhead | ~3600 tokens | ~0 tokens |
| 25-chapter novel total overhead | ~90,000 tokens | ~0 tokens |
| % of 1M context window | ~9% on definitions alone | 0% |

**Source:** Analysis of security MCP server (8 tools, ~4300 chars of descriptions). Each MCP tool sends full JSON Schema for name, description, parameters to the Gemini API as function declarations. Gemini CLI bundles these via `toolRegistry.getAllTools()` which includes `DiscoveredMCPTool` instances alongside built-in tools.

### 1.2 Latency Cost

| Operation | MCP Approach | TOML Approach |
|-----------|-------------|---------------|
| Per tool call (JSON-RPC stdio) | 5-50ms transport | N/A |
| Per tool call (model inference) | 1-3s model decision | N/A |
| Per chapter (9 tool calls) | 9-27s overhead | 0s |
| 25 chapters | 225-675s (3.75-11.25 min) | 0s |

**Source:** MCP uses JSON-RPC over stdio transport. The actual stdio latency is negligible (~5-50ms), but each tool call requires a model inference step: model generates function call -> Gemini CLI executes tool -> returns result -> model generates next action. This round-trip dominates.

### 1.3 Session Startup

MCP server must be spawned, connected, and tools discovered on each Gemini CLI session start. From source: `mcpClientManager.restart()` iterates all enabled servers. For the security MCP: Node.js process spawn + `@modelcontextprotocol/sdk` initialization + tool discovery = ~500ms-2s startup overhead.

---

## 2. Conflict Risk Analysis

### 2.1 Tool Name Conflicts

Gemini CLI uses a flat tool registry (`toolRegistry.getAllTools()`). MCP tools are added as `DiscoveredMCPTool` instances. While the source separates "gemini tools" from "mcp tools" for display purposes, **both are sent to the Gemini API as function declarations**. Risk scenarios:

- MCP tool `save_translation` vs built-in `WriteFileTool`: no name collision, but **semantic overlap**. Model must choose between MCP tool and built-in WriteFile. This creates ambiguity.
- MCP tool `get_chapter` vs built-in `ReadFileTool`: both read files. Model may call wrong one.

**Evidence:** Security MCP has `find_line_numbers` (overlaps with GrepTool) and `install_dependencies` (overlaps with Bash/ShellTool). These work because security auditing is a specialized domain with distinct semantics. Translation file I/O is NOT specialized enough to justify separate tools.

### 2.2 File Operation Conflicts

| MCP Tool | Built-in Equivalent | Conflict Risk |
|----------|-------------------|---------------|
| `save_translation` | WriteFileTool | HIGH - model may write via either |
| `get_chapter` | ReadFileTool | HIGH - model may read via either |
| `detect_chapters` | Bash (python script) | MEDIUM - different paths to same result |
| `validate_translation` | Bash (python script) | LOW - validation logic is unique |

**Key insight:** The brainstorm doc's 9 MCP tools include 3-4 that directly overlap with Gemini CLI built-ins. The model must decide which tool to use on every operation. This is not theoretical - it's a real source of confusion for LLMs.

---

## 3. MCP Server Crash/Timeout During Translation

### 3.1 Gemini CLI Error Handling (Source-Verified)

From `chunk-COQP2M4D.js`:
```
mcpClientManager.restartServer(serverName).catch((error) => {
  context.ui.addItem({
    type: "warning",
    text: `Failed to restart MCP server '${serverName}': ${getErrorMessage(error)}`
  });
})
```

Gemini CLI handles MCP failures gracefully at the session level. However, **mid-translation tool call failures** are a different story:

1. Model calls MCP tool `save_translation` for chapter 15
2. MCP server process crashes (OOM, unhandled exception, Node.js error)
3. Gemini CLI receives error from JSON-RPC transport
4. Model gets error message, must decide how to recover
5. Model may: retry, skip chapter, switch to built-in WriteFile, or ask user

**Recovery is model-dependent, not deterministic.** For a batch translation of 25 chapters, this is a real risk. A pure Python script approach fails deterministically and can be retried from the last checkpoint.

### 3.2 Common MCP Crash Causes

- Node.js OOM (large file processing in MCP server memory)
- Unhandled promise rejections in async tool handlers
- File system race conditions (MCP server + Gemini CLI both writing files)
- Zod schema validation failures on unexpected input
- `@modelcontextprotocol/sdk` version incompatibility

---

## 4. Rate Limiting: Double-Throttle Risk

### 4.1 Gemini CLI Quota System

Gemini CLI has its own rate limiting via `RateLimiter` and `RetryableQuotaError` classes. It handles:
- HTTP 429 (rate limit) with `RetryableQuotaError`
- Daily quota exhaustion via `TerminalQuotaError`
- Automatic retry with exponential backoff

**Quota (Ultra plan):** 2,000 req/day, no published RPM.

### 4.2 MCP's Own Rate Limiting

The brainstorm proposes a `RateLimiter` class in the MCP server itself (token bucket: 20 req burst, 1/sec refill). This creates **double throttling**:

```
User request → Gemini CLI (quota check) → Model decides tool call →
MCP server (own rate limiter) → Tool execution → Response
```

If the MCP server rate-limits a tool call, the model gets an error. It may interpret this as a quota issue and trigger Gemini CLI's own retry logic, compounding the delay.

**Risk:** MCP rate limiter rejects call -> model sees error -> model retries -> Gemini CLI counts retry against quota -> double consumption. For 25 chapters with 9 tool calls each = 225 tool invocations. At 1 MCP call/sec, that's 225s of minimum MCP processing time, independent of model inference time.

---

## 5. Error Recovery Comparison

| Scenario | MCP Approach | TOML+Python Approach |
|----------|-------------|---------------------|
| Chapter 15 of 25 fails mid-write | MCP tool returns error. Model decides: retry? skip? ask user? **Non-deterministic** | Python script catches exception, logs error, skips chapter. Deterministic resume from checkpoint |
| MCP server crashes | Gemini CLI shows warning. Model may try restart. **Session may be lost** | N/A - no server to crash |
| Glossary file missing | MCP tool returns error for `get_glossary`. Model must handle | Python script returns empty dict. Translation proceeds with defaults |
| Invalid chapter input | Zod validation fails in MCP. Error message may be cryptic | Python script validates with clear error message |
| Network/API quota hit during tool call | MCP tool call fails. Model + MCP both retry. Double throttle | Python script pauses, Gemini CLI handles quota retry |

---

## 6. Development & Maintenance Cost

### 6.1 MCP Server Stack

```
TypeScript + @modelcontextprotocol/sdk + Zod + Node.js + tsconfig + build step
```

- **Dependencies:** `@modelcontextprotocol/sdk` (^1.24.0), `zod` (^3.25.76), `typescript` (^5.0.0)
- **Build step:** `tsc` compilation required before use
- **node_modules:** ~5-15MB for a typical MCP server
- **Maintenance:** SDK updates may break tools (Zod v3->v4 migration known issue)
- **Debugging:** Must debug both MCP server process AND Gemini CLI model behavior

### 6.2 TOML+Python Stack

```
TOML command file + Python scripts (standard library + minimal deps)
```

- **Dependencies:** Python 3 (already installed), maybe `epub` package
- **No build step** - Python runs directly
- **No node_modules** - no npm dependency management
- **Maintenance:** Python scripts are self-contained, no SDK version churn
- **Debugging:** Run Python script directly to test, independent of Gemini CLI

### 6.3 Real-World Comparison

| Metric | MCP Server (security ext) | TOML+Python (proofreader ext) |
|--------|-------------------------|------------------------------|
| Source files | 17 .ts files | 34 .py files |
| Build output | dist/ (compiled JS) | No build needed |
| node_modules | Required | N/A |
| Dependencies | @modelcontextprotocol/sdk, zod | Python stdlib |
| Startup time | ~500ms-2s | ~0ms (no server) |
| Crash surfaces | MCP server process, SDK, transport | None (no server) |

---

## 7. Context Window Usage Comparison

### 7.1 MCP Approach

Per-request context consumption:
```
System prompt: ~500 tokens
MCP tool definitions (9 tools): ~1800 tokens
TOML command instructions: ~2000 tokens
SKILL.md instructions: ~1500 tokens
Tool call往返 (accumulated): grows with each call
```

**For a 25-chapter novel:**
- Fixed overhead: ~5800 tokens per request
- Tool call history accumulates (every MCP call + response stays in context)
- At chapter 25: ~225 tool call/response pairs in history = ~45,000 tokens of tool往返
- **Total context eaten by MCP overhead: ~50,800 tokens (~5% of 1M)**

### 7.2 TOML Approach

Per-request context consumption:
```
System prompt: ~500 tokens
TOML command (full instructions inline): ~3000 tokens
SKILL.md instructions: ~1500 tokens
No tool definitions, no tool call history
```

**For a 25-chapter novel:**
- Fixed overhead: ~5000 tokens per request
- No tool call history (model writes directly, Python scripts run via Bash)
- Bash outputs stay in context but are minimal (file paths, status messages)
- **Total context overhead: ~5000 tokens (~0.5% of 1M)**

---

## 8. When MCP Actually Makes Sense

MCP is the right choice when:
1. **Stateful server needed**: WebSocket connections, database connections, auth sessions
2. **External API integration**: Calling DeepL API, Google Translate API, etc.
3. **Real-time streaming**: Progress reporting, streaming translations
4. **Multi-client sharing**: Multiple Gemini CLI sessions sharing same MCP server
5. **Complex tool orchestration**: Tools that call other tools, multi-step workflows

**None of these apply to cli-translator.** The translation task is:
- Stateless (read file -> translate -> write file)
- No external APIs (uses Gemini CLI's built-in model)
- No real-time streaming needed
- Single-session operation
- Linear workflow (detect chapters -> translate each -> validate -> save)

---

## 9. Risk Matrix

| Risk | MCP Approach | TOML+Python | Severity |
|------|-------------|-------------|----------|
| Tool name conflicts with built-ins | HIGH | NONE | High |
| MCP server crash mid-translation | MEDIUM | NONE | High |
| Double rate limiting | MEDIUM | NONE | Medium |
| Context window waste | 5% (50K tokens) | 0.5% (5K tokens) | Medium |
| SDK version churn | HIGH | NONE | Low |
| Build complexity | TypeScript+Node | Python only | Low |
| Debugging difficulty | 2-process debugging | Single process | Medium |
| Latency overhead (25 chapters) | 3.75-11.25 min extra | 0 | High |
| Model confusion (which tool to use) | HIGH | NONE | High |
| Resume after failure | Non-deterministic | Deterministic checkpoint | High |

---

## 10. Recommendations

### Primary: Pure TOML + Python (NO MCP)

Follow the proven `chinese-novel-proofreader` v3.3 pattern:
1. TOML command in `commands/translate.toml` with full instructions
2. Python scripts in `scripts/` for deterministic operations (chapter detection, glossary loading, validation, file I/O)
3. SKILL.md for auto-activation and translation expertise
4. Gemini CLI built-in tools (Bash, ReadFile, WriteFile) for all file operations
5. GEMINI.md for extension context

### What Gets Dropped (and Why)

| MCP Tool | Replacement | Why |
|----------|------------|-----|
| detect_chapters | Python script via Bash | Deterministic regex, no model decision needed |
| get_chapter | Python script via Bash | File reading, no model decision needed |
| get_glossary | Python script + @{file} inline | Load JSON, inject into prompt |
| get_genre_guide | Python script + @{file} inline | Load JSON, inject into prompt |
| save_translation | Built-in WriteFile or Bash | No need for MCP wrapper |
| validate_translation | Python script via Bash | Deterministic checks, no model needed |
| get_translation_cache | Python script via Bash | File-based cache, no model needed |
| auto_detect_characters | Python script via Bash | Regex/frequency analysis |
| get_previous_translation | Python script via Bash | Read last output file |

### What Gets Kept

- TOML command with translation principles (proven effective in proofreader)
- Genre profiles (JSON files loaded by Python)
- Glossary cascade system (Python loads and merges)
- Bilingual output mode
- Chapter detection patterns
- Rate limiting (in Gemini CLI, not MCP)

---

## Source Credibility

| Source | Type | Credibility |
|--------|------|------------|
| Gemini CLI v0.42.0 bundled source | Production code | Highest - direct evidence |
| security MCP server source | Production extension | High - real-world MCP usage |
| chinese-novel-proofreader v3.3 | Production extension | High - proven TOML+Python pattern |
| MCP spec (modelcontextprotocol.io) | Official spec | High but web reader was down |
| maestro extension | Production extension | Medium - MCP usage verified |
| User's Gemini CLI settings.json | Production config | Highest - real user environment |

## Limitations

- Could not access MCP specification (web reader rate-limited)
- Could not search GitHub issues for Gemini CLI MCP bugs (web reader down)
- Token estimates are approximations based on character counts, not actual tokenizer output
- Latency estimates are theoretical, not benchmarked
- No access to Gemini CLI's internal test suite for MCP error handling

---

## Unresolved Questions

1. Does Gemini CLI deduplicate MCP tool names with built-in tool names? (Likely no - flat registry)
2. What is the exact JSON-RPC error recovery path when MCP server returns `isError: true`?
3. Does Gemini CLI v0.42.0 support MCP prompts and resources for extensions (seen in security MCP's `registerPrompt` calls)?
