# 数据模型与元数据契约（候选）

状态：提案。字段语义、默认值、是否必填必须在 E1 冻结；不得只根据字段名推断权限或可信度。

## 1. 核心实体

| 实体 | 关键字段 | 说明 |
|---|---|---|
| VaultProfile | vault_uuid、schema_version、name、direction、paradigm、exclude、allow、field_vocabulary | 库级配置；不保存绝对路径作为唯一身份 |
| Document | relative_path、file_hash、mtime、size、encoding、frontmatter_status | 对应一个 Markdown 文件 |
| Block | block_id、document_id、kind、heading_path、line_range、content_hash | 检索和写入定位单元 |
| IndexState | schema_version、indexed_hash、indexed_at、index_dirty、stale_reason | 派生索引状态 |
| SearchHit | path、block_id、locator、snippet、score、state、source、stale | 返回 Agent 的可追溯命中 |
| LinkEdge | source_block、target_ref、resolved_target、edge_type | 双链/嵌入/引用关系 |
| Provenance | source_ref、owner、created_at、review_by、confidence、extraction_type | 记录来源与复核信息 |
| OperationRequest | operation、selector、expected_hash、idempotency_key、dry_run、confirmation | 统一写入请求 |
| TransactionJournal | transaction_id、state、targets、before_hash、after_hash、staging_ref、created_at | 崩溃恢复记录 |
| Proposal | proposal_id、risk_level、reason、diff_ref、owner、due_at、status | 需要人工决策的治理提案 |
| TaskDefinition | task_id、schedule、action、enabled、last_run、next_run | 定时巡检/维护任务 |
| ChangeEvent | event_id、source_kind、source_ref、observed_at、before_hash、after_hash、cursor | 记录 vault、代码、会话和审核变化 |
| SessionArtifact | artifact_id、session_ref、captured_at、content_hash、retention、consent | 受控保存会话摘要或原始片段 |
| TaskRun | run_id、task_id、started_at、finished_at、status、input_cursor、report_ref | 自动化运行和失败审计 |

## 2. Frontmatter 字段候选字典

| 字段 | 语义 | 需要冻结的规则 |
|---|---|---|
| type | 内容类型/文档类型 | 受控词表还是自由文本；缺失如何处理 |
| kind | 业务/知识分类 | 与 type 是否重复；是否保留 |
| state | 生命周期状态 | 默认值、合法迁移、默认检索集合 |
| tags | 标签 | 大小写、层级、同义词和词表校验 |
| source | 来源 | URL、文件、会话或外部引用的结构 |
| owner | 责任人 | 人名/角色/团队标识及目录默认责任人 |
| review_by | 复核日期 | 时区、过期策略、提醒和 pinning 关系 |
| confidence | 可信度 | 数值、枚举或三档；如何解释和计算 |
| visibility | 检索可见性标签 | private/internal/public；不是 OS 访问控制 |

## 3. 生命周期候选状态

原始方案列出 draft → active → review_due → deprecated → archived。需补充：
- 允许的迁移边；
- 谁可以触发迁移；
- review_due 是否仍可默认检索；
- deprecated 是否只在显式查询返回；
- archived 是否永远从默认结果排除；
- 状态缺失或未知值如何处理。

## 4. Provenance 规则

- 来源应附着在具体断言/重要关系或内容块上，而不只是文件级。
- 提炼内容应标注为提炼/摘要，并链接回原文。
- 不能生成不存在的来源、责任人或置信度。
- 来源冲突时保留双方并标记 contested，禁止按 updated 时间静默覆盖。

## 5. 标识与版本

- vault_uuid 标识知识库实例。
- document_id/block_id 标识逻辑对象。
- relative_path/heading_path/line_range 是当前 locator，不是永久身份。
- content_hash 标识当前内容版本。
- index schema version 与 profile schema version 分开管理。
