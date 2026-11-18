# E8 独立验收当前报告

评审日期：2026-11-18
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

- 开发版测试数：60，全部通过。覆盖库内依赖失效、旧版恢复、绑定代码更新和人工编辑保护。
- Windows Python 3.12.14 和 3.13.9 本地套件通过。Python 3.11 与 Linux 仍由 CI 矩阵验收。
- E2 原型、E3 核心、E4 事务和恢复、E5 graph/lint/lifecycle、E6 Git/backup、E7 Skill/MCP 分发测试均通过。
- 本机 Windows 独立进程锁竞争测试通过。
- 临时干净 venv editable 安装通过。
- 临时 zipapp `--version` 和 `doctor` 通过。
- 可重复的 `scripts/build_zipapp.py` 已加入仓库。
- Skill 兼容矩阵已建立，Skill 文件统一使用 `kbkit-api-version: v1`。
- 本地真实 stdio MCP 子进程已通过 initialize、tools/list、tools/call 往返测试。

## 库内治理候选复验

空白 Agent 只使用本地 Git 克隆地址和公开使用说明完成验收。候选 `58cdb2f3cba23789bfb285b6a7c381bcb227fcfa` 在干净环境安装，60 项测试和 zipapp smoke 通过。Codex Desktop 原生发现 5 个 Skill 并连接 8 个 MCP 工具，同时验证了预检、首篇创建和外部编辑后的检索。

特征验收覆盖设计复核、旧版本回读、依赖过期和默认检索隔离。定时触发维护时，提交变更替换了唯一的实现索引页，依赖旧实现的手册变为 stale，人工修改过的生成页保持原样并报告冲突。

最终本地候选 `db17e7a2a87f794a64fefadf042e1d1ee3f7fc0c` 从独立 Git 克隆按发布 README 安装。Windows Python 3.13.9 下 60 项测试通过。Codex 原生发现五个 Skill，通过 MCP 验证首篇创建和编辑后的检索。设计历史、手册失效、代码定时刷新和生成页冲突保护使用空库复验。两次 zipapp 产物字节一致，SHA-256 为 `5940983208f55656c32f8921571955a108b77c6811857af445422c4ec0e6f039`，版本和 doctor 通过。

实际 Codex MCP 检索默认隐藏 stale 命中，显式包含时返回依赖变化原因。实际 MCP 维护在生成页冲突时返回 `partial` 并保留原文件。定时触发使用临时计时器调用 CLI，宿主持久计划和模型主动调用 Skill 仍属单独验收项。

公开地址验收仍未通过。候选保存在本地 `feat/knowledge-governance`。GitHub 仍返回 `6997e5b`，当前没有该候选分支或正式 `v0.1.0`。

## 发布阻塞项

1. 真实 MCP 客户端互操作矩阵。
2. Codex、Claude Code、Workbuddy 等 Agent 宿主中的 Skill 加载记录。
3. 正式 tag 和 zipapp artifact。
4. 第三方 Markdown 编辑器兼容矩阵。
5. 断电级 durability 的明确证据或正式排除声明。
