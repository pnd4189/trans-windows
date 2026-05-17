#!/bin/bash
# AfterAgent hook for chapter translation loop
# Pattern: deny+clearContext to continue, allow+stop to end
set -uo pipefail

# Read hook input from stdin
INPUT=$(cat)
PROMPT_RESPONSE=$(echo "$INPUT" | jq -r '.prompt_response // ""')
ORIGINAL_PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""')

# --- Context gate: only fire when this turn was initiated by /cli-tran ---
# Gemini CLI AfterAgent hooks fire on EVERY agent turn across ALL active extensions.
# Without this gate, responses from unrelated extensions (e.g. pdf-convert) will
# be processed as if they were chapter translations, marking chapters failed.
if ! echo "$ORIGINAL_PROMPT" | grep -qE "init-translation\.py|Now translate chapter" 2>/dev/null; then
    echo '{"decision":"allow","continue":true}'
    exit 0
fi

# --- Locate state file ---
SOURCE_FILE=""
STATE_FILE=""

# Strategy 0: Read path from temp file written by init script (most reliable)
if [[ -f /tmp/.cli-tran-state-path ]]; then
    CANDIDATE=$(cat /tmp/.cli-tran-state-path 2>/dev/null || true)
    if [[ -n "$CANDIDATE" && -f "$CANDIDATE" ]]; then
        STATE_FILE="$CANDIDATE"
    fi
fi

# Strategy 1: Extract file path from expanded TOML prompt
# The prompt contains: "!python3 scripts/init-translation.py @/path/to/file.txt"
# {{args}} is replaced with the user's arguments before the hook runs
INIT_LINE=$(echo "$ORIGINAL_PROMPT" | grep -oP 'init-translation\.py\s+\K.*' | head -1 || true)
if [[ -n "$INIT_LINE" ]]; then
    SOURCE_FILE=$(echo "$INIT_LINE" | sed 's/^@//; s/\\ / /g')
fi

# Verify file exists
if [[ -n "$SOURCE_FILE" && -f "$SOURCE_FILE" ]]; then
    SOURCE_DIR=$(dirname "$SOURCE_FILE")
    STATE_FILE="$SOURCE_DIR/.translator/state.json"
fi

# Strategy 2: Check agent response for explicit state file path
if [[ -z "$STATE_FILE" || ! -f "$STATE_FILE" ]]; then
    RESPONSE_PATH=$(echo "$PROMPT_RESPONSE" | grep -oP '(?<=State file: )\S+' | head -1 || true)
    if [[ -n "$RESPONSE_PATH" && -f "$RESPONSE_PATH" ]]; then
        STATE_FILE="$RESPONSE_PATH"
    fi
fi

# Strategy 3: Check common absolute paths
if [[ -z "$STATE_FILE" || ! -f "$STATE_FILE" ]]; then
    for candidate in \
        "$HOME/.translator/state.json" \
        ".translator/state.json"; do
        if [[ -f "$candidate" ]]; then
            STATE_FILE="$candidate"
            break
        fi
    done
fi

# Final check — fail open (not a translation session)
if [[ ! -f "$STATE_FILE" ]]; then
    echo '{"decision":"allow","continue":true}'
    exit 0
fi

# Read state
CURRENT=$(jq -r '.current_chapter' "$STATE_FILE")
TOTAL=$(jq -r '.total_chapters' "$STATE_FILE")
ACTIVE=$(jq -r '.active' "$STATE_FILE")

# Not a translation session — fail open
if [[ "$ACTIVE" != "true" ]]; then
    echo '{"decision":"allow","continue":true}'
    exit 0
fi

# Already past all chapters — stop
if [[ "$CURRENT" -gt "$TOTAL" ]]; then
    COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
    rm -f /tmp/.cli-tran-state-path
    echo "{\"decision\":\"allow\",\"continue\":false,\"stopReason\":\"All chapters translated\",\"systemMessage\":\"Translation complete! $COMPLETED/$TOTAL chapters translated.\"}"
    exit 0
fi

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
NEXT=$((CURRENT + 1))
IDX=$((CURRENT - 1))

# --- Quota Detection (before completion check) ---
TAIL=$(echo "$PROMPT_RESPONSE" | tail -20)

# RPD (daily quota) — true exhaustion, cascade to next model
if echo "$TAIL" | grep -qE "Daily quota|quota will reset|Requests per day" 2>/dev/null; then
    TMP="$STATE_FILE.tmp"
    jq --arg now "$NOW" \
       '.quota_exhausted = true | .last_updated = $now' \
       "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"
    COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
    echo "{\"decision\":\"allow\",\"continue\":false,\"stopReason\":\"Daily quota exhausted\",\"systemMessage\":\"Chapter $CURRENT: daily quota exhausted ($COMPLETED/$TOTAL done). Switching model.\"}"
    exit 0
fi

# RPM (rate limit) — transient, retry same chapter
if echo "$TAIL" | grep -qE "Per-minute quota|rateLimitExceeded|Rate limit exceeded" 2>/dev/null; then
    REASON_RPM=$(echo "$ORIGINAL_PROMPT" | jq -Rs '.')
    echo "{\"decision\":\"deny\",\"reason\":$REASON_RPM,\"systemMessage\":\"Chapter $CURRENT: rate limit hit, retrying...\",\"hookSpecificOutput\":{\"clearContext\":true}}"
    exit 0
fi

# --- Completion Marker + Output File Check ---
# Marker alone is insufficient: Gemini can hallucinate the marker without
# calling write_file. We require BOTH the marker AND the actual output file
# to exist before marking the chapter completed.
TMP="$STATE_FILE.tmp"
BAK="$STATE_FILE.bak"
LOG_FILE="$(dirname "$STATE_FILE")/hook.log"
OUTPUT_DIR_NOW=$(jq -r '.output_dir' "$STATE_FILE")
EXPECTED_OUTPUT=$(printf "%s/chapter_%03d.txt" "$OUTPUT_DIR_NOW" "$CURRENT")

MARKER_FOUND=false
FILE_FOUND=false
if echo "$PROMPT_RESPONSE" | grep -q "CHAPTER_TRANSLATION_COMPLETE" 2>/dev/null; then
    MARKER_FOUND=true
fi
if [[ -s "$EXPECTED_OUTPUT" ]]; then
    FILE_FOUND=true
fi

if [[ "$MARKER_FOUND" == "true" && "$FILE_FOUND" == "true" ]]; then
    # Success: mark completed, advance
    jq --arg now "$NOW" \
       --argjson idx "$IDX" \
       --argjson next "$NEXT" \
       --arg outfile "$EXPECTED_OUTPUT" \
       '
       .chapters[$idx].status = "completed" |
       .chapters[$idx].translated_at = $now |
       .chapters[$idx].output_file = $outfile |
       .chapters_completed = (.chapters_completed + 1) |
       .current_chapter = $next |
       .last_updated = $now
       ' "$STATE_FILE" > "$TMP"
    cp "$STATE_FILE" "$BAK"
    mv "$TMP" "$STATE_FILE"
    {
        echo "[$NOW] Chapter $CURRENT: marker+file OK -> completed. advance to $NEXT."
    } >> "$LOG_FILE"
else
    # Failure: marker missing OR output file missing/empty. HALT loop.
    if [[ "$MARKER_FOUND" == "true" ]]; then
        FAIL_REASON="marker present but output file missing or empty: $EXPECTED_OUTPUT"
    elif [[ "$FILE_FOUND" == "true" ]]; then
        FAIL_REASON="output file written but completion marker missing in response"
    else
        FAIL_REASON="marker missing and no output file written"
    fi
    jq --arg now "$NOW" \
       --argjson idx "$IDX" \
       '
       .chapters[$idx].status = "failed" |
       .chapters[$idx].translated_at = $now |
       .chapters_failed = (.chapters_failed + 1) |
       .last_updated = $now |
       .active = false
       ' "$STATE_FILE" > "$TMP"
    cp "$STATE_FILE" "$BAK"
    mv "$TMP" "$STATE_FILE"
    {
        echo "[$NOW] Chapter $CURRENT: FAILED ($FAIL_REASON). Last 30 lines of response:"
        echo "$PROMPT_RESPONSE" | tail -30
        echo "---"
    } >> "$LOG_FILE"
    COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
    rm -f /tmp/.cli-tran-state-path
    jq -n --arg current "$CURRENT" \
          --arg completed "$COMPLETED" \
          --arg total "$TOTAL" \
          --arg log "$LOG_FILE" \
          --arg reason "$FAIL_REASON" \
          '{
            decision: "allow",
            continue: false,
            stopReason: ("Chapter \($current) failed - loop halted"),
            systemMessage: ("Chapter \($current) failed: \($reason). Stopped at \($completed)/\($total). See \($log). Re-run /cli-tran <file> to retry from chapter \($current).")
          }'
    exit 0
fi

# Check if done
if [[ $NEXT -gt $TOTAL ]]; then
    jq '.active = false' "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"
    COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
    rm -f /tmp/.cli-tran-state-path

    # Merge per-chapter files into a single output, delete parts
    MERGE_SCRIPT="$(dirname "$(dirname "$(readlink -f "$0")")")/scripts/merge-chapters.py"
    MERGE_OUT=""
    if [[ -f "$MERGE_SCRIPT" ]]; then
        MERGE_OUT=$(python3 "$MERGE_SCRIPT" "$STATE_FILE" 2>&1 || true)
        echo "[$NOW] Merge result: $MERGE_OUT" >> "$LOG_FILE"
    fi

    jq -n --arg completed "$COMPLETED" \
          --arg total "$TOTAL" \
          --arg merge "$MERGE_OUT" \
          '{
            decision: "allow",
            continue: false,
            stopReason: "All chapters translated",
            systemMessage: ("Translation complete! \($completed)/\($total) chapters translated. \($merge)")
          }'
    exit 0
fi

# --- Build system message with chapter details for re-invocation ---
# Read next chapter metadata from state (single jq call for efficiency)
NEXT_META=$(jq -r ".chapters[$NEXT - 1] | [.title, .start_line, .end_line] | @tsv" "$STATE_FILE")
NEXT_TITLE=$(echo "$NEXT_META" | cut -f1)
NEXT_START=$(echo "$NEXT_META" | cut -f2)
NEXT_END=$(echo "$NEXT_META" | cut -f3)
SOURCE_FILE_PATH=$(jq -r '.source_file' "$STATE_FILE")
OUTPUT_DIR_PATH=$(jq -r '.output_dir' "$STATE_FILE")
NEXT_PADDED=$(printf "chapter_%03d.txt" "$NEXT")

# Continue loop — clear context and re-invoke with explicit chapter instructions
# Use jq to build the entire JSON output safely (handles special chars in titles)
COMPLETED=$(jq -r '.chapters_completed' "$STATE_FILE")
PERCENT=$((COMPLETED * 100 / TOTAL))
jq -n --arg reason "$ORIGINAL_PROMPT" \
      --arg current "$CURRENT" \
      --arg next "$NEXT" \
      --arg completed "$COMPLETED" \
      --arg total "$TOTAL" \
      --arg percent "$PERCENT" \
      --arg title "$NEXT_TITLE" \
      --arg src "$SOURCE_FILE_PATH" \
      --arg start "$NEXT_START" \
      --arg end "$NEXT_END" \
      --arg outdir "$OUTPUT_DIR_PATH" \
      --arg outfile "$NEXT_PADDED" \
      '{
        decision: "deny",
        reason: $reason,
        systemMessage: ("Chapter \($current) done (\($completed)/\($total), \($percent)%). Now translate chapter \($next): \"\($title)\".\nSource file: \($src) (lines \($start)-\($end))\nOutput file: \($outdir)/\($outfile)\nInstructions: Read lines \($start)-\($end) from the source file. Translate to Vietnamese. Write result to the output file. End your response with EXACTLY: CHAPTER_TRANSLATION_COMPLETE"),
        hookSpecificOutput: { clearContext: true }
      }'
