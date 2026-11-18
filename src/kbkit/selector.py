"""Structured selector validation for E4 operations."""

from __future__ import annotations

from pathlib import Path


class SelectorError(ValueError):
    pass


def resolve_selector(root: Path, selector: dict, *, allow_missing_path: bool = False) -> Path:
    keys = [key for key in ("path", "block_id", "heading_path", "line_range") if selector.get(key) is not None]
    if len(keys) != 1:
        raise SelectorError("selector must contain exactly one locator")
    if "path" in keys:
        relative = selector["path"]
    elif "block_id" in keys:
        relative = str(selector["block_id"]).split(":", 1)[0]
    elif "heading_path" in keys:
        relative = str(selector["heading_path"]).split("#", 1)[0]
    else:
        relative = str(selector["line_range"]).split(":", 1)[0]
    target = (root / relative).resolve()
    if root.resolve() not in target.parents or target.suffix.lower() != ".md":
        raise SelectorError("selector is outside the vault")
    if not target.exists() and not (allow_missing_path and keys == ["path"]):
        raise SelectorError("selector matched no file")
    return target
