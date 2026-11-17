"""Minimal command-line entry point for the bootstrap package."""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kbc", description="Manage local Markdown knowledge bases.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="Check the local Python and SQLite runtime.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        import sqlite3
        import sys

        print(f"Python: {sys.version.split()[0]}")
        print(f"SQLite: {sqlite3.sqlite_version}")
        try:
            connection = sqlite3.connect(":memory:")
            connection.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(content)")
            connection.close()
        except sqlite3.Error as exc:
            print(f"FTS5: unavailable ({exc})")
            return 1
        print("FTS5: available")
        return 0
    return 0
