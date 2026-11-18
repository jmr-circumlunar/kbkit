"""E5 controlled frontmatter field validation."""

from __future__ import annotations

from .prototype_markdown import parse_document
from datetime import date


ALLOWED_FIELDS = {"type", "kind", "state", "tags", "source", "owner", "review_by", "confidence", "visibility"}
ALLOWED_VISIBILITY = {"private", "internal", "public"}
DEFAULT_TAGS = {"project", "decision", "reference", "procedure", "meeting", "task"}


def validate_frontmatter(raw: bytes) -> list[dict]:
    document = parse_document(raw)
    findings = []
    for key in document.fields:
        if key not in ALLOWED_FIELDS:
            findings.append({"rule": "FM-UNKNOWN", "severity": "low", "field": key, "message": "unknown frontmatter field"})
    if "state" in document.fields:
        from .lifecycle import validate_state

        if not validate_state(document.fields["state"]):
            findings.append({"rule": "FM-STATE", "severity": "medium", "field": "state", "message": "unknown lifecycle state"})
    if "visibility" in document.fields and document.fields["visibility"] not in ALLOWED_VISIBILITY:
        findings.append({"rule": "FM-VISIBILITY", "severity": "medium", "field": "visibility", "message": "invalid visibility"})
    if "confidence" in document.fields:
        try:
            confidence = float(document.fields["confidence"])
            if not 0 <= confidence <= 1:
                raise ValueError
        except ValueError:
            findings.append({"rule": "FM-CONFIDENCE", "severity": "medium", "field": "confidence", "message": "confidence must be between 0 and 1"})
    if "review_by" in document.fields:
        try:
            if date.fromisoformat(document.fields["review_by"]) < date.today():
                findings.append({"rule": "LIFE-003", "severity": "low", "field": "review_by", "message": "review date is overdue"})
        except ValueError:
            findings.append({"rule": "FM-REVIEW-BY", "severity": "medium", "field": "review_by", "message": "review_by must be ISO date"})
    if "source" in document.fields and not document.fields["source"].strip():
        findings.append({"rule": "FM-SOURCE", "severity": "medium", "field": "source", "message": "source cannot be empty"})
    if "owner" in document.fields and not document.fields["owner"].strip():
        findings.append({"rule": "FM-OWNER", "severity": "low", "field": "owner", "message": "owner cannot be empty"})
    if "tags" in document.fields:
        tags = {tag.strip() for tag in document.fields["tags"].strip("[]").split(",") if tag.strip()}
        for tag in tags - DEFAULT_TAGS:
            findings.append({"rule": "FM-TAG", "severity": "low", "field": "tags", "message": f"tag is outside vocabulary: {tag}"})
    return findings
