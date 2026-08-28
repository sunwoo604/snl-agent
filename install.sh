#!/bin/sh
# Install snl-agent into a self-contained directory under $HOME.
#
#   curl -fsSL https://raw.githubusercontent.com/sunwoo604/snl-agent/main/install.sh | sh
#
# Layout:
#   ~/.snl-agent/venv/         the virtualenv, owned by this script
#   ~/.snl-agent/bin/snl-agent symlink to the console script
#   ~/.snl-agent/data/         user data; never touched by install or uninstall
#
# Environment:
#   SNL_AGENT_HOME  install prefix            (default: ~/.snl-agent)
#   SNL_AGENT_REPO  git URL or local checkout (default: the GitHub repo)
#   SNL_AGENT_REF   git ref to install        (default: main)
#
# Re-running this script is the upgrade path. It rebuilds venv/ and leaves
# data/ alone.

set -eu

SNL_AGENT_HOME="${SNL_AGENT_HOME:-$HOME/.snl-agent}"
# HTTPS, not the git@ SSH form: an installer must work for people who have no
# SSH key for this repo.
SNL_AGENT_REPO="${SNL_AGENT_REPO:-https://github.com/sunwoo604/snl-agent}"
SNL_AGENT_REF="${SNL_AGENT_REF:-main}"

VENV="$SNL_AGENT_HOME/venv"
BIN="$SNL_AGENT_HOME/bin"
DATA="$SNL_AGENT_HOME/data"
LOCAL_BIN="$HOME/.local/bin"

say() { printf '==> %s\n' "$*"; }
err() { printf 'error: %s\n' "$*" >&2; exit 1; }

# --- python ----------------------------------------------------------------
# 3.11 is a hard floor: tasks/convert.py imports tomllib. Probing ourselves
# gives a far better message than pip's requires-python failure.
find_python() {
    for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

if ! PY=$(find_python); then
    err "no Python 3.11 or newer found on PATH.
  snl-agent needs 3.11+ for tomllib.
  macOS:  brew install python@3.12
  Linux:  apt install python3.12-venv  (or your distro's equivalent)"
fi
say "using $PY ($("$PY" --version 2>&1))"

# --- source ----------------------------------------------------------------
# A local directory installs straight from the working tree. That is how this
# script is tested before a first commit exists, and how contributors install
# their own checkout. Anything else is treated as a git URL.
if [ -d "$SNL_AGENT_REPO" ]; then
    SOURCE="$SNL_AGENT_REPO"
    say "installing from local checkout $SOURCE"
else
    command -v git >/dev/null 2>&1 || err "git is required to install from $SNL_AGENT_REPO"
    SOURCE="git+$SNL_AGENT_REPO@$SNL_AGENT_REF"
    say "installing from $SNL_AGENT_REPO@$SNL_AGENT_REF"
fi

# --- venv ------------------------------------------------------------------
# Refuse to delete anything at venv/ that is not actually a virtualenv, in
# case SNL_AGENT_HOME was pointed somewhere unintended.
if [ -e "$VENV" ] && [ ! -f "$VENV/pyvenv.cfg" ]; then
    err "$VENV exists but is not a virtualenv; refusing to remove it"
fi
rm -rf "$VENV"

mkdir -p "$SNL_AGENT_HOME" "$BIN" "$DATA"
say "creating virtualenv at $VENV"
"$PY" -m venv "$VENV"

"$VENV/bin/python" -m pip install --quiet --upgrade pip
say "installing snl-agent"
"$VENV/bin/python" -m pip install --quiet "$SOURCE"

[ -x "$VENV/bin/snl-agent" ] || err "install finished but $VENV/bin/snl-agent is missing"
ln -sf "$VENV/bin/snl-agent" "$BIN/snl-agent"

# --- PATH ------------------------------------------------------------------
# Never edit shell rc files: too many of them, and getting idempotency wrong
# corrupts a user's shell. Link into ~/.local/bin when that is already on
# PATH, otherwise print the line and let the user paste it.
case ":$PATH:" in
    *":$LOCAL_BIN:"*) LOCAL_BIN_ON_PATH=1 ;;
    *)                LOCAL_BIN_ON_PATH=0 ;;
esac

LINKED_INTO_LOCAL_BIN=0
if [ "$LOCAL_BIN_ON_PATH" -eq 1 ]; then
    mkdir -p "$LOCAL_BIN"
    ln -sf "$VENV/bin/snl-agent" "$LOCAL_BIN/snl-agent"
    LINKED_INTO_LOCAL_BIN=1
fi

# --- verify ----------------------------------------------------------------
"$BIN/snl-agent" --help >/dev/null 2>&1 || err "installed, but 'snl-agent --help' failed"

# --- report ----------------------------------------------------------------
echo
say "snl-agent installed"
echo "    program:  $VENV"
echo "    data:     $DATA"

if [ "$LINKED_INTO_LOCAL_BIN" -eq 1 ]; then
    echo "    command:  $LOCAL_BIN/snl-agent"
    echo
    echo "Run 'snl-agent --help' to get started."
else
    echo "    command:  $BIN/snl-agent"
    echo
    echo "$BIN is not on your PATH. Add it:"
    echo
    echo "    export PATH=\"$BIN:\$PATH\""
    echo
    echo "Put that in ~/.zshrc (zsh) or ~/.bashrc (bash), then restart your shell."
fi

echo
echo "snl-agent needs Ollama running locally:"
echo "    ollama serve"
echo "    ollama pull qwen3.6:35b-a3b-coding-bf16"
echo
echo "That model is a large bf16 pull. For a smaller machine, pull something"
echo "lighter and set MODEL, e.g.:"
echo "    ollama pull qwen2.5-coder:7b"
echo "    export MODEL=qwen2.5-coder:7b"
