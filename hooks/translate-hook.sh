#!/bin/bash
# AfterAgent hook for chapter translation loop
# Based on Ralph extension pattern: deny+clearContext to continue, allow+stop to end

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

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
NEXT=$((CURRENT + 1))

# Check if current chapter was completed, then update state atomically in one jq call
if echo "$PROMPT_RESPONSE" | grep -q "CHAPTER_TRANSLATION_COMPLETE"; then
  jq "
    .chapters[$((CURRENT-1))].status = \"completed\" |
    .chapters[$((CURRENT-1))].translated_at = \"$NOW\" |
    .chapters_completed = (.chapters_completed + 1) |
    .current_chapter = $NEXT |
    .last_updated = \"$NOW\"
  " "$STATE_FILE" > tmp_state.json && mv tmp_state.json "$STATE_FILE"
else
  jq "
    .chapters[$((CURRENT-1))].status = \"failed\" |
    .chapters_failed = (.chapters_failed + 1) |
    .current_chapter = $NEXT |
    .last_updated = \"$NOW\"
  " "$STATE_FILE" > tmp_state.json && mv tmp_state.json "$STATE_FILE"
fi

# Check if done (NEXT > TOTAL means we just finished the last chapter)
if [[ $NEXT -gt $TOTAL ]]; then
  jq ".active = false" "$STATE_FILE" > tmp_state.json && mv tmp_state.json "$STATE_FILE"

  COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
  echo "{\"decision\":\"allow\",\"continue\":false,\"stopReason\":\"All chapters translated\",\"systemMessage\":\"Translation complete! $COMPLETED/$TOTAL chapters translated.\"}"
  exit 0
fi

# Continue loop — clear context and re-invoke
COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
PERCENT=$((COMPLETED * 100 / TOTAL))
echo "{\"decision\":\"deny\",\"reason\":\"$ORIGINAL_PROMPT\",\"systemMessage\":\"Chapter $CURRENT done ($COMPLETED/$TOTAL, $PERCENT%). Starting chapter $NEXT.\",\"hookSpecificOutput\":{\"clearContext\":true}}"
