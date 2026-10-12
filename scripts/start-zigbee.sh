#!/usr/bin/env bash
# Start or resume the local stack without replacing containers or network data.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SETUP="$ROOT/scripts/setup-zigbee.sh"
POD=plantctl-zigbee
URL=http://127.0.0.1:8080

case "${1:-}" in
    --help|-h)
        printf '%s\n' 'Usage: scripts/start-zigbee.sh' \
            'Start/resume local Zigbee services and wait for the device-control webpage.' \
            'Existing configuration, paired devices, and network data are preserved.'
        exit 0 ;;
    '') [[ $# -eq 0 ]] || { printf 'Usage: scripts/start-zigbee.sh\n' >&2; exit 2; } ;;
    *) printf 'Usage: scripts/start-zigbee.sh\n' >&2; exit 2 ;;
esac

"$SETUP" check
if podman pod exists "$POD"; then
    # status verifies ownership before we start an existing pod.
    "$SETUP" status >/dev/null
    podman pod start "$POD" >/dev/null
else
    "$SETUP" up
fi

for ((attempt = 0; attempt < 30; attempt++)); do
    if curl --fail --silent --output /dev/null --max-time 2 "$URL"; then
        printf '\nDevice-control webpage ready: %s\n' "$URL"
        exit 0
    fi
    sleep 2
done
printf '\nWebpage did not become ready; recent startup logs follow.\n' >&2
"$SETUP" logs >&2
exit 1
