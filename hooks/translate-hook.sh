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
IDX=$((CURRENT - 1))

# Check completion marker at END of response only (last 5 lines)
# Prevents false matches if source text contains the marker
TAIL=$(echo "$PROMPT_RESPONSE" | tail -5)
if echo "$TAIL" | grep -q "CHAPTER_TRANSLATION_COMPLETE"; then
  STATUS="completed"
  COMPLETED_DELTA=1
  FAILED_DELTA=0
else
  STATUS="failed"
  COMPLETED_DELTA=0
  FAILED_DELTA=1
fi

# Atomic state update: all mutations in single jq call, safe temp file via mktemp
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

# Use jq --arg for safe string interpolation (prevents injection via chapter titles)
jq --arg status "$STATUS" \
   --arg now "$NOW" \
   --argjson idx "$IDX" \
   --argjson next "$NEXT" \
   --argjson completed_delta "$COMPLETED_DELTA" \
   --argjson failed_delta "$FAILED_DELTA" \
   '
   .chapters[$idx].status = $status |
   .chapters[$idx].translated_at = $now |
   .chapters_completed = (.chapters_completed + $completed_delta) |
   .chapters_failed = (.chapters_failed + $failed_delta) |
   .current_chapter = $next |
   .last_updated = $now
   ' "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"

# Check if done (NEXT > TOTAL means we just finished the last chapter)
if [[ $NEXT -gt $TOTAL ]]; then
  jq '.active = false' "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"

  COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
  echo "{\"decision\":\"allow\",\"continue\":false,\"stopReason\":\"All chapters translated\",\"systemMessage\":\"Translation complete! $COMPLETED/$TOTAL chapters translated.\"}"
  exit 0
fi

# Continue loop — clear context and re-invoke
# Use jq -Rs to safely escape the prompt for JSON output
REASON=$(echo "$ORIGINAL_PROMPT" | jq -Rs '.')
COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
PERCENT=$((COMPLETED * 100 / TOTAL))
echo "{\"decision\":\"deny\",\"reason\":$REASON,\"systemMessage\":\"Chapter $CURRENT done ($COMPLETED/$TOTAL, $PERCENT%). Starting chapter $NEXT.\",\"hookSpecificOutput\":{\"clearContext\":true}}"
