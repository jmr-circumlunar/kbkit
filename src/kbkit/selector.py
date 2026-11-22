"""Resolve vault-relative Markdown paths and precise source ranges."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .prototype_markdown import parse_document
from .storage import metadata_dir


class SelectorError(ValueError):
    pass


@dataclass(frozen=True)
class Heading:
    path: tuple[str, ...]
    level: int
    start: int
    end: int


@dataclass(frozen=True)
class Selection:
    start: int
    end: int


def markdown_path(root: Path, relative: str, *, allow_missing: bool = False) -> Path:
    if not isinstance(relative, str):
        raise SelectorError("path must be a vault-relative Markdown path")
    path = Path(relative)
    target = (root / path).resolve()
    if (path.anchor or PureWindowsPath(relative).drive or ".." in path.parts or (os.name == "nt" and ":" in relative) or
            root.resolve() not in target.parents or metadata_dir(root).resolve() in target.parents or target.suffix.lower() != ".md" or
            {".git", ".kbkit"}.intersection(part.lower() for part in target.relative_to(root.resolve()).parts) or
            target.relative_to(root.resolve()) != path):
        raise SelectorError("use a non-aliased Markdown path inside the vault")
    if not target.is_file() and (not allow_missing or target.exists()):
        raise SelectorError("selector matched no Markdown file")
    return target


def source_lines(raw: bytes) -> list[bytes]:
    return raw.splitlines(keepends=True)


def headings(raw: bytes, *, lines: list[bytes] | None = None) -> list[Heading]:
    document = parse_document(raw)
    offset = len(source_lines(document.prefix)) if document.body_offset > 3 else 0
    lines = source_lines(raw) if lines is None else lines
    found = []
    stack = []
    fence = None
    for index in range(offset, len(lines)):
        candidate = lines[index]
        if index == 0 and candidate.startswith(bytes.fromhex("efbbbf")):
            candidate = candidate[3:]
        if candidate[:4].lstrip(b" ")[:1] not in (b"#", b"~", b"`", b"=", b"-"):
            continue
        line = candidate.decode("utf-8").rstrip("\r\n")
        marker = re.match(r"^ {0,3}([~\x60])\1{2,}", line)
        if fence:
            if marker and marker[1] == fence[0] and len(marker[0].lstrip()) >= fence[1] and not line[marker.end():].strip():
                fence = None
            continue
        if marker:
            fence = (marker[1], len(marker[0].lstrip()))
            continue
        match = re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*$", line)
        start = index
        if match:
            level = len(match[1])
            title = re.sub(r"\s+#+$", "", match[2])
        elif index > offset and (underline := re.fullmatch(r" {0,3}(=+|-+)[ \t]*", line)):
            previous = lines[index - 1].decode("utf-8-sig").rstrip("\r\n")
            if not re.fullmatch(r" {0,3}[^#>~\x60*+\-\s].*", previous) or re.match(r"^ {0,3}\d+[.)]\s", previous):
                continue
            start, title = index - 1, previous.strip()
            level = 1 if underline[1].startswith("=") else 2
        else:
            continue
        while stack and found[stack[-1]][1] >= level:
            found[stack.pop()][3] = start
        parent = found[stack[-1]][0] if stack else ()
        stack.append(len(found))
        found.append([(*parent, title), level, start, len(lines)])
    return [Heading(*item) for item in found]


def blocks(raw: bytes, *, sections: list[Heading] | None = None, line_count: int | None = None) -> list[Selection]:
    sections = headings(raw) if sections is None else sections
    line_count = len(source_lines(raw)) if line_count is None else line_count
    breaks = [0, *(h.start for h in sections if h.start), line_count]
    return [Selection(start, end) for start, end in zip(breaks, breaks[1:]) if end > start]


def select(raw: bytes, *, heading=None, block=None, lines=None) -> Selection:
    count = len(source_lines(raw))
    if heading is not None:
        if not isinstance(heading, list) or not heading or not all(isinstance(part, str) and part for part in heading):
            raise SelectorError("heading must be a nonempty array of titles")
        matches = [h for h in headings(raw) if h.path == tuple(heading)]
        if len(matches) != 1:
            raise SelectorError(f"heading matched {len(matches)} sections")
        return Selection(matches[0].start, matches[0].end)
    if block is not None:
        match = re.fullmatch(r"([0-9]{1,9})(?:@([0-9a-f]{32}))?", block)
        if match is None:
            raise SelectorError("block_id must use a valid block ordinal")
        expected = match[2]
        if expected and not hashlib.sha256(raw).hexdigest().startswith(expected):
            raise SelectorError("block_id belongs to an earlier document version; repeat kb_search")
        ranges = blocks(raw)
        ordinal = int(match[1])
        if ordinal >= len(ranges):
            raise SelectorError("block_id matched no block; use an ID returned by kb_search")
        return ranges[ordinal]
    if lines is not None:
        if not isinstance(lines, list) or len(lines) != 2 or any(type(n) is not int for n in lines):
            raise SelectorError("lines must be a pair of inclusive line numbers")
        first, last = lines
        if not 1 <= first <= last <= count:
            raise SelectorError(f"line range is outside the document ({count} lines)")
        return Selection(first - 1, last)
    return Selection(0, count)


def block_locator(block_id: str) -> tuple[str, str]:
    if not isinstance(block_id, str) or ":" not in block_id:
        raise SelectorError("block_id must have the form path:ordinal")
    return tuple(block_id.rsplit(":", 1))


def resolve_source(root: Path, selector: dict, *, allow_missing_path: bool = False) -> tuple[Path, Selection, bytes]:
    if not isinstance(selector, dict):
        raise SelectorError("selector must be an object")
    keys = set(selector)
    if keys == {"block_id"}:
        relative, block = block_locator(selector["block_id"])
        options = {"block": block}
    elif keys == {"path", "heading_path"} or keys == {"path", "line_range"}:
        relative = selector["path"]
        key = "heading_path" if "heading_path" in keys else "line_range"
        if selector[key] is None:
            raise SelectorError(f"{key} cannot be null")
        options = {"heading" if key == "heading_path" else "lines": selector[key]}
    elif keys == {"heading_path"} and isinstance(selector["heading_path"], str) and "#" in selector["heading_path"]:
        relative, *titles = selector["heading_path"].split("#")
        options = {"heading": titles}
    elif keys == {"line_range"} and isinstance(selector["line_range"], str):
        match = re.fullmatch(r"(.+):([0-9]{1,9})-([0-9]{1,9})", selector["line_range"])
        if not match:
            raise SelectorError("line_range must have the form path:first-last")
        relative = match[1]
        options = {"lines": [int(match[2]), int(match[3])]}
    elif keys == {"path"}:
        relative = selector["path"]
        options = {}
    else:
        raise SelectorError("supply path, block_id, path with heading_path, or path with line_range")
    target = markdown_path(root, relative, allow_missing=allow_missing_path and not options)
    raw = target.read_bytes() if target.exists() else b""
    return target, select(raw, **options), raw


def resolve_selector(root: Path, selector: dict, *, allow_missing_path: bool = False) -> tuple[Path, Selection]:
    target, selection, _ = resolve_source(root, selector, allow_missing_path=allow_missing_path)
    return target, selection
