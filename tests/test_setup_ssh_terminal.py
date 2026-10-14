"""Run the setup CLI against real ncurses and a local SSH transport substitute."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/setup-ssh-terminal.sh"
TOOLS = {name: shutil.which(name) for name in ("bash", "infocmp", "tic", "tput")}

FAKE_SSH = r"""
import json
import os
from pathlib import Path
import subprocess
import sys

arguments = sys.argv[1:]
with Path(os.environ["TEST_SSH_CALLS"]).open("a") as handle:
    handle.write(json.dumps(arguments) + "\n")
if os.environ.get("TEST_SSH_FAIL"):
    sys.exit(255)
environment = {**os.environ, "HOME": os.environ["TEST_REMOTE_HOME"]}
environment.pop("TERMINFO", None)
environment.pop("TERMINFO_DIRS", None)
if "TEST_REMOTE_PATH" in environment:
    environment["PATH"] = environment["TEST_REMOTE_PATH"]
result = subprocess.run(["/bin/sh", "-c", arguments[-1]], env=environment, check=False)
sys.exit(result.returncode)
"""


@unittest.skipUnless(all(TOOLS.values()), "Local Bash and ncurses tools are required.")
class SetupSshTerminalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.remote = self.root / "remote home with spaces"
        self.local_tmp = self.root / "source-files"
        self.calls_file = self.root / "calls.jsonl"
        for directory in (self.bin, self.remote, self.local_tmp):
            directory.mkdir()
        transport = self.bin / "ssh"
        transport.write_text(f"#!{sys.executable}\n{FAKE_SSH}")
        transport.chmod(0o700)
        self.environment = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(Path.home()),
            "TERM": "xterm-256color",
            "TMPDIR": str(self.local_tmp),
            "TEST_REMOTE_HOME": str(self.remote),
            "TEST_SSH_CALLS": str(self.calls_file),
        }
        # Keep the client's bundled database; fake SSH removes it on the remote side.

    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [str(TOOLS["bash"]), str(SCRIPT), *arguments],
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            list(self.local_tmp.iterdir()), [], "Terminfo source was not cleaned up."
        )
        return result

    def calls(self) -> list[list[str]]:
        if not self.calls_file.exists():
            return []
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]

    def verify_entry(self, terminal: str) -> None:
        directory = self.remote / ".terminfo"
        self.assertTrue(
            list(directory.rglob(terminal)), "Remote entry was not installed."
        )
        query = subprocess.run(
            [str(TOOLS["infocmp"]), "-A", str(directory), "-x", terminal],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(query.returncode, 0, query.stderr)

    def snapshot(self) -> dict[str, bytes]:
        directory = self.remote / ".terminfo"
        return {
            str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }

    def test_compiles_selected_definition_for_remote_user(self) -> None:
        result = self.invoke("orange-pi-zero-3", "xterm-256color")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.verify_entry("xterm-256color")
        self.assertEqual(self.calls()[0][-2], "orange-pi-zero-3")
        self.assertEqual(self.calls()[0][:2], ["-o", "ConnectTimeout=10"])
        self.assertIn("installed and verified", result.stdout)
        self.assertFalse((self.remote / ".bashrc").exists())
        self.assertFalse((self.remote / ".ssh").exists())

    def test_kitty_definition_preserves_extended_capabilities(self) -> None:
        available = subprocess.run(
            [str(TOOLS["infocmp"]), "-x", "xterm-kitty"],
            capture_output=True,
            check=False,
        )
        if available.returncode != 0:
            self.skipTest("The local Kitty definition is not installed.")
        result = self.invoke("orange-pi-zero-3", "xterm-kitty")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.verify_entry("xterm-kitty")
        definitions = []
        for arguments in (
            ["-x", "-1", "xterm-kitty"],
            ["-A", str(self.remote / ".terminfo"), "-x", "-1", "xterm-kitty"],
        ):
            definition = subprocess.run(
                [str(TOOLS["infocmp"]), *arguments],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(definition.returncode, 0, definition.stderr)
            definitions.append(
                {
                    line.strip()
                    for line in definition.stdout.splitlines()
                    if line.strip() and not line.startswith("#")
                }
            )
        self.assertEqual(definitions[0], definitions[1])
        color = subprocess.run(
            [str(TOOLS["tput"]), "colors"],
            env={
                **self.environment,
                "TERM": "xterm-kitty",
                "TERMINFO": str(self.remote / ".terminfo"),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(color.returncode, 0, color.stderr)
        self.assertEqual(color.stdout.strip(), "256")

    def test_default_uses_current_client_term(self) -> None:
        result = self.invoke("user@example")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.verify_entry("xterm-256color")

    def test_rerun_preserves_unrelated_terminal_entries(self) -> None:
        self.assertEqual(self.invoke("orange-pi-zero-3", "dumb").returncode, 0)
        original = self.snapshot()
        self.assertEqual(
            self.invoke("orange-pi-zero-3", "xterm-256color").returncode, 0
        )
        after = self.snapshot()
        for filename, content in original.items():
            self.assertEqual(after[filename], content)
        self.assertEqual(
            self.invoke("orange-pi-zero-3", "xterm-256color").returncode, 0
        )
        self.assertEqual(self.snapshot(), after)

    def test_invalid_terminal_cannot_inject_remote_commands(self) -> None:
        result = self.invoke("orange-pi-zero-3", "xterm-kitty; touch injected")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.remote / ".terminfo").exists())

    def test_target_cannot_be_an_ssh_option(self) -> None:
        result = self.invoke("-oProxyCommand=bad", "xterm-256color")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_unknown_local_term_fails_before_connecting(self) -> None:
        result = self.invoke("orange-pi-zero-3", "plantctl-no-such-terminal-unique")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Local terminfo", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_ssh_failure_propagates_and_cleans_temporary_source(self) -> None:
        self.environment["TEST_SSH_FAIL"] = "1"
        self.assertEqual(
            self.invoke("orange-pi-zero-3", "xterm-256color").returncode, 255
        )
        self.assertFalse((self.remote / ".terminfo").exists())

    def test_missing_remote_compiler_fails_before_writing(self) -> None:
        empty_bin = self.root / "empty-bin"
        empty_bin.mkdir()
        self.environment["TEST_REMOTE_PATH"] = str(empty_bin)
        result = self.invoke("orange-pi-zero-3", "xterm-256color")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing remote tic", result.stderr)
        self.assertFalse((self.remote / ".terminfo").exists())

    def test_missing_local_tools_have_an_actionable_error(self) -> None:
        self.environment["PATH"] = str(self.bin)
        result = self.invoke("orange-pi-zero-3", "xterm-256color")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing local infocmp", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_help_and_missing_arguments_do_not_connect(self) -> None:
        self.assertEqual(self.invoke("--help").returncode, 0)
        self.assertEqual(self.invoke().returncode, 2)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
