---
phase: 2
title: "Hook Loop Control"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 2: Hook Loop Control

## Overview

Implement the AfterAgent hook that controls the chapter-by-chapter translation loop. Based on Ralph extension's proven pattern: hook returns `deny + clearContext: true` to continue, `allow + continue: false` to stop.

## Requirements

- Functional: Loop continues after each chapter, stops when all done, resumes after crash
- Non-functional: Hook executes in <1s, state survives crashes, clearContext prevents context overflow

## Architecture

```
hooks/
├── hooks.json               ← Hook registration
└── translate-hook.sh         ← AfterAgent hook script

Flow:
1. Model translates chapter N, writes output, updates state.json
2. AfterAgent hook fires
3. Hook reads state.json via jq
4. If current_chapter < total_chapters:
   - Increment current_chapter
   - Return {"decision":"deny","reason":"<original prompt>","hookSpecificOutput":{"clearContext":true}}
   - Context wiped, model starts fresh with new prompt
5. If all chapters done:
   - Return {"decision":"allow","continue":false,"stopReason":"All chapters translated"}
   - Loop ends
```

### Hook Protocol (Verified from Gemini CLI Source)

**Input (stdin JSON):**
```json
{
  "session_id": "...",
  "prompt": "the user's original request",
  "prompt_response": "the agent's final text output",
  "hook_event_name": "AfterAgent",
  "timestamp": "..."
}
```

**Output (stdout JSON) — Continue:**
```json
{
  "decision": "deny",
  "reason": "<original prompt text>",
  "systemMessage": "Chapter 3 done. Starting chapter 4/50.",
  "hookSpecificOutput": {
    "clearContext": true
  }
}
```

**Output (stdout JSON) — Stop:**
```json
{
  "decision": "allow",
  "continue": false,
  "stopReason": "All chapters translated",
  "systemMessage": "Translation complete! 50/50 chapters translated."
}
```

## Related Code Files

- Create: `hooks/hooks.json`
- Create: `hooks/translate-hook.sh`
- Read: `.translator/state.json` (created in Phase 1)

## Implementation Steps

### 2.1 Create hooks/hooks.json

```json
{
  "hooks": {
    "AfterAgent": [{
      "matcher": "*",
      "hooks": [{
        "name": "translate-loop",
        "type": "command",
        "command": "${extensionPath}/hooks/translate-hook.sh"
      }]
    }]
  }
}
```

### 2.2 Create hooks/translate-hook.sh

Core loop logic (bash + jq):

```bash
#!/bin/bash
# AfterAgent hook for chapter translation loop
# Based on Ralph extension pattern

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)
PROMPT_RESPONSE=$(echo "$INPUT" | jq -r '.prompt_response // ""')
ORIGINAL_PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""')

# State file location
STATE_FILE=".translator/state.json"

# Check if state file exists
if [[ ! -f "$STATE_FILE" ]]; then
  echo '{"decision":"allow","continue":false,"stopReason":"No state file found"}'
  exit 0
fi

# Read state
CURRENT=$(jq -r '.current_chapter' "$STATE_FILE")
TOTAL=$(jq -r '.total_chapters' "$STATE_FILE")
ACTIVE=$(jq -r '.active' "$STATE_FILE")

# Check if translation is active
if [[ "$ACTIVE" != "true" ]]; then
  echo '{"decision":"allow","continue":false,"stopReason":"Translation not active"}'
  exit 0
fi

# Check if current chapter was completed (look for completion marker in response)
if echo "$PROMPT_RESPONSE" | grep -q "CHAPTER_TRANSLATION_COMPLETE"; then
  # Mark current chapter as completed
  jq ".chapters[$((CURRENT-1))].status = \"completed\"" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
  
  # Update counters
  COMPLETED=$(jq '.chapters_completed' "$STATE_FILE")
  jq ".chapters_completed = $((COMPLETED + 1))" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
  
  # Advance to next chapter
  NEXT=$((CURRENT + 1))
  jq ".current_chapter = $NEXT" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
  
  # Update timestamp
  jq ".last_updated = \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
else
  # Chapter not completed — mark as failed, but continue to next
  jq ".chapters[$((CURRENT-1))].status = \"failed\"" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
  
  FAILED=$(jq '.chapters_failed' "$STATE_FILE")
  jq ".chapters_failed = $((FAILED + 1))" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
  
  NEXT=$((CURRENT + 1))
  jq ".current_chapter = $NEXT" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
fi

# Check if done
NEXT=$(jq -r '.current_chapter' "$STATE_FILE")
if [[ $NEXT -gt $TOTAL ]]; then
  jq ".active = false" "$STATE_FILE" > tmp_state.json
  mv tmp_state.json "$STATE_FILE"
  
  COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
  echo "{\"decision\":\"allow\",\"continue\":false,\"stopReason\":\"All chapters translated\",\"systemMessage\":\"Translation complete! $COMPLETED/$TOTAL chapters translated.\"}"
  exit 0
fi

# Continue loop — clear context and re-invoke
COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
PERCENT=$((COMPLETED * 100 / TOTAL))
echo "{\"decision\":\"deny\",\"reason\":\"$ORIGINAL_PROMPT\",\"systemMessage\":\"Chapter $CURRENT done ($COMPLETED/$TOTAL, $PERCENT%). Starting chapter $NEXT.\",\"hookSpecificOutput\":{\"clearContext\":true}}"
```

### 2.3 Error Handling

- **State file missing**: Stop loop, report error
- **State file corrupted**: Stop loop, report error (manual recovery needed)
- **Chapter marked failed**: Log failure, advance to next chapter
- **Hook script crashes**: Exit code != 0 triggers warning, loop stops naturally
- **clearContext fails**: Agent accumulates context, eventually hits compression — graceful degradation

### 2.4 Resume Protocol

When user runs `/resume`:
1. Check if `.translator/state.json` exists
2. If exists and `active: true`:
   - Read `current_chapter`
   - Check if output file for current chapter exists
   - If output exists: mark as completed, advance to next
   - If output missing: re-translate current chapter
3. If not exists: error — no translation in progress

### 2.5 Prompt Mismatch Issue

Ralph's ghost detection compares current prompt vs `original_prompt` in state.json. If our prompt changes per chapter (e.g., "Translate chapter 3" vs "Translate chapter 4"), the mismatch detection may kill the loop.

**Solution:** Use a STATIC prompt that doesn't change per chapter. The model reads `state.json` to know which chapter to translate — the prompt itself stays identical.

## Success Criteria

- [ ] `hooks/hooks.json` registers AfterAgent hook correctly
- [ ] `translate-hook.sh` reads state.json and makes correct continue/stop decision
- [ ] Loop continues after chapter completion (deny + clearContext returned)
- [ ] Loop stops when all chapters done (allow + continue:false returned)
- [ ] Progress displayed in systemMessage (e.g., "Chapter 3 done (3/50, 6%)")
- [ ] Failed chapters logged but don't stop the loop
- [ ] Static prompt used (no dynamic chapter numbers in prompt)
- [ ] Hook executes in <1 second

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| clearContext clears GEMINI.md too | HIGH | Test: if yes, use BeforeAgent hook to re-inject context |
| Prompt mismatch triggers ghost detection | HIGH | Use static prompt, model reads state.json for chapter info |
| State file corruption | MEDIUM | Atomic writes (tmp + mv) |
| Hook timeout | LOW | Hook is fast (<1s), translation happens in agent turn |
| 50+ iterations untested | MEDIUM | Ralph proven at 5, we need 50+ — test early |

## Security Considerations

- Hook reads local state file only (no network)
- No user input in shell commands (no injection risk)
- State file is local project data

## Next Steps

- Phase 3 can run in parallel: Glossary system independent of hook
- Phase 4 depends on this: Translation engine uses the loop mechanism
