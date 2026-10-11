#!/usr/bin/env bash
# Local test stack; no automatic host package, permission, or firmware changes.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STATE="$ROOT/.local/zigbee"
POD=plantctl-zigbee
MOS=plantctl-mosquitto
Z2M=plantctl-zigbee2mqtt
OWNER=plantctl.local-zigbee

usage() {
    printf '%s\n' \
        'Usage: scripts/setup-zigbee.sh [check|up|down|status|logs|--help]' \
        '  check   Detect a SONOFF Dongle-E and check serial access (default).' \
        '  up      Pull images, initialize missing config, and start local services.' \
        '  down    Remove the test pod; preserve configuration and network data.' \
        '  status  Show container state.' \
        '  logs    Show the last 100 Zigbee2MQTT log lines.' \
        'Environment: SERIAL_DEVICE=/dev/serial/by-id/... to select a Dongle-E.' \
        '             MOSQUITTO_IMAGE (default docker.io/library/eclipse-mosquitto:2)' \
        '             ZIGBEE2MQTT_IMAGE (default ghcr.io/koenkk/zigbee2mqtt:latest)' \
        'Endpoints: MQTT 127.0.0.1:1883; UI http://127.0.0.1:8080' \
        'Run as your normal user, not with sudo. No boot service is installed.'
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

ACTION=${1:-check}
if [[ $# -gt 1 ]]; then usage >&2; exit 2; fi
case "$ACTION" in
    --help|-h) usage; exit 0 ;;
    check|up|down|status|logs) ;;
    *) usage >&2; exit 2 ;;
esac
[[ $EUID -ne 0 ]] || fail 'Run as your normal user, not with sudo.'
command -v podman >/dev/null || fail 'Install Podman first (Fedora: sudo dnf install podman).'

# Refuse to operate on another application's pod with the same name.
owned_pod() {
    if podman pod exists "$POD"; then
        [[ $(podman pod inspect --format '{{index .Labels "owner"}}' "$POD") == "$OWNER" ]] ||
            fail "Pod $POD is not owned by this script."
        return 0
    fi
    return 1
}

case "$ACTION" in
    down)
        if owned_pod; then podman pod rm -f "$POD"; fi
        printf 'Stopped. Data preserved in %s\n' "$STATE"
        exit 0 ;;
    status)
        owned_pod || fail 'No test pod exists; run scripts/setup-zigbee.sh up.'
        podman ps -a --pod --filter "pod=$POD"
        exit 0 ;;
    logs)
        owned_pod || fail 'No test pod exists; run scripts/setup-zigbee.sh up.'
        podman logs --tail 100 "$Z2M"
        exit 0 ;;
esac

if [[ -z ${SERIAL_DEVICE:-} ]]; then
    shopt -s nullglob
    devices=(/dev/serial/by-id/*Sonoff*Plus_V2*)
    [[ ${#devices[@]} -eq 1 ]] || fail 'Expected one Dongle-E. Set SERIAL_DEVICE to its /dev/serial/by-id path.'
    SERIAL_DEVICE=${devices[0]}
fi
[[ -c $SERIAL_DEVICE ]] || fail "Not a serial device: $SERIAL_DEVICE"
printf 'Dongle-E: %s -> %s\n' "$SERIAL_DEVICE" "$(readlink -f -- "$SERIAL_DEVICE")"
if [[ ! -r $SERIAL_DEVICE || ! -w $SERIAL_DEVICE ]]; then
    group=$(stat -Lc '%G' -- "$SERIAL_DEVICE")
    printf 'Serial access is missing. Add your user to device group %s:\n' "$group" >&2
    printf '  sudo usermod -aG %q %q\n' "$group" "$(id -un)" >&2
    printf 'Then log out and back in, and rerun this script.\n' >&2
    exit 1
fi
printf 'Serial read/write access: OK (firmware not yet verified).\n'
[[ $ACTION == up ]] || exit 0

if owned_pod; then
    fail 'Test pod already exists. Use status/logs, or down then up to recreate it safely.'
fi
for name in "$MOS" "$Z2M"; do
    if podman container exists "$name"; then fail "Container name already in use: $name"; fi
done

MOSQUITTO_IMAGE=${MOSQUITTO_IMAGE:-docker.io/library/eclipse-mosquitto:2}
ZIGBEE2MQTT_IMAGE=${ZIGBEE2MQTT_IMAGE:-ghcr.io/koenkk/zigbee2mqtt:latest}
podman pull "$MOSQUITTO_IMAGE"
podman pull "$ZIGBEE2MQTT_IMAGE"
umask 077
mkdir -p "$STATE/mosquitto" "$STATE/zigbee2mqtt"
# Never overwrite existing settings or regenerate an existing network key.
if [[ ! -e $STATE/mosquitto/mosquitto.conf ]]; then
    printf '%s\n' 'listener 1883' 'allow_anonymous true' 'persistence false' 'log_dest stdout' \
        > "$STATE/mosquitto/mosquitto.conf"
fi
if [[ ! -e $STATE/zigbee2mqtt/configuration.yaml ]]; then
    printf '%s\n' \
        'version: 4' \
        'mqtt:' \
        '  base_topic: zigbee2mqtt' \
        '  server: mqtt://127.0.0.1:1883' \
        'serial:' \
        '  port: /dev/ttyUSB0' \
        '  adapter: ember' \
        '  baudrate: 115200' \
        '  rtscts: false' \
        'frontend:' \
        '  enabled: true' \
        '  port: 8080' \
        'homeassistant:' \
        '  enabled: false' \
        'advanced:' \
        '  network_key: GENERATE' \
        '  pan_id: GENERATE' \
        '  ext_pan_id: GENERATE' \
        > "$STATE/zigbee2mqtt/configuration.yaml"
fi

podman pod create --name "$POD" --userns=keep-id --label "owner=$OWNER" \
    -p 127.0.0.1:1883:1883 -p 127.0.0.1:8080:8080
# A startup failure removes only this newly created pod, never persistent data.
trap 'podman pod rm -f "$POD" >/dev/null 2>&1 || true' ERR
podman run -d --name "$MOS" --pod "$POD" --user "$(id -u):$(id -g)" \
    -v "$STATE/mosquitto:/mosquitto/config:ro,Z" "$MOSQUITTO_IMAGE"
# Disable SELinux container labeling only for the USB consumer, not host-wide.
podman run -d --name "$Z2M" --pod "$POD" \
    --user "$(id -u):$(id -g)" --group-add keep-groups \
    --security-opt label=disable --device "$SERIAL_DEVICE:/dev/ttyUSB0" \
    -v "$STATE/zigbee2mqtt:/app/data" -e TZ=Asia/Shanghai "$ZIGBEE2MQTT_IMAGE"
trap - ERR
printf '\nContainers launched; this does not yet prove coordinator readiness.\n'
printf 'UI: http://127.0.0.1:8080\nMQTT: 127.0.0.1:1883\n'
printf 'Verify with: scripts/setup-zigbee.sh logs\n'
printf 'If startup fails, check serial contention and Dongle-E firmware compatibility.\n'
