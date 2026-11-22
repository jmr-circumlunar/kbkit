# kbkit

kbkit 是一个可从 Git 使用的本地 Markdown 知识库。仓库附带可读、可索引的示例库，以及 CLI、stdio MCP、Agent Skill 和备份与恢复。核心无需模型或第三方 Python 运行时依赖。

从 `main` 安装当前开发版。准备 Python 3.11–3.13 和 SQLite FTS5。

## 安装并打开示例库

macOS 或 Linux

```sh
git clone https://github.com/jmr-circumlunar/kbkit.git
cd kbkit
python3 -m venv .venv
./.venv/bin/python -m pip install --no-deps .
./.venv/bin/python -m kbkit setup
./.venv/bin/python -m kbkit search knowledge 知识库备份 --json
```

Windows PowerShell

```powershell
git clone https://github.com/jmr-circumlunar/kbkit.git
cd kbkit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps .
[Console]::OutputEncoding = [Text.Encoding]::UTF8
.\.venv\Scripts\python.exe -m kbkit setup
.\.venv\Scripts\python.exe -m kbkit search knowledge 知识库备份 --json
```

示例内容在 [knowledge](knowledge/00-索引/工作空间上下文.md)。可将该目录直接作为 Obsidian 仓库打开。安装到当前环境后，kbc 与 `python -m kbkit` 执行相同的命令。

## 接入 Agent 或已有知识库

`kbc setup <vault> --project <project> --host codex` 会初始化并索引知识库，为指定项目生成 MCP、Skill、常驻查询规则和 SessionStart Hook。将宿主改成 claude 可配置 Claude Code。Agent 启动时可读取明确授权的一篇路由笔记，配置时用 `--context-note` 指定库内路径。示例库默认采用自己的路由笔记。需要手动挂接 MCP 时，执行 `kbc mcp stdio`，并设置 `KBKIT_VAULT` 为知识库绝对路径。

进入已配置的项目并开启新会话。询问「怎么备份知识库」，可检查 Agent 是否先使用 `kb_search`，再使用 `kb_read` 验证来源。宿主自己处理项目和 Hook 信任。

## 使用和维护

- `kbc search <vault> <query> --json` 搜索知识。大文档可用 `kb_outline` 和 `kb_read` 定向读取。显式查默认排除区时，提供路径并启用历史范围。
- `kbc write plan <vault> <operations.json>` 预览写入。`kbc write apply <vault> <operations.json> --plan-hash <hash>` 应用同一个计划。Agent 对应调用 `kb_write_plan` 和 `kb_write_apply`。
- `kbc task run <vault>` 手动维护。需定期执行时，由使用者在对应 Agent 宿主保存时间和来源范围。定时运行写出报告供回查。
- `kbc backup create <vault> <archive>` 备份，`kbc backup verify <archive>` 校验，`kbc backup restore <archive> <destination>` 恢复到新目录或空目录。恢复件与原库并存时，给恢复件注册独立身份。
- 已启用外置元数据的知识库搬迁后，用 `kbc add <new> --identity moved --from <old>` 保留其身份。

[接口与配置](docs/architecture/INTERFACES.md) · [知识治理](docs/architecture/KNOWLEDGE_FRESHNESS.md) · [变更记录](CHANGELOG.md) · [优化与复测结果](docs/quality/OPTIMIZATION_RESULTS.md) · [Apache-2.0 许可](LICENSE)
