"""Read-only checks over the user vault's configured governance rules."""

from __future__ import annotations

from pathlib import Path

from .graph import build_graph, link_target
from .profile import Profile, load_profile
from .prototype_markdown import parse_document
from .storage import markdown_files
from .transaction import unresolved_transactions


def link_finding(profile: Profile, path: str, rule: str, message: str) -> dict:
    area = profile.gates.area(path)
    severity = {"historical": "info", "active": "high", "other": "medium" if rule == "LINT-L01" else "low"}
    return {"rule": rule, "path": path, "message": message, "severity": severity[area],
            "area": area, "blocking": area == "active" and (rule == "LINT-L01" or profile.gates.block_orphans)}


def broken_link_finding(profile: Profile, edge: dict, notes) -> dict:
    target = edge["target"]
    finding = link_finding(profile, edge["source"], "LINT-L01", f"broken link: {target}")
    finding["target"] = target
    candidate = profile.gates.link_targets.get(link_target(target))
    if finding["area"] == "active" and candidate in notes:
        finding["suggested_target"] = candidate
    return finding


def check_gates(root: Path) -> list[dict]:
    profile = load_profile(root)
    policy = profile.gates
    paths = markdown_files(root)
    templates = set(profile.templates.values())
    graph = build_graph(root)
    findings = [
        broken_link_finding(profile, edge, paths)
        for edge in graph["broken"] if edge["source"] not in templates and "LINT-L01" not in profile.disabled_rules
    ]
    if "LINT-L02" not in profile.disabled_rules:
        findings.extend(link_finding(profile, path, "LINT-L02", "orphaned document") for path in graph["orphaned"]
                        if path not in templates and policy.area(path) != "other")
    for transaction_id, state in unresolved_transactions(root):
        findings.append({"rule": "GATE-TRANSACTION", "path": "", "area": "vault",
                         "severity": "high", "blocking": True, "transaction_id": transaction_id, "state": state,
                         "message": f"resolve transaction {transaction_id} before committing vault changes"})
    for required in policy.required_entries:
        if required not in paths:
            findings.append({"rule": "GATE-ENTRY", "path": required, "area": "active",
                             "severity": "high", "blocking": True, "message": "required entry is missing"})
    for relative, (path, _) in sorted(paths.items()):
        if relative in templates:
            continue
        area = policy.area(relative)

        def report(rule, message):
            blocking = area != "historical"
            findings.append({"rule": rule, "path": relative, "area": area, "message": message,
                             "severity": "high" if blocking else "info", "blocking": blocking})

        if policy.allowed_roots and relative.split("/", 1)[0] not in policy.allowed_roots:
            report("GATE-LAYOUT", "top-level entry is outside the allowed roots")
        if policy.name_pattern and not policy.name_pattern.fullmatch(path.stem):
            report("GATE-NAME", "filename does not match name_pattern")
        if policy.required_fields or policy.version_pattern:
            document = parse_document(path.read_bytes())
            missing = [name for name in policy.required_fields if not (document.fields.get(name) or document.lists.get(name))]
            if missing:
                report("GATE-FRONTMATTER", "missing required fields: " + ", ".join(missing))
            if policy.version_pattern and not policy.version_pattern.fullmatch(document.fields.get(policy.version_field, "")):
                report("GATE-VERSION", f"{policy.version_field} does not match version_pattern")
    return sorted(findings, key=lambda item: (not item["blocking"], item["path"], item["rule"], item["message"]))
