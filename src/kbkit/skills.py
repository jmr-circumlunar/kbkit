"""Versioned Skill resource discovery."""

from __future__ import annotations

from pathlib import Path


def list_skills(package_root: Path | None = None) -> list[dict]:
    root = package_root or Path(__file__).resolve().parents[2] / "skills"
    result = []
    for path in sorted(root.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        name = path.parent.name
        api_version = next((line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("kbkit-api-version:")), "unknown")
        result.append({"name": name, "path": str(path), "content": text, "api_version": api_version})
    return result
