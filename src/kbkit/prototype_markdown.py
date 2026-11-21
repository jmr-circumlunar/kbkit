"""Read and edit the supported Markdown frontmatter subset."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FrontmatterDocument:
    raw: bytes
    prefix: bytes
    body: bytes
    fields: dict[str, str]
    body_offset: int
    lists: dict[str, tuple[str, ...]]


_FIELD = re.compile(rb"^([A-Za-z_][A-Za-z_0-9-]*):[ \t]*(.*)$")
_ITEM = re.compile(rb"^[ \t]*-[ \t]+(.+)$")


def _split_comment(value: str) -> tuple[str, str]:
    quoted = re.match(r"""[ \t]*(?:"(?:\\.|[^"])*"|'(?:''|[^'])*')""", value)
    boundary = quoted.end() if quoted else 0
    comment = re.search(r"[ \t]+#", value[boundary:])
    if comment is None:
        return value, ""
    index = boundary + comment.start()
    return value[:index], value[index:]


def _scalar(value: str) -> str:
    text, _ = _split_comment(value)
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        try:
            return json.loads(text)
        except ValueError:
            return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1].replace("''", "'")
    return text


def parse_document(raw: bytes) -> FrontmatterDocument:
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    content = raw[len(bom):]
    if not content.startswith((b"---\n", b"---\r\n")):
        return FrontmatterDocument(raw, bom, content, {}, len(bom), {})
    fields: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    offset = len(bom)
    current = None
    for index, line in enumerate(content.splitlines(keepends=True)):
        offset += len(line)
        if index == 0:
            continue
        plain = line.rstrip(b"\r\n")
        if plain == b"---":
            return FrontmatterDocument(raw, raw[:offset], raw[offset:], fields, offset,
                                       {key: tuple(items) for key, items in lists.items()})
        match = _FIELD.fullmatch(plain)
        if match:
            current = match[1].decode("ascii")
            value, _ = _split_comment(match[2].decode("utf-8"))
            fields[current] = _scalar(value)
            lists.pop(current, None)
            if current == "tags" and value.strip().startswith("[") and value.strip().endswith("]"):
                parts = re.findall(r"""(?:"(?:\\.|[^"])*"|'(?:''|[^'])*'|[^,]+)""", value.strip()[1:-1])
                lists[current] = [_scalar(part) for part in parts if part.strip()]
        elif current and not fields[current] and (item := _ITEM.fullmatch(plain)):
            lists.setdefault(current, []).append(_scalar(item[1].decode("utf-8")))
        elif plain.strip() and not plain.lstrip().startswith(b"#"):
            current = None
    return FrontmatterDocument(raw, bom, content, {}, len(bom), {})


def set_frontmatter_field(raw: bytes, key: str, value: str) -> bytes:
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9-]*", key):
        raise ValueError("property name must be a simple frontmatter key")
    if not isinstance(value, str) or not value.strip() or any(char in value for char in "\r\n"):
        raise ValueError("property value must be a nonempty single-line string")
    document = parse_document(raw)
    if document.body_offset <= 3:
        raise ValueError("frontmatter is absent or unsupported")
    lines = document.prefix.splitlines(keepends=True)
    newline = b"\r\n" if lines[0].endswith(b"\r\n") else b"\n"
    replacement = f"{key}: {json.dumps(value, ensure_ascii=False)}".encode("utf-8") + newline
    encoded_key = key.encode("ascii") + b":"
    indices = [index for index, line in enumerate(lines[1:-1], 1) if line.startswith(encoded_key)]
    if len(indices) > 1:
        raise ValueError(f"frontmatter property appears more than once: {key}")
    if indices:
        index = indices[0]
        following = lines[index + 1]
        old = lines[index].rstrip(b"\r\n").split(b":", 1)[1].strip()
        if old.startswith((b"[", b"{", b"|", b">", b"&", b"*")) or following.startswith((b" ", b"\t", b"- ")):
            raise ValueError("only scalar frontmatter properties can be replaced")
        _, comment = _split_comment(old.decode("utf-8"))
        lines[index] = replacement[:-len(newline)] + comment.encode("utf-8") + newline
    else:
        lines.insert(1, replacement)
    return b"".join(lines) + document.body
