# 需求—模块—测试追踪矩阵

状态：规划版。模块编号以候选 MODULE_MAP 为准；冻结模块清单后更新。

| 需求 | 主要模块 | 测试用例 |
|---|---|---|
| FR-001/002 初始化与注册 | path_policy、vault_registry、profile_manager、initializer_templates | INIT-001–010、FS-001–004 |
| FR-003 Markdown 解析 | file_store、md_parser、frontmatter | MD-001–006、MD-012 |
| FR-004 块身份 | block_parser | MD-007–009、WRITE-004、IDX-004 |
| FR-005/006 索引与同步 | change_detector、tokenizer、sqlite_backend、indexer_sync | IDX-001–010、PERF-001/002 |
| FR-007/008 检索与上下文 | query_parser、search_engine、ranker_filters、context_packer | SRCH-001–013、PERF-003–006 |
| FR-009 图谱导航 | link_parser、graph_engine、outline_catalog | MD-010/011、GRAPH-001–004 |
| FR-010/011 写入事务 | selector_engine、operation_engine、diff_planner、transaction_recovery | WRITE-001–013、TXN-01–07 |
| FR-012 溯源与生命周期 | provenance_manager、lifecycle_policy | LIFE-001–004 |
| FR-013 治理 | lint_engine、dedup_budget、proposal_scheduler | LINT-001/002、LIFE-004 |
| FR-014 Git | git_adapter | GIT-001–004 |
| FR-015 自动化 | proposal_scheduler、diagnostics | INIT-009、LINT、task 专项测试待补 |
| FR-016 接口一致性 | cli_adapter、mcp_adapter、application services | ENV、MCP-001–004、CLI/Python contract tests 待补 |
| FR-017 模型辅助 | model_adapter | SRCH-012/013、SEC-005 |
| FR-018 分发 | package/build config | PKG-001/002 |

## 追踪规则

- 每个 FR/NFR 至少有一个 P0/P1 测试。
- 每个 P0 测试必须映射到需求和里程碑。
- 每个实现模块必须列出对应需求、测试、数据持久化影响和索引重建影响。
- 测试用例变更需同步更新本表。
