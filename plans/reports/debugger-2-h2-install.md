# H2 Report — Plugin install + hook firing path

**Verdict: INSTALL_BROKEN.** The Stop hook will NEVER fire because Antigravity does not discover `cli-tran` as a plugin in the first place. The directory layout under `~/.gemini/antigravity-cli/plugins/cli-tran/` is a "staged" copy that the runtime does not auto-scan — it only contains plugins that have been previously **imported** from `~/.gemini/extensions/<name>/` via the one-shot `GeminiCLIImporter` and recorded in `~/.gemini/antigravity-cli/import_manifest.json`. `cli-tran` is absent from that manifest.

## Evidence chain

### 1. Runtime discovery is manifest-driven, not directory-driven
- Log line (`~/.gemini/antigravity-cli/log/cli-20260520_142930.log:1`):
  ```
  gemini_extensions.go:28] Detecting Gemini extensions in /home/dung/.gemini/extensions
  gemini_extensions.go:46] Found 7 extensions: [Stitch code-review conductor convert-doc maestro prompt-generator gemini-cli-security]
  ```
- That list of 7 matches `~/.gemini/antigravity-cli/import_manifest.json` exactly.
- `maestro` is in the list yet **does not exist** in `~/.gemini/extensions/` — only in `~/.gemini/antigravity-cli/plugins/maestro/`. Proof the runtime reads the manifest, not the dir.
- `cli-translator` symlink is in `~/.gemini/extensions/` (since 14:43, well before session start at 14:43) but is NOT loaded — confirms a re-scan does not happen on launch.

### 2. cli-tran is not in import_manifest.json
`~/.gemini/antigravity-cli/import_manifest.json` contains 7 entries imported at `2026-05-20T02:41:39Z`. No `cli-tran`, no `cli-translator`. The directory `~/.gemini/antigravity-cli/plugins/cli-tran/` was hand-placed by `install.sh` and therefore is dead weight.

### 3. The manifest the runtime expects is `gemini-extension.json`, not `plugin.json`
Every loaded extension has `gemini-extension.json` (verified all 6 still on disk):
- `~/.gemini/extensions/security/gemini-extension.json` → `{"name":"gemini-cli-security", "version":"0.5.0", ...}`
- `~/.gemini/extensions/code-review/gemini-extension.json` → `{"name":"code-review", "version":"0.1.0", "contextFileName":"GEMINI.md"}`
- Binary symbol: `gemini.parseGeminiManifest` and the literal string `gemini-extension.json` exist in `~/.local/bin/agy`.
- The cli-translator repo has **`plugin.json`** (`{"name":"cli-tran", "description":"..."}`) and zero `gemini-extension.json`. The current `plugin.json` schema does not match the importer's expectation.

### 4. hooks.json schema is fine (matches maestro's stage output)
`~/.gemini/antigravity-cli/plugins/cli-tran/hooks.json` is valid JSON and structurally identical to `maestro/hooks.json` (top-level `hooks` map → event name → array of groups → each group has its own `hooks` array). `Stop` IS a real registered event — binary contains `agent.StopHook`, `core.runStopHooks`, `registry.RegisterStopHook`, `exa.hooks_pb.StopHookArgs`. So the file would work IF Antigravity actually loaded it. It does not.

### 5. Hook script is executable
- `/home/dung/VIBE_CODING/1. OTHERS/cli-translator/hooks/translate-hook.sh` — mode 0775, shebang `#!/bin/bash`, /bin/bash present. Permissions are correct.

### 6. Space in path — likely fine (UNVERIFIED but indirect evidence)
- Binary symbols show `os/exec.Command` and `syscall.forkAndExecInChild` (fork-exec path), and `os/exec.LookPath`. The `command` field appears to be exec'd directly (argv[0] = full path) rather than passed to `/bin/sh -c`. Reference: maestro's hooks.json has `"command": "node /home/dung/.gemini/extensions/maestro/hooks/hook-runner.js gemini session-start"` which IS split on whitespace (node + args), suggesting the runner DOES tokenize on space — which would break for the cli-tran command containing the literal space in the path.
- **HOWEVER** this is moot until #1–#3 are fixed; the hook is never invoked, space or no space.

### 7. SKILL.md, skills/ layout
- Already-loaded extensions all have `skills/<skill-name>/SKILL.md` — same nesting as cli-tran. So this part is correct.

## Root cause

Two layered defects:

1. **Wrong installation mechanism.** `install.sh` writes to `~/.gemini/antigravity-cli/plugins/cli-tran/` directly. That directory is the *destination* of the import pipeline, not a source. Antigravity does not rescan it. It scans only what is recorded in `import_manifest.json`, which is written once by the `GeminiCLIImporter` during gemini-cli → antigravity-cli migration (timestamp 2026-05-20T02:41:39Z).
2. **Wrong manifest filename.** The repo ships `plugin.json` (and the install symlinks make `~/.gemini/extensions/cli-translator/plugin.json` visible). The importer expects `gemini-extension.json`. Even if reimport could be triggered, the manifest would not parse.

Either defect alone is fatal. Together they explain why the Stop hook silently never fires.

## Concrete fix

### Minimum to be loaded as an extension
1. Add `gemini-extension.json` to repo root (use schema observed in shipped extensions):
   ```json
   {
     "name": "cli-tran",
     "version": "0.1.0",
     "contextFileName": "GEMINI.md"
   }
   ```
2. Keep the symlink `~/.gemini/extensions/cli-translator -> /home/dung/VIBE_CODING/1. OTHERS/cli-translator` (already exists).
3. Trigger a (re)import. Mechanisms to investigate (binary contains relevant symbols, exact UX TBD):
   - `agy plugins import` / `agy extensions import` — symbol `(*GeminiCLIImporter).Import` exists.
   - Delete `~/.gemini/antigravity-cli/import_manifest.json` to force a fresh import on next launch (RISK: also re-stages the other 7, which may overwrite stale `maestro/hooks.json` and stop maestro working — verify before doing this).
4. Move hooks declaration. In gemini-cli extension format, hooks live under `~/.gemini/extensions/cli-translator/hooks/hooks.json` (the importer's `StageHooks` reads from that path). The current location at repo-root `hooks.json` would not be picked up by `StageHooks`. The repo already has a `hooks/` dir — place the JSON there as `hooks/hooks.json` (NOT the current root-level `hooks.json`).

### Path-with-space risk (handle BEFORE testing the loop)
After the plugin is loaded, the staged `hooks.json` will contain the absolute command. Because the runner appears to whitespace-tokenize the `command` field (per the maestro example), the space in `/home/dung/VIBE_CODING/1. OTHERS/cli-translator/hooks/translate-hook.sh` will be split. Two mitigations, in order of preference:
1. Move/symlink the hook script to a no-space path before staging: `ln -s "/home/dung/VIBE_CODING/1. OTHERS/cli-translator/hooks/translate-hook.sh" ~/.gemini/extensions/cli-translator/hooks/translate-hook.sh` and reference the symlink path in hooks.json.
2. Wrap in `/bin/sh -c "'/path with space/script.sh'"` — explicit shell with single-quoted path. Verify by inspecting binary or doing a one-off test once the plugin loads.

### Validation
After fix, on next `agy` launch, expect:
- `gemini_extensions.go:46] Found 8 extensions: [Stitch code-review ... cli-tran]` (or whatever `name` field is set to).
- A new entry in `import_manifest.json` with `"components": ["skills", "commands", "hooks"]`.
- `~/.gemini/antigravity-cli/plugins/cli-tran/hooks.json` re-staged (and the script path resolved through `resolveVariables`, which may rewrite `${extensionPath}` substitutions).

## Unresolved questions

1. Exact UX to trigger `(*GeminiCLIImporter).Import` from the CLI — slash command? config flag? Manual file-delete? Not surfaced in binary strings I scanned.
2. Confirmed shell-exec vs fork-exec semantics for hook `command`. Binary has both `os/exec.Command` (token-aware) and `/bin/sh` strings, but I did not pin down the specific code path used by `runStopHooks`. Easiest empirical test: once cli-tran loads, run with a `command` that includes a space and observe.
3. Whether `hooks/hooks.json` is the importer's path or whether `gemini-extension.json` must include a `hooks` field pointing to the file — `StageHooks` exists but its discovery rule was not extracted from binary symbols alone. Reading any shipped extension that has hooks but ISN'T maestro would resolve this; none of the 6 remaining extensions ship a hooks file.
4. Whether deleting `import_manifest.json` is safe (will it cause `agy` to lose the other 7 plugins or re-stage them safely?).

Sources:
- Microsoft Learn was not consulted (non-MS topic).
- Web search via WebFetch on `geminicli.com/docs/hooks/reference/` listed events without `Stop`, but the binary itself clearly registers `Stop`, indicating Antigravity-CLI extends the gemini-cli hook set — trust the binary.
