# kbkit 项目状态

更新日期：2026-11-17

## 当前结论

项目方向可行。E1 至 E7 的设计、核心实现和本地测试已完成，当前进入 E8 独立验收。

## 已确认

- 项目是面向 Agent 的通用本地 Markdown 知识库组件套件。
- Markdown 原文是正文唯一真相源；索引可重建。
- 不提供 Web Viewer、Web UI、Markdown 渲染器或编辑器；第三方工具负责预览和人工编辑。
- GitHub 仓库 jmr-circumlunar/kbkit 专门管理组件自身的源码、设计和测试。
- 用户未来的知识库 Git 与组件研发仓库分离。
- 当前本地研发环境为 Windows。

## 已完成

- 远程 main 分支建立 Python src-layout 最小工程骨架。
- 建立 README、CONTRIBUTING、CI、.gitignore、.gitattributes。
- 三份原始设计文档已归档到 docs/source。
- 建立产品范围、需求清单、总体架构、边界、候选模块地图、数据布局、数据模型、接口契约、Markdown 兼容、事务协议、安全模型。
- 建立测试策略、测试用例、性能评测、独立性验收和需求追踪。
- 建立 ADR-0001 至 ADR-0007。
- 冻结 Python 3.11–3.13 支持矩阵、核心零依赖原则、LOCALAPPDATA 索引位置、事务保证边界、Markdown round-trip 原则和 Windows 首发平台策略。
- 建立代码规范条约和 E1 退出评审记录。
- 明确组件定位为自成长知识库体系，冻结 vault、审核、代码和授权会话四类变化来源。安全动作和隔离生成页可由定时任务直接执行并留审计，高影响变化进入 proposal 和 Agent 处理。
- 移除未经用户确认的 MIT License 元数据。
- GitHub Actions 当前工程骨架 CI 通过：Windows/Linux × Python 3.11/3.12/3.13，共 6 个 job。

## E8 尚未完成

- 原始 M0 性能数据仍作为历史基线，尚未形成正式发布门禁。
- 真实 Agent 宿主和第三方 MCP 客户端互操作尚未验收。
- 第三方 Markdown 编辑器兼容矩阵尚未验收。
- 正式 release tag 和 artifact 尚未发布。
- 断电级 durability 尚未验证，当前按未承诺处理。

## 当前 E8 待办

1. Agent 宿主 Skill 加载和 MCP 互操作。
2. 正式 tag、zipapp artifact 和发布记录。
3. 第三方编辑器兼容性。
4. 断电级 durability 的证据或排除声明。

## 下一步

1. 按 `docs/quality/E8_RUNBOOK.md` 执行外部验收。
2. 将外部结果写入 E8 报告。
3. 根据结果决定发布或回到对应阶段修复。
