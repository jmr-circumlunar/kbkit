# kbkit

kbkit 是面向 AI Agent 的本地 Markdown 知识库组件。它提供块级检索、CLI、stdio MCP 和可导入的 Skill。知识库用普通 Markdown 保存，可用现有编辑器查看和编辑。索引可以重建，核心运行无需模型或第三方 Python 运行时依赖。

**发布状态**：0.1.0 候选，公开分发及宿主矩阵以 [E8 验收记录](docs/quality/E8_ACCEPTANCE.md) 为准。

## 从 Git 安装

准备 Python 3.11–3.13（含 SQLite FTS5）。Git 用于克隆源码，也用于可选的代码知识同步。以下是 Windows PowerShell 示例。

```powershell
git clone https://github.com/jmr-circumlunar/kbkit.git
cd kbkit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps .
.\.venv\Scripts\python.exe -m kbkit doctor
```

从候选分支或发布标签验证时，在创建虚拟环境前切换到验收指定的引用。需要记录实际克隆的完整 SHA。

## 交给 Agent 使用

1. 把 Git 仓库地址交给 Agent，请它按本页安装并询问知识库路径。Skill 在 `skills/`。Codex 可导入这五个目录到使用项目的 `.agents/skills/`，支持其他加载方式的宿主按其约定导入。
2. Agent 用虚拟环境的 Python 执行 `python -m kbkit init <vault>`。需要 MCP 时，宿主使用同一个 Python 执行 `python -m kbkit mcp stdio`，环境变量 `KBKIT_VAULT` 指向库的绝对路径。
3. 使用 `kb_write_plan` 和 `kb_write_apply` 创建第一篇笔记，再用 `kb_search` 和 `kb_read` 验证。手动维护执行 `python -m kbkit task run <vault>`。需要定时维护时，Agent 首次确认频率和范围，由对应宿主保存计划。日常执行直接写报告。

## 知识自维护

- 检索前同步检测到的 Markdown 变动。定时维护补做内容哈希核验、链接和 lint 检查。
- `knowledge review` 保存设计等知识页的已复核版本和显式依赖。关联依据变化、缺失或失效时，下游从默认检索退出。`knowledge history` 可读取先前复核版。
- `knowledge bind-code` 绑定授权的本地 Git ref 和路径。维护任务按提交自动更新对应的实现索引页，并保留来源 SHA、文件路径和 Python 顶层符号。代码正文保留在仓库。普通笔记的结论由 Agent 对照变更后更新并复核。

操作示例与边界见 [知识治理使用指南](docs/architecture/KNOWLEDGE_FRESHNESS.md)。功能范围和验收见 [文档索引](docs/README.md) 与 [变更记录](CHANGELOG.md)。项目采用 [Apache-2.0](LICENSE) 许可。
