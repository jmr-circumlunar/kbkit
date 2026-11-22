"""Build a kbkit zipapp from the src layout."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
from zipfile import ZipFile, ZipInfo


def build(source: Path, output: Path) -> None:
    """Build a source-only ZIP application independent of checkout metadata."""
    with output.open("wb") as stream:
        stream.write(b"#!/usr/bin/env python\n")
        with ZipFile(stream, "w") as archive:
            def write(name: str, content: bytes) -> None:
                member = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                member.create_system = 3
                member.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(member, content)

            write("__main__.py", b"from kbkit.cli import main\nraise SystemExit(main())\n")
            write("LICENSE", (source.parent / "LICENSE").read_bytes())
            for path in sorted((source / "kbkit").rglob("*.py"), key=lambda item: item.relative_to(source).as_posix()):
                write(path.relative_to(source).as_posix(), path.read_bytes())
            for source_dir, bundle in (("skills", "skills"), ("knowledge", "starter")):
                directory = source.parent / source_dir
                for path in sorted(directory.rglob("*.md")):
                    write(f"share/kbkit/{bundle}/{path.relative_to(directory).as_posix()}", path.read_bytes())
    output.chmod(output.stat().st_mode | stat.S_IXUSR)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build(Path(__file__).parents[1] / "src", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
