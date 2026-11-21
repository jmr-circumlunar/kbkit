"""Check documented CLI commands, tools, named fields and statuses against the implementation."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import patch

import kbkit
from kbkit.application import ApplicationService
from kbkit.cli import build_parser
from kbkit.core import init_vault
from kbkit.graph import build_graph
from kbkit.retrieval import FORMATS
from kbkit.transaction import apply_plan, plan_operations, recover_transaction
from kbkit.prototype_mcp import OPERATIONS, handle


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DOCS = [ROOT / "README.md", ROOT / "docs" / "architecture" / "INTERFACES.md",
               *sorted((ROOT / "skills").glob("*/SKILL.md"))]
TOOL_NAME = re.compile(r"\bkb_[a-z][a-z_]*\b")
CLI = re.compile(r"(?<![-\w])(?:-m\s+kbkit|\bkbc)\s+(?!-)([a-z][a-z-]*)(?:[ \t]+([a-z][a-z-]*))?")
IMPORT = re.compile(r"\bfrom kbkit import ([\w, ]+)")
CLAIM = re.compile(r"<!-- kbkit-contract ([a-z_]+) (.*?) -->")
INLINE = re.compile(r"\x60([a-z_][a-z_0-9-]*)\x60")


def cli_surface():
    top = next(action for action in build_parser()._actions if isinstance(action, argparse._SubParsersAction))
    commands = {}
    for command, parser in top.choices.items():
        choices = next((action.choices for action in parser._actions if action.dest in
                        {"action", "transport", "knowledge_action"}), {})
        flags = {flag for action in parser._actions for flag in action.option_strings}
        for item in choices.values() if isinstance(choices, dict) else ():
            flags.update(flag for action in item._actions for flag in action.option_strings)
        commands[command] = (set(choices), flags)
    return commands


def contract_samples():
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        with patch.dict(os.environ, {"KBKIT_INDEX_DIR": str(temp / "indexes"), "KBKIT_HOME": "",
                                     "KBKIT_REGISTRY_DIR": str(temp / "registry")}):
            vault = temp / "vault"
            profile_path = init_vault(vault)
            profile_dir = profile_path.parent
            profile = tomllib.loads(profile_path.read_text(encoding="utf-8"))
            service = ApplicationService(vault)
            (vault / "sample.md").write_text("# Heading\n\nSample body\n", encoding="utf-8")
            (vault / "old.md").write_text("---\nstate: archived\n---\n# Old\n", encoding="utf-8")
            (vault / "proposal.md").write_text("Missing final newline", encoding="utf-8")

            def call(name, **arguments):
                return handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": name, "arguments": arguments}}, service)["result"]

            write = [{"operation": "append", "selector": {"path": "sample.md", "heading_path": ["Heading"]},
                      "content": "\nNew evidence\n"}]
            responses = {
                "kb_status": call("kb_status"),
                "kb_search": call("kb_search", query="Sample", select="json"),
                "kb_outline": call("kb_outline", path="sample.md"),
                "kb_read": call("kb_read", block_id="sample.md:0"),
                "kb_write_plan": call("kb_write_plan", operations=write),
                "kb_graph": call("kb_graph"),
                "kb_lint": call("kb_lint"),
                "kb_facet": call("kb_facet"),
            }
            responses["kb_write_apply"] = call("kb_write_apply", operations=write,
                                              plan_hash=responses["kb_write_plan"]["structuredContent"]["plan_hash"])
            responses["kb_maintain"] = call("kb_maintain")
            run_id = responses["kb_maintain"]["structuredContent"]["run_id"]
            responses["kb_maintenance_report"] = call("kb_maintenance_report", run_id=run_id, collection="code_sync")
            responses["kb_proposals"] = call("kb_proposals")
            delete = call("kb_write_apply", operations=[{"operation": "delete", "path": "old.md"}])
            entry_id = delete["structuredContent"]["trash"][0]["entry_id"]
            responses["kb_restore"] = call("kb_restore", entry_id=entry_id)
            error = call("kb_search", kind="invented")
            assert all(not result["isError"] for result in responses.values()), responses
            assert error["isError"], error
            long = vault / "long.md"
            long.write_text("# Long\n" + "x" * 9000 + "\nsecond line\n", encoding="utf-8")
            responses["kb_read"] = [responses["kb_read"], call("kb_read", path="long.md", lines=[1, 3], max_bytes=512),
                                    call("kb_read", path="long.md", lines=[2, 3], max_bytes=512)]
            transaction = plan_operations(vault, [{"operation": "append", "path": "sample.md", "content": "extra"}])
            try:
                apply_plan(vault, transaction, fail_after=0)
            except RuntimeError:
                pass
            journal = profile_dir / "transactions" / f"{transaction['transaction_id']}.json"
            pending = json.loads(journal.read_bytes())["state"]
            (vault / "sample.md").write_text("External edit", encoding="utf-8")
            divergent = recover_transaction(vault, journal)
            return responses, delete, error, profile, {pending, divergent}, set(build_graph(vault))


def keys(value):
    if isinstance(value, dict):
        for name, subvalue in value.items():
            yield name
            yield from keys(subvalue)
    elif isinstance(value, list):
        for item in value:
            yield from keys(item)


def instances(value, key):
    if isinstance(value, dict):
        for name, subvalue in value.items():
            if name == key and isinstance(subvalue, str):
                yield subvalue
            yield from instances(subvalue, key)
    elif isinstance(value, list):
        for item in value:
            yield from instances(item, key)


def check(sources=SOURCE_DOCS) -> list[str]:
    catalog = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    schemas = {tool["name"]: tool["inputSchema"] for tool in catalog}
    responses, deleted, error, profile, journal_states, graph_names = contract_samples()
    payloads = {name: [item["structuredContent"] for item in result] if isinstance(result, list)
                else result["structuredContent"] for name, result in responses.items()}
    payloads["kb_write_apply"] = [payloads["kb_write_apply"], deleted["structuredContent"]]
    arguments = {name: set(keys(schema)) for name, schema in schemas.items()}
    response_fields = {name: set(keys(payload)) for name, payload in payloads.items()}
    error_fields = set(error["structuredContent"])
    cli = cli_surface()
    all_fields = set().union(*arguments.values(), *response_fields.values(), error_fields, kbkit.__all__)
    # These optional fields are exercised by the report's large-note and error regression tests.
    from kbkit.paging import page

    all_fields |= set(page([], key="hits", limit=1, offset=0, max_bytes=1024))
    all_fields |= journal_states | graph_names | set(FORMATS) | {"main", "true", "false"}
    all_fields |= set(instances(payloads["kb_write_apply"], "state"))
    all_fields |= profile.keys() | schemas.keys() | set(OPERATIONS["items"]["properties"]["operation"]["enum"])
    issues = []
    for source in sources:
        text = source.read_text(encoding="utf-8")
        domain = source.relative_to(ROOT) if source.is_relative_to(ROOT) else source
        for tool in sorted(set(TOOL_NAME.findall(text)) - schemas.keys()):
            issues.append(f"{domain}: unknown MCP tool {tool}")
        for match in CLI.finditer(text):
            command, action = match.groups()
            if command not in cli:
                issues.append(f"{domain}: unknown CLI command {command}")
                continue
            choices, flags = cli[command]
            if choices and action not in choices:
                issues.append(f"{domain}: invalid {command} action {action}")
            remainder = re.split(r"[\x60\n]", text[match.end():], maxsplit=1)[0]
            for option in set(re.findall(r"--[a-z][a-z-]*", remainder)) - flags:
                issues.append(f"{domain}: unknown {command} flag {option}")
        for exports in IMPORT.findall(text):
            for exported in exports.replace(",", " ").split():
                if exported not in kbkit.__all__:
                    issues.append(f"{domain}: unknown Python export {exported}")
        for token in set(INLINE.findall(text)) - all_fields:
            issues.append(f"{domain}: unknown documented name {token}")
        for kind, words in CLAIM.findall(text):
            name, *fields = words.split()
            if kind == "input":
                allowed = arguments.get(name, set())
            elif kind == "output":
                allowed = response_fields.get(name, set())
            elif kind == "error":
                allowed = error_fields
                fields.insert(0, name)
            elif kind == "state":
                allowed = set(instances(payloads.get(name), "state")) | set(instances(payloads.get(name), "status"))
                if name == "kb_write_apply":
                    allowed |= journal_states
            else:
                issues.append(f"{domain}: unsupported contract assertion {kind}")
                continue
            for field in set(fields) - allowed:
                issues.append(f"{domain}: unsupported {kind} claim {name} {field}")
    return issues


if __name__ == "__main__":
    errors = check()
    for item in errors:
        print(item)
    if not errors:
        print("README, Skills and interface claims agree with the CLI and MCP.")
    raise SystemExit(bool(errors))
