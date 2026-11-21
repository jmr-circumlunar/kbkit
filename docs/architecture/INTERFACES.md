# 接口与配置

CLI 和 stdio MCP 共用应用服务。Agent 应以 `tools/list` 的输入 schema 为当前工具目录。CLI 命令和参数可用 `kbc --help` 或 `kbc search --help` 查看。Python 包公开导出 `__version__`，应用服务是内部实现接口。

## CLI

| 用途 | 命令示例 |
| --- | --- |
| 环境和库 | `kbc doctor --vault <vault>`、`kbc init <vault>`、`kbc status <vault>` |
| 注册和选库 | `kbc add <vault>`、`kbc use <uuid>`、`kbc current` |
| 搜索和导航 | `kbc index <vault>`、`kbc search <vault> <query> --json`、`kbc read <vault> <note>`、`kbc outline <vault> <note>`、`kbc graph <vault>` |
| 治理和恢复 | `kbc lint <vault>`、`kbc maintain <vault>`、`kbc task run <vault>`、`kbc proposal list <vault>`、`kbc proposal approve <vault> <id>`、`kbc proposal reject <vault> <id>`、`kbc proposal apply <vault> <id>`、`kbc recover <vault>`、`kbc restore <vault> <entry-id>` |
| 复核和来源 | `kbc knowledge status <vault>`、`kbc knowledge review <vault> <note>`、`kbc knowledge history <vault> <note>`、`kbc knowledge bind-code <vault> <id> <repo> --ref <ref> --scope <dir>` |
| MCP | `kbc mcp stdio` |

## MCP

stdio 使用 UTF-8。服务协商 `2025-11-25` 或 `2025-06-18`，工具结果同时返回 JSON 文本和 `structuredContent`。工具执行失败时，`isError` 为 `true`，结构化结果含错误码、原因和处理建议。格式错误的 JSON-RPC 请求及未知工具返回协议层错误。

| 用途 | 工具 |
| --- | --- |
| 状态和索引 | `kb_status`、`kb_index` |
| 检索和阅读 | `kb_search`、`kb_read`、`kb_outline`、`kb_facet`、`kb_graph` |
| 维护 | `kb_maintain`、`kb_maintenance_report`、`kb_lint`、`kb_proposals`、`kb_proposal_apply` |
| 事务 | `kb_write_plan`、`kb_write_apply`、`kb_restore` |

### 检索与导航

- `kb_search` 支持 `query`、`path`、`kind`、`state`、`tags`、`symbols`、`exclude` 和 `include_inactive`。`path` 和 `kind` 多值为 OR，`tags` 和 `symbols` 多值为 AND。前缀按目录边界匹配。显式选定某个非活跃状态时，该状态可参与检索。符号过滤区分大小写。非法枚举通过 `KB_QUERY_ENUM_INVALID` 返回有效选项。
- 搜索默认 `limit=8`，最大 50。`max_chars` 默认 1200，`budget_chars` 可限制整页正文字符数。`select` 支持 `snippet`、`path`、`full`、`json`。`full` 从命中块开头取正文，仍受字符和字节预算限制。`total_candidates` 是应用过滤后、分页前的块数。
- 搜索命中提供 `path`、`block_id`、`heading_path`、`lines`、`line_start`、`line_end`、`vault_id`、`state`、`stale`、`score`。正文模式提供 `content`、`content_truncated` 和 `hit_line`。行号从 1 开始，两端均包含。`score` 为反向 BM25，越大越靠前。
- `kb_read` 按 `path` 读源文件，或提供 `heading`（如 `["设计", "边界"]`）、`block_id` 或 `lines`（如 `[12, 18]`）。凭 `block_id` 可省略路径。搜索返回的块 ID 绑定文件版本，源文件变化后重新检索获取 ID。大文件的整篇请求返回章节预览和建议行区间。显式范围过长时，以 `next_lines` 续读。单行超限时，`line_truncated` 和 `hint` 会说明如何读取。
- `kb_outline` 返回标题树及行区间。`kb_facet` 默认预览四个维度；按 `path`、`kind`、`state` 或 `tags` 单独查看完整分布。`kb_graph` 的 `collection` 支持 `edges`、`broken`、`nodes`、`backlinks`、`orphaned`。可用 `path` 将图限定到一篇笔记。

### 分页和维护

集合工具接受 `limit`、`offset`、`max_bytes`，返回 `total`、`truncated` 和可用时的 `next_offset`。按偏移量翻页时保持过滤条件一致。若一个条目超出预算，可以提高 `max_bytes` 或选择更短表示。

`kb_maintain` 运行一次维护并保存全量本地报告。使用 `run_id` 调用 `kb_maintenance_report` 翻页，无需重新运行维护。两者的 `collection` 可选 `findings` 或 `code_sync`。`kb_proposals` 只列出具有执行操作的提案。自动刷新代码绑定页的记录在 `code_sync`。

### 写入与恢复

`kb_write_plan` 和 `kb_write_apply` 接收 `operations`，支持 `create`、`append`、`move`、`rename`、`delete`、`set_prop`。`set_prop` 只支持已有 frontmatter 中可无歧义更新的标量字段。

- 提供 `path` 或 `selector`，二选一。`append` 用 `{"path":"note.md","heading_path":["设计","边界"]}` 追加到该章节末尾，用 `{"block_id":"note.md:1"}` 追加到该索引块末尾，用 `{"path":"note.md","line_range":[12,18]}` 插到第 18 行后。无匹配或章节重名时停止。
- 预览提供 `plan_hash`、各项 `before_hash`、位置、有限的前后文和差异。把 `plan_hash` 提交给 `kb_write_apply` 可拒绝预览后的变更。成功返回 `positions`，并通过 `state` 区分 `applied` 和 `divergent`；中断的写入可能留下 `pending` 日志，通过 `kbc recover <vault>` 检查。
- 删除成功后源文件消失，返回 `trash` 中的 `entry_id`，可用 `kb_restore` 恢复。移动和改名后源文件消失。`index_dirty` 指出 Markdown 事务结果与索引刷新结果需要分别检查。

## Vault profile

初始化命令会打印 `profile.toml` 位置。下面是可选配置示例，保留原有 `vault_uuid` 和 `schema_version`。

```toml
[search]
kinds = ["现状", "方案", "决策"]
title_weight = 1.5
body_weight = 1.0

[search.exclude]
prefixes = ["01-工作台/暂缓", "日记"]
allow = ["01-工作台/暂缓/组件设计"]

[states]
inactive = ["暂停复核"]

[states.aliases]
"待复核" = "unreviewed"

[lint]
disable = []
provenance_fields = ["source", "review_by", "evidence"]
allowed_fields = ["product", "project"]
```

`lint.tags` 可选，用于限制标签词表。未知字段、状态和标签按库汇总。未识别生命周期默认从搜索中排除，`kb_status` 会报告原始取值。修改搜索权重、路径排除或状态映射无需重建索引。

默认元数据保存在库的 `.kbkit/`。在新库初始化之前，可将 `KBKIT_HOME` 指向库外的绝对路径，CLI、MCP 宿主和定时任务应使用同一设置。目录按库的位置分配。`KBKIT_INDEX_DIR` 可单独指定索引位置。已有库切换外置位置前先保留原元数据备份。

<!-- kbkit-contract input kb_search query path kind state tags symbols exclude limit offset max_chars max_bytes -->
<!-- kbkit-contract output kb_search hits total_candidates vault_id path block_id heading_path lines line_start line_end score stale hit_line -->
<!-- kbkit-contract output kb_status initialized indexed_blocks excluded_paths source_state_counts unknown_state_counts -->
<!-- kbkit-contract output kb_write_plan plan_hash before_hash preview position -->
<!-- kbkit-contract output kb_write_apply positions trash entry_id index_dirty -->
<!-- kbkit-contract state kb_write_apply applied pending divergent -->
<!-- kbkit-contract error code message severity hint retryable details -->
