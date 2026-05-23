# Model Switching Review — Flash/Opus Cascade

Reviewer: reviewer-2
Date: 2026-05-22
Scope: Model switching architecture for cli-tran (Flash -> Opus -> Flash -> 30-min wait)

## Architecture Gap Analysis

### How agy selects models

agy reads the `model` field from `~/.gemini/antigravity-cli/settings.json` at startup. The current value is `"Gemini 3.5 Flash (Medium)"`. agy has **no** `--model` CLI flag (verified via `agy --help`). The binary contains model IDs (`claude-opus-4-6`, `claude-sonnet-4-6`, `gemini-2.5-pro`, etc.) and model config machinery, but none of this is exposed as a command-line override.

**Implication:** The only way to switch models between agy subprocess calls is to **mutate `settings.json`** before each invocation. This is a race condition if two agy processes run concurrently (not the case here since the driver is serial, but still fragile).

## Findings

### [CRITICAL] F1: No mechanism to switch agy models between subprocess calls

**Evidence:**
- `translate-chapter.py:155-168` — `_invoke_backend()` calls `["agy", "-p", prompt]` with no model parameter.
- `translate-chapter.py:13` — docstring says `--model <name> model name (informational, agy uses its own config)`.
- `auto-translate.py:180` — passes `--model ""` (empty string) to translate-chapter.
- agy has no `--model` flag. No env var override found (`ANTIGRAVITY_MODEL`, `AGY_MODEL`, `GEMINI_MODEL` not recognized by agy).
- The only model control surface is `~/.gemini/antigravity-cli/settings.json` → `"model"` field.

**Impact:** The entire Flash -> Opus -> Flash switching requirement is impossible with the current architecture. The `--model` arg exists in translate-chapter.py but is explicitly documented as "informational" and never used. The driver always uses whatever model agy's settings.json currently points to.

**Recommendation:** Implement model switching by mutating `~/.gemini/antigravity-cli/settings.json` before each `agy -p` call. Create a helper in `select-cascade.py` (or a new `model-switch.py`):
1. Define `MODEL_TIER = ["Gemini 3.5 Flash (Medium)", "Claude Opus 4.6"]` (or exact display names matching agy's settings.json format).
2. Before each `agy -p` call, write the selected model to settings.json.
3. Track which models are quota-exhausted in `backend_cache.json` or state.json.
4. This is safe because the driver is serial (one subprocess at a time).

---

### [CRITICAL] F2: select-cascade.py has backend-level granularity, not model-level

**Evidence:**
- `select-cascade.py:31` — `BACKENDS = ("agy",)` — single backend.
- `select-cascade.py:92` — `PROBES = {"agy": _probe_agy}` — probes backend health, not model quota.
- `select-cascade.py:73-89` — `_probe_agy()` sends `"OK"` as test prompt. If it sees `RESOURCE_EXHAUSTED`, it marks the **entire agy backend** as dead for 5 minutes.
- `select-cascade.py:106-118` — `pick()` iterates BACKENDS (just agy), returns "" if nothing alive.

**Impact:** The current architecture treats agy as a single backend with a binary alive/dead state. There is no concept of "agy is alive but model X quota is exhausted." When Flash quota runs out, the entire agy backend is marked dead, and the driver halts entirely with "all backends exhausted" — no fallback to Opus.

**Recommendation:** Restructure the cascade to operate at the model level:
1. Change the cascade key from backend name to `model` name.
2. Each model has its own cache entry: `{"Gemini 3.5 Flash": {"alive": true, ...}, "Claude Opus 4.6": {"alive": false, ...}}`.
3. `_probe_agy(model_name)` mutates settings.json to the target model, then probes.
4. On quota exhaustion of model X, mark only that model as dead and try the next.
5. `pick()` returns `(model_name, reason)` instead of `(backend_name, reason)`.

---

### [CRITICAL] F3: No 30-minute recovery timer when both models exhausted

**Evidence:**
- `auto-translate.py:168-171` — when `backend == ""` (all exhausted), the driver just breaks out of the loop and prints a summary.
- `auto-translate.py:170` — `log(f"All backends exhausted; halting. Detail: {cascade_json}", driver_log)` — halts immediately.
- No sleep/retry logic for the "both exhausted" scenario. No timer, no polling.

**Impact:** The user's requirement #4 ("BOTH exhausted -> wait 30 min, check if refilled, continue") is completely unimplemented. The driver stops permanently and the user must manually run `/cli-tran --resume`.

**Recommendation:** Add a recovery loop in `auto-translate.py` after the "all models exhausted" check:
```python
# Pseudocode
if not model:
    if recovery_attempts >= MAX_RECOVERY:
        break
    log(f"All models exhausted, waiting 30 min (attempt {recovery_attempts})...", driver_log)
    time.sleep(1800)  # 30 minutes
    # Clear dead cache entries
    recovery_attempts += 1
    continue
```

---

### [IMPORTANT] F4: State.json has model tracking fields but they are never used by the driver

**Evidence:**
- `init-translation.py:189-197` — Creates state with `model`, `current_model`, `exhausted_models`, `quota_exhausted`, `model_switch_history` fields.
- `init-translation.py:60-71` — On resume, clears `exhausted_models` if last RPD hit was >12h ago. This is the only place these fields are ever read or mutated.
- `auto-translate.py` — Never reads `exhausted_models` or `model_switch_history` from state.
- `select-cascade.py` — Uses its own `backend_cache.json`, not state.json's model fields.
- `translate-chapter.py` — Receives `--model ""` and passes it through to JSON output but never acts on it.

**Impact:** The state.json model fields are dead schema. They are initialized and reset but never drive any switching logic. This creates a misleading impression that model switching exists.

**Recommendation:** Either:
1. Wire these fields into the actual switching logic (ideal), or
2. Remove them to avoid confusion if switching is implemented differently.

---

### [IMPORTANT] F5: Probe sends "OK" as test prompt — may not trigger quota error until real translation

**Evidence:**
- `select-cascade.py:76` — `cmd = ["agy", "-p", "OK"]` — single-token probe.
- `select-cascade.py:85-88` — Checks for `RESOURCE_EXHAUSTED`, `QUOTA_EXHAUSTED`, `PERMISSION_DENIED`, etc. in output.

**Impact:** A probe with a single-token "OK" prompt consumes minimal quota. Some quota limits (RPD = requests per day) may not trigger on this tiny request but will fail on a real chapter translation (which is much larger). The driver could pass the probe, attempt a real chapter, get quota-exhausted on the real call, and then correctly cascade — but the probe gives a false sense of health.

**Recommendation:** The probe is best-effort and acceptable as a pre-check. The real quota detection happens in `translate-chapter.py:287-296` which correctly catches quota markers in the actual translation response. Keep the probe but document that it is a lightweight pre-check, not a guarantee.

---

### [IMPORTANT] F6: init-translation.py reads model from agy settings but never changes it

**Evidence:**
- `init-translation.py:154-167` — Reads model from env or antigravity settings.json, stores it in state.json.
- The model is only stored, never used to configure anything. The driver always calls `agy -p` which uses whatever agy's current settings say.

**Impact:** If the user changes their agy model between init and actual translation, the state.json model field will be stale but has no effect on behavior. No functional bug, but misleading metadata.

**Recommendation:** Update the model metadata in state.json each time a chapter is translated, reflecting the model that was actually used. Or, if model switching is implemented, track model-per-chapter in the chapters array.

---

### [IMPORTANT] F7: No Claude Opus model name in the codebase

**Evidence:**
- `init-translation.py:155` — Only reads current model, no Flash/Opus mapping.
- `select-cascade.py` — No model names defined anywhere.
- `translate-chapter.py` — No model names defined.
- agy binary contains `claude-opus-4-6` as an internal model ID, but the settings.json uses display names like `"Gemini 3.5 Flash (Medium)"`.

**Impact:** Even if the switching mechanism is implemented, the code has no knowledge of what the Claude Opus model's display name should be in agy's settings.json. The mapping between user-facing names ("Flash", "Opus") and agy's internal display names needs to be discovered and hardcoded.

**Recommendation:** Determine the exact settings.json display name for Claude Opus by manually setting it in agy and reading the settings file. Then define a constant in `select-cascade.py`:
```python
MODELS = {
    "flash": "Gemini 3.5 Flash (Medium)",
    "opus": "<discovered display name>",
}
MODEL_PREFERENCE = ["flash", "opus"]  # try flash first
```

---

### [MODERATE] F8: Driver hardcodes `--model ""` — wasted argument

**Evidence:**
- `auto-translate.py:180` — `"--model", ""` — always empty string.
- `translate-chapter.py:228` — `ap.add_argument("--model", default="")` — accepts model name but ignores it.
- `translate-chapter.py:155` — `_invoke_backend()` takes `model` param but does nothing with it.

**Impact:** The `--model` argument plumbing exists but is dead. If model switching is added, the plumbing is partially there (argparse, JSON output), which reduces implementation effort.

**Recommendation:** When implementing model switching, pass the actual model name through this arg so it is recorded in state.json chapter metadata.

---

### [MODERATE] F9: model_switch_history in state.json is never populated

**Evidence:**
- `init-translation.py:197` — `'model_switch_history': []` — initialized empty.
- No script ever appends to this array.

**Impact:** No historical record of model switches for debugging. Low priority since no switching exists yet.

**Recommendation:** When implementing switching, append `{from, to, reason, timestamp}` entries to this array on each switch.

---

### [MODERATE] F10: GEMINI.md claims "no manual override needed" — contradicts user requirement

**Evidence:**
- `GEMINI.md:79-81` — "Model selection is handled automatically by agy — no manual override needed."

**Impact:** This documentation will mislead contributors into thinking model switching is handled by agy itself, when in fact the user's requirement demands explicit Python-side model cascade logic.

**Recommendation:** Update GEMINI.md to describe the Flash/Opus cascade once implemented.

---

## Positive Observations

1. **Serial execution model** — the driver runs one subprocess at a time, which makes settings.json mutation for model switching safe (no concurrent writes).
2. **Atomic state writes** — `advance-chapter.py` uses `_atomic_write_json()` with `.tmp` + `.replace()`, which is safe for cross-platform atomic writes.
3. **Chapter-level state persistence** — every chapter result is persisted before the next one starts, so a mid-switch crash loses at most one chapter.
4. **Clean exit code taxonomy** — translate-chapter.py exit codes (0/1/2/3) cleanly separate retry/cascade/fatal, which maps well to model-level cascade.
5. **Existing `--model` arg plumbing** — the argparse arg and JSON output field already exist, reducing implementation effort.
6. **backend_cache.json** — the caching mechanism in select-cascade.py is well-suited for extension to model-level caching.

## Summary

The current codebase has **zero model switching capability**. agy exposes no model override flag; the only control surface is mutating `settings.json`. Three critical gaps must be addressed:

1. **F1** — Settings.json mutation mechanism for model selection
2. **F2** — Model-level cascade in select-cascade.py (currently backend-level only)
3. **F3** — 30-minute recovery timer in auto-translate.py

The existing code has good foundations (serial execution, atomic writes, clean exit codes, `--model` arg plumbing) that make the implementation straightforward once the approach is decided.

## Recommended Implementation Order

1. Discover exact agy display names for Flash and Opus models (manual step)
2. Add `mutate_agy_model()` helper to `select-cascade.py` or new `model-switch.py`
3. Restructure `select-cascade.py` cascade to model-level with Flash first, Opus fallback
4. Wire `translate-chapter.py` to use the selected model name in JSON output
5. Add 30-minute recovery loop in `auto-translate.py` for dual exhaustion
6. Update `init-translation.py` to define `MODELS` constant
7. Update `GEMINI.md` and `SKILL.md` with cascade documentation
