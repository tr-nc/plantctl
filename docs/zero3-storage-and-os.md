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

## Selected enclosure

User-selected 3D-print model: [Orange Pi Zero 3 Case — Printables #542569](https://www.printables.com/model/542569-orange-pi-zero-3-case).

Selected material/process: **PETG / FDM** (fused deposition modeling). Printing
and physical fit have not yet been verified. Before printing, check the chosen
file variant, Wi-Fi antenna placement, USB access for the SONOFF dongle extension
cable, and clearance for any heatsink or expansion board.

### Assembly and required hardware

From the author's description supplied by the user:

- Print **one base and one chosen top cover**, not every cover variant.
- External-antenna covers route the antenna wire through the slot above the SD
  card and hold the antenna in the retention slots.
- Required fasteners: **4 × M3 × 20mm socket-head cap screws** and **4 × M3 nuts**.

Purchasing guidance:

- Search Taobao for **`M3×20 内六角圆柱头螺丝 304 DIN912`** (socket-head cap screw,
  commonly sold as DIN 912 / ISO 4762). Choose M3 thread diameter and 20mm length;
  length is measured from under the head, not including the head.
- Search for **`M3 六角螺母 304 普通`**. Use ordinary hex nuts, not flange, lock,
  square, or heat-set insert nuts: those may not fit the modeled recesses.
- 304 stainless steel is a practical choice; the author does not require a
  specific fastener material. Buy at least four of each (a ten-piece pack leaves
  spares) and confirm whether the print shop can supply matching fasteners.
- Standard M3 socket-head cap screws normally use a **2.5mm hex key**; confirm with
  the seller and buy one if needed.
- Assemble gently. If recesses are tight or holes obstructed, check print quality
  rather than forcing hardware or overtightening against the PCB/PETG.

### Author's print settings

These are the author's recommendations, transcribed from the user-supplied
Printables description, not a print profile validated by this project:

- Layer height: **0.2mm**.
- Wall thickness: **at least 1mm**.
- Top/bottom thickness: **at least 1mm**.
- Infill: **100% recommended**.
- Enable **Avoid Crossing Perimeters / Combing**, as appropriate to the slicer,
  to reduce stringing in the hex pattern.
- Supports: recommended **only for bolt/nut recess holes**.
- Adhesion: use a little glue stick if adhesion is poor; the print shop should
  choose a PETG-compatible build surface and release method.

The author's update log notes a thicker HEX pattern for nozzles larger than
0.4mm (2023-08-04). Confirm the shop's nozzle size before choosing the file.
Optional printer V-slot mounting versions were added on 2023-08-05 and modified
for V-slot/T-slot on 2023-08-13; those mounting options are not required for our
standalone enclosure.

### Selected model files

The two user-downloaded STL files are stored in this repository, unchanged:

- [Thick HEX base](../models/zero3-case/OrangePiZero3_Base_ThickHex.stl)
- [Thick HEX top with external antenna retention](../models/zero3-case/OrangePiZero3_Top_ThickHex_ExternalAntenna.stl)

These replace the previously selected Standard HEX files. The user selected the
thicker hex-pattern variant; physical fit and print quality remain untested.
Print one of each using PETG / FDM. Source: the Printables model linked above,
by **TheParanoidEngineer**. These are third-party designs, not authored by this
project. The original model's license has not yet been verified; do not assume
commercial printing or redistribution permissions from their inclusion here.

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
