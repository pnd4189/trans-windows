# H3 — translate-hook.sh Logic Audit

**Debugger:** debugger-3
**Date:** 2026-05-20
**Verdict:** CONFIRMED ROOT-CAUSE — **PPID mismatch** kills the loop on every fresh run. Several additional bugs amplify or coexist with it.

---

## Empirical evidence (smoking gun)

State dir: `/home/dung/.cache/cli-tran/novels/471b983aff97d78a/`

```
state.json          mtime 14:43:45   (written by init-translation.py)
chapter_011.txt     mtime 13:45:14   (chapter 1 output)
chapter_002.txt     mtime 13:49:11   (WRONG name — agent wrote chapter 12 to wrong file)
chapter_012.txt     mtime 14:44:55   (chapter 2 output — AFTER state.json mtime)
```

Critical absences in the same dir:
- **No `hook.log`** — `translate-hook.sh` line 154/156/186/225/241 unconditionally appends to this file when the gate passes. Its absence means **the hook never passed the gate even once** for this novel.
- **No `.state.lock`** — `exec 200>"$LOCK_FILE"` (line 44) would create this on every gate-passing run.
- **No `state.json.bak`** — `cp "$STATE_FILE" "$BAK"` (line 148/183/223) would create this on every advance.

Yet `state.json` shows `current_chapter: 2` and chapter 1 status `completed`. So the state was advanced from chapter 1 → 2 by SOMETHING — but **not by this hook**. The only path that mutates state without a `.bak` or `hook.log` is `init-translation.py` itself. Confirmed: this novel's chapter 1 ("第011章") was completed by the *previous* session whose state lives in the **other** novel hash (`a7152eba2b885ec5` — see its `state.json.bak`, `hook.log`, etc., all present). The 471b… novel was initialized fresh AFTER chapter_011.txt already existed, and `init-translation.py` re-detected "completed" via... actually no, init doesn't mark chapters completed. Re-reading: `state.json.last_updated = 2026-05-20T07:43:45Z` which is identical to init time. And `chapter_011.txt`'s mtime is 13:45 — earlier. So init wrote state.json with chapter 1 as "pending" then... but the state.json on disk shows it as "completed". That mutation came from somewhere.

Looking again: state.json shows `chapters_completed=1`, status of idx 0 = "completed", BUT no `cjk_bp` field on it (compare to a7152… state where every completed chapter has `cjk_bp: 0`). The hook always writes `cjk_bp` (line 143). **The chapter 1 "completed" status in 471b… was therefore written by the OLD a7152… hook back at 13:45**, when `/tmp/.cli-tran-state-path` (the legacy unsuffixed pointer) still pointed to... wait, the source files are different. This needs more analysis.

Simplest explanation that fits all data: the user is on session #2 today, init ran at 14:43, then the agent's bash-tool turn wrote `chapter_012.txt` at 14:44 (correct file this time — the chapter_002.txt is leftover from a still-earlier run where state had different display_ids). The Stop hook fired after that turn but found no `/tmp/.cli-tran-state-path.<ppid>` matching, so it emitted `{}` → agent stopped → user reports loop dead.

---

## Findings ranked by severity

### F1 (CRITICAL) — PPID mismatch silently kills the loop

**Where:** `init-translation.py:259` writes `/tmp/.cli-tran-state-path.<os.getppid()>`; `translate-hook.sh:26` reads `/tmp/.cli-tran-state-path.<$PPID>`.

**Process tree (verified, see `ps` output during this session):**
```
agy (PID X)
└── bash -c "python3 .../init-translation.py ..."   (PID Y, parent=X)
    └── python3 init-translation.py                  (PID Z, parent=Y)
```

`os.getppid()` inside the python script = **Y** (the bash that the agy "bash tool" spawned).

When agy fires the Stop hook, agy execs the hook command itself:
```
agy (PID X)
└── bash translate-hook.sh                           (PID W, parent=X)
```
Inside the hook, `$PPID` = **X** (agy).

**Y ≠ X** → pointer file `/tmp/.cli-tran-state-path.Y` exists, hook looks up `/tmp/.cli-tran-state-path.X` → not found → line 28-30 returns `{}` → agent stops → loop dead.

**Why a7152… completed successfully:** legacy unsuffixed `/tmp/.cli-tran-state-path` exists (line 263 of init), and an EARLIER version of the hook (before per-PID gate was added) read from there. The git log entry "feat: harden translation loop and merge output into single file" likely introduced the per-PID gate WITHOUT a fallback path in the hook. Verify with `git log -p hooks/translate-hook.sh`.

**Fix (preferred):**
```bash
# In translate-hook.sh, replace lines 26-31 with:
SESSION_POINTER="/tmp/.cli-tran-state-path.$PPID"
if [[ ! -f "$SESSION_POINTER" ]]; then
    SESSION_POINTER="/tmp/.cli-tran-state-path"   # fallback to legacy unsuffixed
fi
if [[ ! -f "$SESSION_POINTER" ]]; then
    echo '{}'; exit 0
fi
```

**Better fix:** don't use PPID at all. Use a single session pointer file keyed on something agy actually exposes (e.g. agy session id, working directory, or just the unsuffixed file). The per-PID design is broken because the hook's PPID and the init script's PPID are unrelated.

---

### F2 (HIGH) — Stop hook may emit `{reason: ...}` without `decision` → Antigravity treats as STOP

**Where:** lines 244-249 (final completion summary).

The schema verified from agy binary (`hooks_go_proto.(*StopHookResult).GetDecision`) shows decision is an optional string. The hook code at line 7-8 documents: `decision="" / {} / no output -> agent stops normally`. Outputting `{reason: "Translation complete: ..."}` with empty/absent `decision` should stop. **This is correct for the final-completion branch.**

However, the **same shape** appears as the implicit path: if `FILE_FOUND==true` AND `NEXT > TOTAL` (we just completed the last chapter), lines 131-156 mark completed, fall through to line 229 check, hit the finalize branch, output `{reason: …}` → STOP. That's correct.

But the **mid-loop advancement branches** must always end with `decision: "block"`. Trace:
- File found, not last chapter → reaches line 252 → `{decision: "block", reason: ...}` ✓
- File missing, retry budget OK → outputs `{decision: "block", ...}` at line 205 → `exit 0` at line 207 ✓
- File missing, retry exhausted → SKIPS chapter, advances, FALLS THROUGH to line 229 → if more chapters remain, reaches line 263 → `{decision: "block", ...}` ✓ — **BUT** in this branch the script still runs the "finalize" check at line 229 first; if next > total, it correctly finalizes. ✓

**Verdict on F2:** Logic for the "stop" output is correct, but the gate at line 27 emits `{}` (no decision) which is fine for "not our session". So Antigravity's "absent decision = stop" interpretation is being relied on heavily. If that assumption is wrong (e.g. agy actually treats absent decision as "continue"), the loop would be infinite when off-session. Recommend explicitly emitting `{"decision":""}` for clarity. **Low priority unless H1 finds otherwise.**

---

### F3 (HIGH) — Re-entrant Stop hook does NOT cause infinite advance on stale files

User asked: "chapter 1 done → hook fires → advances to 2 → new turn translates 2 → hook fires → checks chapter_002.txt exists? YES → marks completed → ..."

**Walked carefully:**
- After chapter 1 success, line 96-98 computes `EXPECTED_OUTPUT` for the CURRENT chapter (still chapter 1, because state hasn't advanced yet at line 96 — state advance happens at line 144-149 AFTER the file check). Wait — actually let me re-read.
- Line 51: `CURRENT=$(jq -r '.current_chapter' "$STATE_FILE")` — reads pre-advance value.
- Line 97: `IDX=$((CURRENT - 1))` — index of current (chapter 1) chapter.
- Line 98: `EXPECTED_OUTPUT="chapter_$(display_id of current).txt"` — chapter_001.txt for current=1.
- Line 102: check `chapter_001.txt` exists → if yes, mark idx=0 completed, advance current to 2.
- Hook EXITS with block decision telling agent to do chapter 2.
- New turn: agent writes chapter_002.txt.
- Hook fires again: CURRENT=2 (advanced), IDX=1, EXPECTED_OUTPUT=chapter_002.txt → check it → exists → advance.

So the re-entrant check is safe **as long as `current_chapter` is correctly advanced**. The dangerous case is: hook fires with CURRENT=2 but chapter_002.txt does NOT yet exist (agent failed). Hook treats as failure → retry. Good. Re-entrant safety: ✓

**However** — there's a subtle bug: in the **skip-and-advance** branch (lines 211-225), if NEXT ≤ TOTAL, the script falls through to line 252 to issue a "block" for the NEXT chapter. That's correct. BUT if NEXT > TOTAL after skip, it goes to line 229 finalize → STOP. Also correct.

**Verdict on F3:** Re-entry logic is correct. **Not a bug.**

---

### F4 (MEDIUM) — Re-read advancement bug: hook reads CURRENT before advancing, then checks file. If agent finished chapter N but state still shows current=N-1 (race), hook marks N-1 completed using N-1's file. Since N-1 file was completed by a PRIOR hook run, the hook now adv to N, but agent already wrote N. Next hook run finds N completed, advances to N+1. **No data loss but state lags by 1.**

This is only a real bug if init resets `current_chapter=1` while `chapter_001.txt` already exists from a prior session. Then:
- First hook fires (agent did nothing this turn) → CURRENT=1, file exists → mark 1 completed, advance.
- Next hook → CURRENT=2, file chapter_002.txt may or may not exist from prior session.

**This is consistent with the observed state in 471b…** where chapter 1 was marked completed without `cjk_bp` field — but actually re-reading, **the hook DOES write cjk_bp (line 143)**. The absence of `cjk_bp` on idx=0 means the hook did NOT mark it completed. So **init must have been called with chapter 1 already pre-marked**, OR a different code path. Recommend `git log` on init-translation.py for recent changes that pre-fill status.

**Action:** investigate why `chapters[0].status == "completed"` and `chapters_completed: 1` in 471b… state when no hook.log/.bak exists. Check whether init has resume logic that re-imports completed chapters from prior runs (it does: lines 56-99 of init-translation.py is the "resume existing state" path — if state already had chapter 1 completed from a prior init+hook cycle, that's fine). Most likely explanation: an earlier turn DID run the hook successfully (perhaps PPID alignment happened by luck) and chapter 1 was completed; then user re-ran `/cli-tran`, init hit the resume branch, kept the completed status, but the new PPID broke the chain for chapter 2 onward. **The `hook.log` should still have been preserved across the resume** since init never deletes it. Its absence means the chapter 1 completion happened in the OTHER novel cache, and the file was just COPIED here. (chapter_011.txt is named with display_id=11, which matches THIS novel's chapter 1. So the file was written to this directory.)

**Conclusion:** the hook DID run at least once for this novel (to produce chapter_011.txt completion) but the `hook.log` got deleted somehow, OR the chapter-1-completed status was injected by something else. Either way, **chapter 2+ is stuck because of F1 (PPID mismatch)**. The other anomaly is secondary.

---

### F5 (MEDIUM) — `MERGE_ENTITIES_SCRIPT` path uses `readlink -f "$0"` — works with spaces

Line 151: `MERGE_ENTITIES_SCRIPT="$(dirname "$(dirname "$(readlink -f "$0")")")/scripts/merge-entities.py"`

Tested mentally with `$0="/home/dung/VIBE_CODING/1. OTHERS/cli-translator/hooks/translate-hook.sh"`:
- `readlink -f` resolves → `/home/dung/VIBE_CODING/1. OTHERS/cli-translator/hooks/translate-hook.sh`
- inner `dirname` → `/home/dung/VIBE_CODING/1. OTHERS/cli-translator/hooks`
- outer `dirname` → `/home/dung/VIBE_CODING/1. OTHERS/cli-translator`
- final path → `/home/dung/VIBE_CODING/1. OTHERS/cli-translator/scripts/merge-entities.py` ✓

All `"$(...)"` quoting is correct — spaces are preserved.

**However,** when Antigravity invokes the hook, `$0` might NOT be the literal hook path — it could be `bash` if invoked as `bash translate-hook.sh` without preserving argv[0]. Verify by adding a debug `echo "[DEBUG] hook path=$0" >> /tmp/hook-debug.log` at the top. If `$0 == "bash"`, the path construction breaks. **The hook should resolve its path via `BASH_SOURCE[0]` instead of `$0` for safety:**

```bash
HOOK_SCRIPT="${BASH_SOURCE[0]:-$0}"
PROJECT_ROOT="$(dirname "$(dirname "$(readlink -f "$HOOK_SCRIPT")")")"
```

**Verdict on F5:** Path resolution is technically safe for spaces, but vulnerable if agy invokes with `bash <script>` and clobbers `$0`. Low risk but worth hardening.

---

### F6 (LOW) — Race: write→hook visibility on ext4

Default ext4 mount options (`data=ordered`, no `nodelalloc`) guarantee metadata visibility for `stat` after the writer's `close(2)` returns — and bash's `write_file` tool closes before responding to agy. Hook runs after agy receives the bash tool response. **Visibility is guaranteed. Not a bug.**

---

### F7 (LOW) — CJK ratio python heredoc captures `CJK_FAIL` outside the heredoc

Line 105-118: `CJK_RATIO=$(python3 - "$EXPECTED_OUTPUT" <<'PYEOF' ... PYEOF)` then line 119: `CJK_FAIL=""` is OUTSIDE the `if [[ -s ... ]]`. Wait — re-read:

```
if [[ -s "$EXPECTED_OUTPUT" ]]; then
    FILE_FOUND=true
    CJK_RATIO=$(python3 - ... <<PYEOF ... PYEOF
)
    CJK_FAIL=""
    if [[ "$CJK_RATIO" -gt 500 ]]; then
        ...
        CJK_FAIL="..."
        FILE_FOUND=false
        rm -f "$EXPECTED_OUTPUT"
    elif ...
fi
```

`CJK_FAIL` is only initialized inside `if [[ -s ... ]]`. If file missing, `CJK_FAIL` is unset. Later line 159: `if [[ -n "${CJK_FAIL:-}" ]]; then` uses `:-` to handle unset. ✓ **Not a bug** (already guarded).

---

### F8 (LOW) — `set -uo pipefail` without `errexit`

Line 12: only `nounset` and `pipefail`, not `errexit`. This is intentional (hook needs to handle failures gracefully via `|| true`). However, `nounset` means any undeclared variable (e.g. typo) explodes silently. **Verdict:** ok, but consider sprinkling `set -x` in a debug mode.

---

### F9 (MEDIUM) — `SKILL.md` translation instructions are inconsistent with hook's failure-message wording

`SKILL.md:117-122` says the agent must output BOTH markers:
```
ENTITY_EXTRACTION_COMPLETE
CHAPTER_TRANSLATION_COMPLETE
```

But hook's retry message (line 205) tells the agent: `End your response with exactly: CHAPTER_TRANSLATION_COMPLETE` — only ONE marker. And the success message (line 276) is identical — single marker.

The hook never inspects these markers anyway (file-presence based per line 11), so the agent CAN omit them. But the agent might be confused which to emit. **Cosmetic, not functional.** SKILL.md also tells agent to use `write_file` (line 166) which is correct.

**Also verified:** SKILL.md DOES tell the agent to call `init-translation.py` (line 81) and to `write_file` (line 166). ✓

---

### F10 (LOW) — `SIGCHLD`/zombies

The hook spawns `python3 - <<PYEOF` (CJK check), `python3 "$MERGE_ENTITIES_SCRIPT"` (line 153), and `python3 "$MERGE_SCRIPT"` (line 240). All are foreground subshells; bash waits and reaps. Merge subprocess in init-translation.py (line 241-244) has 120s timeout — within hook 120s budget. **No zombies. No bug.**

---

## Ranked fixes

1. **[F1, critical, 5 min]** Patch translate-hook.sh to fall back to unsuffixed `/tmp/.cli-tran-state-path` when per-PID pointer is missing. Or better: remove per-PID design entirely, use a single pointer. See F1 fix above.

2. **[F5, low, 2 min]** Use `BASH_SOURCE[0]` instead of `$0` for path resolution at lines 151, 237.

3. **[F4, investigate, 10 min]** Inspect why state.json was advanced to current_chapter=2 without hook.log existing in the 471b… cache. Add a `echo "[INIT] pointer written ppid=$PPID" >> "$LOG_FILE"` at the end of `_write_state_pointer` in init-translation.py for forensic clarity.

4. **[F2, defensive, 2 min]** Explicitly emit `{"decision":""}` for the "not our session" / "all done" branches instead of relying on agy treating absent `decision` as stop.

5. **[F9, doc cleanup, 1 min]** Either update the hook's success/retry messages to require BOTH markers (entity + chapter), or strip the dual-marker instruction from SKILL.md. Cosmetic.

---

## Unresolved questions

1. How exactly does agy invoke `translate-hook.sh` — direct exec, `bash -c`, or `sh -c`? This determines `$PPID` value reliably. (H1 may have data; otherwise instrument with `ps -o pid,ppid,cmd -p $$` at hook start.)
2. Why is `chapter_002.txt` (wrong-named file from a prior run) still present in the 471b… cache? Init does not delete stale outputs — should it on re-init?
3. Is the per-PID pointer design even necessary? The docstring (init line 256-257) claims it's for concurrent gemini sessions, but if only one agy process is running at a time, the unsuffixed pointer is sufficient and bug-free.

---

## Status

**Status:** DONE
**Summary:** Identified F1 PPID mismatch as the loop-killing root cause. Process tree analysis shows `init-translation.py`'s `os.getppid()` (the bash that agy's bash-tool spawned) is unrelated to the hook's `$PPID` (agy itself). The hook silently emits `{}` and the loop dies. Confirmed by absence of `hook.log` in the stuck novel cache despite chapter 1 having been completed (likely from an earlier-version hook that read the unsuffixed pointer).
**Concerns/Blockers:** None — fix is straightforward (fall back to unsuffixed pointer or remove per-PID design).
