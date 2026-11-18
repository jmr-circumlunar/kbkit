# 实施路线与阶段门禁

## 当前状态

- E0 研发仓库骨架：远程已建立；本地 Windows 环境未验收。
- E1 规划与架构契约：有条件通过。
- E2 高风险技术原型：通过原型门禁，允许进入 E3。
- E3 最小核心：已开始实现，init/index/search/read/task、vault registry、application service、基础 MCP tools 和低风险 proposal 应用已有可运行链路。
- E3 退出评审：本地功能门禁已通过，准备进入 E4 安全写入。
- E4 安全写入：已实现 append dry-run、多文件计划、expected_hash 和基础 journal，故障恢复矩阵尚未完成。
- E5 知识结构与治理：已开始实现 wikilink graph、断链检测和基础 lint。
- E5 退出评审：确定性 graph、lint、lifecycle 和 proposal 风险分级已通过本地测试，准备进入 E6。
- E6 自动化和版本：已实现可选 Git status/commit、ZIP backup/restore/verify、TaskRun 报告和 Agent 调度配置记录。
- E6 退出评审进展：任务成功/失败报告、备份恢复和 Git 可选能力已通过本地测试，准备进入 E7。
- E7 Agent 接口与分发：已开始实现 Skill 资源发现和 MCP tools/list 正式 inputSchema。
- E7 分发验证：干净 venv editable 安装和临时 zipapp 启动已通过，宿主互操作仍待验证。
- E8 独立验收：已建立当前报告，判定为有条件未通过，等待 Agent 宿主互操作和正式发布证据。
- 原始 M0：有用户提供的性能报告，复现材料尚未入库。

## 先行工程阶段

| 阶段 | 目标 | 交付物 | 退出条件 |
|---|---|---|---|
| E0 | 研发仓库初始化 | README、Python 包骨架、CI、开发规范 | 远程结构可读取；Windows 本地安装测试通过 |
| E1 | 方案、边界和契约 | 范围、需求、架构、模块图、数据布局、接口、ADR、测试用例 | P0 决策冻结；需求到测试可追踪 |
| E2 | 高风险技术原型 | Windows 文件锁/事务、Markdown round-trip、FTS5、MCP 互操作原型 | 原型测试与风险结论通过评审 |
| E3 | 最小可用核心 | init、vault、mdio、index、search、read、change events、task run、proposal 基础模型 | 核心端到端与自维护扫描基线通过 |
| E4 | 安全写入 | selector、operation、diff、journal、recovery | 7 个故障注入点通过 |
| E5 | 知识结构与治理 | graph、lint、lifecycle、provenance、proposal | 规则和状态机测试通过 |
| E6 | 自动化和版本 | task、Git、备份/恢复、质量评测 | 自动化无静默失败；Git 可选 |
| E7 | Agent 接口与分发 | MCP、Skill、Git、pip、zipapp | 客户端互操作、Skill 加载和干净环境发布验收 |
| E8 | 独立验收 | I1–I7（及确认后的 I8）完整报告 | 发布门禁全部满足 |

## 与原始 M0–M8 的关系

原始路线保留为产品能力顺序：
- M0 可行性验证；
- M1 初始化底座；
- M2 写入、索引同步和事务；
- M3 查询；
- M4 治理；
- M5 质量闭环；
- M6 自动化；
- M7 版本、接口和分发；
- M8 独立验收。

E0–E8 是研发工程先行阶段，不替代 M0–M8。特别是重点九必须伴随 M2 设计和实现，不能等到最后补。

## 规划纪律

- E1 结束前不铺开 36 个模块的空目录或空类。
- 每个里程碑有需求、设计、测试、验收和回滚方案。
- 每个持久格式/API 变更必须有 ADR 或迁移说明。
- 高风险假设先做小型原型，不以架构图替代证据。
- M0 报告复现前标为历史基线，不把它当作本仓库已通过 CI 的结果。

E1 退出评审记录见 `docs/quality/E1_EXIT_REVIEW.md`。E2 退出评审记录见 `docs/quality/E2_EXIT_REVIEW.md`。E3 退出评审记录见 `docs/quality/E3_EXIT_REVIEW.md`。E5 退出评审记录见 `docs/quality/E5_EXIT_REVIEW.md`。E1 的代码规范见 `docs/engineering/CODE_STYLE.md`。
