# kbkit 项目状态

更新日期：2026-11-17

## 当前结论

项目方向可行，当前工作重点从“马上开发功能”调整为“先冻结产品边界、数据契约、接口契约、事务保证和测试体系”。

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
- 移除未经用户确认的 MIT License 元数据。
- GitHub Actions 当前工程骨架 CI 通过：Windows/Linux × Python 3.11/3.12/3.13，共 6 个 job。

## 尚未完成

- 用户本机 Windows 环境尚未执行安装与验收。
- 原始 M0 性能数据尚未在本仓库复现。
- 原始详细 DESIGN.md、CAPABILITIES.md、FOCUS.md、SYNC.md 尚未取得并对照。
- 36 个模块仍是候选清单，需与原始编号/影响矩阵核对。
- P0 ADR 尚未全部从 Proposed 转为 Accepted。
- 核心业务功能尚未开始实现。

## 当前 P0 待决

1. Python 最低版本与正式平台支持范围。
2. 核心零第三方依赖的精确定义，以及 MCP 首发是否只支持 stdio。
3. block_id 稳定身份规则。
4. Frontmatter YAML 子集语法与写回策略。
5. 外置索引使用 %APPDATA% 还是 %LOCALAPPDATA%，profile 是否进入用户 Git。
6. Windows 多文件事务的进程崩溃、系统崩溃和断电保证边界。
7. 原始独立性判据 I8 是否遗漏。
8. License 与公开发布策略。

## 下一步

1. 对照补充的原始详细设计文件，校准模块清单、CLI 命令表和变更影响矩阵。
2. 评审 P0 ADR，确定哪些可以接受、哪些需要改。
3. 完成 Windows 技术原型：FTS5、Markdown round-trip、文件锁、ReplaceFileW/FlushFileBuffers、事务故障注入。
4. 冻结测试 fixture 和 golden set 结构。
5. 通过 E1 后再进入 E2/E3，不提前铺开空模块。
