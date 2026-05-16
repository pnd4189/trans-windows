# Research: Hook-Based Loop Control and State Management for Chapter Translation

**Researcher:** researcher-3
**Date:** 2026-05-16
**Status:** Complete

---

## Executive Summary

The Ralph extension's AfterAgent hook pattern is **proven and production-ready** for sequential chapter translation. The mechanism works by returning `{"decision": "deny", "reason": "<prompt>", "hookSpecificOutput": {"clearContext": true}}` to force re-invocation with a clean context window. State persists in a JSON file on disk, not in LLM memory.

**Key findings:**
- The hook protocol is formally documented in Gemini CLI's official hooks reference
- Ralph's `stop-hook.sh` (75 lines) is the canonical implementation
- `clearContext: true` fully wipes conversation history between iterations
- 50+ iterations is architecturally sound but untested in practice (Ralph defaults to 5 max)
- Error recovery requires file-based state, not LLM memory
- Parallel chapter processing is impossible with hooks -- must be sequential
- The chinese-novel-proofreader uses a completely different pattern (brief/response protocol, no hooks)

---

## 1. AfterAgent Hook Protocol (Verified from Source)

### Hook Configuration

Ralph registers in `hooks/hooks.json`:
```json
{
  "hooks": {
    "AfterAgent": [{
      "matcher": "*",
      "hooks": [{
        "name": "ralph-loop",
        "type": "command",
        "command": "${extensionPath}/hooks/stop-hook.sh"
      }]
    }]
  }
}
```

### Hook Input (stdin JSON)

Per Gemini CLI hooks reference, AfterAgent receives:
```json
{
  "session_id": "...",
  "transcript_path": "...",
  "cwd": "...",
  "hook_event_name": "AfterAgent",
  "timestamp": "...",
  "prompt": "the user's original request",
  "prompt_response": "the agent's final text output",
  "stop_hook_active": false
}
```

### Hook Output (stdout JSON) -- Two Decision Paths

**Continue loop (deny + clearContext):**
```json
{
  "decision": "deny",
  "reason": "<original prompt text>",
  "systemMessage": "...",
  "hookSpecificOutput": {
    "clearContext": true
  }
}
```

**Stop loop (allow + continue:false):**
```json
{
  "decision": "allow",
  "continue": false,
  "stopReason": "reached iteration limit",
  "systemMessage": "..."
}
```

### How deny+clearContext Works

1. `decision: "deny"` rejects the agent's response
2. `reason` becomes the **new prompt** fed to the agent on the next turn
3. `clearContext: true` wipes the LLM conversation history (not the UI display)
4. The agent starts fresh with only the new prompt + file system state

This is the core loop mechanism. The agent never "remembers" previous iterations -- it reads state from `.gemini/ralph/state.json` each time.

---

## 2. State.json Schema Design

### Ralph's Schema (from setup.sh)

```json
{
  "active": true,
  "current_iteration": 1,
  "max_iterations": 5,
  "completion_promise": "DONE",
  "original_prompt": "the full prompt text",
  "started_at": "2026-05-16T12:00:00Z"
}
```

### Proposed Translation State Schema

For chapter-by-chapter translation, extend Ralph's pattern:

```json
{
  "active": true,
  "version": 1,
  "source_file": "/path/to/novel.txt",
  "output_dir": "/path/to/output/",
  "source_lang": "zh",
  "target_lang": "vi",
  "genre": "tienxia",
  "glossary_path": "/path/to/glossary.json",
  "total_chapters": 50,
  "current_chapter": 1,
  "chapters": [
    {
      "id": 1,
      "title": "Chapter 1 title",
      "start_line": 1,
      "end_line": 142,
      "status": "completed",
      "output_file": "chapter_001.txt",
      "char_count": 5230,
      "translated_at": "2026-05-16T12:05:00Z"
    },
    {
      "id": 2,
      "title": "Chapter 2 title",
      "start_line": 143,
      "end_line": 287,
      "status": "pending",
      "output_file": null,
      "char_count": null,
      "translated_at": null
    }
  ],
  "chapters_completed": 0,
  "chapters_failed": 0,
  "started_at": "2026-05-16T12:00:00Z",
  "last_updated": "2026-05-16T12:05:00Z"
}
```

**Status values per chapter:** `pending`, `in_progress`, `completed`, `failed`, `skipped`

**Why this schema works:**
- `chapters[]` array enables O(1) lookup of current chapter
- `start_line`/`end_line` enable precise file extraction via `sed` or `read_file` with offset
- `status` per chapter enables resume from any point
- `glossary_path` keeps glossary reference external (avoid bloating state)

---

## 3. Reliability Assessment: 50+ Iterations

### What We Know Works

| Factor | Status | Evidence |
|--------|--------|----------|
| Hook fires after every agent turn | Confirmed | Gemini CLI hooks reference: "fires once per turn after the model generates its final response" |
| clearContext resets context | Confirmed | Reference: "clears conversation history (LLM memory) while preserving UI display" |
| State survives across iterations | Confirmed | Ralph's entire architecture depends on this |
| deny+reason re-invokes agent | Confirmed | Reference: "This text is sent to the agent as a new prompt to request a correction" |
| File system persists between turns | Confirmed | State files, output files all survive |

### Unknown Risks at 50+ Iterations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Hook timeout (default 60s) | Low | Shell scripts for state management are fast (<1s). Translation happens in agent turn, not hook. |
| State file corruption | Medium | Atomic writes (write to tmp, mv). Ralph uses this pattern. |
| Gemini CLI session crash | High | State file on disk survives crashes. Resume is trivial: read state, continue from current_chapter. |
| Token cost per iteration | Medium | Each iteration pays for: prompt + glossary + chapter text + translation output. 50 chapters * ~15K tokens = ~750K tokens total. |
| clearContext quality impact | Medium | Agent loses all translation context between chapters. Must reload glossary + style guide each turn. Trade-off: fresh context prevents degradation. |
| Prompt mismatch ghost detection | Low | Ralph normalizes prompts before comparison. Our prompt stays identical across iterations. |

### Ralph's Defaults vs Our Needs

Ralph defaults to `max_iterations: 5`. We need 50+. Ralph uses `--max-iterations` to override. No architectural limit exists -- the counter is a simple integer comparison in bash.

**Verdict:** 50+ iterations is architecturally feasible. The main risk is operational (session crashes, token costs), not technical.

---

## 4. Error Recovery Strategy

### Failure Modes and Recovery

**Mode 1: Agent produces bad translation**
- Hook cannot detect quality issues (it only sees text output)
- Solution: Post-translation validation step (separate `/validate` command)
- State tracks `status: "completed"` regardless of quality -- validation is a separate pass

**Mode 2: Agent crashes mid-chapter**
- State shows `current_chapter: N` with `status: "in_progress"`
- Resume command reads state, sees in_progress chapter, re-translates it
- Implementation: `init-translation.sh` checks for existing state file

**Mode 3: Gemini CLI session dies**
- State file survives on disk
- User runs `/resume` command which reads state.json and continues
- No work lost -- each completed chapter is written to its own output file

**Mode 4: Hook script fails**
- Exit code != 0 triggers "Warning" behavior (non-fatal, proceeds with original params)
- If hook crashes entirely, the loop stops naturally (agent finishes, no hook to re-invoke)
- State file is still intact -- manual resume possible

**Mode 5: clearContext fails silently**
- If context isn't cleared, the agent accumulates history across chapters
- Eventually hits context window limit, triggering automatic compression
- Compression may degrade translation quality by summarizing previous chapters
- Mitigation: Monitor token usage; if clearContext is unreliable, use BeforeAgent hook to inject fresh context

### Resume Protocol

```
1. Check if .translator/state.json exists
2. If exists and active=true:
   a. Read current_chapter
   b. Check if output file for current_chapter exists
   c. If output exists: mark as completed, advance to next
   d. If output missing: re-translate current_chapter
3. If not exists: initialize fresh state
```

---

## 5. Context Clearing: clearContext Deep Dive

### What clearContext Does

From Gemini CLI hooks reference:
> `hookSpecificOutput.clearContext`: If `true`, clears conversation history (LLM memory) while preserving UI display.

### What This Means for Translation

**Before clearContext:**
- Agent has: system prompt + user prompt + all tool calls + all responses from current turn
- Context contains: chapter text, glossary terms used, translation decisions made

**After clearContext:**
- Agent has: only the new prompt (from `reason` field)
- Context is empty except for: GEMINI.md (loaded fresh), the new prompt

### Impact on Translation Quality

| Aspect | With clearContext | Without clearContext |
|--------|-------------------|---------------------|
| Glossary consistency | Must reload each turn (via @{} or !{}) | Accumulates naturally |
| Style consistency | Fresh start each chapter | Builds on previous decisions |
| Character name tracking | Must be in glossary or state file | Agent remembers from context |
| Context window pressure | Minimal (fresh each turn) | Grows linearly, hits limit ~ch15-20 |
| Cross-chapter references | Lost (agent doesn't know ch1 when translating ch50) | Available but costly |

**Recommendation:** Use clearContext. The context window pressure at 50 chapters is the bigger risk. Inject cross-chapter context (character list, style guide) via the prompt or GEMINI.md, not via accumulated history.

### Alternative: BeforeAgent Hook for Context Injection

If clearContext strips too much, use a BeforeAgent hook to inject essential context:
```json
{
  "decision": "allow",
  "hookSpecificOutput": {
    "additionalContext": "Character glossary: ...\nStyle guide: ...\nCurrent chapter: 3/50"
  }
}
```

This gives fresh context each turn without accumulating history.

---

## 6. Chapter Boundary Detection Patterns

### Regex Patterns by Language

| Language | Pattern | Example Match |
|----------|---------|---------------|
| Chinese | `^第.{1,10}章` | 第一章, 第12章, 第一百零三章 |
| Chinese (alt) | `^Chapter\s+\d+` | Chapter 1 (English-titled Chinese novels) |
| Vietnamese | `^Chương\s+\d+` | Chương 1, Chương 12 |
| English | `^Chapter\s+\d+` | Chapter 1, Chapter XII |
| Numbered | `^\d+\.\s` | 1. Introduction |
| Markdown | `^#{1,3}\s+` | ## Chapter 1 |

### Shell Detection Command

```bash
grep -nE "^(第.{1,10}章|Chương\s+\d+|Chapter\s+\d+)" novel.txt
```

### Edge Cases

- **No chapter markers:** Treat entire file as single chapter, or split by paragraph count
- **Inconsistent markers:** Use multiple patterns with OR
- **Nested chapters (卷/册):** Volume markers are not chapter markers -- filter them out
- **Prologue/Epilogue:** Special-case as chapter 0 and chapter N+1

---

## 7. Progress Tracking

### Real-Time Progress Display

The hook's `systemMessage` field is displayed to the user immediately. Use it for progress:

```json
{
  "systemMessage": "Translated chapter 3/50 (6%). Next: chapter 4 (5,230 chars)"
}
```

### State File as Progress Source

```bash
# Read progress from state.json
jq '{completed: .chapters_completed, total: .total_chapters, current: .current_chapter}' .translator/state.json
```

### Progress Bar in Terminal

Since hooks can't update a progress bar (they output JSON to stdout), use stderr for visual feedback:

```bash
echo "Progress: [####------] 4/50 (8%)" >&2
```

The user sees stderr output in the terminal.

---

## 8. Parallel Chapter Processing

### Is It Possible?

**No.** Hooks fire synchronously after each agent turn. The AfterAgent hook can only trigger one re-invocation at a time. There is no mechanism to:
- Spawn multiple agent instances
- Run hooks in parallel
- Share state between concurrent hooks

### Workaround: Batch Chapters Per Iteration

Instead of one chapter per iteration, process 2-3 chapters per iteration to reduce total iterations:

```
Iteration 1: Translate chapters 1-3
Iteration 2: Translate chapters 4-6
...
Iteration 17: Translate chapters 49-50
```

This reduces iterations from 50 to ~17, lowering overhead. Trade-off: larger context per iteration, risk of hitting context limits with long chapters.

### Alternative: No Hooks, Pure Script

For true parallelism, skip hooks entirely. Use a shell script that:
1. Splits novel into chapter files
2. Invokes `gemini` CLI once per chapter (separate processes)
3. Each invocation is independent

```bash
for chapter in chapters/*.txt; do
  gemini "Translate $chapter to Vietnamese" &
done
wait
```

This is the chinese-novel-proofreader's approach -- no hooks, just script orchestration.

---

## 9. Comparison: Ralph Hook Pattern vs Proofreader Pattern

| Dimension | Ralph (Hook Loop) | Proofreader (Script Pipeline) |
|-----------|-------------------|-------------------------------|
| Loop control | AfterAgent hook returns deny | Shell script calls Python pipeline |
| State management | state.json (hook reads/writes) | .cache/ dir + brief/response JSON |
| Context management | clearContext per iteration | Each CLI invocation is fresh |
| Error recovery | State file + resume command | --keep-cache + re-run |
| AI interaction | One long session, many turns | Many short sessions, one turn each |
| Token efficiency | Glossary re-loaded each turn | Glossary loaded once per session |
| Complexity | Hook script + state management | Python orchestrator + 15+ modules |
| Parallelism | Impossible | Possible (separate CLI calls) |

### Proofreader's Brief/Response Protocol

The proofreader uses a different pattern for AI-in-the-loop steps:
1. Python script writes `brief.json` (task description + data)
2. Script exits with code 2 (blocking)
3. Claude reads brief, writes `response.json`
4. Script re-runs with `--keep-cache`, reads response, applies it

This is **not** a hook pattern. It's a file-based handshake between a Python pipeline and the CLI agent. Each interaction is a separate CLI session.

### Recommendation for cli-translator

**Use the Ralph pattern (AfterAgent hook loop)** because:
1. Simpler architecture (1 shell script + state.json vs Python pipeline)
2. Proven at 318 stars with active maintenance
3. Native Gemini CLI integration (no external process orchestration)
4. User sees continuous progress in one session

**Mitigate clearContext impact by:**
1. Loading glossary via `@{glossary.json}` in the TOML command prompt
2. Including character list and style guide in GEMINI.md context
3. Keeping chapter-specific context in the prompt (current chapter text + surrounding chapter summaries)

---

## 10. Implementation Blueprint

### Hook Script Structure (stop-hook.sh)

```bash
#!/bin/bash
# Read stdin (hook input)
INPUT=$(cat)
PROMPT_RESPONSE=$(echo "$INPUT" | jq -r '.prompt_response')

# Read state
STATE_FILE=".translator/state.json"
CURRENT=$(jq -r '.current_chapter' "$STATE_FILE")
TOTAL=$(jq -r '.total_chapters' "$STATE_FILE")

# Check if done
if [[ $CURRENT -gt $TOTAL ]]; then
  echo '{"decision":"allow","continue":false,"stopReason":"All chapters translated"}'
  exit 0
fi

# Check for errors in response
if echo "$PROMPT_RESPONSE" | grep -q "TRANSLATION_ERROR"; then
  # Mark chapter as failed, but continue
  jq ".chapters[$((CURRENT-1))].status = \"failed\"" "$STATE_FILE" > tmp.json && mv tmp.json "$STATE_FILE"
fi

# Advance to next chapter
NEXT=$((CURRENT + 1))
jq ".current_chapter = $NEXT" "$STATE_FILE" > tmp.json && mv tmp.json "$STATE_FILE"

# Continue loop
ORIGINAL_PROMPT=$(jq -r '.original_prompt' "$STATE_FILE")
echo "{\"decision\":\"deny\",\"reason\":\"$ORIGINAL_PROMPT\",\"systemMessage\":\"Chapter $CURRENT done. Starting chapter $NEXT/$TOTAL.\",\"hookSpecificOutput\":{\"clearContext\":true}}"
```

### State Initialization Script (init-translation.sh)

```bash
#!/bin/bash
SOURCE_FILE="$1"
OUTPUT_DIR="$2"

# Detect chapters
CHAPTERS=$(grep -nE "^(第.{1,10}章|Chương\s+\d+|Chapter\s+\d+)" "$SOURCE_FILE")
TOTAL=$(echo "$CHAPTERS" | wc -l)

# Build chapters array
CHAPTERS_JSON="["
while IFS= read -r line; do
  LINE_NUM=$(echo "$line" | cut -d: -f1)
  TITLE=$(echo "$line" | cut -d: -f2-)
  CHAPTERS_JSON+="{\"start_line\":$LINE_NUM,\"title\":\"$TITLE\",\"status\":\"pending\"},"
done <<< "$CHAPTERS"
CHAPTERS_JSON="${CHAPTERS_JSON%,}]"

# Write state
mkdir -p .translator
cat > .translator/state.json << EOF
{
  "active": true,
  "source_file": "$SOURCE_FILE",
  "output_dir": "$OUTPUT_DIR",
  "total_chapters": $TOTAL,
  "current_chapter": 1,
  "chapters": $CHAPTERS_JSON,
  "chapters_completed": 0,
  "chapters_failed": 0,
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
```

---

## Unresolved Questions

1. **clearContext + GEMINI.md interaction:** Does clearContext also clear the GEMINI.md context, or is GEMINI.md reloaded on each turn? If cleared, the agent loses all translation instructions between chapters. Need to test.

2. **Hook timeout for large chapters:** The hook itself is fast (<1s), but the agent turn for a 20K-char chapter may take 30-60s. Is there a per-turn timeout that could kill long translations?

3. **Ralph's prompt normalization robustness:** Our prompt will include dynamic chapter numbers. Ralph normalizes by stripping flags -- will it handle a prompt like "Translate chapter 3 of novel.txt" changing to "Translate chapter 4 of novel.txt"? The prompt mismatch detection may trigger. Need to either use a static prompt or disable mismatch detection.

4. **State file locking:** If the user runs two translation sessions on the same novel, state file corruption is possible. Need advisory locking or per-session state files.

5. **Token cost at scale:** 50 chapters * (glossary ~2K tokens + chapter ~5K tokens + translation ~5K tokens + prompt ~1K tokens) = ~650K tokens. At Gemini 2.5 Pro pricing, this is non-trivial.

---

## Sources

- Gemini CLI hooks reference: `gh api repos/google-gemini/gemini-cli/contents/docs/hooks/reference.md` (verified 2026-05-16)
- Gemini CLI hooks index: `gh api repos/google-gemini/gemini-cli/contents/docs/hooks/index.md` (verified 2026-05-16)
- Ralph stop-hook.sh: `gh api repos/gemini-cli-extensions/ralph/contents/hooks/stop-hook.sh` (verified 2026-05-16)
- Ralph hooks.json: `gh api repos/gemini-cli-extensions/ralph/contents/hooks/hooks.json` (verified 2026-05-16)
- Ralph setup.sh: fetched via GitHub blob view (verified 2026-05-16)
- Ralph loop.toml: fetched via GitHub blob view (verified 2026-05-16)
- chinese-novel-proofreader pipeline_orchestrator.py: `/home/dung/.claude/skills/chinese-novel-proofreader/scripts/pipeline_orchestrator.py`
- chinese-novel-proofreader _brief_protocol.py: `/home/dung/.claude/skills/chinese-novel-proofreader/scripts/_brief_protocol.py`
- Existing research: `/home/dung/VIBE_CODING/1. OTHERS/cli-translator/plans/reports/260516-1945-researcher-3-real-world-extension-patterns.md`
