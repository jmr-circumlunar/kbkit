"""Prepare a vault and project-local integrations for Agent hosts."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tomllib

from .application import ApplicationService
from .selector import SelectorError, markdown_path
from .skills import list_skills, resource_directory
from .transaction import write_atomic


ROUTING = """For the project's methods, business rules, models, decisions, and prior work, search the registered knowledge base first with kb_search. Use the project scope and current state, then verify the relevant passages with kb_read and cite their source. Use current code to verify implementation facts. Use kb_sync before searching if the user just edited Markdown externally or a source locator became stale. If the knowledge base is unavailable or has no useful evidence, say so and continue with the available sources."""
STARTER = "00-索引/工作空间上下文.md"
BEGIN = "<!-- kbkit: begin -->"
END = "<!-- kbkit: end -->"
PREVIOUS_STOCK_SKILLS = {
    "kb-query": {"3243527c2ac5507d14e71a171cc27b1d73868ff379b09c53785d1041b1447c5c"},
    "kb-install": {"6414a973fe61976aec4df5706038662738052fb29a0f6ab6792be90850569a89"},
    "kb-author": {"59abb9027b89b35ca9b683e47f136810a704dcf729b2b3ab6608ebf2fa47d3af"},
    "kb-maintain": {
        "780e5bc7d1f127571f511d6a2243c9aa9749a38b91c66ead4c477ccbe23d94f5",
        "7e94cd30611ea023c31e7f17c1e7cbd55f4deabc704cee51a4ef1eb551912512",
        "2d0ced3c80083f5456fb4a4e09c1b3674ab858bd8cfc2e110831d7ff77a0f4d2",
    },
}


def session_context(vault: Path, note: str | None = None, *, refresh: bool = False) -> dict:
    summary = ROUTING
    warnings = []
    if refresh:
        try:
            ApplicationService(vault).sync()
        except (OSError, ValueError, sqlite3.Error) as error:
            warnings.append(f"kbkit: local sync failed ({str(error)[:400]}). Run kb_sync after fixing it.")
    if note:
        try:
            page = markdown_path(vault.resolve(), note)
            content = page.read_text(encoding="utf-8-sig").strip()
            if not content or len(content) > 3000 or content.startswith('{"content"'):
                raise ValueError("the routing note must contain 1–3000 Markdown characters")
            summary += "\n\n" + content
        except (SelectorError, OSError, ValueError) as error:
            warnings.append(f"kbkit: workspace context could not be loaded ({str(error)[:400]})")
    result = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": summary}}
    if warnings:
        result["systemMessage"] = "\n".join(warnings)
    return result


def _routing_file(path: Path) -> str:
    previous = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    generated = f"{BEGIN}\n## Knowledge base\n\n{ROUTING}\n{END}"
    if BEGIN not in previous and END not in previous:
        return (previous.rstrip() + "\n\n" if previous.strip() else "") + generated + "\n"
    if previous.count(BEGIN) != 1 or previous.count(END) != 1 or previous.index(BEGIN) > previous.index(END):
        raise ValueError(f"incomplete kbkit guidance markers in {path}")
    start, end = previous.index(BEGIN), previous.index(END) + len(END)
    return previous[:start] + generated + previous[end:]


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _host_files(project: Path, vault: Path, host: str, note: str | None) -> dict[Path, bytes]:
    account = project / (".codex" if host == "codex" else ".claude")
    env = {name: os.environ[name] for name in ("KBKIT_HOME", "KBKIT_INDEX_DIR", "KBKIT_REGISTRY_DIR") if os.environ.get(name)}
    env["KBKIT_VAULT"] = str(vault)
    executable = str(Path(sys.executable).absolute())
    archive = getattr(__loader__, "archive", None)
    runtime = [str(Path(archive).resolve())] if archive else ["-m", "kbkit"]
    server = {"command": executable, "args": [*runtime, "mcp", "stdio"], "env": env}
    files = {}
    if host == "codex":
        settings = account / "config.toml"
        existing = settings.read_text(encoding="utf-8-sig") if settings.is_file() else ""
        stanza = tomllib.loads(existing).get("mcp_servers", {}).get("kbkit")
        if stanza is not None and any(stanza.get(key) != value for key, value in server.items()):
            raise ValueError(f"kbkit server already points to a different runtime in {settings}")
        if stanza is None:
            lines = [existing.rstrip(), "", "[mcp_servers.kbkit]",
                     f"command = {json.dumps(server['command'], ensure_ascii=False)}",
                     f"args = {json.dumps(server['args'])}", "", "[mcp_servers.kbkit.env]"]
            lines.extend(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in env.items())
            content = ("\n".join(lines).lstrip() + "\n").encode("utf-8")
            tomllib.loads(content.decode("utf-8"))
            files[settings] = content
        hooks_file = account / "hooks.json"
    else:
        settings = project / ".mcp.json"
        data = _load_json(settings)
        servers = data.setdefault("mcpServers", {})
        server["type"] = "stdio"
        current = servers.get("kbkit")
        if current is not None and any(current.get(key) != value for key, value in server.items()):
            raise ValueError(f"kbkit server already points to a different runtime in {settings}")
        servers.setdefault("kbkit", server)
        files[settings] = _json_bytes(data)
        hooks_file = account / "settings.json"

    hook = _load_json(hooks_file)
    groups = hook.setdefault("hooks", {}).setdefault("SessionStart", [])
    arguments = [executable, *runtime, "context", str(vault)]
    runtime_prefix = list(arguments)
    arguments.append("--session-start")
    hook_env = {key: value for key, value in env.items() if key != "KBKIT_VAULT"}
    if note:
        arguments += ["--note", note]
    if os.name == "nt":
        launcher = account / "kbkit-context.ps1"
        quoted = " ".join("'" + argument.replace("'", "''") + "'" for argument in arguments)
        variables = "".join(f"$env:{key} = '" + value.replace("'", "''") + "'\n" for key, value in hook_env.items())
        program = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + variables + "& " + quoted + "\nexit $LASTEXITCODE\n"
        files[launcher] = program.encode("utf-8-sig")
        command = subprocess.list2cmdline(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(launcher)])
    else:
        assignments = [f"{key}={value}" for key, value in hook_env.items()]
        command = shlex.join(["env", *assignments, *arguments] if assignments else arguments)

    def is_kbkit_hook(entry: dict) -> bool:
        previous = entry.get("command", "")
        if previous == command:
            return True
        if os.name == "nt":
            return False
        try:
            parts = shlex.split(previous)
        except ValueError:
            return False
        if parts and parts[0] == "env":
            parts = parts[1:]
            while parts and parts[0].partition("=")[0] in ("KBKIT_HOME", "KBKIT_INDEX_DIR", "KBKIT_REGISTRY_DIR"):
                parts = parts[1:]
        return parts[:len(runtime_prefix)] == runtime_prefix

    existing = next(((group, entry) for group in groups for entry in group.get("hooks", [])
                     if is_kbkit_hook(entry)), None)
    previous_matcher = "startup|resume|compact"
    matcher = "startup|resume|clear|compact" + ("|fork" if host == "codex" else "")
    if existing is None:
        groups.append({"matcher": matcher, "hooks": [{"type": "command", "command": command}]})
    else:
        group, entry = existing
        entry["command"] = command
        if host == "codex" and group["hooks"] == [entry] and group.get("matcher") == previous_matcher:
            group["matcher"] = matcher
    files[hooks_file] = _json_bytes(hook)
    guide = project / ("AGENTS.md" if host == "codex" else "CLAUDE.md")
    files[guide] = _routing_file(guide).encode("utf-8")
    skills_dir = project / (".agents" if host == "codex" else ".claude") / "skills"
    for skill in list_skills():
        target = skills_dir / skill["name"] / "SKILL.md"
        body = skill["content"].encode("utf-8")
        if target.is_file():
            current = target.read_bytes().replace(b"\r\n", b"\n")
            previous_versions = PREVIOUS_STOCK_SKILLS.get(skill["name"], ())
            if current != body.replace(b"\r\n", b"\n") and sha256(current).hexdigest() not in previous_versions:
                continue  # Preserve customized Skills.
        files[target] = body
    return files


def setup(vault: Path, project: Path, host: str, context_note: str | None) -> dict:
    vault, project = vault.resolve(), project.resolve()
    seed = not vault.exists() or (vault.is_dir() and not any(vault.iterdir()))
    if context_note:
        markdown_path(vault, context_note)
    elif seed:
        context_note = STARTER
    elif (vault / STARTER).is_file() and "[kbkit-starter]" in (vault / STARTER).read_text(encoding="utf-8-sig"):
        context_note = STARTER
    files = _host_files(project, vault, host, context_note) if host != "standalone" else {}
    for path in files:
        if project not in path.resolve().parents:
            raise ValueError(f"project configuration path escapes the requested project: {path}")
    app = ApplicationService(vault)
    initialized = app.initialize()
    if seed:
        starter = resource_directory("starter") / "00-索引"
        for source in starter.iterdir():
            if source.is_file() and source.name.endswith(".md"):
                target = vault / "00-索引" / source.name
                try:
                    write_atomic(target, source.read_bytes(), exclusive=True)
                except FileExistsError:
                    continue
    app.index()
    indexed_blocks = app.status(limit=1)["indexed_blocks"]
    for path, data in files.items():
        if not path.is_file() or path.read_bytes() != data:
            write_atomic(path, data)
    return {**initialized, "vault": str(vault), "host": host, "indexed_blocks": indexed_blocks,
            "files": [str(path) for path in files]}
