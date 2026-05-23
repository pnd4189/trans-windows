---
phase: 3
title: "Backend Simplification"
status: pending
priority: P1
effort: "1h"
dependencies: [1]
---

# Phase 3: Backend Simplification

## Overview

Remove `gemini` CLI backend from the cascade, leaving only `agy`. Simplify `select-cascade.py` and `translate-chapter.py`. **Phase order fix (H4):** Do this BEFORE driver rewrite so the Python driver is written agy-only from the start.

**Red team fix (H5):** Keep env stripping (`_strip_env()` → renamed) for agy too, to prevent `GEMINI_API_KEY` from leaking into agy's auth.

## Requirements

- Functional: Only `agy` backend available; `gemini` CLI path removed entirely
- Functional: `CLI_TRAN_FORCE_BACKEND=agy` still works (only valid value)
- Functional: Probe logic simplified to just check `agy` availability
- Functional: Environment variable stripping kept for agy safety
- Non-functional: Dead code removed, not commented out

## Architecture

**select-cascade.py** changes:
- `BACKENDS = ("agy",)` — single element
- Remove `_probe_gemini()`, `_API_KEY_STRIP`, `_oauth_env()`
- Remove `PROBES["gemini"]` mapping
- Keep caching mechanism (useful for agy quota tracking)

**translate-chapter.py** changes:
- `choices=("agy",)` — single element
- Remove `GEMINI_PROBE_FLAGS` constant
- Remove `if backend == "gemini":` branch
- Keep `_strip_env()` (renamed to `_clean_env()`) — still useful to prevent env var leaks

## Related Code Files

- Modify: `scripts/select-cascade.py`
- Modify: `scripts/translate-chapter.py`

## Implementation Steps

1. Edit `select-cascade.py`:
   - `BACKENDS = ("agy",)`
   - Remove `_probe_gemini()`, `_API_KEY_STRIP`, `_oauth_env()`
   - Remove `"gemini"` from `PROBES` dict
   - Simplify `pick()` — single backend loop
2. Edit `translate-chapter.py`:
   - Remove `GEMINI_PROBE_FLAGS`
   - `choices=("agy",)`
   - Remove `if backend == "gemini":` branch in `_invoke_backend()`
   - Rename `_strip_env()` → `_clean_env()`, keep the function
   - Simplify `_invoke_backend()` to just `cmd = ["agy", "-p", prompt]`
3. Verify: `grep -n 'gemini' scripts/select-cascade.py scripts/translate-chapter.py` — only comments remain

## Success Criteria

- [ ] `BACKENDS = ("agy",)` in `select-cascade.py`
- [ ] `_probe_gemini()` removed
- [ ] `_invoke_backend()` only has agy code path
- [ ] `GEMINI_PROBE_FLAGS` removed
- [ ] `_clean_env()` still strips API key vars (prevents agy auth confusion)
- [ ] `grep -n 'gemini' scripts/select-cascade.py scripts/translate-chapter.py` returns 0 non-comment matches
