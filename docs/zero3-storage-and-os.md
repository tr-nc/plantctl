# Orange Pi Zero 3: storage, OS, and first-boot setup

## Intended use

Run Mosquitto, Zigbee2MQTT, and the Rust controller without a desktop. Connect the
board over Wi-Fi and manage it from Fedora using SSH; no router Ethernet port is
planned. The board, TF card, and reader have arrived. The system card has been
flashed and configured for Wi-Fi. First boot, Wi-Fi connectivity, SSH key login,
and root-filesystem expansion have now been verified.

## Purchased development board

- Model: **Orange Pi Zero 3**.
- RAM: purchased as **1.5GB**; the running kernel reports `MemTotal: 1505864 kB`
  (approximately **1.44 GiB** usable total), consistent with this variant.
- Condition: **new**, according to the user's description on arrival; not
  independently inspected. This supersedes the earlier second-hand description.
- Purchase price: **CNY 159**, as previously reported by the user.
- Delivery: user-confirmed. Boot, Wi-Fi, SSH, and card expansion: verified.
  USB/Zigbee operation, LAN frontend access, network migration, and reboot
  auto-start: verified; controller and load-safety validation: pending.

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
**A2 / U3 / V30**. Quoted price: **CNY 55**, as previously provided by the user.
The user has confirmed a card and reader arrived. The USB reader reported a card
capacity of **62,723,719,168 bytes**; the exact physical card SKU and authenticity
have not been independently inspected.

TF and microSD refer to the same card form factor here. 64GB provides room for
packages, container images, and logs.

The [Orange Pi official wiki](http://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_Zero_3)
recommends a SanDisk card of at least 8GB, Class 10 or better, citing reported
startup issues with some other cards. This is not proof that all other brands
are incompatible.

SanDisk Extreme variants carry Class 10, U3, V30, and A2 ratings; check the exact
SKU. Class 10 and U3 describe sustained-write speed classes; A1/A2 describe
application-oriented random I/O, not endurance. An A2 card can be used without
assuming the board supports full A2 acceleration. Price and authenticity have not
been independently verified. Basic boot and storage checks passed for this
board/card combination; A2 acceleration and long-term endurance remain untested.

## Flashed OS

**Armbian Debian 13 (Trixie) Minimal for Orange Pi Zero 3**, ARM64, without a
graphical desktop. This is a **community nightly image**, not a claim of stable
or standard supported-board status. The local image identifies itself as
`IMAGE_TYPE=nightly`, `BOARD_TYPE=csc`, and `BOARD=orangepizero3`.

- Release: **26.11.0-trunk.83**, current kernel **6.18.55**.
- File: `Armbian_community_26.11.0-trunk.83_Orangepizero3_trixie_current_6.18.55_minimal.img.xz`.
- Source: Armbian's `dl.armbian.com` redirect pointed to the
  [armbian/community GitHub release](https://github.com/armbian/community/releases/tag/26.11.0-trunk.83).
  Direct board-page access failed from the development computer.
- Archive SHA-256 matched the digest from the GitHub release metadata:
  `71056d9db84474fa92e5c2c8ba5cd15883a49289fef0c76706e99b19706d222d`.
  Archive integrity also passed `xz -t`; no detached-signature verification was performed.
- The **1,619,001,344-byte** uncompressed image was written to the identified
  removable USB card, flushed, and every written byte was compared with the image
  after flushing block-device caches. Readback passed.
- The initial ext4 partition is approximately **1.5 GiB**, labeled `armbi_root`.
  This is the image's initial partition size, not the full card capacity;
  first-boot expansion has since been verified: the root filesystem reports
  approximately **57 GiB**, with **55 GiB** available at the first check.

Fallback, if real hardware validation fails: Orange Pi's board-specific
**Debian Server** image. Fedora is not the first choice: general AArch64 support
does not establish Zero 3 boot and onboard Wi-Fi support.

## Wi-Fi configuration on the system card

The Fedora computer was actually connected by Ethernet, with no saved Wi-Fi
profile in NetworkManager. Its disconnected wireless adapter was used only to
scan nearby networks. The user selected a network and entered its password in
local dialogs; neither the password nor the credentials file contents were
printed. The reusable interface is now documented in
[Wi-Fi selector](wifi-selector.md).

The actual image uses **Netplan 1.1.2 + systemd-networkd**, with `wpasupplicant`
installed. A separate root-owned, mode-`0600` file was written on the card:

```text
/etc/netplan/30-wifis-dhcp.yaml
```

It configures `wlan0`, DHCP, and regulatory domain `CN`; the existing Ethernet
DHCP defaults were preserved. This Netplan networkd generator does not support
Wi-Fi `match:` rules, so no wildcard interface match was used. The actual board
has now booted with kernel `6.18.55-current-sunxi64`; `wlan0` is up with a DHCP
address, and SSH is reachable from the wired Fedora computer. The connected
frequency band has not been verified.

YAML serialization and configuration readback passed; owner and permissions were
checked. The temporary credentials file on the Fedora computer was deleted, and
the card was synced, unmounted, and the USB reader safely powered off. Subsequent
first-boot checks confirmed that Wi-Fi connects and the board can be managed over
SSH.

## First-boot results and SSH access

Verified through a real SSH session:

- Board model: `OrangePi Zero3`; architecture: `aarch64`.
- Hostname: `orangepizero3`; first observed DHCP address: `192.168.50.101`.
- User: `terence`; existing Fedora Ed25519 public key authorized for this user.
- Usable total RAM: approximately **1.44 GiB**; available RAM was approximately
  **1.3 GiB** at the initial check. Swap reported **735 MiB**, which is not
  additional physical RAM.
- Root filesystem: `/dev/mmcblk0p1`, approximately **57 GiB** after expansion.
- SSH password-free login validated with `BatchMode=yes` and strict host-key
  checking, using the same host key the user accepted at first login.

The Fedora computer's `~/.ssh/config` is a symlink to the managed source at
`~/code/config-guides/autoconfs/ssh/config`. That source now defines `orange-pi-zero-3`,
using hostname `orangepizero3`, user `terence`, and `~/.ssh/id_ed25519`.
`orange-pi-zero-3` is only this computer's SSH shortcut, named for the hardware
rather than a project; it does not rename the remote host or its services.
On this computer:

```bash
ssh orange-pi-zero-3
ssh orange-pi-zero-3 'free -h'
```

The board's password is **not** in SSH config, this repository, or a retained
temporary file. Only the public key was installed on the board; the private key
stays on Fedora and is available through the existing SSH agent. On future
sessions the agent may need unlocking if the private key is passphrase-protected.
Hostname resolution depends on a reachable local DNS entry; this is not public
internet access or a static-IP guarantee.

## SSH terminal compatibility

The default terminfo database did not recognize `xterm-kitty`, despite
`ncurses-term` being installed. This reproduced through real SSH TTY allocation
and caused `tput` to exit `3`. The reusable initialization step is:

```bash
./scripts/setup-ssh-terminal.sh orange-pi-zero-3 xterm-kitty
```

The client's definition was compiled into `terence`'s `~/.terminfo`, keeping the
advertised terminal type unchanged. Subsequent SSH tests returned 256 colors,
valid column count and clear-screen capability; `xterm-256color` remained working.
This is per-user configuration, not a system-wide or root/sudo guarantee.
See [diagnosis, setup script, and validation](ssh-terminal-setup.md).

Mosquitto and Zigbee2MQTT have now been deployed, with the original network,
LAN frontend login, live device reports, and reboot auto-start verified. See
[the live gateway record](zigbee-host-deployment.md). Next: implement automation
and validate load-safety and recovery behavior. Keep real credentials and Zigbee
network keys out of Git.

## Sources

- [SanDisk Extreme data sheet](https://documents.sandisk.com/content/dam/asset-library/en_us/assets/public/sandisk/product/memory-cards/extreme-uhs-i-microsd/data-sheet-extreme-uhs-i-microsd.pdf)
- [SD Association: speed classes](https://www.sdcard.org/developers/sd-standard-overview/speed-class/)
- [SD Association: application performance classes](https://www.sdcard.org/developers/sd-standard-overview/application-performance-class/)
- [Armbian Zero 3 listing](https://oldwww.armbian.com/orange-pi-zero-3/) — minimal/community status found through search; direct current board-page access failed.
- [Armbian first-boot configuration](https://docs.armbian.com/user-guide/autoconfig/)
- [Armbian UWE5622 wireless driver](https://github.com/armbian/uwe5622)
