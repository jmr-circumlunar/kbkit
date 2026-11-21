"""E5 basic wikilink graph extraction."""

from __future__ import annotations

import re
from pathlib import Path

from .selector import headings, markdown_path
from .storage import markdown_files


WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def build_graph(root: Path) -> dict:
    paths = markdown_files(root)
    by_stem = {}
    for relative in sorted(paths):
        by_stem.setdefault(Path(relative).stem, []).append(relative)
    edges = []
    broken = []
    for source, (path, _) in sorted(paths.items()):
        for target in WIKILINK.findall(path.read_text(encoding="utf-8")):
            relative = target if target.lower().endswith(".md") else target + ".md"
            matches = by_stem.get(Path(target).stem, [])
            resolved = relative if relative in paths else matches[0] if "/" not in target and len(matches) == 1 else None
            edge = {"source": source, "target": target, "resolved_target": resolved}
            edges.append(edge)
            if resolved is None:
                broken.append(edge)
    incoming = dict.fromkeys(sorted(paths), 0)
    for edge in edges:
        if edge["resolved_target"]:
            incoming[edge["resolved_target"]] += 1
    orphaned = [path for path, count in incoming.items() if count == 0]
    return {"edges": edges, "broken": broken, "nodes": sorted(paths), "backlinks": incoming, "orphaned": orphaned}


def outline(root: Path, relative_path: str) -> list[dict]:
    raw = markdown_path(root, relative_path).read_bytes()
    return [{"level": heading.level, "title": heading.path[-1], "heading_path": list(heading.path),
             "line": heading.start + 1, "lines": [heading.start + 1, heading.end]} for heading in headings(raw)]
