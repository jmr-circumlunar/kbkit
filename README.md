# kbkit

面向 AI Agent 的通用本地知识库管理组件套件。

kbkit 面向 Markdown 文件知识库，提供可独立使用的检索、读取、写入、图谱、治理、版本与自动化能力。Obsidian、VS Code、Typora 等编辑器是可选查看器，不是运行依赖。

> **项目状态：工程底座初始化阶段。** 当前仓库只建立研发工程骨架，不代表核心功能已经实现或通过验收。

## 项目目标

- 以 Markdown 原文作为知识内容的权威来源。
- 以可重建索引提供块级检索，不把全文复制进索引。
- 通过统一核心 API 提供 CLI、Python API 与 Agent 接口。
- 让写入、索引同步、治理和版本管理具备可验证的一致性。
- 核心运行时尽量只使用 Python 标准库；可选适配器的依赖边界单独管理。
- 支持离线、本地运行和知识库目录迁移。

## 当前工程基线

- Python：3.11+
- 包布局：src layout
- 核心运行时依赖：暂不引入第三方包
- 测试：先使用标准库 unittest
- 一等验证平台：Windows、Linux
- 默认分支：main

这些是工程启动默认值；涉及 MCP 传输、索引存储位置、事务保证等架构决策，仍以 ADR 和专项设计评审为准。

## 快速开始

### 创建虚拟环境

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Linux：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### 运行检查

```bash
python -m unittest discover -s tests -v
python -m kbkit --version
```

安装后也可运行：

```bash
kbc --version
```

## 目录结构

```text
.
├── .github/workflows/   # CI
├── docs/                # 架构、工程约定、ADR 与验收标准
├── src/kbkit/           # 可分发的 Python 包
├── tests/               # 自动化测试
├── pyproject.toml       # 包与构建配置
├── CONTRIBUTING.md      # 开发与协作约定
└── README.md
```

## 设计原则

1. **原文优先**：Markdown 文件是真相源；索引、缓存等派生数据可重建。
2. **核心与适配器分离**：业务能力集中在核心服务层，CLI/MCP 等接口不重复实现业务逻辑。
3. **安全优先**：写入先定位、校验和预览；歧义、冲突和高风险操作必须停止或升级。
4. **可验证**：性能、检索质量、事务恢复、跨平台行为都以自动化测试和可复现实验验收。
5. **渐进建设**：先建立最小工程底座，再按已确认的模块契约实现，不预建空模块或伪造已完成能力。

## 文档入口

- [工程基线](docs/engineering/BASELINE.md)
- [设计评审待决事项](docs/architecture/OPEN_QUESTIONS.md)
- [贡献与开发约定](CONTRIBUTING.md)
