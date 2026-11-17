# 证据与引用登记

## 1. 证据等级

- V1 一手已核：官方文档、规范或官方仓库已逐项核对并记录 URL、版本/日期。
- V2 实测已验：有脚本、输入数据、环境、日志和可复现结果。
- V3 二手待核：社区文章、二手综述或未回溯的一手来源；不得单独支撑关键架构决策。
- H 历史基线：原始设计文档中的实测/结论，但复现工件尚未进入当前仓库。

## 2. 当前登记

| 主题 | 原始来源/结论 | 当前等级 | 后续动作 |
|---|---|---|---|
| SQLite FTS5 / unicode61 / trigram 限制 | 原始总述记录了 FTS5 和中文 bigram 选型 | H | 补官方 SQLite 文档链接与目标 SQLite 构建测试 |
| 中文 bigram 性能 | 10k 文档、95,765 块、31.7s 等 | H | 入库生成器、seed、数据说明、benchmark 脚本和原始日志 |
| 真实库性能 | 688 篇、9,475 块、7.4s | H | 脱敏或提供可公开复现的替代 fixture |
| 多文件事务 | Atomic Store、fs-transaction、Konnect、MemoryCustodian 等 | V3/H | 回溯官方实现/规范，重点验证 Windows 语义 |
| Agent 检索与上下文预算 | Haystack Europe、RAG for Agents 等 | V3 | 保存原始 URL、发布日期、关键原文和适用边界 |
| Hit@5/MRR 阈值 | 2026 RAG 资料提到 Hit@5 0.8 | V3 | 先建自己的 golden baseline，再确定门槛 |
| TTL/pinning | Copilot Memory 二手资料 | V3 | 查官方文档与 changelog |
| Markdown/YAML 兼容 | 原始设计提出自写 YAML 子集解析器 | 提案 | 明确语法并建立 round-trip fixtures |
| Windows 文件耐久性 | 原始设计要求 fsync/replace | 待验证 | Windows 原型、故障注入和官方 API 依据 |

## 3. 证据管理要求

每项影响核心设计的引用至少记录：
- 标题、作者/组织、URL；
- 发布/更新日期和访问日期；
- 一手或二手；
- 支持的具体结论；
- 不能支持的结论/适用限制；
- 是否有复现代码或测试；
- 对应 ADR、需求和测试 ID。

不能只记录“某文章说过”。V3 来源只能作为线索，关键决策必须补 V1 或 V2。
