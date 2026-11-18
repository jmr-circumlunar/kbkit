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
