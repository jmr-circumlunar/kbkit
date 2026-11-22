"""E5 controlled frontmatter field validation."""

from __future__ import annotations

from .prototype_markdown import parse_document
from .profile import Profile
from datetime import date


ALLOWED_FIELDS = {"type", "kind", "state", "tags", "source", "owner", "review_by", "confidence", "visibility"}
ALLOWED_VISIBILITY = {"private", "internal", "public"}
RULE_IDS = {"FM-UNKNOWN", "FM-STATE", "FM-VISIBILITY", "FM-CONFIDENCE", "LIFE-003", "FM-REVIEW-BY",
            "FM-SOURCE", "FM-OWNER", "FM-TAG"}
DEFAULT_TAGS = {"project", "decision", "reference", "procedure", "meeting", "task"}


def validate_frontmatter(raw: bytes, *, profile: Profile | None = None, document=None) -> list[dict]:
    configured = profile is not None
    profile = profile or Profile()
    document = document or parse_document(raw)
    findings = []
    for key in document.fields:
        if key not in ALLOWED_FIELDS and key not in profile.allowed_fields and key not in profile.provenance_fields:
            findings.append({"rule": "FM-UNKNOWN", "severity": "low", "field": key, "message": "unknown frontmatter field"})
    if "state" in document.fields:
        if profile.canonical_state(document.fields["state"]) == "unknown":
            findings.append({"rule": "FM-STATE", "severity": "medium", "field": "state", "message": "unknown lifecycle state", "value": document.fields["state"]})
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
    vocabulary = profile.tag_vocabulary if configured else DEFAULT_TAGS
    if vocabulary is not None and "tags" in document.fields:
        tags = set(document.lists.get("tags", (value.strip() for value in document.fields["tags"].split(",") if value.strip())))
        for tag in sorted(tags - set(vocabulary)):
            findings.append({"rule": "FM-TAG", "severity": "low", "field": "tags", "value": tag,
                             "message": f"tag is outside vocabulary: {tag}"})
    return findings
