# 功能模拟验证计划

目标是模拟一个新用户在空环境中获取仓库、加载 Skill、初始化 vault，并由 Agent 通过 MCP 使用组件。

## 环境隔离

- 测试目录使用临时目录。
- Python 使用临时 venv。
- `KBKIT_INDEX_DIR`、`KBKIT_REGISTRY_DIR`、`LOCALAPPDATA` 指向临时目录。
- 测试 vault、Git 仓库、backup 和 zipapp 均使用临时路径。
- 不删除当前工作区、用户 vault、用户 Git 配置或现有 registry。

## 阶段一，干净环境安装

```powershell
py -3.13 -m venv <temp>\\venv
<temp>\\venv\\Scripts\\python.exe -m pip install --no-deps -e .
<temp>\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
<temp>\\venv\\Scripts\\python.exe -m kbkit doctor
```

通过标准是安装成功、全部测试通过、FTS5 可用、运行时没有额外依赖。

## 阶段二，空 vault 用户流程

1. 创建空目录。
2. 执行 `kbc init <vault>`。
3. 创建 Markdown 文件和 Frontmatter。
4. 执行 `kbc index <vault>`。
5. 执行 `kbc search <vault> <query>`。
6. 执行 `kbc read <vault> <relative_path>`。
7. 执行 `kbc maintain <vault>`。
8. 检查 `.kbkit/profile.toml`、索引、state、reports 和 proposals。

通过标准是正文可读取、索引可重建、路径越界被拒绝、维护报告可生成。

## 阶段三，Agent Skill 和 MCP

- 发现 `skills/kb-onboard/SKILL.md`、`kb-query`、`kb-author`、`kb-maintain`、`kb-ingest`。
- 检查每个 Skill 的 `kbkit-api-version`。
- 设置 `KBKIT_VAULT` 指向临时 vault。
- 启动 `python -m kbkit mcp stdio`。
- 发送 `initialize`、`tools/list`、`tools/call`。
- 执行 `kb_status`、`kb_index`、`kb_search`、`kb_read`、`kb_maintain`。
- 执行 `kb_write_plan`，确认 dry-run 不修改文件。

通过标准是 stdout 只包含 JSON-RPC，工具数量为 8，schema 可解析，错误结构稳定。

## 阶段四，写入和恢复

- append dry-run 和 apply。
- expected_hash 冲突。
- 多文件事务。
- fault injection 和 recover。
- delete 到 trash 和 restore。
- backup、verify、restore。
- 临时 Git status、commit 和重新读取。

通过标准是冲突不覆盖，恢复幂等，正文和索引一致，backup 可恢复。

## 阶段五，结果记录

每轮记录以下字段：

- 测试时间和 commit SHA；
- Python、SQLite、OS 和架构；
- 临时目录位置；
- 命令和输入；
- 通过、失败、跳过；
- stdout、stderr 和报告路径；
- 发现的问题及严重度；
- 是否满足对应 E 阶段退出条件。
