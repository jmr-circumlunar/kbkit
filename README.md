# kbkit

面向 AI Agent 的通用本地 Markdown 知识库基础设施组件套件。

kbkit 为 Markdown 文件知识库提供块级检索、读取、写入、图谱、治理、版本和自动化能力。Obsidian、VS Code、Typora 等第三方工具负责预览和人工编辑。

**kbkit 不提供 Web Viewer、Web UI、Markdown 渲染器或编辑器。**

> **项目状态：规划与架构契约阶段。** 当前仓库已建立最小 Python 工程骨架和 CI；核心业务能力尚未实现，原始 M0 性能数据尚待复现。

## 目标

- Markdown 原文是知识内容的唯一权威来源。
- SQLite FTS5 索引可重建，正文命中后回源读取。
- CLI、Python API、MCP 共用同一应用服务和数据契约。
- 写入具备预检、dry-run、冲突检测、事务恢复和审计。
- 核心运行时零第三方依赖，默认离线、本地运行。
- Git、模型服务和计划任务为可选能力。

## 工程基线（待 ADR 最终冻结）

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

注意：当前 CLI 仅为工程引导占位，不代表 init/search/write 等产品能力已经实现。
