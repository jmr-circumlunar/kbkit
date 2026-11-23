"""Read the user-editable vault profile and resolve search filters."""

from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .storage import metadata_dir


INACTIVE_STATES = frozenset({"draft", "archived", "deprecated", "stale", "unverified", "conflicted", "unreviewed", "missing", "unknown"})
STATE_ALIASES = {
    "active": "active", "review_due": "review_due", "生效": "active", "已生效": "active", "有效": "active",
    "草稿": "draft", "待确认": "unreviewed", "待审核": "unreviewed",
    "已被取代": "deprecated", "已归档": "archived", "归档": "archived", "已终结": "archived", "已关闭": "archived", "已完成": "archived",
    "废弃": "deprecated", "已废弃": "deprecated", "已过期": "stale", "暂缓": "unverified", "冻结": "unverified",
}


class QueryError(ValueError):
    def __init__(self, message: str, *, field: str, allowed=None) -> None:
        super().__init__(message)
        self.field = field
        self.allowed = allowed


def _strings(value, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(f"{name} must be an array of nonempty strings")
    return tuple(v.strip() for v in value)


def prefix(value: str) -> str:
    normalized = value.replace("\\", "/").strip().strip("/")
    path = PurePosixPath(normalized)
    if not normalized or value.startswith(("/", "\\")) or ":" in normalized or ".." in path.parts or path.as_posix() == ".":
        raise ValueError(f"invalid vault-relative path prefix: {value}")
    return path.as_posix()


def matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    path = os.path.normcase(path)
    for entry in prefixes:
        entry = os.path.normcase(entry)
        if path == entry or path.startswith(entry + os.sep):
            return True
    return False


@dataclass(frozen=True)
class Profile:
    warnings: tuple[str, ...] = ()
    git_remote: str | None = None
    git_branch: str | None = None
    exclude: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    require_state: bool = False
    inactive: frozenset[str] = INACTIVE_STATES
    aliases: dict[str, str] = field(default_factory=lambda: STATE_ALIASES.copy())
    disabled_rules: frozenset[str] = frozenset()
    provenance_kinds: tuple[str, ...] = ()
    provenance_fields: tuple[str, ...] = ("source", "review_by")
    allowed_fields: tuple[str, ...] = ()
    tag_vocabulary: tuple[str, ...] | None = None
    title_weight: float = 1.0
    body_weight: float = 1.0

    def excluded(self, path: str) -> bool:
        return matches_prefix(path, self.exclude) and not matches_prefix(path, self.allow)

    def canonical_state(self, value: str) -> str:
        key = value.strip().casefold()
        if key in self.aliases:
            return self.aliases[key]
        return key if key in self.inactive else "unknown"


def load_profile(root: Path) -> Profile:
    file = metadata_dir(root) / "profile.toml"
    if not file.is_file():
        return Profile()
    try:
        config = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"invalid vault profile {file}: {error}") from error
    search = config.get("search", {})
    states = config.get("states", {})
    lint = config.get("lint", {})
    git = config.get("git", {})
    if any(not isinstance(table, dict) for table in (search, states, lint, git)):
        raise ValueError("search, states, lint and git settings must be TOML tables")
    remote, branch = git.get("remote"), git.get("branch")
    if git and any(not isinstance(value, str) or not value.strip() for value in (remote, branch)):
        raise ValueError("git.remote and git.branch must both be nonempty strings")
    warnings = []
    for table, namespace, known in (
        (config, "", {"vault_uuid", "schema_version", "search", "states", "lint", "git"}),
        (search, "search.", {"exclude", "allow", "kinds", "require_state", "title_weight", "body_weight"}),
        (states, "states.", {"aliases", "inactive"}),
        (git, "git.", {"remote", "branch"}),
        (lint, "lint.", {"disable", "provenance_kinds", "provenance_fields", "allowed_fields", "tags"}),
    ):
        warnings.extend(f"Unknown profile key: {namespace}{key}" for key in sorted(table.keys() - known))
    exclude = search.get("exclude", ())
    allow = search.get("allow", ())
    if isinstance(exclude, dict):
        warnings.extend(f"Unknown profile key: search.exclude.{key}" for key in sorted(exclude.keys() - {"prefixes", "allow"}))
        if "allow" in exclude:
            if "allow" in search and exclude["allow"] != allow:
                warnings.append("Both allow settings differ. search.exclude.allow takes precedence.")
            allow = exclude["allow"]
        exclude = exclude.get("prefixes", ())
    user_aliases = states.get("aliases", {})
    if not isinstance(user_aliases, dict):
        raise ValueError("states.aliases must be a TOML table")
    aliases = {**STATE_ALIASES, **user_aliases}
    inactive = frozenset(INACTIVE_STATES | {state.casefold() for state in _strings(states.get("inactive", ()), "states.inactive")})
    if "active" in inactive:
        raise ValueError("states.inactive cannot include active")
    canonical = inactive | {"active", "review_due"}
    if any(not isinstance(value, str) or value not in canonical for value in aliases.values()):
        raise ValueError("states.aliases values must name a supported canonical state")
    weights = [search.get(key, 1.0) for key in ("title_weight", "body_weight")]
    if any(type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 100 for value in weights):
        raise ValueError("title_weight and body_weight must be greater than 0 and at most 100")
    require_state = search.get("require_state", False)
    if type(require_state) is not bool:
        raise ValueError("search.require_state must be a boolean")
    disabled = frozenset(_strings(lint.get("disable", ()), "lint.disable"))
    from .lint import RULE_IDS

    warnings.extend(f"Unknown lint rule: {rule}" for rule in sorted(disabled - RULE_IDS))
    return Profile(
        warnings=tuple(warnings), git_remote=remote, git_branch=branch, require_state=require_state,
        provenance_kinds=_strings(lint.get("provenance_kinds", ()), "lint.provenance_kinds"),
        exclude=tuple(map(prefix, _strings(exclude, "search.exclude.prefixes"))),
        allow=tuple(map(prefix, _strings(allow, "search.exclude.allow"))),
        kinds=_strings(search.get("kinds", ()), "search.kinds"),
        inactive=inactive, aliases={key.casefold(): value for key, value in aliases.items()},
        disabled_rules=disabled,
        provenance_fields=_strings(lint.get("provenance_fields", ("source", "review_by")), "lint.provenance_fields"),
        allowed_fields=_strings(lint.get("allowed_fields", ()), "lint.allowed_fields"),
        tag_vocabulary=_strings(lint["tags"], "lint.tags") if "tags" in lint else None,
        title_weight=weights[0], body_weight=weights[1],
    )


def values(value, name: str) -> tuple[str, ...]:
    return _strings([value] if isinstance(value, str) else (() if value is None else value), name)
