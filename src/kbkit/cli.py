"""Command-line and stdio entry points."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from . import __version__
from .application import ApplicationService
from .code_sync import bind_code
from .core import init_vault
from .git_adapter import GitUnavailable
from .knowledge import KnowledgeVault
from .prototype_lock import file_lock
from .prototype_mcp import handle
from .registry import VaultRegistry
from .state import StateStore
from .storage import metadata_dir
from .transaction import recover_transaction
from .vault_profile import index_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kbc", description="Manage local Markdown knowledge bases.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="Check Python, SQLite FTS5, Git and optional vault configuration.").add_argument("--vault", type=Path)
    commands.add_parser("mcp", help="Run the Agent protocol adapter.").add_argument("transport", choices=["stdio"])
    for name in ("init", "add"):
        command = commands.add_parser(name, help=f"{name.capitalize()} a Markdown vault.")
        command.add_argument("path", type=Path)
        command.add_argument("--identity", choices=["moved", "copy"])
    commands.add_parser("use", help="Select a registered vault.").add_argument("vault_uuid")
    commands.add_parser("current", help="Show the active vault.")

    for name in ("index", "status", "search", "read", "outline", "graph", "lint", "task", "maintain", "proposal", "recover", "restore"):
        command = commands.add_parser(name, help=f"Run {name} for a vault.")
        if name in {"task", "proposal"}:
            command.add_argument("action", choices=["run"] if name == "task" else ["list", "approve", "reject", "apply"])
        command.add_argument("path", type=Path)
        if name in {"search", "status", "outline", "graph", "lint", "task", "maintain", "proposal"}:
            command.add_argument("--limit", type=int, default=8 if name in {"search", "outline"} else 25)
            command.add_argument("--offset", type=int, default=0)
            command.add_argument("--max-bytes", type=int, default=640 if name == "outline" else 36_000)
        if name == "search":
            command.add_argument("query")
            command.add_argument("--include-inactive", action="store_true")
            command.add_argument("--json", action="store_true")
            command.add_argument("--max-chars", type=int, default=1200)
            for option in ("path", "kind", "state", "tags", "symbols", "exclude"):
                command.add_argument("--" + option, dest=f"filter_{option}", action="append")
        if name in {"read", "outline"}:
            command.add_argument("relative_path", nargs="?" if name == "read" else None)
        if name == "read":
            selection = command.add_mutually_exclusive_group()
            selection.add_argument("--heading", action="append")
            selection.add_argument("--block-id")
            selection.add_argument("--lines", type=int, nargs=2)
            command.add_argument("--max-bytes", type=int, default=8000)
        if name == "graph":
            command.add_argument("--collection", choices=["edges", "broken", "nodes", "backlinks", "orphaned"], default="edges")
            command.add_argument("--note")
        if name in {"task", "maintain"}:
            command.add_argument("--collection", choices=["findings", "code_sync"], default="findings")
        if name == "proposal":
            command.add_argument("proposal_id", nargs="?")
            command.add_argument("--status")
        if name == "restore":
            command.add_argument("entry_id")

    knowledge = commands.add_parser("knowledge", help="Review revisions and bind committed code sources.")
    actions = knowledge.add_subparsers(dest="knowledge_action", required=True)
    review = actions.add_parser("review")
    review.add_argument("vault", type=Path)
    review.add_argument("page")
    review.add_argument("--depends-on", action="append")
    history = actions.add_parser("history")
    history.add_argument("vault", type=Path)
    history.add_argument("page")
    history.add_argument("--revision", type=int)
    actions.add_parser("status").add_argument("vault", type=Path)
    code = actions.add_parser("bind-code")
    code.add_argument("vault", type=Path)
    code.add_argument("source")
    code.add_argument("repository", type=Path)
    code.add_argument("--ref", required=True)
    code.add_argument("--scope", action="append", required=True)
    return parser


def _json(value) -> None:
    print(json.dumps(value, ensure_ascii=False))


def _doctor(root: Path | None) -> int:
    print(f"Python: {sys.version.split()[0]} (minimum 3.11)")
    print(f"SQLite: {sqlite3.sqlite_version}")
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(content)")
    except sqlite3.Error as exc:
        print(f"FTS5: unavailable ({exc})")
        return 1
    print("FTS5: available")
    print(f"Git: {'available' if shutil.which('git') else 'unavailable (needed for Git features)'}")
    if root is None and os.environ.get("KBKIT_VAULT"):
        root = Path(os.environ["KBKIT_VAULT"])
    if root is None:
        print("Vault: use --vault PATH to check initialization and index directory access")
        return 0
    root = root.resolve()
    initialized = (metadata_dir(root) / "profile.toml").is_file()
    print(f"Vault: {'initialized' if initialized else 'not initialized'} ({root})")
    if not initialized:
        return 1
    try:
        directory = index_path(root, create=True).parent
        with tempfile.TemporaryFile(dir=directory):
            pass
    except OSError as exc:
        print(f"Index directory: not writable ({exc})")
        return 1
    print(f"Index directory: writable ({directory})")
    return 0


def _stdio() -> int:
    vault = os.environ.get("KBKIT_VAULT")
    service = ApplicationService(Path(vault)) if vault else None
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}}
        else:
            response = handle(message, service)
        if response is not None:
            sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
    return 0


def _knowledge(args):
    with file_lock(metadata_dir(args.vault) / "maintenance.lock"):
        knowledge = KnowledgeVault(args.vault)
        if args.knowledge_action == "review":
            return knowledge.review(args.page, args.depends_on)
        if args.knowledge_action == "history":
            return knowledge.history(args.page, args.revision)
        if args.knowledge_action == "status":
            return knowledge.statuses()
        return bind_code(knowledge, args.source, args.repository, args.ref, args.scope)


def _proposal(service, args, window):
    if args.action == "list":
        return service.proposals(args.status, **window)
    if not args.proposal_id:
        raise ValueError("proposal_id is required")
    if args.action == "apply":
        return service.apply_proposal(args.proposal_id)
    with closing(StateStore(service.vault)) as state, file_lock(metadata_dir(service.vault) / "maintenance.lock"):
        row = state.get_proposal(args.proposal_id)
        if row is None or row[3] not in {"pending", "approved"}:
            raise ValueError("proposal must exist and be pending or approved")
        status = "approved" if args.action == "approve" else "rejected"
        state.set_proposal_status(args.proposal_id, status)
        return {"proposal_id": args.proposal_id, "status": status}


def _vault_command(args) -> int:
    root = args.path.resolve()
    service = ApplicationService(root)
    name = args.command
    if name in {"init", "add"}:
        profile = init_vault(root) if name == "init" else None
        with closing(VaultRegistry()) as registry:
            identity = registry.add(root, identity=args.identity)
        print(f"profile: {profile}\nvault_uuid: {identity}" if profile else identity)
        return 0
    window = {key: getattr(args, key) for key in ("limit", "offset", "max_bytes")} if hasattr(args, "limit") else {}
    if name == "search":
        filters = {key: getattr(args, "filter_" + key) for key in ("path", "kind", "state", "tags", "symbols", "exclude")}
        result = service.search(args.query, args.include_inactive, max_chars=args.max_chars, **filters, **window)
        if args.json:
            _json(result)
        else:
            for hit in result["hits"]:
                print(f"{hit['path']}\t{hit['block_id']}\t{hit['content']}")
            if result["next_offset"] is not None:
                print(f"More hits: use --offset {result['next_offset']}", file=sys.stderr)
        return 0
    if name == "read":
        result = service.read(args.relative_path, heading=args.heading, block_id=args.block_id,
                              lines=args.lines, max_bytes=args.max_bytes)
        if result["truncated"]:
            _json(result)
        else:
            sys.stdout.write(result["content"])
        return 0
    if name == "index":
        print(f"blocks: {service.index()['blocks']}")
        return 0
    if name == "outline":
        result = service.outline(args.relative_path, **window)
    elif name == "graph":
        result = service.graph(args.collection, path=args.note, **window)
    elif name == "proposal":
        result = _proposal(service, args, window)
    elif name in {"task", "maintain"}:
        result = service.maintain(collection=args.collection, **window)
        _json(result)
        return int(result["status"] != "succeeded")
    elif name == "recover":
        journals = sorted((metadata_dir(root) / "transactions").glob("*.json"))
        result = {journal.name: recover_transaction(root, journal) for journal in journals}
    elif name == "restore":
        result = service.restore(args.entry_id)
    else:
        result = getattr(service, name)(**window)
    _json(result)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "mcp":
        return _stdio()
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.command is None:
            parser.print_help()
        elif args.command == "doctor":
            return _doctor(args.vault)
        elif args.command == "knowledge":
            if not (metadata_dir(args.vault) / "profile.toml").is_file():
                raise ValueError("vault is not initialized; run kbc init first")
            _json(_knowledge(args))
        elif args.command in {"use", "current"}:
            with closing(VaultRegistry()) as registry:
                value = registry.use(args.vault_uuid) if args.command == "use" else registry.current()
            if value:
                print(value)
        else:
            return _vault_command(args)
    except (ValueError, OSError, sqlite3.Error, GitUnavailable) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
