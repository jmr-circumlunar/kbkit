# 模块地图（候选 V0.1）

状态：提案，尚未冻结。原始总述声明“36 个模块、9 层”，但本轮三份原始文件没有给出完整 36 个模块名称、编号和变更影响矩阵。本表是为规划而提出的候选拆分，不应误读为原文已有清单。

## 九层、三十六个候选模块

| 层 | 模块 | 职责 |
|---|---|---|
| L0 Core Contracts | errors | 统一错误码、错误分类和可执行 hint |
| L0 Core Contracts | domain_models | Vault、Document、Block、Operation、SearchHit 等领域模型 |
| L0 Core Contracts | config | 配置加载、校验、默认值和版本迁移 |
| L0 Core Contracts | diagnostics | doctor、运行时能力探测和诊断输出 |
| L1 Workspace | path_policy | 路径规范化、根目录约束和安全检查 |
| L1 Workspace | vault_registry | 多库注册、发现、current/use |
| L1 Workspace | profile_manager | 库 profile、目录范式、排除/白名单规则 |
| L1 Workspace | initializer_templates | 八步初始化向导、目录骨架和模板 |
| L2 Markdown IO | file_store | 文件读取、编码、换行、原子单文件写入 |
| L2 Markdown IO | md_parser | Markdown 结构解析与字节区间定位 |
| L2 Markdown IO | frontmatter | YAML 子集解析、字段校验和原样保留 |
| L2 Markdown IO | block_parser | 块切分、标题路径、块身份和行区间 |
| L3 Index | change_detector | mtime/size/hash/Git 变更检测 |
| L3 Index | tokenizer | 中文 bigram、ASCII 标识符和查询归一化 |
| L3 Index | sqlite_backend | SQLite FTS5 schema、事务和查询适配 |
| L3 Index | indexer_sync | 全量构建、单文件增量、删除和 stale 检测 |
| L4 Retrieval | query_parser | 查询语法、短词、标识符和过滤条件解析 |
| L4 Retrieval | search_engine | FTS 召回、结果契约和来源定位 |
| L4 Retrieval | ranker_filters | 字段/状态过滤与确定性规则排序 |
| L4 Retrieval | context_packer | token/字符预算、去重和上下文组装 |
| L5 Knowledge Structure | link_parser | wikilink、embed、别名、标题和 block ref |
| L5 Knowledge Structure | graph_engine | 正向/反向链接、缺链和图查询 |
| L5 Knowledge Structure | outline_catalog | 标题树、文件清单、标签和导航 |
| L5 Knowledge Structure | provenance_manager | 来源、引用、责任人和复核元数据 |
| L6 Writer | selector_engine | block id、标题路径、行区间和属性选择器 |
| L6 Writer | operation_engine | create/set_prop/append/edit/move/rename/delete/bulk |
| L6 Writer | diff_planner | 预检、影响面、dry-run、差异和写后断言 |
| L6 Writer | transaction_recovery | journal、staging、锁、应用和崩溃恢复 |
| L7 Governance | lint_engine | 12 条健康规则和报告 |
| L7 Governance | lifecycle_policy | 状态机、可见性过滤、TTL/pinning |
| L7 Governance | dedup_budget | 重复候选、增长预算和效率指标 |
| L7 Governance | proposal_scheduler | 提案箱、风险分级、任务调度和升级 |
| L8 Adapters | cli_adapter | kbc 命令行 |
| L8 Adapters | mcp_adapter | MCP 工具 schema、stdio/协议适配 |
| L8 Adapters | git_adapter | 用户 vault 的 Git 操作 |
| L8 Adapters | model_adapter | OpenAI 兼容 HTTP 重排/裁剪 |

## 依赖方向

Adapters → Application Services → Domain/Contracts ← Infrastructure Adapters。

上表中的九层是职责分组，不代表严格的运行时调用顺序。具体模块依赖图必须在接口契约冻结时补充，禁止模块间循环依赖。

## 变更影响与索引重建

原始总述称仅 7 个模块改动需要重建索引，并给出内部编号 M01/M05/M07/M09/M13/M14/M15，但没有提供这些编号到模块名的映射。本轮不擅自映射。

E1 必须为每个模块补充输入/输出契约、持久化数据影响、是否改变块切分/tokenize/索引 schema、重建范围、对外 API 影响和对应测试 ID。

## 冻结门槛

模块边界通过以下检查后才能冻结：单一职责明确、无循环依赖、数据所有权明确、失败语义明确、能独立测试、影响矩阵可解释。若原始详细 DESIGN.md/CAPABILITIES.md 提供了不同的 36 模块编号，应先对照再调整本表。
