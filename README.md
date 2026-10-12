# plantctl

An offline-first Rust controller for plant-growing equipment, such as water pumps
and lights, using Zigbee devices through Zigbee2MQTT and Mosquitto.

## Intended setup

Test locally on Fedora first, then deploy to an Orange Pi Zero 3 running a suitable
64-bit Linux system, managed over SSH.
Home Assistant, cloud accounts, and internet access are not required for core
control. Installation and remote administration require an appropriate network
connection or other means of transferring software.

```text
plantctl (Rust)
    ↕ MQTT
Mosquitto (local broker)
    ↕ MQTT
Zigbee2MQTT
    ↕ USB Zigbee coordinator
Zigbee plugs and sensors
    ↓
Pumps and lights
```

The planned host is an Orange Pi Zero 3. Current test hardware is recorded below.
Verify suitability for the actual electrical loads before use.

## Current hardware

| Item | Model / identity | Verified details |
| --- | --- | --- |
| USB Zigbee coordinator | SONOFF **ZBDongle-E (Plus V2)** | Zigbee2MQTT adapter: `ember`; EmberZNet firmware **7.4.4**; successfully formed a network on Fedora |
| Metering smart plug | Zigbee model **TS011F**; manufacturer identifier **`_TZ3210_cehuw1lw`** | Zigbee2MQTT definition: **`TS011F_plug_1`**; firmware **1.1.3**; friendly name **`plant-light`** |

Coordinator label details (provided by the user):

- Product name: **Zigbee 3.0 USB Dongle Plus**.
- Model: **E** (`ZBDongle-E`).
- Purchase price: **CNY 94** (provided by the user).
- Rated input: **5 V DC, 100 mA** (label rating, not measured consumption).
- Working temperature: **−10 °C to +40 °C**.
- Enclosure: **aluminum alloy**, dimensions **75 × 25.5 × 13.5 mm**.
- Antenna: **one external antenna**.
- Interface: **USB Type-A**.

Plug label details (provided by the user):

- Manufacturer: **文光汇**.
- Product model: **WHDZ04**.
- Purchase price: **CNY 35** (provided by the user).
- Supported platform: **Tuya (涂鸦)**; not necessarily manufactured by Tuya.
- Network: **Zigbee**, consistent with the verified pairing.
- Stated rated current: **10 A** (current rating, not power or a verified motor-load rating).
- Energy metering: **supported**, with MQTT metering reports observed.
- Working-voltage range: **85–240 V** (provided by the user).
- Separate voltage marking: **250 V**, likely a rated upper limit according to
  the user; its precise meaning remains unverified. It is not the stated
  operating-voltage range.
- Enclosure material: **V0-rated flame-retardant PC (polycarbonate)**, as reported
  by the user; certification has not been independently verified.
- Working temperature: **−20 °C to +40 °C**.
- An earlier user-provided wireless-standard description was **IEEE 802.11 b/g/n,
  2.4 GHz** (Wi-Fi). The subsequently confirmed network is **Zigbee**. The source
  of that discrepancy remains unverified; Wi-Fi capability is not established.

Zigbee2MQTT classifies the plug under Tuya-compatible devices; this does not
establish its retail brand. Keep the manufacturer identifier alongside `TS011F`,
since that model is shared by variants.

### WHDZ04 pairing procedure

User-confirmed procedure:

1. Power the plug without a pump or other hazardous load connected.
2. Temporarily enable **Permit join** in the Zigbee2MQTT frontend.
3. Hold the plug's button for approximately **10 seconds**, until its **green LED
   flashes rapidly**, indicating pairing mode.
4. Wait for the device to appear and its interview to complete successfully.
5. Disable **Permit join**, then name the device and test ON/OFF in the frontend.

### Plug verification

The plug completed its interview and supports working frontend ON/OFF control.
MQTT reports power (W), current (A), voltage (V), and cumulative energy (kWh).
Observed readings included 25 W, 0.21 A, 229 V, and 0 kWh; metering accuracy and
energy accumulation over time have not yet been validated. `energy` is read-only
in the exposed interface, with no energy-reset command. Application-level usage
statistics can use a saved baseline instead. Power-restoration configuration was
reported as `off`; actual power-cycle behavior still needs testing.

## Planned behavior

- Control equipment by schedules and sensor conditions.
- Keep configuration and necessary execution records locally.
- Subscribe to device reports and publish commands through MQTT using `rumqttc`.
- Use calendar time for schedules and monotonic time for run durations.
- Run as a `systemd` service alongside Mosquitto and Zigbee2MQTT.

## Safety requirements

- Enforce a maximum pump runtime; do not rely on separate on/off schedules.
- Never retain actuation commands; prevent stale commands from running after reconnects.
- Treat command publication, device state reports, and actual water flow as distinct
  signals. Handle unavailable devices, stale sensor data, and confirmation timeouts.
- Define restart recovery, duplicate-run prevention, and missed-schedule behavior.
- Require trustworthy calendar time for schedules; use a battery-backed RTC when
  reliable offline operation after power loss is needed.
- Validate plug power-restoration behavior and preserve independent hardware
  timeout, dry-run, and electrical protections where needed. Software and wireless
  control alone cannot guarantee safe shutdown.

## Local Fedora test setup

Install Podman if necessary (`sudo dnf install podman`), then run as your normal
user. For routine startup, including after reboot, use:

```bash
./scripts/start-zigbee.sh
```

This starts or resumes the local services, preserves paired devices and network
data, and waits for <http://127.0.0.1:8080> to respond. It is safe to rerun when
services are already running. It does not install automatic boot startup or
change device switch states.

For individual setup and diagnostic operations:

```bash
./scripts/setup-zigbee.sh check
./scripts/setup-zigbee.sh up
./scripts/setup-zigbee.sh status
./scripts/setup-zigbee.sh logs
```

The script detects a single SONOFF Dongle-E, or accepts `SERIAL_DEVICE` pointing
to its `/dev/serial/by-id/` path. If serial access is missing, it prints the group
membership command; log out and back in after applying it. Rootless Podman uses
`keep-groups`, which requires the `crun` runtime.

Mosquitto and Zigbee2MQTT share a Podman pod. MQTT is available at
`127.0.0.1:1883`, and the frontend at <http://127.0.0.1:8080>. This is a local,
anonymous-auth test stack, not a secured production deployment. The Zigbee2MQTT
container alone has SELinux container labeling disabled for USB access; the script
does not disable SELinux globally or change device permissions.

Configuration and Zigbee network data live in ignored `.local/zigbee/`. Reruns
preserve existing configuration. `up` refuses to replace an existing pod; use
`down` followed by `up` to recreate containers without deleting data. Do not delete
network keys or backups casually; keep them for migration to the Orange Pi.

```bash
./scripts/setup-zigbee.sh down
```

Startup pulls Mosquitto `:2` and Zigbee2MQTT `:latest`; use `MOSQUITTO_IMAGE` and
`ZIGBEE2MQTT_IMAGE` to select fixed versions for reproducible testing. No automatic
boot service or firmware flashing is configured. Only one application may use the
coordinator at a time. The `ember` adapter requires compatible coordinator firmware;
USB detection alone does not verify that firmware or successful Zigbee startup.
Check logs before pairing, enable joining temporarily in the frontend, and close
joining afterward. Test plugs without connected pumps or other hazardous loads.

Official references: [container installation](https://www.zigbee2mqtt.io/guide/installation/02_docker.html)
and [Dongle-E / Ember adapter](https://www.zigbee2mqtt.io/guide/adapters/emberznet.html).

## Status

Local Fedora startup verified: Mosquitto and Zigbee2MQTT are connected, the
Dongle-E runs EmberZNet 7.4.4, a Zigbee network has formed, and the frontend returns
HTTP 200. The `plant-light` plug is paired, frontend switching works, and metering
data is reported. Controller implementation, metering accuracy, power-cycle
behavior, and load-safety validation remain outstanding.

## Design references

Documentation is maintained in this repository:

- [Zero 3 storage and OS choices](docs/zero3-storage-and-os.md)
- [Original Raspberry Pi Zigbee guide](docs/raspberry-pi-zigbee.md) — historical planning reference
- [Original Zigbee plug research](docs/raspberry-pi-zigbee-plug-research.md) — historical purchasing reference

The current hardware inventory above supersedes the original purchasing suggestions.
