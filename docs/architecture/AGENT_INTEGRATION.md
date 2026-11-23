# Agent 集成、Skill、服务与自动化

## 目标

kbkit 的主要消费者是智能体。Git 仓库提供完整源码、内置 Skill 模板、MCP 服务入口和 CLI。用户只需克隆仓库并在本地安装，Agent 通过 Skill 获得使用规则，通过 MCP 调用实际能力。

## 四个运行部件

### Skill

Skill 是给 Agent 的使用说明和操作约束，内容包括：

- 如何发现或初始化 vault；
- search/read 的查询格式和来源引用要求；
- 写入必须先 dry-run，再显式确认；
- 冲突、stale、index_dirty 和 divergent 的处理；
- lint、graph、status 和恢复操作的调用顺序。

Skill 不实现业务逻辑，也不保存 vault 状态。它可以作为仓库内的文本资源由 Agent 加载，也可以由集成方复制到自己的 Skill 目录。

首次接入使用 [kb-install](../../skills/kb-install/SKILL.md)。安装后可使用 `kb-onboard`、`kb-query`、`kb-author`、`kb-maintain` 和 `kb-ingest`。每个 Skill 都标明接口版本，Agent 可直接读取对应的 `SKILL.md`。

### MCP Server

MCP Server 是 Agent 的机器接口。首发使用 stdio，由 Agent 宿主按配置启动本地子进程：

```text
Agent Host → 启动 python -m kbkit mcp stdio
           → stdin/stdout JSON-RPC
           → kbkit application service
           → vault / SQLite index
```

MCP Server 不需要常驻后台。每个 Agent 会话可以启动一个进程，进程退出后文件和 SQLite 连接都确定性释放。stdout 只输出协议消息，日志写 stderr。

### CLI

CLI 用于人工初始化、诊断、脚本和自动化任务。它与 MCP 调用同一个 application service，因此不会产生第二套业务规则。

### Automation Runner

自动化由独立的 CLI 任务运行器执行，例如：

```text
python -m kbkit task run C:\path\to\vault
```

Windows Task Scheduler 负责定时唤起命令，kbkit 负责读取任务定义、执行巡检、记录运行结果和生成提案。没有安装计划任务时，Agent 或用户仍可手动运行任务。

自动化任务分三类：直接执行的安全动作、直接生成并写入隔离区域的派生内容、需要人工裁决的高风险变更。高风险写入、权威内容改写、合并、移动和删除不能由后台任务静默执行。

## 用户安装和 Agent 加载流程

1. 用户把 [README 的安装指令](../../README.md#复制一句话给-agent) 交给当前项目里的 Agent，也可先用 Skills CLI 加载 `kb-install`。
2. Agent 检查 Git 和 Python，确认涉及已有库或调度的用户选择，构建本地 zipapp 并运行 `doctor`。
3. Agent 调用 `setup` 注册 vault、建立索引，为 Codex 或 Claude Code 生成项目级配置。其他支持 stdio 的宿主可挂接 MCP 并自行加载项目规则。
4. Agent 验证 search、read 和 status。宿主完成项目与 Hook 信任后，在新会话检查工具发现和查询顺序。

项目规则要求在回答项目知识问题时先用 `kb_search`，再用 `kb_read` 核对原文和来源。这个规则保存在 `AGENTS.md` 或 `CLAUDE.md`。SessionStart 用 `additionalContext` 加载同一规则，加上明示授权的一篇库内 Markdown 路由笔记（最多 3000 字符）。新建或恢复会话、清空会话时，Hook 先执行一次本地增量同步，再加载会话上下文。压缩或分叉沿用已建立的索引，并继续加载路由上下文。正常查询直接读取索引。用户在会话中通过 Obsidian 等外部编辑器改动知识后，Agent 可调用 kb_sync；常规 kbkit 写入仍立即刷新受影响文件。已授权的知识库 Git 拉取由 Skill 调用组件同步入口。

MCP 配置的最小形态如下，具体字段名由宿主决定：

```json
{
  "kbkit": {
    "command": "C:\\path\\to\\kbkit\\.venv\\Scripts\\python.exe",
    "args": ["-m", "kbkit", "mcp", "stdio"],
    "env": {"KBKIT_VAULT": "C:\\path\\to\\vault"}
  }
}
```

服务启动时只读取配置和环境变量，不从 Agent 消息中拼接 shell 命令。vault 路径必须经过根目录策略校验。

## 自动化能力

自动化分为三层。

### 确定性本地任务

这些任务不需要模型，也不应因为模型不可用而失败：

- 增量扫描和索引同步；
- stale、index_dirty 和事务 journal 检查；
- Markdown/frontmatter 结构检查；
- lint 规则检查和统计报告；
- 备份、快照和恢复状态检查；
- Git status 和本地变更报告。

### 模型辅助任务

这些任务需要模型判断时才接入模型服务：

- 近似重复候选的语义裁决；
- 摘要、标签和 provenance 建议；
- 冲突内容的比较和提案说明；
- 过期内容的保留、合并或归档建议；
- 检索结果的可选重排和上下文裁剪。

模型服务是可选配置。未配置、断网、超时或调用失败时，任务降级为确定性检查并保留输入证据。只有在用户启用 generated-content 模式后，模型才可以把结果写入隔离的生成目录。模型请求默认只发送必要的脱敏片段，是否允许发送正文由用户逐库确认。

### Agent 编排任务

需要对话、用户确认或跨步骤决策的流程由 Agent 宿主负责，例如首次初始化、首次授权来源、修改自动化范围、处理冲突和选择模型服务。例行安全维护完成后只需报告结果，不再逐项阻塞任务。

## 定时任务的优先级

默认优先使用 Agent 宿主自己的定时任务能力，例如 Codex、Claude Code 或 Workbuddy 的定时任务。宿主能保留对话上下文、向用户请求确认并展示结果，适合模型辅助任务和需要人工决策的流程。

kbkit 自带任务运行器作为便携的兜底能力，适合没有 Agent 调度器、需要离线运行或只执行确定性维护的场景。Windows Task Scheduler 只负责唤起 `python -m kbkit task run <vault>`，不承载业务逻辑；该命令与 `maintain` 共用同一套扫描、proposal、报告和审计流程。

推荐的默认策略如下：

| 任务 | 默认执行者 | 是否需要模型 |
|---|---|---|
| 增量索引、doctor、stale 检查 | Agent 宿主或 kbkit runner | 否 |
| lint 和报告 | Agent 宿主或 kbkit runner | 否 |
| 重复候选和摘要建议 | Agent 宿主 | 可选 |
| 新建隔离的生成页 | Agent 宿主或 kbkit runner | 用户启用后可自动执行 |
| 批量写入、归档、删除 | Agent 宿主 | 必须用户确认 |
| 事务恢复和冲突处理 | Agent 宿主 | 视冲突复杂度而定 |

首次启用自动化时，`kb-maintain` Skill 必须先询问用户，再在对应 Agent 宿主中创建定时任务。询问内容包括扫描来源、生成内容目录、自动执行级别、模型权限和保留期。默认配置和可修改项见 `AUTOMATION_CONFIG.md`。kbkit 不擅自创建宿主定时任务，也不覆盖用户已有计划。用户后续可以通过 Agent 修改或暂停任务。定时任务执行安全动作和隔离生成内容时直接完成，并在运行报告中留下完整审计记录。

## 分发原则

- Git 仓库是首要分发渠道，版本由 Git tag 和 commit SHA 标识。
- pip 和 zipapp 属于后续便利分发，不改变 Git 安装路径和接口契约。
- Skill、MCP schema、CLI schema 和 Python API 的版本必须能相互追踪。
- Skill 是安装后的编排入口，负责把用户意图转换为 MCP/CLI 调用，不要求用户手动执行内部命令。
- MCP 服务不依赖某个特定 Agent 宿主。任何支持 stdio MCP 的客户端都可以接入。
- 外部模型服务不是 Agent 集成前提。L0 本地检索必须可独立工作。

## 服务是否需要常驻

核心能力不要求常驻服务。推荐默认采用按会话启动的 stdio MCP 进程，便于隔离 vault、权限和生命周期。只有在后续需要远程多客户端共享或集中调度时，才单独设计 Streamable HTTP 服务，并补充认证、会话和网络安全模型。
