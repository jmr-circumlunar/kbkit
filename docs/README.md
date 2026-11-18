# kbkit 设计与工程文档

> 状态：规划基线（2026-11-17）。本目录记录产品边界、架构契约、测试标准、实施路线和决策记录。除标记为“已确认”的内容外，不应把提案当作已经冻结的实现要求。

## 阅读顺序

1. 产品范围与非目标：product/SCOPE.md
2. 需求清单：product/REQUIREMENTS.md
3. 总体架构：architecture/ARCHITECTURE.md
4. 职责边界：architecture/BOUNDARIES.md
5. 候选模块地图：architecture/MODULE_MAP.md
6. 数据与目录布局：architecture/DATA_LAYOUT.md
7. 接口契约：architecture/INTERFACES.md
8. Markdown 兼容策略：architecture/MARKDOWN_COMPATIBILITY.md
9. 写入与事务协议：architecture/TRANSACTION_PROTOCOL.md
10. 安全模型：architecture/SECURITY_MODEL.md
11. E1 决策登记：architecture/E1_DECISION_REGISTER.md
12. Agent 集成、Skill、服务与自动化：architecture/AGENT_INTEGRATION.md
13. 自成长知识库架构：architecture/SELF_GROWING_KB.md
14. 自动化配置契约：architecture/AUTOMATION_CONFIG.md
15. 测试策略与用例：quality/TEST_STRATEGY.md、quality/TEST_CASES.md
16. 性能与检索评测：quality/PERFORMANCE_AND_EVAL.md
17. 独立性验收：quality/ACCEPTANCE.md
18. E2 退出评审：quality/E2_EXIT_REVIEW.md
19. E3 退出评审：quality/E3_EXIT_REVIEW.md
20. E8 当前验收报告：quality/E8_ACCEPTANCE.md
21. Skill 兼容矩阵：quality/SKILL_COMPATIBILITY.md
22. E8 外部验收运行手册：quality/E8_RUNBOOK.md
23. 功能模拟验证报告：quality/FUNCTIONAL_SIMULATION_REPORT.md
24. 实施路线：implementation/ROADMAP.md
25. Windows 开发环境：implementation/WINDOWS_ENVIRONMENT.md
26. 证据与引用登记：research/EVIDENCE_REGISTER.md

## 状态标签

- 已确认：用户明确确认，或原始设计文档明确作为现行方案。
- 提案：本轮审查提出的推荐方案，尚待确认。
- 待决：存在多个合理选择，需原型、资料核验或用户决策。
- 已验证：有可复现测试、报告或一手资料支持；必须附验证记录。
- 历史基线：来自原始设计文档的既有数据或判断，尚未在本仓库复现。

## 项目原则

- 本仓库是 kbkit 组件本身的研发仓库，管理源代码、设计、测试、发布和版本记录。
- 用户未来创建的知识库是运行目标；其 Git 仓库与本仓库完全独立。
- Markdown 原文是用户知识内容的权威来源；索引、缓存和运行日志是派生数据。
- 不提供 Web Viewer、Web UI、Markdown 渲染器或编辑器；预览与人工编辑由第三方工具完成。
- 核心能力不依赖 Obsidian、Obsidian 插件或某个特定 MCP 宿主。
- 所有持久化格式、公开 API、事务语义和依赖例外必须先记录决策，再实现。

## 原始材料

原始设计文档快照保存在 source/。新设计文档对原始方案进行拆解、补充和风险标记，不覆盖原文。

## 当前阶段

E0 远程仓库骨架、本机 Python 3.13.9 验收、E1 至 E7 的本地实现和测试已经完成。当前处于 E8 独立验收，外部 Agent 宿主互操作、正式发布证据和断电级 durability 仍待完成。不得把本地测试结果描述为完整发布验收。


## 项目状态与测试资料

- 当前进展：PROJECT_STATUS.md
- 测试数据与 Fixture 规范：quality/TEST_FIXTURES.md
- 需求追踪矩阵：requirements/TRACEABILITY.md


### 数据模型与追踪

- 数据模型：architecture/DATA_MODEL.md
- 需求—模块—测试追踪：requirements/TRACEABILITY.md
- 代码规范与工程约束：engineering/CODE_STYLE.md
- E1 退出评审：quality/E1_EXIT_REVIEW.md
