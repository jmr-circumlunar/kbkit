# kbkit

面向 AI Agent 的通用本地 Markdown 知识库基础设施组件套件。

kbkit 为 Markdown 文件知识库提供块级检索、读取、写入、图谱、治理、版本和自动化能力。Obsidian、VS Code、Typora 等第三方工具负责预览和人工编辑。

**kbkit 不提供 Web Viewer、Web UI、Markdown 渲染器或编辑器。**

项目采用 Apache-2.0 开源许可。用户可以直接从 Git 仓库获取源码，并通过仓库内的 `skills/` 目录让 Agent 加载 onboarding、query、author、maintenance 和 file-ingest 能力。

> **项目状态：E8 独立验收准备阶段。** E1 至 E7 的核心设计、实现和本地测试已经完成，真实 Agent 宿主互操作和正式发布验收仍待执行。

## 目标

- Markdown 原文是知识内容的唯一权威来源。
- SQLite FTS5 索引可重建，正文命中后回源读取。
- CLI、Python API、MCP 共用同一应用服务和数据契约。
- 写入具备预检、dry-run、冲突检测、事务恢复和审计。
- 核心运行时零第三方依赖，默认离线、本地运行。
- Git、模型服务和计划任务为可选能力。

## 工程基线

- 当前脚手架：Python 3.11+
- 包布局：src layout
- 核心运行时：Python 标准库
- 测试：unittest
- 首要开发/验收平台：Windows
- Linux：CI 兼容性烟测；正式支持承诺待定

## 文档

从 docs/README.md 开始，查看产品范围、需求、架构、模块地图、数据布局、接口、事务协议、测试用例、验收标准和路线。

原始设计输入保存在 docs/source/，新的方案和决策在 docs 下持续演进。

## Windows 开发环境

    git clone https://github.com/jmr-circumlunar/kbkit.git
    cd kbkit
    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -e .
    python -m unittest discover -s tests -v
    python -m kbkit doctor

当前 CLI 已支持 init、index、search、read、maintain、proposal、recover、MCP stdio 和 vault registry 操作。完整发布能力以 E8 验收报告为准。

## 从新 Agent 开始

让 Agent 从仓库地址克隆源码，按上面的命令创建虚拟环境并安装。Skill 位于仓库的 `skills/` 目录。Codex 可将五个 Skill 目录复制到使用项目的 `.agents/skills/`，再由宿主发现。其他宿主可按自己的方式加载这些目录。若宿主缺少 Skill 加载入口，可让 Agent 直接读取对应的 `SKILL.md`。

使用虚拟环境的 Python 执行 `python -m kbkit init <vault>`。Agent 通过 `python -m kbkit mcp stdio` 启动按会话运行的服务，环境变量 `KBKIT_VAULT` 指向初始化时选定的绝对路径。可用工具由 `tools/list` 返回。CLI 维护入口为 `python -m kbkit task run <vault>`。

检索会同步检测到的本地 Markdown 变更。手动索引或维护会逐文件核验内容哈希。代码仓库、外部文件和会话派生知识的自动刷新仍需接入来源跟踪，见 [信息新鲜度与漂移处理](docs/architecture/KNOWLEDGE_FRESHNESS.md)。
