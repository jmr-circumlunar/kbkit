# Skill 兼容矩阵

Skill 文件使用 `kbkit-api-version: v1` 标记接口版本。宿主加载 Skill 后应先读取该版本，再通过 MCP `initialize` 获取服务版本。

| Skill | API 版本 | 需要 MCP | 状态 |
|---|---|---|---|
| kb-onboard | v1 | 是 | 仓库资源已验证 |
| kb-query | v1 | 是 | 仓库资源已验证 |
| kb-author | v1 | 是 | 仓库资源已验证 |
| kb-maintain | v1 | 是 | 仓库资源已验证 |
| kb-ingest | v1 | 是 | 仓库资源已验证 |

当前已验证 Skill 文件发现、版本读取和 MCP schema。Codex、Claude Code、Workbuddy 的宿主加载仍需分别执行互操作验收。
