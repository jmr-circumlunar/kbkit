"""E5 basic wikilink graph extraction."""

from __future__ import annotations

import re
from pathlib import Path


WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def build_graph(root: Path) -> dict:
    files = {path.stem: path.relative_to(root).as_posix() for path in root.rglob("*.md") if ".kbkit" not in path.parts}
    edges = []
    broken = []
    for path in root.rglob("*.md"):
        if ".kbkit" in path.parts:
            continue
        source = path.relative_to(root).as_posix()
        for target in WIKILINK.findall(path.read_text(encoding="utf-8")):
            edge = {"source": source, "target": target, "resolved_target": files.get(target)}
            edges.append(edge)
            if target not in files:
                broken.append(edge)
    incoming = {path: 0 for path in files.values()}
    for edge in edges:
        if edge["resolved_target"]:
            incoming[edge["resolved_target"]] += 1
    orphaned = [path for path, count in incoming.items() if count == 0]
    return {"edges": edges, "broken": broken, "nodes": sorted(files.values()), "backlinks": incoming, "orphaned": orphaned}


def outline(root: Path, relative_path: str) -> list[dict]:
    path = (root / relative_path).resolve()
    if root.resolve() not in path.parents or not path.exists():
        raise ValueError("document is outside the vault or missing")
    result = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#") and line.lstrip("#").startswith(" "):
            level = len(line) - len(line.lstrip("#"))
            result.append({"level": level, "title": line.lstrip("#").strip(), "line": number})
    return result
