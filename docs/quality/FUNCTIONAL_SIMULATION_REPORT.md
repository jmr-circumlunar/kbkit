# 功能模拟验证报告

验证方式：独立子 agent 使用本地开发工作区源码，运行环境和测试数据使用临时目录。原始结果属于开发验证。
平台：Windows
Python：3.13.9

## 结果

- 原始本地快照的全量 unittest：55/55 通过。
- 临时 vault：init、index、search、read、maintain 全部成功。
- 临时 MCP stdio 子进程：initialize、tools/list、tools/call status/index/search 全部成功。
- 临时 zipapp：构建、`--version`、`doctor` 全部成功。
- 临时 Git：status、commit 成功。
- backup、verify、restore 成功。
- Skill 文件发现和 API 版本读取成功。

## GitHub 空白 Agent 复验

2026-11-18，另一个只收到公开 Git URL 和使用需求的 Agent 从 GitHub 克隆了提交 `6997e5b6d7e0b04e80f9eccb8e3091b77458ab9c`。在新建的 Python 3.13.9 venv 中安装成功，`doctor` 确认 FTS5 可用，3 项基础测试通过。`kbc init` 退出码为 2，CLI 仅提供 `doctor`。该提交缺少 Skill 文件和可运行的 MCP 服务。公开 Git 分发验收结果为未通过。

## 本地 Git 候选空白 Agent 验收

独立 Agent 通过 Git 克隆本地候选 `06dd3cb6c9029b9cb62e658a684b6ad10b07ed60`。Windows 新 venv 安装、57 项测试及 zipapp 通过。Codex Desktop 实际注册了放入临时项目 `.agents/skills/` 的五个 Skill，并通过 MCP 发现八个工具。文件夹保持为仓库原始 `skills/` 时，宿主原生发现数量为零。

首篇笔记按旧 Skill 的 `append` 流程创建失败。Agent 手工创建空文件后，完成了 MCP 预检、追加、检索、回源读取和维护报告验证。外部编辑后首次查询命中新词，旧词无结果。这个用例暴露了显式创建操作和安装指引的缺口。

修复后从本地 Git 重新克隆 `79d5808702cd641240b381071b01d68b9487142f`，使用全新虚拟环境和空库复验。58 项测试通过。Codex Desktop 原生注册五个 Skill 并通过 MCP 发现八个工具。按新版 `kb-author` 调用 `create`，预览保持文件不存在，应用后创建首篇笔记。检索、读取、编辑后刷新和维护报告落盘均通过。该提交保存在本地 `e8/acceptance-candidate` 分支。

当前 MCP 的检索命中仍只包含路径、块 ID 和内容，尚缺行定位、来源和有效性状态。协议成功响应中的文本仍使用 Python 字典表示。

## 发现并修复

CLI `init` 原先只创建 profile，不注册当前 vault，导致 `current` 可能返回旧路径。现已修复，CLI init 会自动注册并切换当前 vault。

维护报告原先用 `blocks` 表示本次变化块数，容易误解。现已同时输出：

- `blocks`，当前 vault 的总块数；
- `changed_blocks`，本次扫描实际更新的块数。

## 隔离策略

测试使用临时 vault、临时 registry、临时 index 目录、临时 Git 仓库和临时 zipapp。没有删除当前工作区、用户 vault 或现有 registry。

## 待外部验证

- Codex、Claude Code、Workbuddy 的真实宿主加载。
- 第三方 MCP 客户端互操作。
- 第三方 Markdown 编辑器矩阵。
- 断电级 durability。
