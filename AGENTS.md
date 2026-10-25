# AGENTS.md

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
