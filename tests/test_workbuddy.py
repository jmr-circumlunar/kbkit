import hashlib
import io
import json
import os
import runpy
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile


REPO = Path(__file__).resolve().parents[1]
CONNECTOR = REPO / "integrations" / "workbuddy"
MIRROR = "https://gitee.example.invalid/kbkit.pyz"
UPSTREAM = "https://github.example.invalid/kbkit.pyz"


class Response(io.BytesIO):
    def __init__(self, url: str, data: bytes) -> None:
        super().__init__(data)
        self.url = url

    def geturl(self) -> str:
        return self.url


class WorkBuddyTests(unittest.TestCase):
    def test_runtime_falls_back_and_rejects_unverified_bytes(self):
        installer = runpy.run_path(str(CONNECTOR / "install.py"))
        download = installer["download"]
        expected = b"pinned kbkit archive"
        release = {"urls": [MIRROR, UPSTREAM], "bytes": len(expected), "sha256": hashlib.sha256(expected).hexdigest()}

        def response(url, timeout):
            data = b"x" * len(expected) if url == MIRROR else expected
            return Response(url, data)

        with patch.dict(download.__globals__, {"urlopen": response}):
            self.assertEqual(download(release), expected)
            with self.assertRaisesRegex(OSError, "checksum or size mismatch"):
                download({**release, "urls": [MIRROR]})

        def missing_or_downgraded(url, timeout):
            if url == MIRROR:
                raise TimeoutError("mirror timed out")
            return Response(url.replace("https://", "http://"), expected)

        with patch.dict(download.__globals__, {"urlopen": missing_or_downgraded}):
            with self.assertRaisesRegex(OSError, "mirror timed out.*non-HTTPS"):
                download(release)

    def test_connector_package_lifecycle_and_local_cli(self):
        with tempfile.TemporaryDirectory(prefix="kbkit-wb-test-") as temporary:
            root = Path(temporary)
            output = root / "build"
            subprocess.run([sys.executable, str(REPO / "scripts" / "build_workbuddy.py"), "--preview",
                            "--output", str(output), "--mirror-url", MIRROR], check=True, capture_output=True, timeout=30)
            build = json.loads((output / "release.json").read_bytes())
            self.assertEqual(build["urls"][0], MIRROR)
            bundle = output / build["connector_zip"]
            with ZipFile(bundle) as archive:
                self.assertIn("skills/kbkit-workbuddy/SKILL.md", archive.namelist())
                metadata = json.loads(archive.read("connector-meta.json"))
                config = json.loads(archive.read("cli.json"))
            self.assertEqual(metadata["version"], config["versionCheck"]["minVersion"])
            self.assertEqual(metadata["type"], "cli")
            self.assertNotIn("auth", config)
            runtime = (output / "kbkit.pyz").read_bytes()
            self.assertEqual(hashlib.sha256(runtime).hexdigest(), build["sha256"])
            self.assertEqual(len(runtime), build["bytes"])

            installed = root / "安装路径 with space"
            cache = installed / "runtimes" / build["sha256"] / "kbkit.pyz"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(runtime)
            env = {
                **os.environ,
                "KBKIT_WORKBUDDY_DIR": str(installed),
                "KBKIT_VAULT": str(root / "uninitialized ambient vault"),
                "KBKIT_HOME": str(root / "state"),
                "KBKIT_INDEX_DIR": str(root / "index"),
                "KBKIT_REGISTRY_DIR": str(root / "registry"),
            }
            platform = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"

            def invoke(commands):
                self.assertEqual(set(commands), {"darwin", "linux", "win32"})
                args = shlex.split(commands[platform])
                self.assertEqual(args[0], "python")
                return subprocess.run([sys.executable, *args[1:]], env=env, capture_output=True, timeout=30)

            self.assertNotEqual(invoke(config["status"]).returncode, 0)
            self.assertFalse((installed / "connection.json").exists())
            self.assertEqual(invoke(config["versionCheck"]["command"]).stdout.strip(), b"0.0.0")
            activation = invoke(config["init"])
            self.assertEqual(activation.returncode, 0, activation.stderr)
            self.assertIn(config["statusMatch"].encode(), invoke(config["status"]).stdout)
            self.assertEqual(invoke(config["versionCheck"]["command"]).stdout.strip(), metadata["version"].encode())
            receipt = json.loads((installed / "connection.json").read_bytes())
            self.assertEqual(receipt["commit"], build["commit"])
            self.assertEqual(receipt["kbkit_version"], build["kbkit_version"])
            vault = root / "测试 vault"

            def cli(*options):
                command = ([receipt["python"], "-I", "-X", "utf8", receipt["archive"]] if sys.platform == "win32"
                           else [str(installed / "kbc")])
                return subprocess.check_output([*command, *options], env=env, timeout=20)

            cli("setup", str(vault), "--host", "standalone")
            note = vault / "connector.md"
            note.write_bytes(b"# WorkBuddy\n\nRelease verification")
            cli("sync", str(vault))
            self.assertEqual(json.loads(cli("search", str(vault), "verification", "--json"))["hits"][0]["path"], note.name)
            cli("task", "run", str(vault), "--auto-apply", "safe")
            self.assertTrue(note.read_bytes().endswith(b"\n"))

            with patch.object(sys, "path", [str(REPO / "scripts"), *sys.path]):
                builder = runpy.run_path(str(REPO / "scripts" / "build_workbuddy.py"))
            major, minor, revision = map(int, metadata["version"].split("."))
            updated = {**build, "connector_version": f"{major}.{minor}.{revision + 1}"}
            installer = (CONNECTOR / "install.py").read_bytes()
            version_command = builder["lifecycle"](installer, updated, "version")
            self.assertEqual(invoke(version_command).stdout.strip(), metadata["version"].encode())
            upgrade = invoke(builder["lifecycle"](installer, updated, "init"))
            self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
            self.assertEqual(invoke(version_command).stdout.strip(), updated["connector_version"].encode())
            self.assertTrue(note.read_bytes().endswith(b"\n"))
            self.assertEqual(invoke(config["unAuth"]).returncode, 0)
            self.assertEqual(invoke(config["unAuth"]).returncode, 0)
            self.assertNotEqual(invoke(config["status"]).returncode, 0)
            self.assertTrue(cache.is_file())
            self.assertTrue(note.is_file())
