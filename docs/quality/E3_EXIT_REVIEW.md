# E3 退出评审

## 当前结论

E3 核心链路已通过本地功能测试，允许进入 E4 的安全写入实现。E3 的退出范围覆盖初始化、vault 注册、Markdown 读取、索引、检索、维护任务、事件记录、proposal 和基础 MCP 服务。

## 已验证

- `init → index → search → read` 端到端链路。
- vault `add/use/current` 注册和切换。
- 内容 hash 变化、删除和同内容移动识别。
- `task run` 和 `maintain` 记录 TaskRun。
- ChangeEvent、Proposal、SessionArtifact 基础持久化。
- approved 低风险 append proposal 的 expected_hash 校验、redo journal 和冲突拒绝。
- ApplicationService 统一调用。
- MCP `kb_status`、`kb_index`、`kb_search`、`kb_read`、`kb_maintain`、`kb_proposals` 基础调用。
- 路径越界拒绝和会话 artifact consent 校验。

## 当前测试证据

本机 Python 3.13.9，SQLite 3.51.0，测试总数 19，全部通过。`kbc doctor` 报告 FTS5 可用。

## E4 前必须保留的边界

- 复杂多文件写入仍由 E4 实现。
- proposal 的 move、rename、delete 和 bulk 操作仍由 E4 实现。
- MCP schema、错误码和宿主互操作矩阵仍需 E7 完成。
- SessionArtifact 保留期清理和脱敏策略仍需继续实现。
