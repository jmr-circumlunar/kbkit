"""E5 deterministic lint rules."""

from __future__ import annotations

from pathlib import Path

from .graph import build_graph
from .frontmatter import validate_frontmatter


def lint(root: Path) -> list[dict]:
    findings: list[dict] = []
    graph = build_graph(root)
    for edge in graph["broken"]:
        findings.append({"rule": "LINT-L01", "severity": "medium", "path": edge["source"], "message": f"broken link: {edge['target']}"})
    for path in graph["orphaned"]:
        findings.append({"rule": "LINT-L02", "severity": "low", "path": path, "message": "orphaned document"})
    for path in root.rglob("*.md"):
        if ".kbkit" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        findings.extend({**finding, "path": path.relative_to(root).as_posix()} for finding in validate_frontmatter(path.read_bytes()))
        if text.strip() == "":
            findings.append({"rule": "LINT-L11", "severity": "low", "path": path.relative_to(root).as_posix(), "message": "empty document"})
        if "review_by:" not in text and "source:" not in text:
            findings.append({"rule": "LINT-L04", "severity": "low", "path": path.relative_to(root).as_posix(), "message": "missing provenance fields"})
    return findings
