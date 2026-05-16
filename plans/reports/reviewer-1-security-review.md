---
title: Security Review — cli-translator
date: 2026-05-16
reviewer: code-reviewer
scope: Full codebase security audit
---

## Code Review Summary

### Scope
- Files: 11 (hooks/, scripts/, commands/)
- LOC: ~550
- Focus: Full security audit
- Areas: Shell injection, path traversal, EPUB parsing, file operations, input validation, credential exposure

### Overall Assessment
Codebase is small and well-structured. Shell hook uses safe jq interpolation. Python scripts use `pathlib` consistently. **Two critical issues found** in EPUB zip handling and state-file-driven path construction. Several moderate issues around atomicity and path boundary validation.

---

## Critical Issues

### [CRITICAL] Zip path traversal in EPUB extraction — `scripts/epub2txt.py:90`

```python
file_path = f"{base_path}/{href}" if base_path else href
content = epub.read(file_path).decode('utf-8')
```

`href` comes from the EPUB's OPF manifest XML, which is attacker-controlled. A malicious EPUB can set `<item href="../../../../etc/passwd" id="x" media-type="text/html"/>` in its manifest. `zipfile.ZipFile.read()` with a path containing `../` sequences will follow the traversal, reading arbitrary files on the system.

**Impact:** Arbitrary file read. An attacker who distributes a crafted EPUB can exfiltrate `/etc/shadow`, SSH keys, API tokens, etc.

**Recommendation:** Sanitize href — strip `../` sequences and verify the resolved path stays within the zip:
```python
from posixpath import normpath
safe_href = normpath(href)
if safe_href.startswith('..'):
    continue
file_path = f"{base_path}/{safe_href}" if base_path else safe_href
```

---

### [CRITICAL] Path traversal via state file in validate-translation.py — `scripts/validate-translation.py:115`

```python
tr = str(Path(state['output_dir']) / ch['output_file'])
```

`output_file` is read from `state.json` without sanitization. If state.json is tampered (e.g., `output_file: "../../etc/passwd"`), `validate_chapter` reads arbitrary files via `Path(translated_file).read_text()`.

**Impact:** Arbitrary file read. State file lives in `.translator/` which is user-writable.

**Recommendation:** Validate that the resolved path stays under `output_dir`:
```python
resolved = (Path(state['output_dir']) / ch['output_file']).resolve()
if not resolved.is_relative_to(Path(state['output_dir']).resolve()):
    result.add_error(f"Path traversal detected: {ch['output_file']}")
    return result
```

---

## Important Issues

### [IMPORTANT] Non-atomic state file update — `hooks/translate-hook.sh:67`

```bash
jq ... "$STATE_FILE" > "$TMP" && cp "$TMP" "$STATE_FILE"
```

`cp` is not atomic — if the process is killed mid-copy, `state.json` is truncated/corrupted. The Python scripts (`init-translation.py:89`) correctly use `tmp_file.rename(state_file)` which is atomic on the same filesystem.

**Impact:** Corrupted state.json kills the translation loop. Recovery requires manual intervention.

**Recommendation:** Use `mv` instead of `cp`:
```bash
jq ... "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"
```

### [IMPORTANT] No path boundary validation on source file — `scripts/init-translation.py:20-21`

```python
source_path = Path(source_file).resolve()
if not source_path.exists():
```

The resolved path is used directly to create `.translator/` directory at `source_path.parent`. If `source_file` is something like `/etc/important_file`, the script creates `/etc/.translator/state.json`.

**Impact:** Arbitrary directory creation. Low severity since the attacker needs to control the CLI argument, but defense-in-depth is warranted.

**Recommendation:** Add a check that the source file is a regular file (not device, pipe, etc.) and optionally validate it's under an expected directory.

### [IMPORTANT] EPUB has no zip bomb protection — `scripts/epub2txt.py:50`

```python
with zipfile.ZipFile(epub_path, 'r') as epub:
```

No check on uncompressed size before extraction. A crafted EPUB can claim a small compressed size but decompress to gigabytes.

**Recommendation:** Check `info.file_size` before reading, or set a reasonable limit (e.g., 100MB per file).

---

## Moderate Issues

### [MODERATE] TOCTOU race in shell hook — `hooks/translate-hook.sh:16-19`

```bash
if [[ ! -f "$STATE_FILE" ]]; then
  echo '{"decision":"allow","continue":false,...}'
  exit 0
fi
```

The existence check and subsequent read are not atomic. Another process could delete or modify the file between check and read.

**Impact:** Low — the hook runs in a controlled environment with single-agent access. `set -euo pipefail` will catch failures.

### [MODERATE] KeyError risk in get-progress.py — `scripts/get-progress.py:18-21`

```python
total = state['total_chapters']
completed = state['chapters_completed']
```

Direct dict access without `.get()`. If state.json is malformed or partially written (see non-atomic update above), this raises `KeyError` with an unhandled traceback.

**Recommendation:** Use `.get()` with defaults or wrap in try/except.

### [MODERATE] Shell hook reads untrusted prompt response without size limit — `hooks/translate-hook.sh:8`

```bash
INPUT=$(cat)
```

The full hook input is read into a shell variable. If the LLM response is extremely large (e.g., a failed translation dumps the entire novel), this consumes unbounded memory.

**Recommendation:** Truncate input or use a size check.

---

## No Issues Found

- **Hardcoded credentials:** None found. No API keys, tokens, or passwords in any file.
- **Command injection via TOML:** TOML files use `{{args}}` template variables which are Gemini CLI parameters, not shell-executed. No injection vector.
- **JSON parsing safety:** `glossary-loader.py` uses standard `json.load()` which is safe. No YAML/custom parsers.
- **XXE in EPUB XML:** `xml.etree.ElementTree.fromstring()` does not process external entities by default in Python 3. Safe.
- **API key exposure in logs:** No logging of sensitive data found.
- **Symlink attacks:** All file operations use regular file paths. No symlink-specific vulnerabilities.

---

## Positive Observations

- Shell hook uses `jq --arg` / `--argjson` for all variable interpolation — prevents injection via chapter titles or status values.
- `translate-hook.sh` uses `set -euo pipefail` — fails fast on errors.
- `mktemp` + trap pattern for temp files — proper cleanup.
- Atomic write pattern in `init-translation.py` (`rename`).
- `jq -Rs` used to safely escape prompt text for JSON embedding (line 80).
- Completion marker checked only in last 5 lines (line 38) — prevents false matches from source text.

---

## Recommended Actions (Priority Order)

1. **Fix EPUB zip path traversal** — `epub2txt.py:90` — sanitize href before `epub.read()`
2. **Fix path traversal in validate-translation.py** — line 115 — validate resolved path under output_dir
3. **Replace `cp` with `mv`** — `translate-hook.sh:67` — atomic state update
4. **Add zip bomb protection** — `epub2txt.py` — check decompressed size limits
5. **Add KeyError handling** — `get-progress.py` — use `.get()` with defaults

---

## Unresolved Questions

- Are there additional TOML commands beyond the three reviewed? (Only translate.toml, resume.toml, validate.toml were provided.)
- Is the `.translator/` directory ever exposed to untrusted users (e.g., shared filesystem)? This affects severity of state file tampering risks.
