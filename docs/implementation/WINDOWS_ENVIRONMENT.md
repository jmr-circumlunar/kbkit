# Windows 本地研发环境

目标：在 Windows 本机建立可重复的 kbkit 开发环境。具体工作目录由维护者选择；下文以 C:\workspace\kbkit 为示例。

## 1. 前置工具

- Git for Windows；
- Python（最低版本待 ADR 冻结，当前工程脚手架要求 3.11+）；
- PowerShell；
- VS Code 或其他 Markdown/Python 编辑器（可选，不是运行依赖）。

## 2. 克隆仓库

    cd C:\workspace
    git clone https://github.com/jmr-circumlunar/kbkit.git
    cd .\kbkit

## 3. 建立虚拟环境

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -e .

如果 PowerShell 禁止激活脚本，可直接使用：

    .\.venv\Scripts\python.exe -m pip install -e .
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

## 4. 基础检查

    python --version
    python -c "import sqlite3; print(sqlite3.sqlite_version)"
    python -m kbkit --version
    python -m kbkit doctor
    python -m unittest discover -s tests -v
    git status --short

doctor 应检测 SQLite FTS5，而不是仅打印 SQLite 版本。

## 5. Git 工作约定（提案）

- main 保持可构建、可测试。
- 功能开发使用 feat/*，缺陷修复使用 fix/*，文档规划使用 docs/*。
- 通过 PR 或明确评审合并；每个架构决策保留 ADR。
- 提交信息使用 Conventional Commit 风格。
- Windows 工作区统一 UTF-8；仓库通过 .gitattributes 固定文本文件换行策略。

## 6. 本地验收状态

远程仓库文件已创建并复核；本机 Python/Git 安装、venv、单元测试和推送尚未由本会话执行。用户本机运行以上命令后，需把实际输出作为 E0 验收记录，不应预先标记通过。


## 7. 远程 CI 验证记录

2026-11-17，GitHub Actions 的当前工程骨架 CI 已完成并通过 6 个 job：
- Windows：Python 3.11、3.12、3.13；
- Ubuntu：Python 3.11、3.12、3.13。

运行记录：https://github.com/jmr-circumlunar/kbkit/actions/runs/44033244379

这只验证当前占位包、基础单元测试和 doctor 命令，不代表用户本机环境已经验收，也不代表尚未实现的知识库功能已经通过测试。
