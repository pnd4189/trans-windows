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

# Check last 20 lines for quota patterns and completion markers
TAIL=$(echo "$PROMPT_RESPONSE" | tail -20)

# --- Quota Detection (before completion check) ---

# RPD (daily quota) — true exhaustion, cascade to next model
if echo "$TAIL" | grep -qE "Daily quota|quota will reset|Requests per day"; then
  TMP=$(mktemp)
  trap 'rm -f "$TMP"' EXIT
  jq --arg now "$NOW" \
     '.quota_exhausted = true | .last_updated = $now' \
     "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"
  COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
  echo "{\"decision\":\"allow\",\"continue\":false,\"stopReason\":\"Daily quota exhausted\",\"systemMessage\":\"Chapter $CURRENT: daily quota exhausted ($COMPLETED/$TOTAL done). Switching model.\"}"
  exit 0
fi

# RPM (rate limit) — transient, retry same chapter
if echo "$TAIL" | grep -qE "Per-minute quota|rateLimitExceeded|Rate limit exceeded"; then
  REASON_RPM=$(echo "$ORIGINAL_PROMPT" | jq -Rs '.')
  echo "{\"decision\":\"deny\",\"reason\":$REASON_RPM,\"systemMessage\":\"Chapter $CURRENT: rate limit hit, retrying...\",\"hookSpecificOutput\":{\"clearContext\":true}}"
  exit 0
fi

# --- Completion Marker Check ---
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

# Atomic state update: all mutations in single jq call
# Use a local temp file in the same directory as the state file to ensure atomic rename (same filesystem)
DIR=$(dirname "$STATE_FILE")
TMP="$STATE_FILE.tmp"
BAK="$STATE_FILE.bak"

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
   ' "$STATE_FILE" > "$TMP"

# Backup and move (atomic rename)
cp "$STATE_FILE" "$BAK"
mv "$TMP" "$STATE_FILE"

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
