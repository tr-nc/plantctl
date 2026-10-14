"""Migration contracts: preserve the network, reject unsafe inputs, keep secrets private."""

import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare-zigbee-host.py"
SPEC = importlib.util.spec_from_file_location("prepare_zigbee_host", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.target = self.root / "target"
        self.config = {
            "version": 5,
            "advanced": {
                "network_key": list(range(16)),
                "pan_id": 1234,
                "ext_pan_id": list(range(8)),
                "channel": 20,
            },
            "mqtt": {
                "server": "mqtt://old-host:1883",
                "base_topic": "zigbee2mqtt",
                "user": "old-user",
                "password": "old-password",
            },
            "serial": {
                "port": "/dev/old-device",
                "adapter": "ember",
                "baudrate": 115200,
                "rtscts": False,
            },
            "frontend": {"enabled": True},
            "devices": {"0x1234": {"friendly_name": "plant-light"}},
        }
        self.save_config()
        (self.source / "database.db").write_bytes(b"saved-device-database\n")
        (self.source / "coordinator_backup.json").write_text('{"saved":true}\n')
        (self.source / "secret.yaml").write_text("network_key: saved-test-secret\n")
        self.password = "test-only-frontend-password"
        self.auth = self.root / "auth.json"
        self.auth.write_text(json.dumps({"frontend_password": self.password}))
        self.auth.chmod(0o600)

    def save_config(self):
        (self.source / "configuration.yaml").write_text(yaml.safe_dump(self.config))

    def invoke(self):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.source),
                str(self.target),
                "--auth-file",
                str(self.auth),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_preserves_network_devices_backups_and_original(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = yaml.safe_load((self.target / "configuration.yaml").read_text())
        for field in MODULE.NETWORK_FIELDS:
            self.assertEqual(saved["advanced"][field], self.config["advanced"][field])
        self.assertEqual(saved["devices"], self.config["devices"])
        self.assertEqual(saved["serial"]["adapter"], "ember")
        self.assertEqual(saved["serial"]["baudrate"], 115200)
        self.assertFalse(saved["serial"]["rtscts"])
        for name in ("database.db", "coordinator_backup.json", "secret.yaml"):
            self.assertEqual((self.target / name).read_bytes(), before[name])
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in self.source.iterdir()}
        )
        self.assertNotIn(self.password, result.stdout + result.stderr)
        self.assertNotIn("old-password", result.stdout + result.stderr)

    def test_host_endpoints_auth_and_private_files(self):
        MODULE.prepare(self.source, self.target, self.password)
        saved = yaml.safe_load((self.target / "configuration.yaml").read_text())
        self.assertEqual(saved["mqtt"]["server"], "mqtt://127.0.0.1:1883")
        self.assertNotIn("password", saved["mqtt"])
        self.assertNotIn("user", saved["mqtt"])
        self.assertEqual(saved["frontend"]["host"], "0.0.0.0")
        self.assertEqual(saved["frontend"]["port"], 8080)
        self.assertEqual(saved["frontend"]["auth_token"], self.password)
        self.assertEqual(saved["serial"]["port"], "/dev/ttyUSB0")
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        for path in self.target.rglob("*"):
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600
            )

    def test_refuses_generated_or_missing_network_fields_before_copy(self):
        for field in MODULE.NETWORK_FIELDS[:3]:
            for value in (None, "GENERATE"):
                with self.subTest(field=field, value=value):
                    cfg = dict(self.config["advanced"])
                    self.config["advanced"][field] = value
                    self.save_config()
                    result = self.invoke()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(field, result.stderr)
                    self.assertFalse(self.target.exists())
                    self.config["advanced"] = cfg
        self.save_config()

    def test_refuses_existing_target_and_leaves_it_intact(self):
        self.target.mkdir()
        sentinel = self.target / "keep"
        sentinel.write_text("do-not-overwrite")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "do-not-overwrite")

    def test_private_secret_references_are_preserved(self):
        self.config["advanced"]["network_key"] = "!secret.yaml network_key"
        self.save_config()
        MODULE.prepare(self.source, self.target, self.password)
        saved = yaml.safe_load((self.target / "configuration.yaml").read_text())
        self.assertEqual(saved["advanced"]["network_key"], "!secret.yaml network_key")
        self.assertEqual(
            (self.target / "secret.yaml").read_bytes(),
            (self.source / "secret.yaml").read_bytes(),
        )

    def test_invalid_yaml_never_echoes_its_sensitive_line(self):
        secret = "test-only-SECRET-MUST-NOT-APPEAR"
        (self.source / "configuration.yaml").write_text(f"password: [{secret}\n")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_refuses_missing_database_or_backup(self):
        for name in ("database.db", "coordinator_backup.json"):
            path = self.source / name
            contents = path.read_bytes()
            path.unlink()
            result = self.invoke()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(name, result.stderr)
            self.assertFalse(self.target.exists())
            path.write_bytes(contents)

    def test_refuses_shared_auth_file_or_parent(self):
        self.auth.chmod(0o644)
        self.assertNotEqual(self.invoke().returncode, 0)
        self.auth.chmod(0o600)
        self.root.chmod(0o755)
        try:
            self.assertNotEqual(self.invoke().returncode, 0)
        finally:
            self.root.chmod(0o700)
        self.assertFalse(self.target.exists())

    def test_rejects_symlinks_and_nested_destination(self):
        (self.source / "outside").symlink_to(self.auth)
        self.assertNotEqual(self.invoke().returncode, 0)
        (self.source / "outside").unlink()
        with self.assertRaises(ValueError):
            MODULE.prepare(self.source, self.source / "inside", self.password)
        self.assertFalse(self.target.exists())

    def test_normalizes_legacy_frontend_and_removes_obsolete_join_config(self):
        self.config["frontend"] = True
        self.config["permit_join"] = True
        self.save_config()
        MODULE.prepare(self.source, self.target, self.password)
        saved = yaml.safe_load((self.target / "configuration.yaml").read_text())
        self.assertIs(saved["frontend"]["enabled"], True)
        self.assertNotIn("permit_join", saved)


if __name__ == "__main__":
    unittest.main()
