"""Resources shared by a source checkout, a wheel and the zipapp."""

from __future__ import annotations

from pathlib import Path
import sysconfig
from zipfile import Path as ZipPath


def resource_directory(name: str):
    archive = getattr(__loader__, "archive", None)
    if archive:
        return ZipPath(archive, f"share/kbkit/{name}/")
    source = Path(__file__).resolve().parents[2] / ("knowledge" if name == "starter" else name)
    marker = "00-索引" if name == "starter" else "kb-onboard"
    if (source / marker).is_dir():
        return source
    return Path(sysconfig.get_path("data")) / "share" / "kbkit" / name


def list_skills(package_root: Path | None = None) -> list[dict]:
    root = package_root or resource_directory("skills")
    if not root.is_dir():
        return []
    result = []
    for folder in sorted(root.iterdir(), key=lambda item: item.name):
        path = folder / "SKILL.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        header = text.split("---", 2)[1] if text.startswith("---") and text.count("---") > 1 else ""
        api_version = next((line.split(":", 1)[1].strip() for line in header.splitlines() if line.lstrip().startswith("kbkit-api-version:")), "unknown")
        result.append({"name": folder.name, "path": str(path), "content": text, "api_version": api_version})
    return result
