# Architecture & Design Patterns Review

**Reviewer**: code-reviewer (Staff Engineer)
**Date**: 2026-05-16
**Scope**: Full codebase architecture review
**Files reviewed**: 25+ files across commands/, hooks/, scripts/, glossary/, references/, skills/

---

## Summary

The cli-translator architecture is well-conceived: hook-based loop control via deny+clearContext is a clever pattern for Gemini CLI's extension model. The 2-tier glossary system and atomic state writes show thoughtful design. However, there are critical reliability gaps around state corruption recovery and non-atomic file writes that would cause data loss in production at scale.

---

## Critical Issues

### [CRITICAL] State.json write is not atomic -- `hooks/translate-hook.sh:67`

The hook uses `jq ... > "$TMP" && cp "$TMP" "$STATE_FILE"`. The `cp` command is NOT atomic on Linux -- it opens the destination, writes chunks, and closes. If the process is killed mid-write (OOM, SIGKILL, power loss), state.json will be partially written and corrupt.

**Evidence**: `translate-hook.sh:67` -- `jq ... "$STATE_FILE" > "$TMP" && cp "$TMP" "$STATE_FILE"`

**Impact**: A corrupted state.json loses all translation progress. No recovery mechanism exists.

**Recommendation**: Use `mv` instead of `cp` (rename is atomic on same filesystem), or use the same pattern already in `init-translation.py:89` which uses `tmp_file.rename(state_file)`:
```bash
mv "$TMP" "$STATE_FILE"  # atomic on same filesystem
```
Also add a `.bak` backup before the move: `cp "$STATE_FILE" "${STATE_FILE}.bak" 2>/dev/null; mv "$TMP" "$STATE_FILE"`

### [CRITICAL] No state.json corruption recovery mechanism

If state.json becomes corrupt (partial write, JSON parse error, disk error), the entire translation session is lost. There is no backup, no checksum, and no way to reconstruct state from the output files.

**Evidence**: No backup file is created anywhere. `translate-hook.sh` reads state at line 22-24 with `jq -r` which will fail on corrupt JSON. `init-translation.py` creates state once and never backs it up.

**Impact**: At 50+ chapters, losing state means re-translating everything or manually reconstructing state.json.

**Recommendation**:
1. Keep a rolling `.translator/state.json.bak` (copy before each update)
2. Add a `recover-state.py` script that scans `output_dir` for `chapter_NNN.txt` files and reconstructs state
3. In the hook, before updating state: `cp "$STATE_FILE" "${STATE_FILE}.bak"`

---

## Important Issues

### [IMPORTANT] Resume command has no retry logic for failed chapters -- `commands/resume.toml:4-12`

The resume prompt says "Find the first chapter with status != completed". This means failed chapters get retried, but there's no retry limit, no backoff, and no way to distinguish "failed once, retry" from "failed 5 times, skip". A chapter that consistently fails (e.g., corrupted source text) will block the entire resume.

**Evidence**: `resume.toml:3` -- "Find the first chapter with status != 'completed'"

**Impact**: Infinite retry loop on consistently-failing chapters. User must manually intervene.

**Recommendation**: Add `retry_count` to chapter state. After N retries (e.g., 3), mark as `skipped` and move on. Add a `/resume --skip-failed` flag.

### [IMPORTANT] Prologue/epilogue/chapter 0 not detected -- `scripts/detect-chapters.py:9-15`

The chapter patterns only match `第X章`, `Chapter N`, `Chương N`, numbered lists, and markdown headings. Common novel structures like "Prologue", "Epilogue", "序章", "尾声", "番外" are not detected. These will be silently merged into adjacent chapters or become part of the "全文" fallback.

**Evidence**: `detect-chapters.py:9-15` -- CHAPTER_PATTERNS list has no prologue/epilogue patterns.

**Impact**: For novels with prologues/epilogues, the first or last chapter will contain extra content, producing incorrect translations for those sections.

**Recommendation**: Add patterns:
```python
(r'^序章|^序幕|^楔子|^Prologue|^Epilogue|^尾声|^番外', 'special'),
```

### [IMPORTANT] Numbered-list pattern too broad -- `scripts/detect-chapters.py:13`

The pattern `^\d+\.\s` matches ANY numbered list item (e.g., recipe steps, battle formations, dialogue lists). This will create false chapter boundaries in novels that use numbered lists within chapter text.

**Evidence**: `detect-chapters.py:13` -- `(r'^\d+\.\s', 'num')`

**Impact**: False chapter splits in novels with numbered lists, breaking translation continuity.

**Recommendation**: Add a minimum line-count heuristic: only treat a numbered-list match as a chapter boundary if followed by substantial content (>50 lines) before the next match. Or require the match to be standalone (the only content on the line, no continuation).

### [IMPORTANT] validate_all reads source file N times -- `scripts/validate-translation.py:107-117`

For each completed chapter, `validate_chapter` reads the full source file. For a 100-chapter novel, this reads the same source file 100 times.

**Evidence**: `validate-translation.py:90` -- `source = Path(source_file).read_text(encoding='utf-8')` inside `validate_chapter`, called in a loop at line 112-116.

**Impact**: Unnecessary I/O. Not a correctness bug, but wasteful for large novels.

**Recommendation**: Read source once in `validate_all`, pass the content string to `validate_chapter`.

---

## Moderate Issues

### [MODERATE] Relative path for STATE_FILE assumes CWD -- `hooks/translate-hook.sh:14`

`STATE_FILE=".translator/state.json"` is relative. If Gemini CLI changes the working directory (e.g., to the extension's install path), the hook will fail to find state.json.

**Evidence**: `translate-hook.sh:14` -- `STATE_FILE=".translator/state.json"`

**Recommendation**: Use `$PWD/.translator/state.json` or derive from the hook input's file path if available.

### [MODERATE] Context duplication across 4 files -- `GEMINI.md`, `commands/translate.toml`, `skills/novel-translator/SKILL.md`, `references/translation-principles.md`

Translation principles (P1-P4), glossary usage, and genre information are duplicated across these files. Each copy consumes tokens in Gemini CLI's context window. Changes must be synchronized manually.

**Evidence**: Compare `GEMINI.md:7-25` with `translate.toml:18-40` and `SKILL.md:13-37` -- nearly identical content.

**Impact**: Token waste, maintenance burden, drift risk.

**Recommendation**: `GEMINI.md` should be the single source of truth for context. `translate.toml` should reference it ("Follow principles in GEMINI.md") rather than repeating. `SKILL.md` should focus on behavior/decision-making, not repeat the same rules.

### [MODERATE] No `/progress` or `/status` command -- missing from `commands/`

`get-progress.py` exists but has no corresponding TOML command. Users cannot check translation progress without running the script manually.

**Evidence**: `commands/` contains only `translate.toml`, `resume.toml`, `validate.toml`. No `progress.toml` or `status.toml`.

**Recommendation**: Add `commands/progress.toml` that invokes `get-progress.py`.

### [MODERATE] EPUB title extraction only catches h1-h3 in raw HTML -- `scripts/epub2txt.py:100`

The regex `r'<h[1-3][^>]*>(.*?)</h[1-3]>'` searches the original HTML, not the extracted text. If the EPUB uses `<span>` or `<div>` with class-based styling for chapter titles (common in professionally-produced EPUBs), titles won't be detected.

**Evidence**: `epub2txt.py:100` -- `title_match = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', content, re.IGNORECASE)`

**Recommendation**: Also check for `<title>` tags and common class patterns like `class="chapter-title"`.

### [MODERATE] `epub2txt.py` always prepends `第N章` marker -- `scripts/epub2txt.py:127`

For non-Chinese EPUBs (e.g., English novels being translated), the output will have `第1章 Chapter 1` as markers. The detect-chapters.py pattern `^第.{1,10}章` will match these synthetic markers, but the original chapter title is lost as the primary marker.

**Evidence**: `epub2txt.py:127` -- `f.write(f"第{i + 1}章 {title}\n")`

**Recommendation**: Make the marker format configurable, or use the original title as-is when it already matches a chapter pattern.

### [MODERATE] `deep_merge` doesn't handle nested unknown keys -- `scripts/glossary-loader.py:35`

If a genre glossary introduces a new top-level key not in the known set (`terms`, `characters`, `protected_phrases`, `compound_context`, `pronoun_rules`), it falls through to the `else` at line 35 which does a simple override. This is fine now, but if two genre glossaries both add the same unknown key with different structures, the merge could silently lose data.

**Evidence**: `glossary-loader.py:35` -- `else: result[key] = value`

**Recommendation**: Document the expected glossary schema. Add a schema validation step.

### [MODERATE] `glossary-loader.py` uses relative path default -- `scripts/glossary-loader.py:43`

`load_glossary` defaults to `Path('glossary')` which is relative. If called from a different working directory, it will fail.

**Evidence**: `glossary-loader.py:43` -- `glossary_dir: Path = Path('glossary')`

**Recommendation**: Use `Path(__file__).parent.parent / 'glossary'` as default.

---

## Test Coverage Assessment

| Component | Unit Tests | Integration Tests | Edge Cases |
|-----------|-----------|-------------------|------------|
| detect-chapters.py | Yes (7 tests) | No | Missing: prologue, numbered lists, huge files |
| epub2txt.py | Yes (6 tests) | No | Missing: corrupt EPUB, DRM, no OPF |
| glossary-loader.py | Yes (7 tests) | No | Missing: missing genre file, corrupt JSON |
| validate-translation.py | Yes (8 tests) | No | Missing: empty source, binary file |
| init-translation.py | **No** | **No** | Missing: all |
| get-progress.py | **No** | **No** | Missing: all |
| translate-hook.sh | **No** | **No** | Missing: all |
| State corruption recovery | **No** | **No** | Missing: all |

**Key gaps**: `init-translation.py`, `get-progress.py`, and `translate-hook.sh` have zero test coverage. The hook is the most critical component (it controls the entire translation loop) and is completely untested.

---

## Positive Observations

1. **Atomic state design in init-translation.py:87-89** -- Uses `tmp_file.rename(state_file)` which is atomic on same filesystem. The hook should follow this pattern.
2. **jq --arg for safe string interpolation** -- `translate-hook.sh:54` uses `--arg` and `--argjson` to prevent injection via chapter titles or status values.
3. **Marker detection in tail only** -- `translate-hook.sh:38` checks only the last 5 lines for the completion marker, preventing false matches if source text contains the marker.
4. **2-tier glossary with proper merge semantics** -- Each key type has appropriate merge strategy (override for terms, append for protected_phrases, union for compound_context, by-from dedup for pronoun_rules).
5. **Volume marker exclusion** -- `detect-chapters.py:22-26` correctly excludes volume markers (第X卷) that would otherwise be matched by the chapter pattern.
6. **Reference docs are excellent** -- `common-errors.md`, `pronoun-guide.md`, and `translation-principles.md` are well-structured and domain-specific. These provide high-quality context for the LLM.

---

## Recommended Actions (Priority Order)

1. **Fix atomic write in translate-hook.sh** -- Replace `cp` with `mv`. Add `.bak` backup. (5 min fix, prevents data loss)
2. **Add state recovery script** -- `scripts/recover-state.py` that scans output dir and reconstructs state.json. (30 min)
3. **Add retry_count to chapter state** -- Update init-translation.py schema, update hook to track retries, update resume.toml to handle skip-failed. (1 hour)
4. **Add prologue/epilogue patterns** to detect-chapters.py. (10 min)
5. **Add tests for init-translation.py, get-progress.py, translate-hook.sh**. (2 hours)
6. **Deduplicate context** across GEMINI.md, translate.toml, SKILL.md. (30 min)
7. **Add progress.toml** command. (5 min)
