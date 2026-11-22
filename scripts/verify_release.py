"""Verify shipped behavior from a clean Git clone without using a real vault."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory


def require(condition: bool, description: str) -> None:
    if not condition:
        raise ValueError(description)


def run(
    cwd: Path, arguments: list[str], env: dict[str, str], *, payload: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments, cwd=cwd, env=env, input=payload, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    if result.returncode:
        raise ValueError(f"{arguments[0]} exited {result.returncode}: {(result.stderr or result.stdout).strip()}")
    return result


def verify_offline_wheel(root: Path, clone: Path, python: str, env: dict[str, str]) -> None:
    wheels = root / "wheels"
    run(root, [python, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheels), str(clone)], env)
    (wheel,) = wheels.glob("kbkit-*.whl")
    home = root / "offline-env"
    run(root, [sys.executable, "-m", "venv", str(home)], env)
    offline_python = str(home / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    guard = """
import sys
def reject_network(event, args):
    if event in {'socket.connect', 'socket.sendto', 'socket.getaddrinfo', 'socket.gethostbyname'}:
        raise RuntimeError('network is disabled for the release probe')
sys.addaudithook(reject_network)
"""
    install = guard + """
import runpy
sys.argv[0] = 'pip'
runpy.run_module('pip', run_name='__main__')
"""
    run(root, [offline_python, "-c", install, "--isolated", "install", "--no-index", "--no-deps",
               "--disable-pip-version-check", str(wheel)], env)
    exercise = guard + """
from pathlib import Path
from kbkit.application import ApplicationService
from kbkit.onboarding import setup
from kbkit.skills import list_skills
vault = Path(sys.argv[1])
result = setup(vault, vault.parent / 'offline-project', 'codex', None)
if not result['indexed_blocks'] or "kb-install" not in {skill["name"] for skill in list_skills()}:
    raise RuntimeError('starter notes or bundled skills are missing')
app = ApplicationService(vault)
app.initialize()
result = app.apply_operations([
    {'operation': 'create', 'path': 'offline.md', 'content': '# Offline proof\\n\\nlocaltoken'}
])
if not result['consistency']['ok'] or not app.search('localtoken')['hits']:
    raise RuntimeError('offline write or search failed')
if 'localtoken' not in app.read('offline.md')['content'] or 'findings' not in app.lint():
    raise RuntimeError('offline read or lint failed')
"""
    run(root, [offline_python, "-c", exercise, str(root / "offline-vault")], env)


def verify(url: str, branch: str | None, expected_sha: str | None, evidence: dict) -> None:
    with TemporaryDirectory(prefix="kbkit-release-") as directory:
        root = Path(directory)
        clone, vault, repo = (root / name for name in ("clone", "vault", "code"))
        env = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "KBKIT_VAULT", "KBKIT_HOME"):
            env.pop(name, None)
        env.update({
            "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1", "GIT_TERMINAL_PROMPT": "0",
            "KBKIT_INDEX_DIR": str(root / "index"), "KBKIT_REGISTRY_DIR": str(root / "registry"),
            "LOCALAPPDATA": str(root / "localappdata"), "APPDATA": str(root / "appdata"),
        })
        clone_args = ["git", "clone", "--quiet"]
        if branch:
            clone_args += ["--branch", branch]
        run(root, [*clone_args, "--", url, str(clone)], env)
        sha = run(clone, ["git", "rev-parse", "HEAD"], env).stdout.strip()
        evidence["sha"] = sha
        require(expected_sha is None or sha == expected_sha, f"expected {expected_sha}, cloned {sha}")

        checks = evidence["checks"]
        checks["clone"] = "passed"
        run(root, [sys.executable, "-m", "venv", str(root / "venv")], env)
        python = str(root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        run(root, [python, "-m", "pip", "install", "--no-deps", str(clone)], env)

        def cli(*arguments: str) -> str:
            return run(root, [python, "-m", "kbkit", *arguments], env).stdout

        require("FTS5: available" in cli("doctor"), "doctor did not confirm FTS5")
        checks["clean_install"] = "passed"
        starter = clone / "knowledge"
        hosted = json.loads(cli("setup", str(starter), "--project", str(root / "agent-project"), "--host", "codex"))
        require(hosted["indexed_blocks"] > 0 and len(hosted["files"]) >= 8, "clone onboarding did not provision knowledge and skills")
        require(json.loads(cli("search", str(starter), "知识库备份", "--json"))["hits"], "starter knowledge is not searchable")
        ctx = json.loads(cli("context", str(starter), "--note", "00-索引/工作空间上下文.md"))
        require("工作空间上下文" in ctx["hookSpecificOutput"]["additionalContext"], "Chinese hook context is missing")
        archive = root / "starter.zip"
        cli("backup", "create", str(starter), str(archive))
        require(json.loads(cli("backup", "verify", str(archive)))["ok"], "starter backup did not verify")
        restored = root / "restored"
        cli("backup", "restore", str(archive), str(restored))
        require((restored / "00-索引" / "工作空间上下文.md").read_bytes() ==
                (starter / "00-索引" / "工作空间上下文.md").read_bytes(), "backup changed starter note bytes")
        checks["clone_onboarding_and_backup"] = "passed"
        cli("init", str(vault))
        checks["init"] = "passed"
        env["KBKIT_VAULT"] = str(vault)

        def mcp(method: str, **params) -> dict:
            request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            messages = [request]
            if method != "initialize":
                messages = [
                    {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                        "protocolVersion": "2025-11-25", "capabilities": {},
                        "clientInfo": {"name": "kbkit-release-check", "version": "1"},
                    }},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    request,
                ]
            payload = "\n".join(json.dumps(message, ensure_ascii=False) for message in messages) + "\n"
            result = run(root, [python, "-m", "kbkit", "mcp", "stdio"], env, payload=payload)
            require(not result.stderr, "MCP emitted stderr during a successful probe")
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            require([response["id"] for response in responses] == ([1] if method == "initialize" else [0, 1]),
                    "MCP returned unsolicited responses or omitted a response")
            return responses[-1]["result"]

        def call(name: str, **arguments) -> dict:
            result = mcp("tools/call", name=name, arguments=arguments)
            if "structuredContent" in result:
                return result["structuredContent"]
            return ast.literal_eval(result["content"][0]["text"])

        evidence["mcp_protocol"] = mcp("initialize")["protocolVersion"]
        require(mcp("ping") == {}, "MCP ping is not available")
        names = {tool["name"] for tool in mcp("tools/list")["tools"]}
        require({"kb_search", "kb_read", "kb_write_plan", "kb_write_apply", "kb_maintain"} <= names, "missing advertised tools")
        design = vault / "design.md"
        request = [{"operation": "create", "path": design.name, "content": "# Design\n\nbluefinch\n"}]
        require(call("kb_write_plan", operations=request)["dry_run"] and not design.exists(), "preview wrote the first note")
        require(call("kb_write_apply", operations=request)["consistency"]["ok"] and design.is_file(), "first note write failed")
        require(bool(call("kb_search", query="bluefinch")["hits"]), "new note was not searchable")
        checks["stdio_first_note"] = "passed"
        (vault / "中文.md").write_text("# 数据库连接池设计\n\nERR_TIMEOUT", encoding="utf-8")
        (vault / "旧版.md").write_text("---\nstate: archived\n---\n# 数据库连接池旧版", encoding="utf-8")
        (vault / "标识符.md").write_text("# ERR TIMEOUT", encoding="utf-8")
        for query in ("连接", "连接池", "ERR_TIMEOUT"):
            require({hit["path"] for hit in call("kb_search", query=query)["hits"]} == {"中文.md"},
                    f"unexpected retrieval results for {query}")
        checks["retrieval_golden"] = "passed"
        skills = {item.parent.name for item in (clone / "skills").glob("*/SKILL.md")}
        require({"kb-install", "kb-onboard", "kb-query", "kb-author", "kb-maintain", "kb-ingest"} <= skills, "missing Skill files")
        evidence["skill_files"] = sorted(skills)

        manual = vault / "manual.md"
        manual.write_text("# Manual\n\noldmanual\n", encoding="utf-8")
        cli("knowledge", "review", str(vault), design.name)
        cli("knowledge", "review", str(vault), manual.name, "--depends-on", design.name)
        design.write_text("# Design\n\nredfinch revised\n", encoding="utf-8")
        require(bool(call("kb_search", query="redfinch", include_inactive=True)["hits"]), "edit not refreshed")
        require(not call("kb_search", query="oldmanual")["hits"], "stale dependency remained in default results")
        require(call("kb_search", query="oldmanual", include_inactive=True)["hits"][0]["state"] == "stale", "stale state was not exposed")
        cli("knowledge", "review", str(vault), design.name)
        history = json.loads(cli("knowledge", "history", str(vault), design.name, "--revision", "1"))
        require("bluefinch" in history["content"], "reviewed history was lost")
        checks["knowledge_revisions"] = "passed"

        repo.mkdir()
        run(repo, ["git", "init", "--quiet", "-b", "main"], env)
        (repo / "src").mkdir()
        source = repo / "src" / "demo.py"

        def commit(symbol: str) -> None:
            source.write_text(f"def {symbol}():\n    return 'sourcebody'\n", encoding="utf-8")
            run(repo, ["git", "add", "--", "src/demo.py"], env)
            run(repo, ["git", "-c", "user.name=Release Fixture", "-c", "user.email=fixture@example.invalid",
                       "commit", "-qm", symbol], env)

        commit("oldentry")
        cli("knowledge", "bind-code", str(vault), "demo", str(repo), "--ref", "refs/heads/main", "--scope", "src")
        cli("task", "run", str(vault))
        code_page = vault / "_generated" / "code" / "demo.md"
        require("oldentry" in code_page.read_text(encoding="utf-8"), "initial code map missing")
        cli("knowledge", "review", str(vault), manual.name, "--depends-on", "_generated/code/demo.md")
        commit("newentry")
        report = call("kb_maintain", collection="code_sync")
        require(report["code_sync"][0]["status"] == "updated" and Path(report["report_path"]).is_file(), "scheduled maintenance report missing code update")
        code = code_page.read_text(encoding="utf-8")
        require("newentry" in code and "oldentry" not in code and "sourcebody" not in code, "code map did not replace old symbols or leaked source body")
        require(not call("kb_search", query="oldmanual")["hits"], "manual was not invalidated by code update")
        checks["committed_code_refresh"] = "passed"

        note = vault / "portability.md"
        note.write_text("# Portable\n\nseedalpha\n", encoding="utf-8")
        cli("index", str(vault))
        copied = root / "copy"
        shutil.copytree(vault, copied)
        target = copied / note.name
        original_stat = target.stat()
        target.write_text("# Portable\n\nseedbravo\n", encoding="utf-8")
        os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        require("seedbravo" in cli("search", str(copied), "seedbravo"), "copied vault used the original index")
        require(not cli("search", str(copied), "seedalpha"), "original content leaked into the copied index")
        cli("add", str(copied), "--identity", "copy")
        require("seedalpha" in cli("search", str(vault), "seedalpha"), "copy changed the original vault")
        checks["vault_copy_isolation"] = "passed"

        verify_offline_wheel(root, clone, python, env)
        checks["offline_wheel_and_core"] = "passed"

        tests = run(root, [python, "-m", "unittest", "discover", "-s", str(clone / "tests"), "-q"], env)
        checks["tests"] = (tests.stderr or tests.stdout).strip()
        packages = [root / "first.pyz", root / "second.pyz"]
        rebuild = root / "rebuild"
        run(root, ["git", "clone", "--no-local", "--quiet", "--no-checkout", str(clone), str(rebuild)], env)
        run(rebuild, ["git", "checkout", "--quiet", "--detach", sha], env)
        require(run(rebuild, ["git", "rev-parse", "HEAD"], env).stdout.strip() == sha, "rebuild checkout changed SHA")
        os.utime(rebuild / "src" / "kbkit" / "cli.py", (946684800, 946684800))
        for checkout, package in zip((clone, rebuild), packages, strict=True):
            run(root, [python, str(checkout / "scripts" / "build_zipapp.py"), str(package)], env)
        require(packages[0].read_bytes() == packages[1].read_bytes(), "zipapp differs between checkouts of the same SHA")
        run(root, [python, str(packages[0]), "--version"], env)
        require("FTS5: available" in run(root, [python, str(packages[0]), "doctor"], env).stdout, "zipapp doctor did not confirm FTS5")
        evidence["zipapp_sha256"] = hashlib.sha256(packages[0].read_bytes()).hexdigest()
        bundled = json.loads(run(root, [python, str(packages[0]), "setup", str(root / "zip-vault"),
                                       "--project", str(root / "zip-project"), "--host", "claude"], env).stdout)
        require(bundled["indexed_blocks"] > 0 and len(bundled["files"]) >= 8, "zipapp did not bundle starter or skills")
        require((root / "zip-project" / ".claude" / "skills" / "kb-install" / "SKILL.md").is_file(),
                "zipapp did not bundle kb-install")
        command = json.loads((root / "zip-project" / ".mcp.json").read_bytes())["mcpServers"]["kbkit"]
        require(command["args"][0] == str(packages[0].resolve()), "zipapp setup points to an installed module instead of itself")
        explicit_note = root / "zip-vault" / "routing.md"
        explicit_note.write_text("# Explicit route\n", encoding="utf-8")
        run(root, [python, str(packages[0]), "setup", str(root / "zip-vault"), "--project", str(root / "zip-project"),
                   "--host", "claude", "--context-note", explicit_note.name], env)
        hooks = json.loads((root / "zip-project" / ".claude" / "settings.json").read_bytes())["hooks"]["SessionStart"]
        require(len(hooks) == 1, "zipapp reconfiguration duplicated the SessionStart hook")
        checks["zipapp"] = "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public URL or an explicit local Git source.")
    parser.add_argument("--branch", help="Branch or tag to clone.")
    parser.add_argument("--expect-sha", help="Require the full tested commit SHA.")
    args = parser.parse_args()
    evidence = {"url": args.url, "branch": args.branch, "platform": platform.platform(),
                "python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "checks": {}}
    try:
        verify(args.url, args.branch, args.expect_sha, evidence)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        evidence.update(status="failed", error=str(exc))
    else:
        evidence["status"] = "passed"
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return int(evidence["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
