"""Unified application service used by CLI and MCP adapters."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from .audit import AUDIT_DISPOSITIONS, read_audit, record_audit
from .consistency import check_consistency
from .core import _build_index, _document_metadata, build_index, init_vault, maintain
from .gates import check_gates
from .git_adapter import sync_worktree
from .graph import build_graph
from .knowledge import KnowledgeVault
from .lint import lint
from .paging import MAX_PAYLOAD_BYTES, integer, json_size, page, window
from .profile import load_profile, matches_prefix
from .prototype_lock import file_lock
from .registry import VaultRegistry
from .retrieval import _rows, _snapshot, _status, facets, search_page
from .selector import SelectorError, block_locator, headings, markdown_path, select, source_lines
from .state import StateStore
from .storage import metadata_dir
from .transaction import guard_transactions, plan_operations, restore_from_trash, submit_operations, transaction_status
from .vault_profile import vault_id
from .writer import apply_proposal


DEFAULT_OUTLINE_BYTES = 2_000
MAINTENANCE_COLLECTIONS = ("findings", "code_sync", "automatic_fixes")


class ApplicationService:
    def __init__(self, vault: Path) -> None:
        self.vault = vault.resolve()

    def initialize(self) -> dict:
        profile = init_vault(self.vault)
        with closing(VaultRegistry()) as registry:
            vault_uuid = registry.add(self.vault)
        return {"vault_uuid": vault_uuid, "profile": str(profile)}

    def index(self) -> dict:
        return {"blocks": build_index(self.vault)}

    def sync(self, *, git: bool = False) -> dict:
        vault_id(self.vault)
        profile = load_profile(self.vault)
        metadata = metadata_dir(self.vault)
        with file_lock(metadata / "maintenance.lock"), file_lock(metadata / "write.lock"):
            result = {}
            if git:
                if not profile.git_remote or not profile.git_branch:
                    raise ValueError("configure git.remote and git.branch in profile.toml before syncing Git")
                guard_transactions(self.vault)
                result = sync_worktree(self.vault, profile.git_remote, profile.git_branch)
                # A tracked profile can change when the worktree advances.
                try:
                    vault_id(self.vault)
                    load_profile(self.vault)
                except (ValueError, OSError) as error:
                    return {**result, "index_dirty": True, "error": str(error)}
            try:
                return {**result, "changed_blocks": _build_index(self.vault, verify=False), "index_dirty": False}
            except (sqlite3.Error, ValueError, OSError) as error:
                if not git:
                    raise
                return {**result, "index_dirty": True, "error": str(error)}

    def search(self, query: str = "", include_inactive: bool = False, **options) -> dict:
        return search_page(self.vault, query, include_inactive, **options)

    def facet(self, **options) -> dict:
        return facets(self.vault, **options)

    def read(self, path: str | None = None, *, heading=None, block_id=None, lines=None, max_bytes=8000) -> dict:
        integer(max_bytes, "max_bytes", 512, MAX_PAYLOAD_BYTES)
        if sum(value is not None for value in (heading, block_id, lines)) > 1:
            raise SelectorError("choose one of heading, block_id or lines")
        block = None
        if block_id is not None:
            relative, block = block_locator(block_id)
            if path is not None and markdown_path(self.vault, path) != markdown_path(self.vault, relative):
                raise SelectorError("path and block_id must identify the same document")
            path = relative
        target = markdown_path(self.vault, path)
        relative = target.relative_to(self.vault).as_posix()
        raw = target.read_bytes()
        source = source_lines(raw)
        selection = select(raw, heading=heading, block=block, lines=lines)
        result = {"path": relative, "total_lines": len(source), "truncated": False}
        profile = load_profile(self.vault)
        tracked = KnowledgeVault(self.vault).statuses(profile).get(relative)
        result.update(_status(_document_metadata(raw), profile, tracked))
        limit = max_bytes - json_size(result) - 300
        targeted = any(value is not None for value in (heading, block, lines))
        if not targeted and json_size(raw.decode("utf-8-sig")) > limit:
            result.update(truncated=True, outline=[], suggested_lines=[1, min(len(source), 40)],
                          hint="Use kb_outline, or call kb_read with heading, block_id or lines.")
            outline = self._outline(raw, relative, limit=5, offset=0, max_bytes=min(800, max_bytes))
            for item in outline["outline"]:
                if json_size(result) + json_size(item) + 1 > max_bytes:
                    break
                result["outline"].append(item)
            return result
        kept = []
        used = 0
        for line in source[selection.start:selection.end]:
            text = line.decode("utf-8-sig" if selection.start == 0 and not kept else "utf-8")
            cost = json_size(text) - 2
            if used + cost > limit:
                if not kept:
                    kept.append(text.encode("utf-8")[:max(0, limit // 6)].decode("utf-8", errors="ignore"))
                    result["line_truncated"] = True
                break
            kept.append(text)
            used += cost
        last = selection.start + len(kept)
        result.update(content="".join(kept), lines=[selection.start + 1, last] if kept else [],
                      truncated=last < selection.end or result.get("line_truncated", False))
        if last < selection.end:
            result["next_lines"] = [last + 1, selection.end]
            result["hint"] = "Use next_lines to read the rest of the selected range."
        if result.get("line_truncated"):
            result["hint"] = "A source line exceeds max_bytes. Increase max_bytes or inspect the local file."
        return result

    def status(self, limit=25, offset=0, max_bytes=36_000) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        profile_path = metadata_dir(self.vault) / "profile.toml"
        initialized = profile_path.is_file()
        try:
            profile = load_profile(self.vault)
            if initialized:
                vault_id(self.vault)
        except (ValueError, OSError) as error:
            context = {"initialized": initialized, "profile_valid": False, "profile_error": "",
                       "hint": "Fix profile.toml before searching or syncing."}
            message = str(error)[:max_bytes]
            while json_size({**context, "profile_error": message}) > max_bytes - 100:
                message = message[:-1]
            context["profile_error"] = message
            return page([], key="knowledge_entries", limit=limit, offset=offset, max_bytes=max_bytes, context=context)
        knowledge = KnowledgeVault(self.vault)
        statuses = []
        source_states, effective, unknown = Counter(), Counter(), Counter()
        indexed_blocks = None
        unmatched = set(profile.exclude) | set(profile.allow)
        excluded_documents = 0
        if profile_path.is_file():
            with _snapshot(self.vault) as connection:
                indexed_blocks = connection.execute("SELECT count(*) FROM block_text").fetchone()[0]
                reviewed = knowledge.statuses(profile)
                for path, doc, status, _ in _rows(connection, reviewed, profile):
                    unmatched.difference_update([entry for entry in unmatched if matches_prefix(path, (entry,))])
                    excluded_documents += profile.excluded(path)
                    raw = doc.get("state")
                    if raw is not None:
                        source_states[raw] += 1
                        if profile.canonical_state(raw) == "unknown":
                            unknown[raw] += 1
                    effective[status["state"]] += 1
            statuses = [{"path": path, **value} for path, value in sorted(reviewed.items())]
        context = {"initialized": profile_path.is_file(), "vault": str(self.vault), "profile": str(profile_path),
                   "indexed_blocks": indexed_blocks, "unknown_state_documents": sum(unknown.values()),
                   "excluded_paths": [], "allowed_paths": [], "state_counts": {}, "source_state_counts": {},
                   "unknown_state_counts": {}, "summary_truncated": False}
        config_warnings = list(profile.warnings)
        config_warnings.extend(f"Path prefix matched no indexed Markdown: {path}" for path in sorted(unmatched))
        fields = []
        if config_warnings:
            context["config_warnings"] = []
            fields.append(("config_warnings", (message[:400] for message in config_warnings)))
        if profile.exclude:
            context["excluded_documents"] = excluded_documents
        if unknown:
            context["warning"] = "Unknown states are excluded by default; configure states.aliases."
        budget = max_bytes - 120
        size = json_size(context)
        if size > budget:
            paths = (context["vault"], context["profile"])
            context.update(vault="", profile="", summary_truncated=True)
            slots = max(0, (budget - json_size(context)) // 2)
            # Budget for escaping in JSON as well as UTF-8 path bytes.
            for key, value in zip(("vault", "profile"), paths, strict=True):
                segment = value.encode("utf-8")[:slots].decode("utf-8", errors="ignore")
                while json_size(segment) - 2 > slots:
                    segment = segment[:-1]
                context[key] = segment
            size = json_size(context)
        for key, values in (
            *fields, ("excluded_paths", profile.exclude), ("allowed_paths", profile.allow),
            ("state_counts", effective.most_common()), ("source_state_counts", source_states.most_common()),
            ("unknown_state_counts", unknown.most_common()),
        ):
            field = context[key]
            for item in values:
                cost = json_size(item) + 4
                if size + cost > budget:
                    context["summary_truncated"] = True
                    break
                size += cost
                if isinstance(field, list):
                    field.append(item)
                else:
                    name, count = item
                    field[name] = count
        result = page(statuses, key="knowledge_entries", limit=limit, offset=offset,
                      max_bytes=max_bytes, context=context)
        return result

    def maintain(self, limit=25, offset=0, max_bytes=36_000, collection="findings", *, auto_apply=None) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        if collection not in MAINTENANCE_COLLECTIONS:
            raise ValueError("collection must be findings, code_sync or automatic_fixes")
        report = maintain(self.vault, auto_apply=auto_apply)
        return self._maintenance_page(report, limit, offset, max_bytes, collection)

    def maintenance_report(self, run_id, limit=25, offset=0, max_bytes=36_000, collection="findings") -> dict:
        from uuid import UUID

        limit, offset, max_bytes = window(limit, offset, max_bytes)
        report_path = metadata_dir(self.vault) / "reports" / f"{UUID(run_id)}.json"
        report = json.loads(report_path.read_bytes())
        return self._maintenance_page({**report, "report_path": str(report_path)}, limit, offset, max_bytes, collection)

    @staticmethod
    def _maintenance_page(report, limit, offset, max_bytes, collection):
        summary = {key: report[key] for key in (
            "run_id", "status", "blocks", "changed_blocks", "proposals", "expired_proposals", "report_path", "auto_apply"
        ) if key in report}
        summary["code_sync_counts"] = dict(Counter(row["status"] for row in report.get("code_sync", [])))
        summary["automatic_fix_counts"] = dict(Counter(row["status"] for row in report.get("automatic_fixes", [])))
        if "consistency" in report:
            summary["index_consistent"] = report["consistency"]["ok"]
        summary["graph_counts"] = {key: len(report["graph"][key]) for key in ("nodes", "edges", "broken")} if "graph" in report else {}
        if "error" in report:
            summary["error"] = str(report["error"])[:500]
        if collection not in MAINTENANCE_COLLECTIONS:
            raise ValueError("collection must be findings, code_sync or automatic_fixes")
        return page(report.get(collection, []), key=collection, context=summary,
                    limit=limit, offset=offset, max_bytes=max_bytes)

    def proposals(self, status: str | None = None, limit=25, offset=0, max_bytes=36_000) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        with closing(StateStore(self.vault)) as store:
            total, rows = store.proposal_page(status, limit, offset)
        return page(rows, key="proposals", limit=limit, offset=offset, max_bytes=max_bytes, total=total, presliced=True)

    def apply_proposal(self, proposal_id: str) -> dict:
        return self._refresh_after_write(apply_proposal(self.vault, proposal_id))

    def restore(self, entry_id: str) -> dict:
        return self._refresh_after_write(restore_from_trash(self.vault, entry_id))

    def plan_operations(self, operations: list[dict], limit=100, offset=0, max_bytes=36_000) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        plan = plan_operations(self.vault, operations)
        previews = [{
            "path": change.relative_path, "operation": change.operation,
            "before_hash": change.before_hash, "removed": change.after is None,
            "position": change.position, "preview": change.preview,
        } for change in plan["changes"]]
        result = page(previews, key="previews", limit=limit, offset=offset, max_bytes=max_bytes,
                      context={"transaction_id": plan["transaction_id"], "plan_hash": plan["plan_hash"],
                               "dry_run": True, "changes": []}, item_overhead=lambda item: json_size(item["path"]) + 1)
        result["changes"] = [item["path"] for item in result["previews"]]
        return result

    def apply_operations(self, operations: list[dict], plan_hash: str | None = None,
                         request_id: str | None = None) -> dict:
        return self._refresh_after_write(submit_operations(self.vault, operations, plan_hash, request_id))

    def write_status(self, transaction_id: str) -> dict:
        return transaction_status(self.vault, transaction_id)

    def _refresh_after_write(self, result: dict) -> dict:
        try:
            paths = tuple(result.get("paths") or [result["path"]])
            init_vault(self.vault)
            with file_lock(metadata_dir(self.vault) / "maintenance.lock"):
                _build_index(self.vault, selected=paths)
                result["consistency"] = check_consistency(self.vault, paths)
        except (OSError, sqlite3.Error, ValueError) as error:
            result["consistency"] = {"ok": False, "errors": [str(error)]}
        result["index_dirty"] = not result["consistency"]["ok"]
        if result["index_dirty"]:
            result["consistency"]["errors"] = [str(error)[:400] for error in result["consistency"]["errors"][:20]]
            result["index_hint"] = "Fix the index error and run kb_index. Check the transaction state before retrying the write."
        return result

    def graph(self, collection="edges", path=None, limit=25, offset=0, max_bytes=36_000) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        graph = build_graph(self.vault)
        if collection not in graph:
            raise ValueError("collection must be edges, broken, nodes, backlinks or orphaned")
        items = graph[collection]
        if collection == "backlinks":
            items = [{"path": name, "count": count} for name, count in items.items()]
        if path is not None:
            relative = markdown_path(self.vault, path).relative_to(self.vault).as_posix()
            items = [item for item in items if (
                item == relative if isinstance(item, str) else relative in
                (item.get("path"), item.get("source"), item.get("resolved_target"))
            )]
        return page(items, key=collection, limit=limit, offset=offset, max_bytes=max_bytes)

    @staticmethod
    def _outline(raw, relative, limit, offset, max_bytes):
        items = [{"level": h.level, "title": h.path[-1], "heading_path": list(h.path),
                  "line": h.start + 1, "lines": [h.start + 1, h.end]} for h in headings(raw)]
        return page(items, key="outline", limit=limit, offset=offset, max_bytes=max_bytes,
                    context={"path": relative}, continuation_hint="Use next_offset.")

    def outline(self, path: str, limit=8, offset=0, max_bytes=DEFAULT_OUTLINE_BYTES) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        target = markdown_path(self.vault, path)
        return self._outline(target.read_bytes(), target.relative_to(self.vault).as_posix(), limit, offset, max_bytes)

    def check(self, limit=25, offset=0, max_bytes=36_000) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        vault_id(self.vault)
        findings = check_gates(self.vault)
        blocking = sum(item["blocking"] for item in findings)
        return page(findings, key="findings", limit=limit, offset=offset, max_bytes=max_bytes,
                    context={"ok": not blocking, "blocking_findings": blocking})

    def record_audit(self, run_id: str, reviewer: str, scope: list[str], findings: list[dict]) -> dict:
        receipt = record_audit(self.vault, run_id, reviewer, scope, findings)
        return {key: value for key, value in receipt.items() if key != "findings"}

    def audit_report(self, run_id: str, disposition: str | None = None,
                     limit=25, offset=0, max_bytes=36_000) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        if disposition is not None and disposition not in AUDIT_DISPOSITIONS:
            raise ValueError("unknown audit finding disposition")
        receipt = read_audit(self.vault, run_id)
        entries = receipt.pop("findings")
        if disposition is not None:
            entries = [item for item in entries if item["disposition"] == disposition]
        return page(entries, key="findings", context=receipt, limit=limit, offset=offset, max_bytes=max_bytes)

    def lint(self, limit=25, offset=0, max_bytes=36_000) -> dict:
        limit, offset, max_bytes = window(limit, offset, max_bytes)
        return page(lint(self.vault), key="findings", limit=limit, offset=offset, max_bytes=max_bytes)
