# AGENTS.md

## Local dashboard

- Main dashboard: `http://192.168.50.102/` over Wi-Fi, or `http://192.168.50.101/` over Ethernet. Source: `web/`; deployment: `scripts/install-web.sh`; service: `plantctl-web`.
- The dark dashboard is passwordless for trusted LAN clients and connects automatically. Its proxy loads the existing upstream token via systemd credentials; never serve/store that token in frontend assets or Git. Original advanced UI remains password-protected on port 8080, but the trusted-LAN proxy exposes the same gateway API (not a separate restricted authorization role).
- Read `docs/web-dashboard.md` for architecture, security boundaries and validation. Daily scheduling is implemented in `controller/`, owned by `plantctl-scheduler.service`, persisted under `/var/lib/plantctl-scheduler/`; it runs independently of the page. Calendar automation is not implemented.
- Daily times use Asia/Shanghai, default disabled; the 24-hour dial previews half-hour steps, then saves explicitly. Legacy minute-level inputs remain compatible. Enable/edit/restart reconciles the current window; manual controls last until the next schedule edge. Reinstalling restarts the scheduler, so review enabled rules first.
- Device status is server-owned: one non-retained MQTT query every 30 seconds, fresh non-retained state expires after 90 seconds. `/device-status` reads never trigger extra device queries. Do not reintroduce a refresh button or normal-state update timestamps.
- Test with `node --test tests/test_web.cjs tests/test_schedule_ui.cjs tests/test_dial.cjs` and `uv run --with 'paho-mqtt>=2,<3' --with 'PyYAML>=6,<7' python -m unittest discover -s tests -p 'test_*.py' -v`. Do not toggle real loads or enable real schedules merely to test the UI without confirming that it is safe.

## Orange Pi network access

- Device: `orangepizero3`; SSH user: `terence`.
- Router / gateway: `192.168.50.10`.
- Wi-Fi SSID: `GL-MT3000-TRC-5G`. Do not record Wi-Fi passwords in the repository.
- Router DHCP reservations (user-confirmed):
  - Ethernet (`end0`): `192.168.50.101`.
  - Wi-Fi (`wlan0`): `192.168.50.102`; MAC `58:2a:55:00:ef:ad`.
- Ethernet is preferred when connected (route metric 100); Wi-Fi automatically connects and provides the fallback route (metric 600).
- The device uses Netplan with systemd-networkd. Wi-Fi configuration is persisted in `/etc/netplan/30-wifis-dhcp.yaml`; `disable-wifi.service` is disabled.
- The workstation's existing SSH alias `orangepizero3` points to Ethernet `.101`. For Wi-Fi access, use the explicit address and the existing device host-key identity:
  ```sh
  ssh -o HostKeyAlias=orangepizero3 terence@192.168.50.102
  ```
- Verified with Ethernet unplugged: Wi-Fi-only SSH access, followed by a normal reboot and successful SSH reconnection to `.102`. The boot ID changed, Ethernet carrier remained 0, and the default route used `wlan0`. Sudden power-loss recovery was not tested.
