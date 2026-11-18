"""Small E2 prototype for loss-aware Markdown frontmatter updates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrontmatterDocument:
    raw: bytes
    prefix: bytes
    body: bytes
    fields: dict[str, str]
    body_offset: int


def parse_document(raw: bytes) -> FrontmatterDocument:
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    content = raw[len(bom) :]
    if not content.startswith(b"---\n") and not content.startswith(b"---\r\n"):
        return FrontmatterDocument(raw, bom, content, {}, len(bom))
    newline = b"\r\n" if content.startswith(b"---\r\n") else b"\n"
    marker = newline + b"---" + newline
    end = content.find(marker, len(b"---") + len(newline))
    if end < 0:
        return FrontmatterDocument(raw, bom, content, {}, len(bom))
    prefix = content[: end + len(marker)]
    body = content[end + len(marker) :]
    fields: dict[str, str] = {}
    for line in prefix.splitlines()[1:-1]:
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        fields[key.decode("utf-8").strip()] = value.decode("utf-8").strip()
    return FrontmatterDocument(raw, bom + prefix, body, fields, len(bom) + end + len(marker))


def set_frontmatter_field(raw: bytes, key: str, value: str) -> bytes:
    document = parse_document(raw)
    if not document.fields and not document.raw.startswith((b"---\n", b"---\r\n", b"\xef\xbb\xbf---")):
        raise ValueError("frontmatter is absent or unsupported")
    newline = b"\r\n" if b"\r\n" in document.raw.split(b"---", 2)[0] else b"\n"
    header = document.prefix
    lines = header.splitlines(keepends=True)
    encoded_key = key.encode("utf-8")
    replacement = f"{key}: {value}".encode("utf-8") + newline
    for index, line in enumerate(lines):
        if line.lstrip().startswith(encoded_key + b":"):
            lines[index] = replacement
            return b"".join(lines) + document.body
    insert_at = 1
    lines.insert(insert_at, replacement)
    return b"".join(lines) + document.body
