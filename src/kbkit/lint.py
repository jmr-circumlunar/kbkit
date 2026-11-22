"""Deterministic findings and mechanical fixes for vault maintenance."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .frontmatter import validate_frontmatter
from .graph import build_graph
from .profile import load_profile
from .prototype_markdown import parse_document
from .storage import markdown_files
from .transaction import digest


def lint(root: Path, *, graph: dict | None = None, protected=()) -> list[dict]:
    profile = load_profile(root)
    graph = build_graph(root) if graph is None else graph
    findings = [
        {"rule": "LINT-L01", "severity": "medium", "path": edge["source"], "message": f"broken link: {edge['target']}"}
        for edge in graph["broken"]
    ]
    findings.extend({"rule": "LINT-L02", "severity": "low", "path": path, "message": "orphaned document"}
                    for path in graph["orphaned"])
    compatibility = Counter()
    for relative, (path, _) in sorted(markdown_files(root).items()):
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        document = parse_document(raw)
        for finding in validate_frontmatter(raw, profile=profile, document=document):
            if finding["rule"] in profile.disabled_rules:
                continue
            if finding["rule"] in {"FM-UNKNOWN", "FM-STATE", "FM-TAG"}:
                compatibility[(finding["rule"], finding.get("value") or finding["field"])] += 1
            else:
                findings.append({**finding, "path": relative})
        if not text.strip():
            findings.append({"rule": "LINT-L11", "severity": "low", "path": relative, "message": "empty document"})
        elif relative not in protected and not raw.endswith((b"\n", b"\r")):
            newline = "\r\n" if b"\r\n" in raw else "\n"
            findings.append({"rule": "FM-FINAL-NEWLINE", "severity": "low", "path": relative, "message": "missing final newline",
                             "fix": {"finding_rule": "FM-FINAL-NEWLINE", "operation": "append", "path": relative, "content": newline, "expected_hash": digest(raw)}})
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
