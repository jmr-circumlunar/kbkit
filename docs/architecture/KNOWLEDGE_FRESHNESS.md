# 知识治理使用指南

同一个项目通常有三类页面。

| 页面 | 权威依据 | 漂移处理 |
|---|---|---|
| 设计、ADR、目标和取舍 | 复核后的设计决策 | 当前版沿用固定路径。每次复核保存版本，历史由显式命令查看。设计里的拟实现内容仍应写成计划。 |
| 实现索引 | 已绑定的 Git ref 和提交中的文件 | 定时任务自动刷新单个生成页。记录 commit、路径、blob 和可解析的 Python 顶层公开符号。 |
| 操作手册、发布说明和其他派生结论 | 明确登记的设计页、实现页或其他依据 | 依据变化、删除或失效时，下游退出默认检索。更新内容或核实结论仍成立后，复核并重新纳入。 |

普通双链用于导航。只有经复核登记的依赖参与失效传播，避免误伤链接到历史资料的页面。直接修改已复核页时，当前内容标记为 `unreviewed`。依赖变化时标记为 `stale`，并传递给间接下游。按路径读仍能看到页面。CLI 的 `--include-inactive` 和 MCP 的 `include_inactive: true` 可查看标明状态和原因的检索结果。标记为草稿、废弃和归档的笔记同样退出默认检索。复核日期到期由 lint 提醒。

## 复核、替换和归档

以下命令假设已初始化 `<vault>`，且 `design.md` 和 `runbook.md` 已存在。

```text
python -m kbkit knowledge review <vault> design.md
python -m kbkit knowledge review <vault> runbook.md --depends-on design.md
python -m kbkit knowledge status <vault>
python -m kbkit knowledge history <vault> design.md
python -m kbkit knowledge history <vault> design.md --revision 1
```

在原路径编辑设计，核对后再次运行 `knowledge review` 保存新的复核版。旧版以内容哈希保存于 `.kbkit/history/`，可通过历史命令读取。业务含义已废弃的现有页可写入 `state: deprecated` 或 `state: archived`，关联分页随之失效。复核下游时先检查上游内容和状态。重新复核可省略 `--depends-on` 以沿用已有依赖。备份包含版本记录和快照。

## 每日更新实现知识

用户首次选定本地仓库、Git ref 和目录范围时，由 Agent 执行绑定。同一个库可以绑定多个项目。

```text
python -m kbkit knowledge bind-code <vault> my-project <repo-root> --ref refs/heads/main --scope src
python -m kbkit task run <vault>
python -m kbkit knowledge review <vault> runbook.md --depends-on design.md --depends-on _generated/code/my-project.md
```

让宿主定时运行同一命令或调用 `kb_maintain`。每次读取 ref 指向的已提交版本。生成页位于 `_generated/code/<source-id>.md`。下次运行时，范围内代码文件发生变化才替换生成页。生成页被人工编辑或删除时，维护保留现状并报告冲突。ref 无法读取时标为 `unverified`。两种异常均表现为部分成功，报告给出来源、状态及受影响的页面。

代码的未提交改动、自动联网拉取和外部文件及会话事实同步不在当前机制范围内。若用户把本地的远程跟踪 ref 作为依据，其新鲜度由独立的 Git 更新流程决定。生成页用于定位实现证据。API 行为、架构差异和迁移结论需要从代码与测试中核实，再维护为依赖实现索引的知识页。

## 性能与规模

查询检查库内文件元数据，并对已登记页面及依赖复验内容哈希。维护运行全库哈希核验。相同 Git 提交跳过实现提取，非授权范围的变更不重写生成页。报告保留刷新状态和哈希，默认检索只暴露当前内容。调度时间由宿主配置，本库运行报告可用于核对是否按期触发。
