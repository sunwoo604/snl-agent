#!/bin/sh
# Remove an snl-agent installation created by install.sh.
#
#   sh uninstall.sh            remove the program, keep ~/.snl-agent/data
#   sh uninstall.sh --purge    remove everything, including user data
#
# Environment:
#   SNL_AGENT_HOME  install prefix (default: ~/.snl-agent)

set -eu

SNL_AGENT_HOME="${SNL_AGENT_HOME:-$HOME/.snl-agent}"

VENV="$SNL_AGENT_HOME/venv"
BIN="$SNL_AGENT_HOME/bin"
DATA="$SNL_AGENT_HOME/data"
LOCAL_BIN="$HOME/.local/bin"

PURGE=0
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        -h|--help)
            sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) printf 'error: unknown option %s\n' "$arg" >&2; exit 1 ;;
    esac
done

say() { printf '==> %s\n' "$*"; }

if [ ! -d "$SNL_AGENT_HOME" ]; then
    say "nothing to remove: $SNL_AGENT_HOME does not exist"
    exit 0
fi

# Remove the ~/.local/bin shim only when it points back into our own install.
# Someone may have an unrelated snl-agent on their PATH; it is not ours to delete.
if [ -L "$LOCAL_BIN/snl-agent" ]; then
    target=$(readlink "$LOCAL_BIN/snl-agent")
    case "$target" in
        "$SNL_AGENT_HOME"/*)
            rm -f "$LOCAL_BIN/snl-agent"
            say "removed $LOCAL_BIN/snl-agent"
            ;;
        *)
            say "left $LOCAL_BIN/snl-agent alone (points outside $SNL_AGENT_HOME)"
            ;;
    esac
fi

if [ "$PURGE" -eq 1 ]; then
    # Only ever purge something that looks like one of our installs.
    if [ ! -d "$VENV" ] && [ ! -d "$BIN" ] && [ ! -d "$DATA" ]; then
        printf 'error: %s does not look like an snl-agent install; refusing to purge\n' \
            "$SNL_AGENT_HOME" >&2
        exit 1
    fi
    rm -rf "$SNL_AGENT_HOME"
    say "removed $SNL_AGENT_HOME, including user data"
    exit 0
fi

rm -rf "$VENV" "$BIN"
say "removed the program from $SNL_AGENT_HOME"

# If no user data was ever written, do not leave an empty directory behind.
if [ -d "$DATA" ] && [ -z "$(find "$DATA" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    rmdir "$DATA" 2>/dev/null || true
    rmdir "$SNL_AGENT_HOME" 2>/dev/null || true
fi

if [ -d "$DATA" ]; then
    echo
    echo "Your data was kept:"
    echo "    $DATA"
    echo
    echo "Remove it too with:  sh uninstall.sh --purge"
fi
