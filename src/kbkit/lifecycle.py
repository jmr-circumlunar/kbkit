"""E5 lifecycle state transitions."""

from __future__ import annotations

ALLOWED = {
    "draft": {"active", "archived"},
    "active": {"review_due", "deprecated", "archived"},
    "review_due": {"active", "deprecated", "archived"},
    "deprecated": {"archived", "active"},
    "archived": set(),
}


def validate_transition(current: str, target: str) -> bool:
    return target in ALLOWED.get(current, set())


def validate_state(value: str | None) -> bool:
    return value in ALLOWED
