# kbkit

kbkit 是面向 AI Agent 的本地 Markdown 知识库组件。它提供块级检索、CLI、stdio MCP 和可加载的 Skill。Markdown 可继续用原来的编辑器维护，索引可重建，核心运行无需模型或第三方 Python 运行时依赖。

`main` 是开发和试用入口。项目尚未正式发版。

## 从 Git 安装

准备 Python 3.11–3.13（含 SQLite FTS5）。在 Windows PowerShell 中执行：

```powershell
git clone https://github.com/jmr-circumlunar/kbkit.git
cd kbkit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps .
[Console]::OutputEncoding = [Text.Encoding]::UTF8
.\.venv\Scripts\python.exe -m kbkit doctor
```

Linux 和 macOS 使用 `./.venv/bin/python` 作为虚拟环境的解释器。跨电脑复测时，用 `git rev-parse HEAD` 记录实际测试的提交。

## 交给 Agent 使用

1. 把仓库 URL 交给 Agent。由 Agent 克隆并安装，准备仓库 `skills/` 下的 Skill，询问现有知识库路径或确认新库路径。Codex 项目使用 `.agents/skills/`，Claude Code 项目使用 `.claude/skills/`。各宿主实测范围见 [Skill 兼容矩阵](docs/quality/SKILL_COMPATIBILITY.md)。
2. Agent 使用虚拟环境执行 `python -m kbkit init <vault>`。MCP 宿主使用同一解释器执行 `python -m kbkit mcp stdio`，环境变量 `KBKIT_VAULT` 指向库的绝对路径。
3. 用 `kb_write_plan` 预览，再用 `kb_write_apply` 创建第一篇笔记。将预览的 `plan_hash` 交回写入工具。用 `kb_search` 找到结果，再用 `kb_read` 按块或按章节核对。
4. 手动维护执行 `python -m kbkit task run <vault>`。如需定时维护，由 Agent 首次询问频率和授权范围，然后在对应宿主创建计划。用户后续在宿主修改计划，日常执行写入报告供回查。

## 使用现有知识库

- `kb_status` 会报告排除路径、源状态分布及未知状态。可在 `profile.toml` 中设置排除目录、白名单例外、类型和生命周期别名，现有笔记可以保留原位置和字段。配置样例见 [接口与配置](docs/architecture/INTERFACES.md)。
- 默认返回最多 8 个检索块。用 `kb_outline` 看大文件的标题树，用 `kb_read` 定向读取。CLI 可执行 `kbc search <vault> <query> --json` 获取结构化结果。
- `knowledge review` 保存已复核版本和显式依赖。依据发生漂移时，下游从默认检索退出；`knowledge history` 可取回历史版本。
- `knowledge bind-code` 绑定授权的本地 Git ref 和文件范围。维护自动刷新实现索引页，保留提交 SHA、路径和 Python 顶层符号。代码正文保留在仓库。普通知识页由 Agent 核验源证据后更新并复核。
- 移动已注册的库，执行 `kbc add <path> --identity moved` 保留身份。保留源库及副本时，用 `kbc add <path> --identity copy` 给副本分配身份。

详见 [知识治理使用指南](docs/architecture/KNOWLEDGE_FRESHNESS.md)、[变更记录](CHANGELOG.md)和 [Apache-2.0 许可](LICENSE)。
