# Orange Pi Zero 3: preliminary storage and OS choices

## Intended use

Run Mosquitto, Zigbee2MQTT, and the Rust controller without a desktop. Connect the
board over Wi-Fi and manage it from Fedora using SSH; no router Ethernet port is
planned. The board has not arrived, so hardware compatibility remains untested.

## Purchased development board

- Model: **Orange Pi Zero 3**.
- RAM: **1.5GB**.
- Condition: **second-hand, near-new** (seller/user description; not yet inspected).
- Purchase price: **CNY 159**, as reported by the user.
- Delivery and hardware validation: pending.

## Selected storage

User-selected card: **SanDisk (闪迪) Extreme 64GB microSDXC UHS-I**, marked
**A2 / U3 / V30**. Quoted price: **CNY 55** (provided by the user; purchase and
hardware validation not yet confirmed).

TF and microSD refer to the same card form factor here. 64GB provides room for
packages, container images, and logs.

The [Orange Pi official wiki](http://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_Zero_3)
recommends a SanDisk card of at least 8GB, Class 10 or better, citing reported
startup issues with some other cards. This is not proof that all other brands
are incompatible.

SanDisk Extreme variants carry Class 10, U3, V30, and A2 ratings; check the exact
SKU. Class 10 and U3 describe sustained-write speed classes; A1/A2 describe
application-oriented random I/O, not endurance. An A2 card can be used without
assuming the board supports full A2 acceleration. Prices, authenticity, and this
specific board/card combination have not been verified.

## OS candidate

**Armbian Minimal / IOT specifically for Orange Pi Zero 3**, preferably a
Debian-based image when available. This is a preliminary candidate, not a
finalized or tested selection.

- No graphical desktop; suitable for a small SSH-managed service host.
- Zero 3 images are community-maintained. Recheck image availability, maintenance,
  and onboard Wi-Fi support when the board arrives.
- Fallback: Orange Pi's board-specific **Debian Server** image.
- Fedora is not the first choice: general AArch64 support does not establish
  Zero 3 boot and onboard Wi-Fi support, and official board support was not found.

## Configuration deferred until hardware arrives

Plan to preconfigure Wi-Fi and login access before first boot, avoiding the need
for Ethernet or a display. Armbian documents first-boot network/account presets;
choose the exact method against the actual downloaded image.

Flashing, configuration commands, first connection, service deployment, and
migration of the existing Zigbee network will be documented as they are tested.
Keep real credentials and Zigbee network keys out of Git.

## Sources

- [SanDisk Extreme data sheet](https://documents.sandisk.com/content/dam/asset-library/en_us/assets/public/sandisk/product/memory-cards/extreme-uhs-i-microsd/data-sheet-extreme-uhs-i-microsd.pdf)
- [SD Association: speed classes](https://www.sdcard.org/developers/sd-standard-overview/speed-class/)
- [SD Association: application performance classes](https://www.sdcard.org/developers/sd-standard-overview/application-performance-class/)
- [Armbian Zero 3 listing](https://oldwww.armbian.com/orange-pi-zero-3/) — minimal/community status found through search; direct current board-page access failed.
- [Armbian first-boot configuration](https://docs.armbian.com/user-guide/autoconfig/)
- [Armbian UWE5622 wireless driver](https://github.com/armbian/uwe5622)
