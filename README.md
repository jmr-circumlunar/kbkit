# kbkit

kbkit 是一个可从 Git 使用的本地 Markdown 知识库。仓库附带可读、可索引的示例库，以及 CLI、stdio MCP、Agent Skill 和备份与恢复。核心无需模型或第三方 Python 运行时依赖。

首个稳定版本为 [v1.0.0](https://github.com/jmr-circumlunar/kbkit/tree/v1.0.0)。也可从 `main` 安装当前开发版。准备 Python 3.11–3.13 和 SQLite FTS5。

## 复制一句话给 Agent

> 请从 https://github.com/jmr-circumlunar/kbkit 的 main 读取 `skills/kb-install/SKILL.md`，按它安装 kbkit，为当前项目接入知识库并验收；接入已有库时询问路径，启用定时维护前确认频率、时区和来源范围。

在 Windows、macOS 或 Linux 的执行环境中打开项目，再把这句话交给 Agent。iPhone 上可在 ChatGPT 的 Codex（或 Remote）里打开已配对的 Mac 或 Windows 项目，发送同一句话。组件、知识库和维护任务都在执行主机上。[Codex 手机端连接说明](https://learn.chatgpt.com/docs/remote-connections#before-you-set-up-mobile-access)

使用 Skills CLI 的项目也可运行下列命令，再让 Agent 执行 [kb-install](skills/kb-install/SKILL.md)。Claude Code 使用 `-a claude-code`。

```sh
npx skills add jmr-circumlunar/kbkit --skill kb-install -a codex -y
```

## 安装并打开示例库

macOS 或 Linux

```sh
git clone --branch v1.0.0 https://github.com/jmr-circumlunar/kbkit.git
cd kbkit
python3 -m venv .venv
./.venv/bin/python -m pip install --no-deps .
./.venv/bin/python -m kbkit setup
./.venv/bin/python -m kbkit search knowledge 知识库备份 --json
```

Windows PowerShell

```powershell
git clone --branch v1.0.0 https://github.com/jmr-circumlunar/kbkit.git
cd kbkit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps .
[Console]::OutputEncoding = [Text.Encoding]::UTF8
.\.venv\Scripts\python.exe -m kbkit setup
.\.venv\Scripts\python.exe -m kbkit search knowledge 知识库备份 --json
```

示例内容在 [knowledge](knowledge/00-索引/工作空间上下文.md)。可将该目录直接作为 Obsidian 仓库打开。安装到当前环境后，kbc 与 `python -m kbkit` 执行相同的命令。

## WorkBuddy

WorkBuddy 使用托管 Python 和本地 CLI。连接器打包、双源校验和手动更新流程见 [WorkBuddy 连接器](integrations/workbuddy/README.md)。

## 接入 Agent 或已有知识库

`kbc setup <vault> --project <project> --host codex` 会初始化并索引知识库，为指定项目生成 MCP、Skill、常驻查询规则和 SessionStart Hook。将宿主改成 claude 可配置 Claude Code。Agent 启动时可读取明确授权的一篇路由笔记，配置时用 `--context-note` 指定库内路径。示例库默认采用自己的路由笔记。需要手动挂接 MCP 时，执行 `kbc mcp stdio`，并设置 `KBKIT_VAULT` 为知识库绝对路径。

进入已配置的项目并开启新会话。Codex 读取 `AGENTS.md`，Claude Code 读取 `CLAUDE.md`。涉及项目方法、业务规则、模型、决策或历史时，按规则先调用 `kb_search`，再调用 `kb_read` 核对并引用原文。实现事实以当前代码为准。

升级已有项目时，重新运行 `kbc setup <vault> --project <project> --host codex`，Claude Code 使用对应的宿主参数。通过宿主的项目和 Hook 信任后，SessionStart 用 `additionalContext` 加入同一条查库规则，以及配置时授权的一篇路由笔记（最多 3000 字符）。工具调用顺序由 Agent 按项目规则执行。可以在新会话问「怎么备份知识库」，查看实际工具调用及来源。

## 使用和维护

- `kbc sync <vault>` 或 `kb_sync` 检查外部 Markdown 改动。受信任的会话启动 Hook 会执行一次本地同步。kbkit 自己的写入仍立即更新对应文件的索引。
- `kbc sync <vault> --git` 快进同步知识库自己的 Git 分支，然后刷新索引。首次配置远端和分支后，由用户或已授权的定时任务通过 Skill 触发。详细规则见 [同步与检索接口](docs/architecture/INTERFACES.md#同步与配置诊断)。
- `kbc search <vault> <query> --json` 读取现有索引。大文档可用 `kb_outline` 和 `kb_read` 定向读取。显式查默认排除区时，提供路径并启用历史范围。
- `kbc write plan <vault> <operations.json>` 预览写入，可用偏移继续读大计划。`kbc write apply <vault> <operations.json> --plan-hash <hash> --request-id <uuid>` 应用计划并保留可安全重试的回执。`kbc write status <vault> <uuid>` 查询结果。Agent 可调用 `kb_write_plan`、`kb_write_apply` 和 `kb_write_status`。
- `kbc task run <vault>` 手动维护。Agent 确认频率、时区、来源范围和机械修复权限后，在对应宿主创建可修改的任务。已授权的运行使用 `--auto-apply safe`，自动补齐末尾换行并记录结果。报告模式可用 `--auto-apply none`。
- `kbc backup create <vault> <archive>` 备份，`kbc backup verify <archive>` 校验，`kbc backup restore <archive> <destination>` 恢复到新目录或空目录。恢复件与原库并存时，给恢复件注册独立身份。
- 已启用外置元数据的知识库搬迁后，用 `kbc add <new> --identity moved --from <old>` 保留其身份。只复制正文时，用 `kbc add <copy> --identity copy` 创建独立的身份和元数据。

[接口与配置](docs/architecture/INTERFACES.md) · [知识治理](docs/architecture/KNOWLEDGE_FRESHNESS.md) · [变更记录](CHANGELOG.md) · [优化与复测结果](docs/quality/OPTIMIZATION_RESULTS.md) · [Apache-2.0 许可](LICENSE)
