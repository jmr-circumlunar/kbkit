"""Minimal command-line entry point for the bootstrap package."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import closing
from pathlib import Path

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kbc", description="Manage local Markdown knowledge bases.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="Check the local Python and SQLite runtime.")
    mcp_parser = subparsers.add_parser("mcp", help="Run the Agent protocol adapter.")
    mcp_parser.add_argument("transport", choices=["stdio"])
    init_parser = subparsers.add_parser("init", help="Initialize a Markdown vault.")
    init_parser.add_argument("path", type=str)
    init_parser.add_argument("--identity", choices=["moved", "copy"])
    index_parser = subparsers.add_parser("index", help="Build the vault index.")
    index_parser.add_argument("path", type=str)
    search_parser = subparsers.add_parser("search", help="Search indexed blocks.")
    search_parser.add_argument("path", type=str)
    search_parser.add_argument("query", type=str)
    search_parser.add_argument("--include-inactive", action="store_true", help="Include labeled historical and stale hits.")
    read_parser = subparsers.add_parser("read", help="Read a Markdown file.")
    read_parser.add_argument("path", type=str)
    read_parser.add_argument("relative_path", type=str)
    task_parser = subparsers.add_parser("task", help="Run a deterministic maintenance task.")
    task_parser.add_argument("action", choices=["run"])
    task_parser.add_argument("path", type=str)
    add_parser = subparsers.add_parser("add", help="Register a vault.")
    add_parser.add_argument("path", type=str)
    add_parser.add_argument("--identity", choices=["moved", "copy"])
    use_parser = subparsers.add_parser("use", help="Select a registered vault.")
    use_parser.add_argument("vault_uuid", type=str)
    subparsers.add_parser("current", help="Show the active vault.")
    maintain_parser = subparsers.add_parser("maintain", help="Run a maintenance scan.")
    maintain_parser.add_argument("path", type=str)
    proposal_parser = subparsers.add_parser("proposal", help="Inspect or update proposals.")
    proposal_parser.add_argument("action", choices=["list", "approve", "reject", "apply"])
    proposal_parser.add_argument("path", type=str)
    proposal_parser.add_argument("proposal_id", nargs="?")
    recover_parser = subparsers.add_parser("recover", help="Recover pending transactions.")
    recover_parser.add_argument("path", type=str)
    knowledge_parser = subparsers.add_parser("knowledge", help="Review knowledge revisions and bind committed code sources.")
    knowledge_commands = knowledge_parser.add_subparsers(dest="knowledge_action", required=True)
    review = knowledge_commands.add_parser("review")
    review.add_argument("vault", type=Path)
    review.add_argument("page")
    review.add_argument("--depends-on", action="append")
    history = knowledge_commands.add_parser("history")
    history.add_argument("vault", type=Path)
    history.add_argument("page")
    history.add_argument("--revision", type=int)
    knowledge_status = knowledge_commands.add_parser("status")
    knowledge_status.add_argument("vault", type=Path)
    code = knowledge_commands.add_parser("bind-code")
    code.add_argument("vault", type=Path)
    code.add_argument("source")
    code.add_argument("repository", type=Path)
    code.add_argument("--ref", required=True)
    code.add_argument("--scope", action="append", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        import sqlite3

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
    if args.command == "mcp" and args.transport == "stdio":
        from .application import ApplicationService
        from .prototype_mcp import handle

        vault = Path(os.environ["KBKIT_VAULT"]).resolve() if "KBKIT_VAULT" in os.environ else None
        service = ApplicationService(vault) if vault else None

        for line in sys.stdin:
            if not line.strip():
                continue
            response = handle(json.loads(line), service)
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return 0
    if args.command == "knowledge":
        from .code_sync import bind_code
        from .git_adapter import GitUnavailable
        from .knowledge import KnowledgeVault
        from .prototype_lock import file_lock

        try:
            if not (args.vault / ".kbkit" / "profile.toml").is_file():
                raise ValueError("vault is not initialized")
            with file_lock(args.vault / ".kbkit" / "maintenance.lock"):
                knowledge = KnowledgeVault(args.vault)
                if args.knowledge_action == "review":
                    result = knowledge.review(args.page, args.depends_on)
                elif args.knowledge_action == "history":
                    result = knowledge.history(args.page, args.revision)
                elif args.knowledge_action == "status":
                    result = knowledge.statuses()
                else:
                    result = bind_code(knowledge, args.source, args.repository, args.ref, args.scope)
        except (OSError, ValueError, GitUnavailable) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command in {"init", "index", "search", "read", "task", "maintain", "proposal", "recover", "add", "use", "current"}:
        from .core import build_index, init_vault, maintain, read, search_details
        from .registry import VaultRegistry
        from .state import StateStore

        if args.command == "current":
            registry = VaultRegistry()
            current = registry.current()
            registry.close()
            if current:
                print(current)
            return 0
        if args.command == "use":
            registry = VaultRegistry()
            print(registry.use(args.vault_uuid))
            registry.close()
            return 0
        root = Path(args.path).resolve()
        if args.command in {"init", "add"}:
            try:
                profile = init_vault(root) if args.command == "init" else None
                with closing(VaultRegistry()) as registry:
                    vault_uuid = registry.add(root, identity=args.identity)
            except (ValueError, OSError) as exc:
                print(str(exc), file=sys.stderr)
                return 1
            print(f"profile: {profile}\nvault_uuid: {vault_uuid}" if profile else vault_uuid)
            return 0
        if args.command == "maintain":
            report = maintain(root)
            print(report)
            return int(report["status"] != "succeeded")
        if args.command == "recover":
            from .transaction import recover_transaction

            transaction_dir = root / ".kbkit" / "transactions"
            results = []
            journals = sorted(transaction_dir.glob("*.json")) if transaction_dir.exists() else []
            for journal in journals:
                results.append((journal.name, recover_transaction(root, journal)))
            print(results)
            return 0
        if args.command == "proposal":
            state = StateStore(root)
            if args.action == "list":
                for proposal in state.list_proposals():
                    print(proposal)
            else:
                if not args.proposal_id:
                    raise ValueError("proposal_id is required")
                if args.action in {"approve", "reject"}:
                    state.set_proposal_status(args.proposal_id, "approved" if args.action == "approve" else "rejected")
                    print(args.proposal_id)
                else:
                    from .writer import apply_proposal

                    state.close()
                    print(apply_proposal(root, args.proposal_id))
                    return 0
            state.close()
            return 0
        if args.command == "index":
            print(f"blocks: {build_index(root)}")
        elif args.command == "search":
            for hit in search_details(root, args.query, args.include_inactive):
                if args.include_inactive:
                    print(json.dumps(hit, ensure_ascii=False))
                else:
                    print(f"{hit['path']}\t{hit['block_id']}\t{hit['content']}")
        elif args.command == "read":
            sys.stdout.write(read(root, args.relative_path))
        else:
            report = maintain(root)
            print(report)
            return int(report["status"] != "succeeded")
        return 0
    return 0
