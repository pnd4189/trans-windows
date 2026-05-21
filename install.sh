#!/usr/bin/env bash
# Install cli-translator as an Antigravity CLI extension.
#
# Antigravity's CLI scans ~/.gemini/extensions/<name>/ for plugins and registers
# them via the GeminiCLIImporter. `agy plugin install <local-dir>` writes a
# placeholder manifest entry without wiring hooks at runtime, so we use the
# extension-import path instead. Verified working layout matches maestro.
#
# Hook commands are tokenized on whitespace by the runner, so we stage everything
# behind a no-space symlink at ~/.local/share/cli-tran-src that points at the
# repo (the repo itself sits under a path containing a literal space).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PLUGIN_NAME="cli-tran"
AGY_BIN="${AGY_BIN:-$HOME/.local/bin/agy}"
ALIAS_PATH="$HOME/.local/share/cli-tran-src"
EXT_DIR="$HOME/.gemini/extensions/$PLUGIN_NAME"
# Legacy dirs from previous install attempts (drop so they cannot shadow this one).
STALE_PATHS=(
    "$HOME/.gemini/skills/cli-tran"
    "$HOME/.gemini/antigravity-cli/plugins/cli-translator"
    "$HOME/.gemini/extensions/cli-translator"
)

if [[ ! -x "$AGY_BIN" ]]; then
    echo "ERROR: agy binary not found at $AGY_BIN" >&2
    echo "Set AGY_BIN env var or install Antigravity CLI first." >&2
    exit 1
fi

if [[ ! -f "$REPO_ROOT/gemini-extension.json" ]]; then
    echo "ERROR: $REPO_ROOT/gemini-extension.json missing" >&2
    exit 1
fi

echo "Repo:    $REPO_ROOT"
echo "Plugin:  $PLUGIN_NAME"
echo "Alias:   $ALIAS_PATH (no-space hook command path)"
echo "ExtDir:  $EXT_DIR"
echo "agy:     $AGY_BIN"

# Whitespace-tokenization fix: link the repo at a no-space path so the hook
# command resolves cleanly when agy execs it.
mkdir -p "$(dirname "$ALIAS_PATH")"
ln -sfn "$REPO_ROOT" "$ALIAS_PATH"

# Build a fresh extension dir under ~/.gemini/extensions/ — Antigravity scans
# this directory on every startup and the GeminiCLIImporter stages it into
# ~/.gemini/antigravity-cli/plugins/<name>/ with the hooks component registered.
rm -rf "$EXT_DIR"
mkdir -p "$EXT_DIR/skills/$PLUGIN_NAME"

cp "$REPO_ROOT/gemini-extension.json" "$EXT_DIR/gemini-extension.json"

# Hooks: deploy only when the repo declares non-empty hook bindings. The driver
# architecture does not need a Stop hook; an empty hooks.json signals that.
HOOKS_NONEMPTY=$(python3 -c "
import json, sys
try:
    d = json.load(open('$REPO_ROOT/hooks/hooks.json'))
except Exception:
    print('0'); sys.exit(0)
print('1' if d.get('hooks') else '0')
" 2>/dev/null)
if [[ "$HOOKS_NONEMPTY" == "1" ]]; then
    mkdir -p "$EXT_DIR/hooks"
    sed "s|__EXT_ROOT__|$ALIAS_PATH|g" "$REPO_ROOT/hooks/hooks.json" \
        > "$EXT_DIR/hooks/hooks.json"
fi

# Substitute __EXT_ROOT__ with the no-space alias path in SKILL.md.
sed "s|__EXT_ROOT__|$ALIAS_PATH|g" "$REPO_ROOT/skills/$PLUGIN_NAME/SKILL.md" \
    > "$EXT_DIR/skills/$PLUGIN_NAME/SKILL.md"

# contextFileName points at GEMINI.md — symlink so doc edits flow through.
if [[ -f "$ALIAS_PATH/GEMINI.md" ]]; then
    ln -sfn "$ALIAS_PATH/GEMINI.md" "$EXT_DIR/GEMINI.md"
fi

chmod +x "$REPO_ROOT/scripts/auto-translate.sh"

# Clean up legacy install artifacts.
for stale in "${STALE_PATHS[@]}"; do
    if [[ -L "$stale" || -d "$stale" ]]; then
        echo "Removing stale: $stale"
        rm -rf "$stale"
    fi
done

# Drop any previous agy plugin entry so the import runs fresh (and so a stale
# local-install row cannot mask the new gemini-cli import).
"$AGY_BIN" plugin uninstall "$PLUGIN_NAME" >/dev/null 2>&1 || true

# `agy plugin import gemini` re-scans ~/.gemini/extensions/ and stages new ones
# into the manifest with their detected components (skills, hooks, ...). The
# `--force` flag is not needed for newly added extensions.
echo ""
echo "Importing via agy..."
"$AGY_BIN" plugin import gemini

echo ""
echo "Verifying registration:"
"$AGY_BIN" plugin list 2>&1 | grep -A 6 "\"name\": \"$PLUGIN_NAME\"" || {
    echo "ERROR: $PLUGIN_NAME did not appear in agy plugin list" >&2
    exit 1
}

echo ""
echo "Installed. Restart Antigravity CLI (or open a new session) for hooks to be loaded."
