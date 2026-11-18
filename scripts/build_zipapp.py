"""Build a kbkit zipapp from the src layout."""

from __future__ import annotations

import argparse
import zipapp
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    zipapp.create_archive(Path(__file__).parents[1] / "src", args.output, interpreter="/usr/bin/env python", main="kbkit.cli:main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
