"""Command-line and stdio entry points."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from uuid import UUID
from contextlib import closing
from pathlib import Path
from zipfile import BadZipFile

from . import __version__
from .application import ApplicationService
from .backup import create_backup, restore_backup, verify_backup
from .code_sync import bind_code
from .core import init_vault
from .git_adapter import GitUnavailable
from .knowledge import KnowledgeVault
from .onboarding import session_context, setup
from .profile import load_profile
from .prototype_index import fts5_error
from .prototype_lock import file_lock
from .prototype_mcp import OUTPUT_MODES, handle
from .registry import VaultRegistry
from .state import StateStore
from .storage import metadata_dir
from .transaction import find_journal, recover_transaction, transaction_journals
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
        if name == "add":
            command.add_argument("--from", dest="moved_from", type=Path)
    commands.add_parser("use", help="Select a registered vault.").add_argument("vault_uuid")
    commands.add_parser("current", help="Show the active vault.")
    setup_parser = commands.add_parser("setup", help="Prepare the starter vault or an existing vault and connect an Agent host.")
    setup_parser.add_argument("vault", nargs="?", type=Path, default=Path("knowledge"))
    setup_parser.add_argument("--project", type=Path, default=Path.cwd())
    setup_parser.add_argument("--host", choices=["standalone", "codex", "claude"], default="standalone")
    setup_parser.add_argument("--context-note")
    context = commands.add_parser("context", help="Emit bounded SessionStart context as JSON.")
    context.add_argument("vault", type=Path)
    context.add_argument("--note")
    context.add_argument("--session-start", action="store_true", help="Read the SessionStart event from stdin.")
    write = commands.add_parser("write", help="Plan or apply operations from a JSON file, or from - for stdin.")
    write.add_argument("action", choices=["plan", "apply", "status"])
    write.add_argument("vault", type=Path)
    write.add_argument("operations", help="JSON file or - for stdin, or the transaction UUID for status.")
    write.add_argument("--plan-hash")
    write.add_argument("--request-id")
    write.add_argument("--limit", type=int, default=100)
    write.add_argument("--offset", type=int, default=0)
    write.add_argument("--max-bytes", type=int, default=36_000)
    backup = commands.add_parser("backup", help="Archive, verify or restore a vault.")
    backup_actions = backup.add_subparsers(dest="action", required=True)
    for action in ("create", "verify", "restore"):
        command = backup_actions.add_parser(action)
        if action == "create":
            command.add_argument("vault", type=Path)
        command.add_argument("archive", type=Path)
        if action == "restore":
            command.add_argument("destination", type=Path)

    for name in ("index", "sync", "status", "search", "read", "outline", "graph", "lint", "task", "maintain", "proposal", "recover", "restore"):
        command = commands.add_parser(name, help=f"Run {name} for a vault.")
        if name in {"task", "proposal"}:
            command.add_argument("action", choices=["run"] if name == "task" else ["list", "approve", "reject", "apply"])
        command.add_argument("path", type=Path)
        if name in {"search", "status", "outline", "graph", "lint", "task", "maintain", "proposal"}:
            command.add_argument("--limit", type=int, default=8 if name in {"search", "outline"} else 25)
            command.add_argument("--offset", type=int, default=0)
            command.add_argument("--max-bytes", type=int, default=640 if name == "outline" else 36_000)
        if name == "sync":
            command.add_argument("--git", action="store_true", help="Fetch the configured vault branch and fast-forward it.")
        if name == "search":
            command.add_argument("query")
            command.add_argument("--include-excluded", action="store_true")
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
        if name == "recover":
            command.add_argument("--transaction-id", type=UUID)
            command.add_argument("--accept-current", action="store_true",
                                 help="Record the reconciled files of one divergent transaction.")

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
    if error := fts5_error():
        print(f"FTS5: unavailable ({error})")
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
    for warning in load_profile(root).warnings:
        print(f"Profile: {warning}")
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
    output = os.environ.get("KBKIT_MCP_OUTPUT", "text")
    if output not in OUTPUT_MODES:
        print("KBKIT_MCP_OUTPUT must be text or structured", file=sys.stderr)
        return 1
    vault = os.environ.get("KBKIT_VAULT")
    service = ApplicationService(Path(vault)) if vault else None
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except (ValueError, RecursionError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}}
        else:
            response = handle(message, service, output=output)
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
            identity = registry.add(root, identity=args.identity, moved_from=getattr(args, "moved_from", None))
        print(f"profile: {profile}\nvault_uuid: {identity}" if profile else identity)
        return 0
    window = {key: getattr(args, key) for key in ("limit", "offset", "max_bytes")} if hasattr(args, "limit") else {}
    if name == "search":
        filters = {key: getattr(args, "filter_" + key) for key in ("path", "kind", "state", "tags", "symbols", "exclude")}
        result = service.search(args.query, args.include_inactive, max_chars=args.max_chars, include_excluded=args.include_excluded, **filters, **window)
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
        print(f"changed_blocks: {service.index()['blocks']}")
        return 0
    if name == "sync":
        result = service.sync(git=args.git)
        _json(result)
        return int(result["index_dirty"])
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
        if args.accept_current and args.transaction_id is None:
            raise ValueError("--accept-current requires --transaction-id")
        if args.transaction_id is None:
            journals = transaction_journals(root)
        else:
            journal = find_journal(root, str(args.transaction_id))
            if journal is None:
                raise ValueError(f"transaction not found: {args.transaction_id}")
            journals = [journal]
        result = {}
        ok = True
        refresh = False
        for journal in journals:
            try:
                outcome = recover_transaction(root, journal, accept_current=args.accept_current)
            except (ValueError, OSError, KeyError, TypeError) as error:
                outcome = {"state": "error", "message": str(error)}
            result[journal.name] = outcome
            ok = ok and outcome in ("applied", "resolved")
            refresh |= outcome == "applied" and journal.parent.name == "transactions"
        if refresh and (metadata_dir(root) / "profile.toml").is_file():
            try:
                service.sync()
            except (ValueError, OSError, sqlite3.Error) as error:
                print(f"Files recovered. Run kbc sync to refresh the index: {error}", file=sys.stderr)
                ok = False
        _json(result)
        return int(not ok)
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
        elif args.command == "setup":
            _json(setup(args.vault, args.project, args.host, args.context_note))
        elif args.command == "context":
            event = {}
            if args.session_start and not sys.stdin.isatty():
                payload = sys.stdin.buffer.read(65_537)
                try:
                    event = json.loads(payload) if payload and len(payload) <= 65_536 else {}
                except (ValueError, RecursionError):
                    event = {}
            source = event.get("source") if isinstance(event, dict) else None
            refresh = args.session_start and source in (None, "startup", "resume", "clear")
            _json(session_context(args.vault, args.note, refresh=refresh))
        elif args.command == "write":
            service = ApplicationService(args.vault)
            if args.action == "status":
                result = service.write_status(args.operations)
            else:
                source = sys.stdin.buffer.read() if args.operations == "-" else Path(args.operations).read_bytes()
                operations = json.loads(source)
                if args.action == "plan":
                    result = service.plan_operations(operations, args.limit, args.offset, args.max_bytes)
                else:
                    result = service.apply_operations(operations, args.plan_hash, args.request_id)
            _json(result)
            return int(result.get("state") == "divergent")
        elif args.command == "backup":
            if args.action == "create":
                _json(create_backup(args.vault, args.archive))
            elif args.action == "verify":
                result = verify_backup(args.archive)
                _json(result)
                return int(not result["ok"])
            else:
                _json(restore_backup(args.archive, args.destination))
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
    except (ValueError, OSError, BadZipFile, sqlite3.Error, GitUnavailable, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
