#!/usr/bin/env bash
# Run as root on the existing Debian 13 Zigbee host; web/ is next to scripts/.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo on the Orange Pi.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "$0")/../web" && pwd)
for file in index.html app.js style.css nginx.conf; do test -f "$SOURCE/$file"; done
if systemctl is-active --quiet nginx; then
    echo 'An existing system nginx is active; refusing to replace it.' >&2; exit 1
fi
if [[ -e /opt/plantctl-web && ! -f /etc/plantctl/web.owner ]]; then
    echo 'Unowned /opt/plantctl-web exists; refusing to overwrite it.' >&2; exit 1
fi
# Prevent the package default server from being started with unrestricted access.
systemctl mask nginx.service
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nginx-light
install -d -m 0755 /opt/plantctl-web /etc/plantctl
install -m 0644 "$SOURCE/index.html" "$SOURCE/app.js" "$SOURCE/style.css" /opt/plantctl-web/
install -m 0644 "$SOURCE/nginx.conf" /etc/plantctl/web-nginx.conf
# Keep upstream credentials on the host, outside the public document root.
python3 - <<'PY'
import os
from pathlib import Path
from urllib.parse import quote
import yaml
try:
    config = yaml.safe_load(Path('/var/lib/plantctl/zigbee2mqtt/configuration.yaml').read_text())
    token = config['frontend']['auth_token']
    if not isinstance(token, str) or not token:
        raise ValueError('missing token')
except Exception:
    raise SystemExit('Cannot load the existing gateway credential; details omitted.') from None
path = Path('/etc/plantctl/web-upstream.conf')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write('proxy_pass http://127.0.0.1:8080/api?token=' + quote(token, safe='') + ';\n')
PY
printf '%s\n' plantctl.web > /etc/plantctl/web.owner
cat > /etc/systemd/system/plantctl-web.service <<'UNIT'
[Unit]
Description=Plantctl local garden dashboard
After=network.target plantctl-zigbee2mqtt.service

[Service]
Type=simple
DynamicUser=yes
RuntimeDirectory=plantctl-web
LoadCredential=upstream.conf:/etc/plantctl/web-upstream.conf
ExecStartPre=/usr/sbin/nginx -t -c /etc/plantctl/web-nginx.conf
ExecStart=/usr/sbin/nginx -c /etc/plantctl/web-nginx.conf -g "daemon off;"
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=3
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_UNIX

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable plantctl-web.service
systemctl restart plantctl-web.service
systemctl is-active plantctl-web.service
