# H1 Verdict: Antigravity Stop Hook Schema Verification

**Verdict:** SCHEMA_CORRECT (with one cosmetic stdin bug — does not block the loop)

**Date:** 2026-05-20
**Investigator:** debugger-1
**Subject:** Whether `hooks/translate-hook.sh` schema assumptions match agy binary contracts.

---

## Summary

The /cli-tran Stop-hook fix's schema is essentially correct. The hook will fire, the `decision="block"` response will re-prompt the agent, and the loop will continue. There is **one minor bug** in stdin parsing (snake_case vs camelCase) that degrades user-cancel handling and error-reason diagnostics, but it does **not** prevent the loop from advancing.

---

## Evidence Chain

All evidence extracted from `~/.local/bin/agy` (Antigravity binary, 183 MB) via `strings`.

### 1. Event name `Stop` — CORRECT

```
$ strings ~/.local/bin/agy | grep -aE '^(Stop|AfterAgent|UserPromptSubmit|PreToolUse|PostToolUse|SubagentStop|Notification|PreCompact)$' | sort -u
PostToolUse
PreToolUse
Stop
```

Only `Stop`, `PreToolUse`, `PostToolUse` exist. No `AfterAgent` (legacy Gemini-CLI event). `hooks.json` uses `"Stop"` — correct.

Side observation: `~/.gemini/antigravity-cli/plugins/maestro/hooks.json` still uses `AfterAgent`, `BeforeAgent`, `SessionStart`, `SessionEnd` — those hooks are dead under Antigravity. Not our concern.

### 2. StopHookArgs proto schema (stdin to hook) — CONFIRMED

Field tags pulled directly from compiled-in protobuf reflection metadata:

```
ExecutionNum     protobuf:"varint,1,opt,name=execution_num,json=executionNum,proto3"
FullyIdle        protobuf:"varint,4,opt,name=fully_idle,json=fullyIdle,proto3"
TerminationReason protobuf:"bytes,2,opt,name=termination_reason,json=terminationReason,proto3"
                 (note: bytes/string at this site, not enum — but values are enum string names)
Error            (proto-side getter exists: StopHookArgs.GetError)
```

Plus accessor methods confirmed:
```
(*StopHookArgs).GetExecutionNum
(*StopHookArgs).GetFullyIdle
(*StopHookArgs).GetTerminationReason
(*StopHookArgs).GetError
```

### 3. StopHookResult proto schema (stdout from hook) — CONFIRMED

```
StopHookResult struct {
  Decision string  protobuf:"bytes,1,opt,name=decision,proto3" json:"decision,omitempty"
  Reason   string  protobuf:"bytes,2,opt,name=reason,proto3"   json:"reason,omitempty"
}
```

(Inlined verbatim in `hookcaller.callHookAs[...]` generic instantiation string.)

Hook script outputs `{"decision":"block","reason":"..."}` — exact match.

### 4. Decision enum values — `"block"` is valid

```
$ strings ~/.local/bin/agy | grep -aE "^(block|allow|deny|continue|approve|skip)$" | sort -u
allow
approve
block
deny
skip
```

`"block"` is a recognized decision value. The PreToolUse/PostToolUse hook ecosystem uses `allow`/`deny`/`ask`; Stop hooks support `block` (matches Claude Code semantic: "block stop, re-prompt agent").

### 5. Loop prevention mechanism — EXISTS (`MaxForcedInvocations`)

Antigravity has an explicit re-invocation counter:

```
google3/.../posthooks/posthooks.CountForcedInvocations
(*CascadeExecutorConfig).GetMaxForcedInvocations
(*ExecutorMetadata).GetNumForcedInvocations
protobuf:"varint,10,opt,name=max_forced_invocations,...,oneof"
protobuf:"varint,5,opt,name=num_forced_invocations,..."
log: "Hit %dth forced invocation for trajectory %s"
enum: EXECUTOR_TERMINATION_REASON_MAX_FORCED_INVOCATIONS
proto field: disable_loop_detection (varint,47,oneof) — server-side opt-out
```

When the counter hits `MaxForcedInvocations`, the executor terminates with `EXECUTOR_TERMINATION_REASON_MAX_FORCED_INVOCATIONS`. Default numerical value is server-controlled (proto3 `oneof`, no default visible in client strings).

**Implication for cli-tran:** if a novel has more chapters than the server-side max-forced-invocations cap, the loop will silently die at chapter N with the executor termination reason set to MAX_FORCED_INVOCATIONS. Hook script does not currently surface this — it would fall through to the generic "output file missing" failure path and retry until budget exhausted.

Also found: `AutoContinueOnMaxGeneratorInvocations` (`autoContinueOnMaxGeneratorInvocations`) and `proceededWithAutoContinue` — there is server-side auto-continuation logic separate from hook-driven block.

### 6. Hook caller uses protojson — CONFIRMED

```
"failed to unmarshal result from hook %s via protojson: %s"
"JSON hook %q: executing command"
"JSON hook %q command failed: %w"
"JSON hook command stderr: %s"
"failed to marshal hook args: %w"
"no JSON hook handler registered for %q"
```

These strings prove agy uses **protojson** (not generic JSON) for both directions:
- stdin: `protojson.Marshal(StopHookArgs) → stdin`
- stdout: `protojson.Unmarshal(stdout, &StopHookResult)`

### 7. Key protojson default behavior

**stdin (Marshal, agy → hook):** Default `protojson.MarshalOptions{}` emits `json:` tag names = **lowerCamelCase**. Unless `UseProtoNames=true` is set, agy sends:
- `executionNum`, `fullyIdle`, `terminationReason`, `error`

I could not find a string match indicating `UseProtoNames=true` is enabled for hook marshal. Default behavior is camelCase.

**stdout (Unmarshal, hook → agy):** protojson Unmarshal **accepts both** the proto name (`decision`, `reason`) and the JSON camelCase (`decision`, `reason` are single-word, identical). Either works.

---

## The Minor Bug

`hooks/translate-hook.sh:16`:
```bash
TERMINATION_REASON=$(echo "$INPUT" | jq -r '.termination_reason // ""' 2>/dev/null || echo "")
```

If agy emits camelCase (default), this returns empty string. Confirmed with a probe:

```
$ echo '{"terminationReason": "EXECUTOR_TERMINATION_REASON_USER_CANCELED"}' | jq -r '.termination_reason // ""'
(empty)
$ echo '{"terminationReason": "EXECUTOR_TERMINATION_REASON_USER_CANCELED"}' | jq -r '.terminationReason // ""'
EXECUTOR_TERMINATION_REASON_USER_CANCELED
```

### Impact

| Site | Effect when `TERMINATION_REASON` is always empty |
|------|--------------------------------------------------|
| `translate-hook.sh:20` user-cancel check | Never matches → user Ctrl+C cannot break the loop cleanly. Hook still tries to continue. |
| `translate-hook.sh:163` `EXECUTOR_TERMINATION_REASON_ERROR` | Never matches → fall through to generic reason. Diagnostic only. |
| `translate-hook.sh:165` `EXECUTOR_TERMINATION_REASON_NO_TOOL_CALL` | Same — diagnostic only. |
| `translate-hook.sh:168` fallback message | Includes empty `(termination=)`. Cosmetic. |

**`.error` field is correctly named** — single-word fields are identical between snake_case and camelCase, so error propagation works.

### NOT impacted

- Loop continuation: works. `decision="block"` is parsed by protojson regardless of case.
- File-presence completion detection: works (independent of stdin).
- Chapter advancement, retry counting, state updates: all work.

---

## Recommended Fix

`hooks/translate-hook.sh` lines 16–17 — read both keys defensively:

```bash
TERMINATION_REASON=$(echo "$INPUT" | jq -r '.termination_reason // .terminationReason // ""' 2>/dev/null || echo "")
AGENT_ERROR=$(echo "$INPUT" | jq -r '.error // ""' 2>/dev/null || echo "")
```

Single-line change. Eliminates the camelCase-vs-snake_case fragility for now and forever, with no downside.

---

## Probe Approach (for stricter verification, NOT executed)

To definitively prove the marshal casing, drop in a non-installed probe hook:

```bash
#!/bin/bash
# /tmp/probe-stop-hook.sh
exec >>/tmp/antigravity-stop-probe.log 2>&1
echo "--- $(date -u +%FT%TZ) ---"
echo "STDIN_RAW:"
tee /tmp/last-stop-stdin.json
echo
echo "Replying with {} (no-op)"
echo '{}'
```

Then temporarily point `hooks.json` Stop hook to this probe, run any /cli-tran invocation, and inspect `/tmp/last-stop-stdin.json` to see exactly what keys agy sends. **Not performed here** — no authorization to disrupt the user's setup.

---

## Adversarial Self-Check

Tried to disprove the hypothesis "schema is mostly correct":

- ✗ Could `"block"` be wrong? — No, it's a literal string in the binary.
- ✗ Could the event name be different? — No, only `Stop`/`PreToolUse`/`PostToolUse` exist.
- ✗ Could the proto field tags be wrong? — No, reflection metadata is embedded and matches.
- ✓ Could the JSON casing differ from what jq reads? — **Yes** — that's the bug above, but it's a degraded-diagnostics bug, not a loop-killer.
- ✗ Could there be a `stop_hook_active`-style 1-shot kill? — No such string found; instead, there's a counter-based `MaxForcedInvocations` cap which would only matter for novels exceeding the server-side limit (numerical default not extractable).

---

## Unresolved Questions

1. **Exact default value of `MaxForcedInvocations`** — not extractable from strings alone; would need to either (a) trace via DELVE or (b) run a long loop and observe termination_reason. If the default is e.g. 25, then a 50-chapter novel will halt at chapter ~25. This is worth flagging to team-lead as a real risk separate from H1.
2. **Whether agy hook caller passes `UseProtoNames=true` to protojson Marshal** — Default is `false` (camelCase). I could not find an explicit override. Probe hook (above) would settle this in 5 seconds if the user authorizes.
3. **`disable_loop_detection` proto field** — exists but unclear if user-configurable from CLI; might require server-side flag.

---

## Verdict (TL;DR)

- Schema: **CORRECT** for the loop continuation path. `decision="block"` + `reason` will re-invoke the agent.
- One bug: stdin field read uses snake_case; agy emits camelCase by default. Cosmetic for the loop, real for user-cancel and diagnostics. **One-line fix** at `translate-hook.sh:16`.
- Loop-limit risk: `MaxForcedInvocations` exists; numerical default unknown. Worth a separate hypothesis (H4?) if cli-tran novels regularly exceed ~25–50 chapters.

**Status:** DONE_WITH_CONCERNS (the schema is right but the camelCase stdin bug and the unknown loop cap warrant follow-up.)
