"""Prepare a manually published WorkBuddy CLI connector and its pinned runtime."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import runpy
import stat
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build_zipapp import build


REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "integrations" / "workbuddy"
GITHUB = "https://github.com/jmr-circumlunar/kbkit"
PLATFORMS = ("darwin", "linux", "win32")


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=REPO, text=True, encoding="utf-8").strip()


def https_address(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("Runtime sources must be public HTTPS URLs without embedded credentials or fragments.")
    return value


def lifecycle(source: bytes, release: dict, action: str) -> dict:
    call = f"\nraise SystemExit(main({release!r}, {action!r}))\n".encode("utf-8")
    payload = base64.urlsafe_b64encode(zlib.compress(source + call, 9)).decode("ascii")
    command = f"""python -I -c "import base64,zlib;exec(zlib.decompress(base64.urlsafe_b64decode('{payload}')))\""""
    if len(command) >= 8_000:
        raise ValueError("Embedded installer exceeds the Windows command length budget.")
    return dict.fromkeys(PLATFORMS, command)


def package(output: Path, mirror_url: str | None, *, allow_dirty: bool = False) -> tuple[Path, dict]:
    if not allow_dirty and git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Build from a clean Git checkout so the runtime corresponds to the reported commit.")
    commit = git("rev-parse", "HEAD")
    if allow_dirty:
        return build_package(REPO, output, mirror_url, commit, preview=True)
    with tempfile.TemporaryDirectory(prefix="kbkit-workbuddy-build-") as temporary:
        path = Path(temporary)
        git_archive = path / "source.zip"
        subprocess.run(["git", "archive", "--format=zip", "--output", str(git_archive), commit,
                        "LICENSE", "src/kbkit", "skills", "knowledge", "integrations/workbuddy"],
                       cwd=REPO, check=True)
        with ZipFile(git_archive) as archive:
            archive.extractall(path / "source")
        return build_package(path / "source", output, mirror_url, commit, preview=False)


def build_package(root: Path, output: Path, mirror_url: str | None, commit: str, *, preview: bool) -> tuple[Path, dict]:
    template = root / "integrations" / "workbuddy"
    metadata = json.loads((template / "connector-meta.json").read_bytes())
    connector_version = metadata["version"]
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", connector_version):
        raise ValueError("The connector version must be a numeric semantic version.")
    tag = f"workbuddy-v{connector_version}"
    github_url = f"{GITHUB}/releases/download/{tag}/kbkit.pyz"
    urls = list(dict.fromkeys(https_address(url) for url in (mirror_url, github_url) if url))

    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "kbkit.pyz"
    build(root / "src", runtime)
    version_output = subprocess.check_output([sys.executable, "-I", str(runtime), "--version"], text=True).strip()
    prefix, _, core_version = version_output.partition(" ")
    if prefix != "kbc" or not core_version:
        raise ValueError("The bundled CLI did not report its version.")
    release = {
        "connector_version": connector_version, "kbkit_version": core_version, "commit": commit,
        "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(), "bytes": runtime.stat().st_size, "urls": urls,
    }
    installer = (template / "install.py").read_bytes()
    cli = {
        "runtime": {"type": "python", "version": "3.13"},
        "init": lifecycle(installer, release, "init"),
        "status": lifecycle(installer, release, "status"),
        "unAuth": lifecycle(installer, release, "disconnect"),
        "statusMatch": "KBKIT_READY",
        "versionCheck": {"command": lifecycle(installer, release, "version"), "minVersion": connector_version},
    }
    bundle = output / f"kbkit-workbuddy-{connector_version}.zip"
    with ZipFile(bundle, "w") as archive:
        files = {
            "connector-meta.json": (template / "connector-meta.json").read_bytes(),
            "cli.json": (json.dumps(cli, indent=2) + "\n").encode("utf-8"),
            "icon.svg": (template / "icon.svg").read_text(encoding="utf-8").encode("utf-8"),
            "LICENSE": (root / "LICENSE").read_bytes(),
        }
        files.update({item.relative_to(template).as_posix(): item.read_bytes()
                      for item in (template / "skills").rglob("SKILL.md")})
        for name, content in sorted(files.items()):
            info = ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content, compress_type=ZIP_DEFLATED, compresslevel=9)
    manifest = {
        **release, "tag": tag, "connector_zip": bundle.name, "connector_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "working_tree_preview": preview,
    }
    (output / "release.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return bundle, manifest


def verify_sources(manifest: dict) -> None:
    installer = runpy.run_path(str(PACKAGE / "install.py"))
    failures = []
    for url in manifest["urls"]:
        try:
            installer["download"]({**manifest, "urls": [https_address(url)]})
        except OSError as error:
            failures.append(str(error))
        else:
            print(f"Verified {url}")
    if failures:
        raise OSError(" | ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mirror-url", help="Public HTTPS URL of the same released kbkit.pyz on the domestic mirror.")
    parser.add_argument("--preview", action="store_true", help="Build a local preview that may include uncommitted changes.")
    parser.add_argument("--verify-sources", action="store_true", help="Verify all published URLs against the saved release manifest.")
    arguments = parser.parse_args()
    try:
        version = json.loads((PACKAGE / "connector-meta.json").read_bytes())["version"]
        output = arguments.output or REPO / "dist" / "workbuddy" / version
        if arguments.verify_sources:
            verify_sources(json.loads((output / "release.json").read_bytes()))
        else:
            _, manifest = package(output, arguments.mirror_url, allow_dirty=arguments.preview)
            print(json.dumps(manifest, indent=2))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"WorkBuddy package: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
