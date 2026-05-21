#!/usr/bin/env bash
# auto-translate.sh — External driver for cli-translator (pdf-convert pattern).
#
# Lifecycle:
#   1. Read state pointer at /tmp/.cli-tran-state-path
#   2. While the novel has pending chapters:
#        a. select-cascade.py picks gemini-flash or agy
#        b. translate-chapter.py runs ONE subprocess per chapter
#        c. advance-chapter.py validates output and advances state
#        d. on backend quota errors, mark backend dead and re-pick
#   3. Emit a final summary line for the calling skill to surface.
#
# The driver is meant to be invoked from the cli-tran slash command. It runs
# entirely outside the agent's turn context: every Gemini/Antigravity call is
# a separate process with its own bounded prompt, so the loop scales to ~500
# chapters without blowing the parent session's context window.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
POINTER="${CLI_TRAN_STATE_POINTER:-/tmp/.cli-tran-state-path}"

# Sensible upper bounds so a runaway loop cannot pin the machine forever.
MAX_TOTAL_CHAPTERS="${CLI_TRAN_MAX_CHAPTERS:-600}"
MAX_RETRIES_PER_CHAPTER="${CLI_TRAN_MAX_RETRIES:-5}"
CHAPTER_COOLDOWN_SECS="${CLI_TRAN_COOLDOWN:-2}"

log() {
    printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
    log "FATAL: $*" >&2
    exit 1
}

# --- Resolve state file ---
if [[ ! -f "$POINTER" ]]; then
    die "no active translation (pointer $POINTER missing). Run /cli-tran <file> first."
fi
STATE_FILE=$(cat "$POINTER" 2>/dev/null || true)
[[ -n "$STATE_FILE" && -f "$STATE_FILE" ]] || die "state file from $POINTER is not readable: $STATE_FILE"

NOVEL_DIR=$(dirname "$STATE_FILE")
DRIVER_LOG="$NOVEL_DIR/driver.log"
HOOK_LOG="$NOVEL_DIR/hook.log"
mkdir -p "$NOVEL_DIR"

log "Driver start. State=$STATE_FILE" | tee -a "$DRIVER_LOG"

processed_count=0

# --- Helper: read JSON value via python (jq may not be guaranteed) ---
state_json_query() {
    "$PYTHON" - "$STATE_FILE" "$1" <<'PY' 2>/dev/null || echo ""
import json, sys
state = json.loads(open(sys.argv[1], encoding='utf-8').read())
path = sys.argv[2].split('.')
cur = state
for p in path:
    if p.isdigit():
        cur = cur[int(p)]
    else:
        cur = cur.get(p)
    if cur is None:
        break
print(cur if cur is not None else "")
PY
}

active=$(state_json_query "active")
if [[ "$active" != "True" && "$active" != "true" ]]; then
    log "Novel state.active=false. Nothing to do." | tee -a "$DRIVER_LOG"
    exit 0
fi

# --- Main loop ---
while :; do
    # Refresh state every iteration -- advance-chapter.py mutates it.
    if [[ ! -f "$STATE_FILE" ]]; then
        die "state file vanished mid-run: $STATE_FILE"
    fi
    active=$(state_json_query "active")
    if [[ "$active" != "True" && "$active" != "true" ]]; then
        log "Novel marked inactive. Loop ends." | tee -a "$DRIVER_LOG"
        break
    fi

    # Determine the next pending chapter using Python (handles skipped + completed).
    next_meta=$("$PYTHON" - "$STATE_FILE" <<'PY'
import json, sys
state = json.loads(open(sys.argv[1], encoding='utf-8').read())
for ch in state.get("chapters", []):
    if ch.get("status") not in {"completed", "skipped"}:
        print(json.dumps({"id": ch["id"], "display_id": ch.get("display_id", ch["id"]),
                          "title": ch.get("title", ""),
                          "retry_count": ch.get("retry_count", 0)}))
        sys.exit(0)
print("")
PY
)
    if [[ -z "$next_meta" ]]; then
        log "All chapters terminal. Loop complete." | tee -a "$DRIVER_LOG"
        break
    fi

    chapter_id=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])['id'])" "$next_meta")
    display_id=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])['display_id'])" "$next_meta")
    title=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1])['title'])" "$next_meta")

    if [[ "$processed_count" -ge "$MAX_TOTAL_CHAPTERS" ]]; then
        log "Hit MAX_TOTAL_CHAPTERS=$MAX_TOTAL_CHAPTERS; halting safety stop." | tee -a "$DRIVER_LOG"
        break
    fi

    # --- Pick backend ---
    cascade_json=$("$PYTHON" "$SCRIPT_DIR/select-cascade.py" --state "$STATE_FILE" --json 2>/dev/null || echo '{"backend":"","reason":"selector error"}')
    backend=$("$PYTHON" -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('backend',''))" "$cascade_json")
    if [[ -z "$backend" ]]; then
        log "All backends exhausted; halting until quota refreshes. Detail: $cascade_json" | tee -a "$DRIVER_LOG"
        break
    fi

    model="gemini-2.5-flash"
    [[ "$backend" == "agy" ]] && model="(antigravity-active)"

    log "Chapter $chapter_id (display $display_id) [$title] via $backend/$model" | tee -a "$DRIVER_LOG"

    # --- Translate ---
    translate_result=$("$PYTHON" "$SCRIPT_DIR/translate-chapter.py" \
        --state "$STATE_FILE" \
        --chapter "$chapter_id" \
        --backend "$backend" \
        --model "$model" 2>>"$DRIVER_LOG" || true)

    if [[ -z "$translate_result" ]]; then
        translate_result='{"status":"retry","fail_reason":"empty translator stdout"}'
    fi

    status=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "$translate_result" 2>/dev/null || echo "")
    fail_reason=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1]).get('fail_reason',''))" "$translate_result" 2>/dev/null || echo "")
    output_file=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1]).get('output_file',''))" "$translate_result" 2>/dev/null || echo "")

    case "$status" in
        ok)
            log "  -> translated, validating..." | tee -a "$DRIVER_LOG"
            advance_result=$("$PYTHON" "$SCRIPT_DIR/advance-chapter.py" \
                --state "$STATE_FILE" \
                --chapter "$chapter_id" \
                --output-file "$output_file" 2>>"$DRIVER_LOG" || true)
            action=$("$PYTHON" -c "import json,sys; print(json.loads(sys.argv[1]).get('action',''))" "$advance_result" 2>/dev/null || echo "")
            log "  advance action=$action ($advance_result)" | tee -a "$DRIVER_LOG"
            ;;
        cascade)
            log "  -> backend $backend exhausted: $fail_reason. Marking + retrying." | tee -a "$DRIVER_LOG"
            "$PYTHON" "$SCRIPT_DIR/select-cascade.py" --state "$STATE_FILE" --mark-fail "$backend" >/dev/null 2>&1 || true
            sleep "$CHAPTER_COOLDOWN_SECS"
            continue
            ;;
        retry)
            log "  -> transient failure: $fail_reason. Advancing retry counter." | tee -a "$DRIVER_LOG"
            "$PYTHON" "$SCRIPT_DIR/advance-chapter.py" \
                --state "$STATE_FILE" \
                --chapter "$chapter_id" \
                --output-file "${output_file:-/dev/null}" \
                --fail-reason "$fail_reason" >/dev/null 2>>"$DRIVER_LOG" || true
            ;;
        fatal)
            log "  -> fatal: $fail_reason. Halting." | tee -a "$DRIVER_LOG"
            break
            ;;
        *)
            log "  -> unknown translator status='$status' result=$translate_result" | tee -a "$DRIVER_LOG"
            "$PYTHON" "$SCRIPT_DIR/advance-chapter.py" \
                --state "$STATE_FILE" \
                --chapter "$chapter_id" \
                --output-file "/dev/null" \
                --fail-reason "unknown translator status" >/dev/null 2>>"$DRIVER_LOG" || true
            ;;
    esac

    processed_count=$((processed_count + 1))
    sleep "$CHAPTER_COOLDOWN_SECS"
done

# --- Final summary ---
final=$("$PYTHON" - "$STATE_FILE" <<'PY'
import json, sys
s = json.loads(open(sys.argv[1], encoding='utf-8').read())
total = s.get("total_chapters", 0)
done = s.get("chapters_completed", 0)
fail = s.get("chapters_failed", 0)
active = s.get("active", False)
pending = sum(1 for ch in s.get("chapters", [])
              if ch.get("status") not in {"completed", "skipped"})
print(json.dumps({"total": total, "completed": done, "skipped": fail,
                  "pending": pending, "active": active}))
PY
)
log "Driver done. Summary=$final" | tee -a "$DRIVER_LOG"

# Emit a human-readable line on stdout for the slash command to surface.
FINAL="$final" DRIVER_LOG_PATH="$DRIVER_LOG" "$PYTHON" - <<'PY'
import json, os
d = json.loads(os.environ["FINAL"])
status = "complete" if not d["active"] else "paused"
print(f"Translation {status}: {d['completed']}/{d['total']} chapters done, "
      f"{d['skipped']} skipped, {d['pending']} pending. "
      f"Log: {os.environ['DRIVER_LOG_PATH']}")
PY
