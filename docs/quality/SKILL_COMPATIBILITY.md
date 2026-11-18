# Skill 兼容矩阵

Skill 在 `metadata` 中使用 `kbkit-api-version: v1` 标记接口版本。宿主加载 Skill 后可读取该版本，并通过 MCP `initialize` 获取服务版本。

| Skill | API 版本 | 需要 MCP | 状态 |
|---|---|---|---|
| kb-onboard | v1 | 是 | 仓库资源已验证 |
| kb-query | v1 | 是 | 仓库资源已验证 |
| kb-author | v1 | 是 | 仓库资源已验证 |
| kb-maintain | v1 | 是 | 仓库资源已验证 |
| kb-ingest | v1 | 是 | 仓库资源已验证 |

| 宿主与工具 | 已验证 | 待验证 |
|---|---|---|
| Codex Desktop，候选 `db17e7a` | 原生发现五个项目 Skill，连接 stdio 并调用核心 MCP 工具 | 模型主动调用 Skill、持久调度 |
| Claude Code 2.1.177，候选 `74ccca2` | 五个 Skill 目录部署至临时项目。宿主 `mcp list` 对 stdio 返回 `Connected` | Skill 注册及调用、模型驱动工具调用、持久调度 |
| 官方 Python MCP SDK 1.30.0，候选 `c6e7144` | 握手、ping、发现和调用工具、结构化结果 | Agent 宿主层 |
| Workbuddy | 待验证 | Skill、MCP、持久调度 |

Claude Code 的项目 Skill 位于 `.claude/skills/`。通过其 MCP 配置指定虚拟环境的 Python，参数为 `["-m", "kbkit", "mcp", "stdio"]`，环境变量 `KBKIT_VAULT` 指向已初始化 vault。`mcp list` 返回 `Connected` 时可记录连接通过。Skill 加载另需宿主报告或实际调用证据。参见 [Claude Code 项目 Skill](https://code.claude.com/docs/en/skills)。
