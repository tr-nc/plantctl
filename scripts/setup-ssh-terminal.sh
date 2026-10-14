#!/usr/bin/env bash
# Install the client's terminal definition for one SSH login user; no sudo or TERM override.
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage: scripts/setup-ssh-terminal.sh SSH_TARGET [TERMINAL_TYPE]' \
        '  SSH_TARGET      An SSH alias or user@hostname, e.g. orange-pi-zero-3.' \
        '  TERMINAL_TYPE   Defaults to the current local $TERM.' \
        'Examples:' \
        '  ./scripts/setup-ssh-terminal.sh orange-pi-zero-3 xterm-kitty' \
        '  ./scripts/setup-ssh-terminal.sh user@raspberrypi.local' \
        'Requires local ssh/infocmp and remote ncurses tic/infocmp/tput.' \
        'Uses ordinary SSH authentication and host-key checks; never stores a password.' \
        'Writes only the selected terminal entry (and its aliases) in remote ~/.terminfo.' \
        'Safe to rerun. Does not change TERM, SSH config, or system-wide terminal data.'
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

if [[ $# -eq 1 && ( $1 == --help || $1 == -h ) ]]; then usage; exit 0; fi
if [[ $# -lt 1 || $# -gt 2 ]]; then usage >&2; exit 2; fi
host=$1
if [[ $# -eq 2 ]]; then terminal=$2; else terminal=${TERM:-}; fi
case "$host" in
    ''|-*) printf 'Error: specify an SSH alias or user@hostname, not an option.\n' >&2; usage >&2; exit 2 ;;
esac
# The terminal is embedded in a remote shell command: accept names, never shell syntax.
case "$terminal" in
    ''|-*|*[!A-Za-z0-9_.+-]*)
        printf 'Error: invalid terminal type; pass a name such as xterm-kitty.\n' >&2
        exit 2 ;;
esac
for tool in ssh infocmp mktemp; do
    command -v "$tool" >/dev/null || fail "Missing local $tool; install OpenSSH and ncurses tools."
done

source_file=$(mktemp)
trap 'rm -f -- "$source_file"' EXIT
# Expand the local database entry, retaining extended capabilities. Compile on the target.
if ! infocmp -a -x "$terminal" > "$source_file"; then
    fail "Local terminfo has no $terminal entry. Install its terminal package on this computer first."
fi

remote_command='set -eu
for tool in tic infocmp tput; do
    if ! command -v "$tool" >/dev/null; then
        printf "Error: missing remote %s; on Debian/Ubuntu install ncurses-bin.\n" "$tool" >&2
        exit 1
    fi
done
umask 077
mkdir -p "$HOME/.terminfo"
tic -x -o "$HOME/.terminfo" /dev/stdin
'
remote_command+=$'\n'"infocmp -x '$terminal' >/dev/null"
remote_command+=$'\n'"TERM='$terminal' tput longname >/dev/null"
remote_command+=$'\n'"printf 'Terminal definition installed and verified: %s (user %s)\\n' '$terminal' \"\$(id -un)\""
ssh -o ConnectTimeout=10 "$host" "$remote_command" < "$source_file"
