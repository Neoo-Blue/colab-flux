#!/bin/sh
# colab-flux installer: the skill, the fluxx CLI, uv, and the Colab CLI. Safe to run again (it updates).
#   curl -fsSL https://raw.githubusercontent.com/Neoo-Blue/colab-flux/main/install.sh | sh
# or, from a clone: sh install.sh
set -eu
REPO=https://github.com/Neoo-Blue/colab-flux

case "$(uname -s)" in
  Darwin|Linux) ;;
  *) echo "colab-flux needs macOS or Linux (on Windows, run it inside WSL2: wsl --install -d Ubuntu)"; exit 1 ;;
esac
for c in git python3 curl; do
  command -v "$c" >/dev/null 2>&1 || { echo "missing $c: install it and run this again"; exit 1; }
done

# Where the skill lives: this folder if run from a clone, else Claude Code's skills folder
# (or ~/.agents/skills when Claude Code is not installed).
SELF=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)
if [ -n "$SELF" ] && [ -f "$SELF/fluxx" ] && [ -f "$SELF/SKILL.md" ]; then
  DIR=$SELF
else
  if [ -d "$HOME/.claude" ]; then DIR=$HOME/.claude/skills/colab-flux; else DIR=$HOME/.agents/skills/colab-flux; fi
  if [ -d "$DIR/.git" ]; then git -C "$DIR" pull -q --ff-only; else mkdir -p "$(dirname "$DIR")"; git clone -q --depth 1 "$REPO" "$DIR"; fi
fi
chmod +x "$DIR/fluxx"

# Make the skill visible to every agent that is installed.
for base in "$HOME/.claude" "$HOME/.agents" "$HOME/.codex"; do
  if [ -d "$base" ] && [ "$base/skills/colab-flux" != "$DIR" ]; then
    mkdir -p "$base/skills"
    ln -sfn "$DIR" "$base/skills/colab-flux"
  fi
done
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/fluxx" "$HOME/.local/bin/fluxx"
export PATH="$HOME/.local/bin:$PATH"

command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
command -v colab >/dev/null 2>&1 || uv tool install -q google-colab-cli

echo "colab-flux installed at $DIR"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "note: add ~/.local/bin to your PATH" ;; esac
fluxx selftest
fluxx doctor || echo "
Next: run 'fluxx login' in a terminal (Google sign-in for Colab; the Hugging Face token is optional),
then ask your agent for product pictures. It will set up your brand with a few questions."
