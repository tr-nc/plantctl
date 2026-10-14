"""Exercise the public CLI with fake desktop tools; never touch a real network."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/select-wifi.py"
PASSWORD = 'test-only-"password"\\123'

FAKE_TOOL = r"""
import json
import os
from pathlib import Path
import sys

arguments = sys.argv[1:]
events = Path(os.environ["TEST_EVENTS"])
previous = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
with events.open("a") as handle:
    handle.write(json.dumps({"tool": Path(sys.argv[0]).name, "arguments": arguments}) + "\n")
if Path(sys.argv[0]).name == "nmcli":
    if "status" in arguments:
        print(os.environ["TEST_DEVICES"])
    elif "list" in arguments:
        if os.environ.get("TEST_SCAN_FAIL"):
            sys.exit(1)
        print(os.environ["TEST_SCAN"])
    else:
        sys.exit(99)
else:
    if "--list" in arguments:
        choices = json.loads(os.environ.get("TEST_CHOICES", '["0"]'))
        count = sum(event["tool"] == "zenity" and "--list" in event["arguments"] for event in previous)
        if count >= len(choices) or choices[count] == "cancel":
            sys.exit(1)
        print(choices[count])
    elif "--password" in arguments:
        passwords = json.loads(os.environ["TEST_PASSWORDS"])
        count = sum(event["tool"] == "zenity" and "--password" in event["arguments"] for event in previous)
        if count >= len(passwords) or passwords[count] is None:
            sys.exit(1)
        print(passwords[count])
    elif "--question" in arguments:
        sys.exit(int(os.environ.get("TEST_QUESTION_EXIT", "0")))
"""


def escaped(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def scan_row(
    ssid: str, frequency: int = 2412, signal: int = 75, security: str = "WPA2"
) -> str:
    return f"{escaped(ssid)}:{frequency} MHz:{signal}:{security}"


@unittest.skipIf(os.geteuid() == 0, "The desktop CLI deliberately refuses root.")
class SelectWifiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.runtime = self.root / "runtime"
        self.bin.mkdir()
        self.runtime.mkdir(mode=0o700)
        self.events = self.root / "events.jsonl"
        for name in ("nmcli", "zenity"):
            tool = self.bin / name
            tool.write_text(f"#!{sys.executable}\n{FAKE_TOOL}")
            tool.chmod(0o700)
        self.environment = {
            **os.environ,
            "PATH": str(self.bin),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "TEST_EVENTS": str(self.events),
            "TEST_DEVICES": "wifi-test:wifi\neth-test:ethernet",
            "TEST_SCAN": scan_row("Example"),
            "TEST_PASSWORDS": json.dumps([PASSWORD]),
        }

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotIn(PASSWORD, result.stdout + result.stderr)
        for event in self.calls():
            self.assertNotIn(PASSWORD, json.dumps(event))
            if event["tool"] == "nmcli":
                self.assertTrue(
                    "status" in event["arguments"] or "list" in event["arguments"]
                )
        return result

    def calls(self) -> list[dict]:
        if not self.events.exists():
            return []
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def credentials(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(result.returncode, 0, result.stderr)
        path = Path(result.stdout.strip())
        self.assertEqual(path.parent, self.runtime)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(path.stat().st_uid, os.getuid())
        return json.loads(path.read_text())

    def test_selects_network_and_saves_private_credentials_without_changing_host_network(
        self,
    ) -> None:
        ssid = '--untrusted: "中文" \\ WiFi'
        self.environment["TEST_SCAN"] = scan_row(ssid)
        details = self.credentials(self.invoke())
        self.assertEqual(
            details,
            {
                "version": 1,
                "ssid": ssid,
                "password": PASSWORD,
                "mode": "psk",
                "country": "CN",
                "hidden": False,
            },
        )
        selector = next(
            event for event in self.calls() if "--list" in event["arguments"]
        )
        self.assertGreater(
            selector["arguments"].index(ssid), selector["arguments"].index("--")
        )
        scanner = next(
            event
            for event in self.calls()
            if event["tool"] == "nmcli" and "list" in event["arguments"]
        )
        self.assertEqual(
            scanner["arguments"][scanner["arguments"].index("ifname") + 1], "wifi-test"
        )

    def test_filter_excludes_unsupported_and_unrequested_bands(self) -> None:
        self.environment["TEST_SCAN"] = "\n".join(
            [
                scan_row("Two", 2412, 90),
                scan_row("Five", 5180, 70),
                scan_row("Six", 5975, 100),
            ]
        )
        self.assertEqual(self.credentials(self.invoke("--band", "5"))["ssid"], "Five")
        selector = next(
            event for event in self.calls() if "--list" in event["arguments"]
        )
        self.assertNotIn("Two", selector["arguments"])
        self.assertNotIn("Six", selector["arguments"])

    def test_duplicate_access_points_display_only_strongest_per_ssid_band_security(
        self,
    ) -> None:
        self.environment["TEST_SCAN"] = "\n".join(
            [
                scan_row("Example", signal=20),
                scan_row("Example", signal=85),
                scan_row("Other", signal=70),
            ]
        )
        self.assertEqual(self.credentials(self.invoke())["ssid"], "Example")
        selector = next(
            event for event in self.calls() if "--list" in event["arguments"]
        )
        self.assertEqual(selector["arguments"].count("Example"), 1)
        self.assertIn("85%", selector["arguments"])
        self.assertNotIn("20%", selector["arguments"])

    def test_country_and_explicit_interface_are_not_tied_to_current_machine(
        self,
    ) -> None:
        self.environment["TEST_DEVICES"] = "wifi-a:wifi\nwifi-b:wifi"
        details = self.credentials(
            self.invoke("--interface", "wifi-b", "--country", "us")
        )
        self.assertEqual(details["country"], "US")
        scanner = next(
            event
            for event in self.calls()
            if event["tool"] == "nmcli" and "list" in event["arguments"]
        )
        self.assertIn("wifi-b", scanner["arguments"])

    def test_multiple_adapters_require_explicit_selection(self) -> None:
        self.environment["TEST_DEVICES"] = "wifi-a:wifi\nwifi-b:wifi"
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertIn("--interface", result.stderr)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_cancel_network_selection_creates_no_credentials(self) -> None:
        self.environment["TEST_CHOICES"] = '["cancel"]'
        self.assertEqual(self.invoke().returncode, 130)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_cancel_password_creates_no_credentials(self) -> None:
        self.environment["TEST_PASSWORDS"] = "[null]"
        self.assertEqual(self.invoke().returncode, 130)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_invalid_password_can_be_corrected_without_logging_it(self) -> None:
        self.environment["TEST_PASSWORDS"] = json.dumps(["short", PASSWORD])
        self.assertEqual(self.credentials(self.invoke())["password"], PASSWORD)
        self.assertEqual(
            sum("--password" in event["arguments"] for event in self.calls()), 2
        )

    def test_wpa3_only_network_records_sae(self) -> None:
        self.environment["TEST_SCAN"] = scan_row("WPA3", security="WPA3")
        self.assertEqual(self.credentials(self.invoke())["mode"], "sae")

    def test_mixed_wpa2_wpa3_network_records_psk(self) -> None:
        self.environment["TEST_SCAN"] = scan_row("Mixed", security="WPA2 WPA3")
        self.assertEqual(self.credentials(self.invoke())["mode"], "psk")

    def test_enterprise_network_is_rejected_before_requesting_password(self) -> None:
        self.environment["TEST_SCAN"] = "\n".join(
            [
                scan_row("Enterprise", signal=90, security="WPA2 802.1X"),
                scan_row("Home", signal=70),
            ]
        )
        self.environment["TEST_CHOICES"] = '["0", "1"]'
        self.assertEqual(self.credentials(self.invoke())["ssid"], "Home")
        passwords = [
            event for event in self.calls() if "--password" in event["arguments"]
        ]
        self.assertEqual(len(passwords), 1)
        self.assertNotIn("Enterprise", json.dumps(passwords[0]))

    def test_open_network_requires_confirmation_and_has_no_password(self) -> None:
        self.environment["TEST_SCAN"] = scan_row("Open", security="--")
        details = self.credentials(self.invoke())
        self.assertEqual(details["mode"], "none")
        self.assertEqual(details["password"], "")
        self.assertTrue(
            any("--question" in event["arguments"] for event in self.calls())
        )
        self.assertFalse(
            any("--password" in event["arguments"] for event in self.calls())
        )

    def test_scan_failure_creates_no_credentials(self) -> None:
        self.environment["TEST_SCAN_FAIL"] = "1"
        self.assertEqual(self.invoke().returncode, 1)
        self.assertEqual(list(self.runtime.iterdir()), [])
        self.assertFalse(any(event["tool"] == "zenity" for event in self.calls()))

    def test_empty_scan_creates_no_credentials(self) -> None:
        self.environment["TEST_SCAN"] = ""
        self.assertEqual(self.invoke().returncode, 1)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_help_does_not_need_graphical_tools(self) -> None:
        (self.bin / "zenity").unlink()
        (self.bin / "nmcli").unlink()
        result = self.invoke("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--band", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_invalid_country_is_rejected_before_scanning(self) -> None:
        self.assertEqual(self.invoke("--country", "invalid").returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_missing_desktop_tools_provides_install_hint(self) -> None:
        (self.bin / "zenity").unlink()
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertIn("dnf install", result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
