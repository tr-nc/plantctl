#!/usr/bin/env bash
# Run on the Debian host as root, after preparing and privately copying data.
set -euo pipefail
umask 077

usage() {
    printf '%s\n' \
        'Usage: install-zigbee-host.sh DATA_DIRECTORY IMAGE LAN_IPV4_CIDR' \
        'Example: sudo bash install-zigbee-host.sh ~/private-stage/data ghcr.io/koenkk/zigbee2mqtt:2.14.2 192.168.50.0/24' \
        'Installs Podman, Mosquitto, a systemd-managed Zigbee container, and a LAN-only web firewall.' \
        'Requires Debian 13, systemd, one SONOFF Dongle-E, and prepared complete data with frontend authentication.' \
        'Preserves existing owned network data; refuses unrelated installations or network-identity changes.' \
        'MQTT: 127.0.0.1:1883. Web: IPv4 port 8080, allowed only from loopback and the supplied private LAN.' \
        'No coordinator flashing, factory reset, pairing, or device-switch commands are performed.'
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
[[ ${1:-} != --help && ${1:-} != -h ]] || { usage; exit 0; }
[[ $# == 3 ]] || { usage >&2; exit 2; }
[[ $EUID == 0 ]] || fail 'Run on the target host with sudo; use --help for the command shape.'
SOURCE=$(realpath -- "$1")
IMAGE=$2
LAN=$3
DATA=/var/lib/plantctl/zigbee2mqtt
OWNER=/etc/plantctl/zigbee-host.owner
QUADLET=/etc/containers/systemd/plantctl-zigbee2mqtt.container
[[ $IMAGE =~ ^ghcr\.io/koenkk/zigbee2mqtt:[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
    fail 'Use a fixed release image, e.g. ghcr.io/koenkk/zigbee2mqtt:2.14.2, not latest.'
. /etc/os-release
[[ $ID == debian && ${VERSION_ID:-} == 13 ]] || fail 'This installer is validated for Debian 13 (Podman 5.4); review other OS releases before adapting it.'
[[ -d /run/systemd/system ]] || fail 'The host must be booted with systemd.'
[[ ! -e $OWNER || $(<"$OWNER") == plantctl.zigbee-host ]] || fail 'Installation owner mismatch.'
for path in "$DATA" "$QUADLET" /etc/mosquitto/conf.d/plantctl-local.conf /etc/systemd/system/plantctl-lan-guard.service; do
    [[ ! -e $path || -e $OWNER ]] || fail "Existing unowned path: $path. Back up and inspect it; no data overwritten."
done
if [[ ! -e $OWNER ]]; then
    if dpkg-query -W -f='${Status}' mosquitto 2>/dev/null | grep -q 'install ok installed'; then
        fail 'An unowned Mosquitto installation exists. Inspect/back up its config before explicitly adopting it; this installer will not replace it.'
    fi
    if command -v podman >/dev/null && podman container exists plantctl-zigbee2mqtt; then
        fail 'An unowned container already uses plantctl-zigbee2mqtt; inspect it before installing.'
    fi
fi
shopt -s nullglob
devices=(/dev/serial/by-id/*Sonoff*Plus_V2*)
[[ ${#devices[@]} == 1 ]] || fail 'Expected one Dongle-E under /dev/serial/by-id; check the USB cable.'
SERIAL=${devices[0]}
[[ -c $SERIAL ]] || fail 'The coordinator serial device is unavailable.'
DEVICE_GROUP=$(stat -Lc '%g' -- "$SERIAL")
python3 - "$SOURCE" "$DATA" "$LAN" <<'PY'
import ipaddress
from pathlib import Path
import sys
import yaml
source, target = map(Path, sys.argv[1:3])
network = ipaddress.ip_network(sys.argv[3], strict=True)
if network.version != 4 or not network.is_private or network.is_loopback or network.prefixlen < 8:
    raise SystemExit('Supply a private IPv4 LAN CIDR, not a public or all-addresses network.')
for name in ('configuration.yaml', 'database.db', 'coordinator_backup.json'):
    if not (source / name).is_file():
        raise SystemExit('Prepared migration data is incomplete; rerun prepare-zigbee-host.py.')
def read_config(path):
    try:
        value = yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError):
        raise SystemExit('Cannot parse configuration; sensitive YAML details omitted.') from None
    if not isinstance(value, dict):
        raise SystemExit('Configuration must contain a mapping.')
    return value
cfg = read_config(source / 'configuration.yaml')
front = cfg.get('frontend', {})
if front.get('host') != '0.0.0.0' or front.get('port') != 8080 or len(front.get('auth_token', '')) < 12:
    raise SystemExit('Prepared frontend must use IPv4 port 8080 with a password of at least 12 characters.')
if cfg.get('mqtt', {}).get('server') != 'mqtt://127.0.0.1:1883':
    raise SystemExit('Prepared MQTT must use the local broker.')
if cfg.get('serial', {}).get('adapter') != 'ember' or cfg.get('serial', {}).get('port') != '/dev/ttyUSB0':
    raise SystemExit('Prepared serial config must use ember and /dev/ttyUSB0 inside the container.')
if (target / 'configuration.yaml').exists():
    old = read_config(target / 'configuration.yaml')
    fields = ('network_key', 'pan_id', 'ext_pan_id', 'channel')
    if any(old.get('advanced', {}).get(k) != cfg.get('advanced', {}).get(k) for k in fields):
        raise SystemExit('Existing network identity differs; refusing to overwrite or reform the network.')
print('Migration and LAN preflight passed; no network secrets displayed.')
PY

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends podman mosquitto mosquitto-clients nftables ca-certificates
# Reuse the fixed release locally; startup and image reuse never contact the registry.
if ! podman image exists "$IMAGE"; then
    podman pull "$IMAGE"
fi
DIGEST=$(podman image inspect "$IMAGE" --format '{{.Digest}}')
[[ $DIGEST =~ ^sha256:[0-9a-f]{64}$ ]] || fail 'Image digest unavailable; refusing an unpinned service.'
PINNED_IMAGE="ghcr.io/koenkk/zigbee2mqtt@$DIGEST"
getent passwd plantctl-zigbee >/dev/null || useradd --system --user-group --home-dir "$DATA" --no-create-home --shell /usr/sbin/nologin plantctl-zigbee
APP_UID=$(id -u plantctl-zigbee)
APP_GID=$(id -g plantctl-zigbee)
install -d -m 0755 /etc/plantctl /etc/containers/systemd /var/lib/plantctl
printf '%s\n' plantctl.zigbee-host > "$OWNER"
chmod 0644 "$OWNER"
if [[ ! -e $DATA/configuration.yaml ]]; then
    [[ ! -e $DATA ]] || fail 'Incomplete existing data directory; inspect it before retrying.'
    cp -a -- "$SOURCE" "$DATA"
    chown -R "$APP_UID:$APP_GID" "$DATA"
    find "$DATA" -type d -exec chmod 0700 {} +
    find "$DATA" -type f -exec chmod 0600 {} +
else
    printf 'Existing owned data retained; frontend password and paired devices unchanged.\n'
    systemctl stop plantctl-zigbee2mqtt.service || true
fi

# A dedicated table changes only access to this application's web port, never SSH.
cat > /etc/plantctl/zigbee-lan.nft <<EOF
destroy table inet plantctl_zigbee
table inet plantctl_zigbee {
    chain input {
        type filter hook input priority -10; policy accept;
        tcp dport 8080 ip saddr { 127.0.0.1, $LAN } accept
        tcp dport 8080 drop
    }
}
EOF
chmod 0644 /etc/plantctl/zigbee-lan.nft
nft --check -f /etc/plantctl/zigbee-lan.nft
cat > /etc/systemd/system/plantctl-lan-guard.service <<'EOF'
[Unit]
Description=LAN-only access to the plantctl Zigbee frontend
Before=plantctl-zigbee2mqtt.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f /etc/plantctl/zigbee-lan.nft
ExecReload=/usr/sbin/nft -f /etc/plantctl/zigbee-lan.nft

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/mosquitto/conf.d/plantctl-local.conf <<'EOF'
# Keep MQTT on the host; only the authenticated frontend is exposed to the LAN.
listener 1883 127.0.0.1
allow_anonymous true
EOF
chmod 0644 /etc/systemd/system/plantctl-lan-guard.service /etc/mosquitto/conf.d/plantctl-local.conf
cat > "$QUADLET" <<EOF
[Unit]
Description=plantctl Zigbee2MQTT gateway
Requires=mosquitto.service plantctl-lan-guard.service
After=mosquitto.service plantctl-lan-guard.service
StartLimitIntervalSec=0

[Container]
Image=$PINNED_IMAGE
Pull=never
ContainerName=plantctl-zigbee2mqtt
Network=host
AddDevice=$SERIAL:/dev/ttyUSB0:rw
Volume=$DATA:/app/data
Volume=/run/udev:/run/udev:ro
User=$APP_UID
Group=$APP_GID
GroupAdd=$DEVICE_GROUP
Environment=TZ=Asia/Shanghai
Environment=NODE_OPTIONS=--max-old-space-size=256
DropCapability=ALL
NoNewPrivileges=true
ReadOnly=true
LogDriver=journald
StopTimeout=30
PodmanArgs=--memory=512m --memory-swap=768m

[Service]
Restart=always
RestartSec=10
TimeoutStartSec=180
TimeoutStopSec=45

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$QUADLET"
systemctl daemon-reload
systemctl enable mosquitto.service plantctl-lan-guard.service
systemctl restart plantctl-lan-guard.service mosquitto.service
# Quadlet's [Install] is applied by the generator; generated units are not enabled manually.
systemctl start plantctl-zigbee2mqtt.service
systemctl is-active mosquitto.service plantctl-lan-guard.service plantctl-zigbee2mqtt.service
printf '\nInstallation applied. Verify broker bridge state, authenticated web access, devices, and reboot before declaring readiness.\n'
