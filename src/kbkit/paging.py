"""Response budgets shared by Agent and CLI adapters."""

from __future__ import annotations

import json
from itertools import islice


MAX_PAYLOAD_BYTES = 60_000


def json_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def integer(value, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def window(limit: int, offset: int, max_bytes: int) -> tuple[int, int, int]:
    return (integer(limit, "limit", 1, 200), integer(offset, "offset", 0, 100_000_000),
            integer(max_bytes, "max_bytes", 512, MAX_PAYLOAD_BYTES))


def page(items, *, key: str, limit: int, offset: int, max_bytes: int,
         total: int | None = None, presliced: bool = False, context: dict | None = None,
         item_overhead=None, continuation_hint: str | None = None) -> dict:
    total = len(items) if total is None else total
    result = {**(context or {}), key: [], "total": total, "truncated": True, "next_offset": offset}
    empty_hint = "Increase max_bytes or request a shorter representation."
    if continuation_hint and offset < total:
        result["hint"] = continuation_hint
    size = json_size(result) + 16
    for item in islice(items, 0 if presliced else offset, limit if presliced else offset + limit):
        size += json_size(item) + 1 + (item_overhead(item) if item_overhead else 0)
        if size > max_bytes:
            break
        result[key].append(item)
    next_offset = offset + len(result[key])
    result["truncated"] = next_offset < total
    result["next_offset"] = next_offset if result["truncated"] else None
    if not result["truncated"] and continuation_hint:
        result.pop("hint", None)
    elif result["truncated"] and not result[key]:
        if continuation_hint:
            result["hint"] = "Increase max_bytes."
        elif json_size(result) + json_size(empty_hint) + 8 <= max_bytes:
            result["hint"] = empty_hint
    return result

