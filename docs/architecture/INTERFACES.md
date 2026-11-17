# 对外接口契约

## 1. 统一应用服务

CLI、Python API、MCP 必须调用相同的应用服务。应用服务接收领域输入、返回结构化结果，不依赖终端输出或 MCP JSON-RPC 对象。

## 2. CLI 命令分组（候选）

- Vault：init、add、use、current、doctor、profile。
- Index：index build/status/stats/reindex/reset。
- Read/Search：search、read、outline、list、find、facet、graph。
- Write：new、set、append、edit、move、rename、rm、bulk、verify、diff。
- Governance：lint、fix、template。
- Version/Automation：git、task。
- Integration/Distribution：serve-mcp、export、version。

具体参数和返回码必须由接口 schema 单一真相源生成或校验，避免文档与实现漂移。

## 3. Python API（候选）

    from kbkit import Vault, Index, Search, Writer, Graph, Lint

公开 API 只暴露稳定的应用对象与类型；内部模块可重构。需要定义对象生命周期、资源关闭、同步/异步行为和异常类型。

## 4. MCP（候选）

原始要求：Agent 全量能力、工具不超过 8 个、参数 schema 单一真相源、结构化错误带 hint。

候选工具分组：
1. kb_search：搜索、分面和上下文预算。
2. kb_read：按文件或块读取。
3. kb_navigate：outline/list/find/graph。
4. kb_write：结构化写入和 bulk。
5. kb_inspect：verify/diff/doctor/index status。
6. kb_govern：lint/lifecycle/proposal。
7. kb_version：Git status/commit/log/snapshot。
8. kb_admin：vault/profile/task 管理。

这 8 个名称是提案，不是冻结的协议。需要确认 MCP 协议版本、首发 stdio 或 HTTP transport、通知/取消/超时和客户端兼容矩阵。

## 5. 统一结果结构

搜索命中至少包含：
- vault_id、relative_path；
- block_id、heading_path、line_start、line_end；
- title/snippet（snippet 有长度上限）；
- source_hash、indexed_hash 或可比较的 freshness 标记；
- state、visibility、source、owner、review_by、confidence（可用时）；
- score、score_breakdown、model_stage；
- stale、index_dirty 或 partial 等明确状态。

读取结果必须回源，不得仅返回索引中保存的旧正文。

## 6. 统一错误结构

建议字段：
- code：稳定机器可读错误码；
- message：人类可读原因；
- hint：下一步可执行建议；
- retryable：是否可重试；
- details：字段、路径、selector、冲突 hash 等安全细节；
- transaction_state：rolled_back / partially_applied / unknown / completed 等事务状态（仅写操作适用）。

## 7. 写入请求

- operation：create / set_prop / append / edit / move / rename / delete / bulk。
- selector：block_id、heading_path、line_range、property_key 等结构化选择器。
- expected_hash：乐观并发控制。
- idempotency_key：重复调用保护。
- dry_run：默认 true；返回计划与 diff。
- confirmation：对高风险操作要求显式确认。

selector 有零匹配、多匹配或语义歧义时必须停止，禁止默认取第一个结果。
