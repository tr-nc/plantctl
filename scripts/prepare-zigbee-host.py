#!/usr/bin/python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML>=6,<7"]
# ///
"""Prepare a private host migration without changing an existing Zigbee network.

Requires PyYAML (Debian/Fedora: python3-yaml). No hardware is accessed.
"""

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

import yaml

NETWORK_FIELDS = ("network_key", "pan_id", "ext_pan_id", "channel")
REQUIRED_FILES = ("configuration.yaml", "database.db", "coordinator_backup.json")


def load_configuration(source: Path) -> dict[str, Any]:
    try:
        config = yaml.safe_load((source / "configuration.yaml").read_text())
    except yaml.YAMLError:
        raise ValueError(
            "Invalid configuration YAML; sensitive details omitted."
        ) from None
    if not isinstance(config, dict):
        raise TypeError("configuration.yaml must contain a mapping.")
    for field in ("advanced", "mqtt", "serial"):
        if not isinstance(config.get(field), dict):
            raise TypeError(f"Configuration {field} must contain a mapping.")
    advanced = config["advanced"]
    for field in NETWORK_FIELDS[:3]:
        value = advanced.get(field)
        if value is None or value == "GENERATE":
            raise ValueError(
                f"Missing saved {field}; refusing to create a new network."
            )
    if config.get("serial", {}).get("adapter") != "ember":
        raise ValueError(
            "This deployment requires an existing ember coordinator config."
        )
    return config


def prepare(source: Path, destination: Path, frontend_password: str) -> None:
    source, destination = source.resolve(), destination.resolve()
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError(
            "Source and destination must be separate, non-nested directories."
        )
    if destination.exists():
        raise ValueError("Destination exists; choose a new private staging directory.")
    if (
        not isinstance(frontend_password, str)
        or len(frontend_password) < 12
        or "\n" in frontend_password
        or "\r" in frontend_password
    ):
        raise ValueError(
            "The frontend password needs at least 12 characters and no line breaks."
        )
    for filename in REQUIRED_FILES:
        if not (source / filename).is_file():
            raise ValueError(
                f"Missing {filename}; migration requires all saved network data."
            )
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Data contains symlinks; resolve them before migration.")
    config = load_configuration(source)
    if (
        not destination.parent.is_dir()
        or stat.S_IMODE(destination.parent.stat().st_mode) & 0o077
    ):
        raise ValueError(
            "Use an existing private staging parent directory (chmod 700)."
        )
    network = {field: config["advanced"].get(field) for field in NETWORK_FIELDS}
    shutil.copytree(source, destination)
    for path in (destination, *destination.rglob("*")):
        path.chmod(0o700 if path.is_dir() else 0o600)
    config["mqtt"]["server"] = "mqtt://127.0.0.1:1883"
    for field in ("user", "password", "ca", "cert", "key"):
        config["mqtt"].pop(field, None)
    config["serial"]["port"] = "/dev/ttyUSB0"
    frontend = config.get("frontend")
    if not isinstance(frontend, dict):
        frontend = {}
    frontend.update(
        enabled=True, host="0.0.0.0", port=8080, auth_token=frontend_password
    )
    config["frontend"] = frontend
    # Modern Zigbee2MQTT starts with joining closed; remove the obsolete config option.
    config.pop("permit_join", None)
    config["advanced"].update(log_level="info", log_output=["console"])
    if network != {field: config["advanced"].get(field) for field in NETWORK_FIELDS}:
        raise ValueError("Network settings unexpectedly changed; refusing migration.")
    (destination / "configuration.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Stopped instance's complete data directory"
    )
    parser.add_argument("destination", type=Path, help="New private staging directory")
    parser.add_argument(
        "--auth-file",
        required=True,
        type=Path,
        help="Private mode-0600 JSON file containing frontend_password; never pass passwords as arguments",
    )
    args = parser.parse_args()
    try:
        info = args.auth_file.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError(
                "Auth file must be owned by the current user and private (mode 0600)."
            )
        password = json.loads(args.auth_file.read_text())["frontend_password"]
        prepare(args.source, args.destination, password)
    except (ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except (OSError, KeyError):
        print(
            "Error: Cannot read complete saved data or frontend_password from the private auth file. Check paths and permissions; no secrets printed.",
            file=sys.stderr,
        )
        return 1
    print(
        "Private migration prepared; network identity, backups, paired devices, and source data preserved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
