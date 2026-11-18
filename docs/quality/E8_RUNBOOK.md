# E8 外部验收运行手册

将公开 URL 和用户意图交给一个空白 Agent。Agent 从仓库主页发现安装和使用路径，测试人员记录克隆 URL、分支和完整 SHA。每个来源单独记录结果，候选提交的测试结果用于候选验证，公开 Git 分发结果来自 GitHub 可达的那个 SHA。

## 干净环境

```powershell
git clone https://github.com/jmr-circumlunar/kbkit.git
cd kbkit
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m kbkit doctor
```

判定要求是测试全通过，doctor 报告 FTS5 可用。随后由 Agent 初始化临时 vault，使用 MCP 写入和查询，再通过外部编辑器或普通文件写入改动，验证下次检索反映改动。执行一次维护并确认报告实际落盘。索引目录、注册目录和 vault 都使用临时路径。

可用 `scripts/verify_release.py` 从任意明确的 Git URL 重跑基础验收。脚本克隆到新目录并从该提交安装。JSON 结果记录 SHA、运行时、通过阶段、当前阻塞以及同一提交的两份独立检出能否生成一致的 zipapp。传入 `--branch` 可指定候选分支或标签，`--expect-sha` 可锁定验收提交。

```powershell
python scripts/verify_release.py https://github.com/jmr-circumlunar/kbkit.git --branch <branch-or-tag> --expect-sha <full-sha>
```

脚本覆盖实际 stdio 调用、Skill 文件发现、库副本隔离，并在 wheel 构建后使用禁用包索引及 Python 网络调用的干净环境验证本地安装和核心操作。空白 Agent 自主安装、宿主原生 Skill 加载、持久计划和第三方编辑器仍按各自的验收项记录。

## Skill 加载

从仓库读取以下文件并记录宿主名称、Skill 版本和加载结果：

```text
skills/kb-onboard/SKILL.md
skills/kb-query/SKILL.md
skills/kb-author/SKILL.md
skills/kb-maintain/SKILL.md
skills/kb-ingest/SKILL.md
```

每个文件必须包含 `kbkit-api-version: v1`。

分别记录 Skill 文件发现、Agent 依据文件执行流程和宿主原生加载。原生加载要求观察宿主实际注册或调用对应 Skill。

## 自成长验收

使用临时 vault 和临时代码仓库。按 [知识治理使用指南](../architecture/KNOWLEDGE_FRESHNESS.md) 复核一份设计和一份依赖设计的手册，修改设计后验证手册退出默认检索。复核新设计版，通过历史命令读取旧版。绑定临时代码仓库，提交一次授权范围内的代码变更，执行同一维护命令并检查生成页和运行报告。生成页应自动替换且只有一份，依赖旧实现的手册应失效。再改动生成页，验证维护报告冲突并保留该编辑。

## MCP stdio

宿主使用当前虚拟环境中的命令：

```text
python -m kbkit mcp stdio
```

设置 `KBKIT_VAULT` 环境变量后，依次发送 `initialize`、`tools/list` 和 `tools/call`。记录协议版本、工具数量、schema、错误结构和 stderr 日志。stdout 只能包含 JSON-RPC 消息。

## 发布 artifact

```powershell
python scripts/build_zipapp.py .\dist\kbkit.pyz
python .\dist\kbkit.pyz --version
python .\dist\kbkit.pyz doctor
```

记录 commit SHA、Python 版本、SQLite 版本、操作系统和 artifact hash。

## 通过标准

- Skill 在目标 Agent 宿主中可加载。
- MCP 客户端完成 initialize、tools/list、tools/call。
- clean venv 和 zipapp 均可运行。
- 所有 P0 测试通过。
- 未通过项记录原因、影响范围和后续处理人。
