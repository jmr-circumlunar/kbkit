"""Reviewed Markdown revisions and dependency freshness."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from .storage import metadata_dir
from .profile import Profile, load_profile
from .prototype_markdown import parse_document
from .transaction import digest, write_atomic


class KnowledgeVault:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.manifest = metadata_dir(self.root) / "knowledge.json"
        self.data = json.loads(self.manifest.read_text(encoding="utf-8")) if self.manifest.exists() else {
            "version": 1, "pages": {}, "code": {},
        }
        if self.data.get("version") != 1:
            raise ValueError("unsupported knowledge manifest version")

    def save(self) -> None:
        write_atomic(self.manifest, json.dumps(self.data, ensure_ascii=False, indent=2).encode("utf-8"))

    def markdown_path(self, relative: str) -> str:
        path = Path(relative)
        if path.is_absolute() or path.anchor or ".." in path.parts or path.suffix.lower() != ".md":
            raise ValueError("use a vault-relative Markdown path")
        resolved = (self.root / path).resolve().relative_to(self.root)
        if resolved != path or {".git", ".kbkit"}.intersection(resolved.parts):
            raise ValueError("use a non-aliased Markdown path inside the vault")
        return resolved.as_posix()

    def _bytes(self, relative: str) -> bytes | None:
        try:
            return (self.root / self.markdown_path(relative)).read_bytes()
        except FileNotFoundError:
            return None

    def statuses(self, profile: Profile | None = None) -> dict[str, dict]:
        profile = profile or load_profile(self.root)
        pages = self.data["pages"]
        code = {entry["page"]: entry for entry in self.data["code"].values()}
        dependents: dict[str, list[str]] = defaultdict(list)
        for path, page in pages.items():
            for dependency in page["dependencies"]:
                dependents[dependency].append(path)
        current = {path: self._bytes(path) for path in pages.keys() | code.keys() | dependents.keys()}
        hashes = {path: digest(raw) for path, raw in current.items() if raw is not None}
        statuses: dict[str, dict] = {}
        for path, raw in current.items():
            if raw is None:
                statuses[path] = {"state": "missing", "reason": "page_missing"}
                continue
            state = parse_document(raw).fields.get("state", "active")
            canonical = profile.canonical_state(state)
            statuses[path] = {"state": canonical, "source_state": state, "reason": "frontmatter"} if canonical in profile.inactive else {"state": "active"}
        for path, page in pages.items():
            if statuses[path]["state"] == "active" and hashes[path] != page["hash"]:
                statuses[path] = {"state": "unreviewed", "reason": "page_changed"}
            for dependency, expected in page["dependencies"].items():
                if statuses[path]["state"] == "active" and hashes.get(dependency) != expected:
                    statuses[path] = {"state": "stale", "reason": "dependency_changed", "dependency": dependency}
        for path, entry in code.items():
            if hashes.get(path) != entry.get("page_hash") or entry.get("issue"):
                issue = entry.get("issue")
                statuses[path] = {"state": "unverified" if issue == "source_unavailable" else "conflicted",
                                  "reason": issue or "generated_page_changed"}
        queue = deque(path for path, status in statuses.items() if status["state"] in profile.inactive)
        while queue:
            dependency = queue.popleft()
            for path in dependents[dependency]:
                if statuses[path]["state"] == "active":
                    statuses[path] = {"state": "stale", "reason": "dependency_inactive", "dependency": dependency}
                    queue.append(path)
        return statuses

    def review(self, relative: str, dependencies: list[str] | None) -> dict:
        path = self.markdown_path(relative)
        if path in {source["page"] for source in self.data["code"].values()}:
            raise ValueError("generated code pages are refreshed by maintenance")
        pages = self.data["pages"]
        previous = pages.get(path, {})
        edges = sorted({self.markdown_path(dep) for dep in dependencies}) if dependencies is not None else list(previous.get("dependencies", {}))
        pending = list(edges)
        visited: set[str] = set()
        while pending:
            candidate = pending.pop()
            if candidate == path:
                raise ValueError("knowledge dependency cycle")
            if candidate not in visited:
                visited.add(candidate)
                pending.extend(pages.get(candidate, {}).get("dependencies", {}))
        profile = load_profile(self.root)
        statuses = self.statuses(profile)
        baselines = {}
        for dependency in edges:
            raw = self._bytes(dependency)
            if raw is None or statuses.get(dependency, {}).get("state") in profile.inactive or profile.canonical_state(parse_document(raw).fields.get("state", "active")) in profile.inactive:
                raise ValueError(f"review a current dependency first: {dependency}")
            baselines[dependency] = digest(raw)
        raw = self._bytes(path)
        if raw is None:
            raise ValueError(f"page does not exist: {path}")
        revision = {"hash": digest(raw), "dependencies": baselines}
        versions = previous.get("versions", [])
        if not versions or any(versions[-1][key] != value for key, value in revision.items()):
            archive = self.manifest.parent / "history" / f"{revision['hash']}.md"
            if not archive.exists():
                write_atomic(archive, raw)
            versions = [*versions, {**revision, "reviewed_at": datetime.now(timezone.utc).isoformat()}]
            pages[path] = {**revision, "versions": versions}
            self.save()
        return {"path": path, "hash": revision["hash"], "revision": len(versions)}

    def history(self, relative: str, revision: int | None = None) -> dict:
        path = self.markdown_path(relative)
        versions = self.data["pages"].get(path, {}).get("versions", [])
        if revision is None:
            return {"path": path, "versions": versions}
        if not 1 <= revision <= len(versions):
            raise ValueError("unknown knowledge revision")
        version = versions[revision - 1]
        raw = (self.manifest.parent / "history" / f"{version['hash']}.md").read_bytes()
        if digest(raw) != version["hash"]:
            raise ValueError("knowledge revision failed integrity check")
        return {"path": path, "revision": revision, **version, "content": raw.decode("utf-8-sig")}
