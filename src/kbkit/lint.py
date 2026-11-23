"""Deterministic findings and mechanical fixes for vault maintenance."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .frontmatter import RULE_IDS as FRONTMATTER_RULE_IDS, validate_frontmatter
from .gates import broken_link_finding, link_finding
from .graph import build_graph, link_edit, link_target
from .profile import load_profile
from .prototype_markdown import parse_document
from .storage import markdown_files
from .transaction import digest


RULE_IDS = FRONTMATTER_RULE_IDS | {"FM-FINAL-NEWLINE", "FM-COMPATIBILITY", "LINT-L01", "LINT-L02", "LINT-L04", "LINT-L11"}


def lint(root: Path, *, graph: dict | None = None, protected=()) -> list[dict]:
    profile = load_profile(root)
    graph = build_graph(root) if graph is None else graph
    notes = set(graph["nodes"]) if profile.gates.link_targets else ()
    findings = [broken_link_finding(profile, edge, notes) for edge in graph["broken"]]
    findings.extend(link_finding(profile, path, "LINT-L02", "orphaned document") for path in graph["orphaned"])
    redirects = {}
    if "LINT-L01" not in profile.disabled_rules:
        for finding in findings:
            if "suggested_target" in finding and finding["path"] not in protected:
                redirects.setdefault(finding["path"], []).append(finding)
    compatibility = Counter()
    for relative, (path, _) in sorted(markdown_files(root).items()):
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        document = parse_document(raw)
        aliases = redirects.get(relative, [])
        replacements = {link_target(item["target"]): item["suggested_target"] for item in aliases}
        replacements = dict(list(replacements.items())[:32])
        edit = link_edit(raw, replacements) if replacements else None
        if edit is not None:
            _, _, used = edit
            finding = next(item for item in aliases if link_target(item["target"]) in used)
            finding["fix"] = {"finding_rule": "LINT-L01", "operation": "replace", "path": relative,
                              "link_targets": used, "expected_hash": digest(raw)}
        for finding in validate_frontmatter(raw, profile=profile, document=document):
            if finding["rule"] in profile.disabled_rules:
                continue
            if finding["rule"] in {"FM-UNKNOWN", "FM-STATE", "FM-TAG"}:
                compatibility[(finding["rule"], finding.get("value") or finding["field"])] += 1
            else:
                findings.append({**finding, "path": relative})
        if not text.strip():
            findings.append({"rule": "LINT-L11", "severity": "low", "path": relative, "message": "empty document"})
        elif relative not in protected and profile.gates.area(relative) != "historical" and not raw.endswith((b"\n", b"\r")):
            newline = "\r\n" if b"\r\n" in raw else "\n"
            finding = {"rule": "FM-FINAL-NEWLINE", "severity": "low", "path": relative, "message": "missing final newline"}
            if edit is None:
                finding["fix"] = {"finding_rule": "FM-FINAL-NEWLINE", "operation": "append", "path": relative,
                                  "content": newline, "expected_hash": digest(raw)}
            findings.append(finding)
        needs_provenance = not profile.provenance_kinds or document.fields.get("kind") in profile.provenance_kinds
        if needs_provenance and profile.provenance_fields and not any(document.fields.get(field) for field in profile.provenance_fields):
            findings.append({"rule": "LINT-L04", "severity": "low", "path": relative, "message": "missing provenance fields"})
    if compatibility:
        counts = Counter()
        for (rule, _), count in compatibility.items():
            counts[rule] += count
        findings.append({"rule": "FM-COMPATIBILITY", "severity": "low", "message": "frontmatter values outside the vault profile",
                         "counts": dict(counts), "examples": [{"rule": rule, "value": value[:80], "count": count}
                                                             for (rule, value), count in compatibility.most_common(8)]})
    return [item for item in findings if item["rule"] not in profile.disabled_rules]
