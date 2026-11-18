# E8 独立验收当前报告

评审日期：2026-11-17
Python：3.13.9
SQLite：3.51.0
平台：Windows

## 判定

当前为 **有条件未通过**。核心离线能力、数据搬运、Markdown 兼容、事务协议、Git 可选能力和本地分发已有证据。Agent 宿主互操作、完整 MCP 客户端验证、断电级耐久性和发布 artifact 仍待完成。

2026-11-18 的空白 Agent 公开分发验收在初始化失败。远端默认分支为 `6997e5b6d7e0b04e80f9eccb8e3091b77458ab9c`，仅有 `doctor`。本页其余本地证据对应开发工作区。见 [功能模拟验证报告](FUNCTIONAL_SIMULATION_REPORT.md)。

## I1–I7

| 判据 | 当前状态 | 证据 |
|---|---|---|
| I1 不依赖宿主软件 | 通过本地范围 | 核心 CLI/Python 测试不依赖 Obsidian 或特定宿主 |
| I2 不依赖网络 | 通过本地范围 | 核心实现使用标准库，模型和 Git 可选 |
| I3 零第三方运行时依赖 | 通过 | `pyproject.toml` dependencies 为空，干净 venv 安装通过 |
| I4 数据可搬运 | 部分通过 | vault 重建索引和路径安全测试通过，跨环境报告待补 |
| I5 格式通用 | 部分通过 | BOM、CRLF、Frontmatter round-trip 测试通过，第三方编辑器矩阵待补 |
| I6 分发即用 | 公开分发未通过 | 本地 clean venv 和临时 zipapp 通过，GitHub 新克隆无法初始化知识库 |
| I7 Agent 能力完整 | 未通过 | MCP schema 和本地 tools/call 已通过，真实第三方客户端互操作待验证 |

## 当前自动化证据

- 开发版测试总数：58，全部通过。
- E2 原型、E3 核心、E4 事务和恢复、E5 graph/lint/lifecycle、E6 Git/backup、E7 Skill/MCP 分发测试均通过。
- 本机 Windows 独立进程锁竞争测试通过。
- 临时干净 venv editable 安装通过。
- 临时 zipapp `--version` 和 `doctor` 通过。
- 可重复的 `scripts/build_zipapp.py` 已加入仓库。
- Skill 兼容矩阵已建立，Skill 文件统一使用 `kbkit-api-version: v1`。
- 本地真实 stdio MCP 子进程已通过 initialize、tools/list、tools/call 往返测试。

## 发布阻塞项

1. 真实 MCP 客户端互操作矩阵。
2. Codex、Claude Code、Workbuddy 等 Agent 宿主中的 Skill 加载记录。
3. 正式 tag 和 zipapp artifact。
4. 第三方 Markdown 编辑器兼容矩阵。
5. 断电级 durability 的明确证据或正式排除声明。
