"""E5 basic wikilink graph extraction."""

from __future__ import annotations

import re
from pathlib import Path
import unicodedata

from .storage import markdown_files, vault_files


WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def _targets(text: str):
    fence = None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}([`~])\1{2,}", line)
        if match:
            marker = match.group()
            if fence is None:
                fence = marker.strip()
            elif marker.strip().startswith(fence) and not line[match.end():].strip():
                fence = None
            continue
        if fence is None:
            line = re.sub(r"(`+).*?\1", "", line)
            yield from WIKILINK.findall(line)


def build_graph(root: Path) -> dict:
    root = root.resolve()
    paths = markdown_files(root)
    files = {}
    for path in vault_files(root):
        relative = path.relative_to(root)
        if relative.parts[0] == ".obsidian":
            continue
        normalized = unicodedata.normalize("NFC", relative.as_posix())
        files[normalized] = relative.as_posix()
    by_name = {}
    for relative, actual in files.items():
        path = Path(relative)
        name = path.stem if path.suffix.lower() == ".md" else path.name
        by_name.setdefault(name, []).append(actual)
    edges, broken = [], []
    incoming = dict.fromkeys(sorted(paths), 0)
    for source, (path, _) in sorted(paths.items()):
        for target in _targets(path.read_text(encoding="utf-8-sig")):
            # Obsidian table aliases use an escaped pipe, e.g. [[note\|label]].
            name = unicodedata.normalize("NFC", target.rstrip("\\").replace("\\", "/"))
            relative = name if name in files else name + ".md"
            matches = by_name.get(name.removesuffix(".md"), [])
            resolved = files.get(relative)
            if resolved is None and len(matches) == 1:
                resolved = matches[0]
            edge = {"source": source, "target": target, "resolved_target": resolved}
            edges.append(edge)
            if resolved is None:
                broken.append(edge)
            elif resolved in incoming:
                incoming[resolved] += 1
    orphaned = [path for path, count in incoming.items() if count == 0]
    return {"edges": edges, "broken": broken, "nodes": sorted(paths), "backlinks": incoming, "orphaned": orphaned}
