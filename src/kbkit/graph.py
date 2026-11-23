"""E5 basic wikilink graph extraction."""

from __future__ import annotations

import re
from pathlib import Path
import unicodedata

from .prototype_markdown import parse_document
from .storage import markdown_files, vault_files


WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def _link_lines(lines: list[str]):
    fence = None
    for number, line in enumerate(lines, 1):
        match = re.match(r"^ {0,3}([`~])\1{2,}", line)
        if match:
            marker = match.group()
            if fence is None:
                fence = marker.strip()
            elif marker.strip().startswith(fence) and not line[match.end():].strip():
                fence = None
            continue
        if fence is None:
            yield number, line


def _targets(text: str):
    for _, line in _link_lines(text.splitlines()):
        yield from WIKILINK.findall(re.sub(r"(`+).*?\1", "", line))


def link_target(value: str) -> str:
    return unicodedata.normalize("NFC", value.rstrip("\\").replace("\\", "/"))


def link_edit(raw: bytes, targets: dict[str, str]) -> tuple[list[int], str, dict[str, str]] | None:
    """Return a bounded replacement that edits only matching unanchored links."""
    document = parse_document(raw)
    lines = [line.decode("utf-8") for line in document.body.splitlines(keepends=True)]
    first = last = None
    used = {}
    for number, line in _link_lines(lines):
        masked = re.sub(r"(`+).*?\1", lambda match: " " * len(match[0]), line)
        changes = []
        for match in WIKILINK.finditer(masked):
            escapes = len(line[:match.start()]) - len(line[:match.start()].rstrip("\\"))
            if escapes % 2:
                continue
            start, end = match.span(1)
            original = line[start:end]
            old = link_target(original)
            target = targets.get(old)
            if target and line[end:end + 1] != "#" and all(char not in target for char in "#|[]"):
                changes.append((start, end, original, old, target))
        if not changes:
            continue
        updated = line
        for start, end, original, _, target in reversed(changes):
            value = target + ("\\" if original.endswith("\\") else "")
            updated = updated[:start] + value + updated[end:]
        earliest = first if first is not None else number
        if len(("".join(lines[earliest - 1:number - 1]) + updated).encode("utf-8")) > 8192:
            break
        first, last = earliest, number
        lines[number - 1] = updated
        used.update((old, target) for _, _, _, old, target in changes)
    if first is None:
        return None
    offset = len(document.prefix.splitlines()) if document.body_offset > 3 else 0
    return [first + offset, last + offset], "".join(lines[first - 1:last]), used


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
            name = link_target(target)
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
