# E1 退出评审

评审日期：2026-11-17
评审对象：`6997e5b6d7e0b04e80f9eccb8e3091b77458ab9c`

## 结论

E1 **有条件通过**，允许进入 E2 高风险技术原型。产品边界、依赖原则、数据真相、写入安全边界、接口分层、代码规范和自成长闭环已经冻结。Windows 文件事务耐久性、MCP 互操作、Markdown round-trip、索引性能和多来源 artifact 隐私策略必须在 E2 取得证据后，才能扩大实现范围。

License 与公开发布策略仍需维护者确认，因此当前只允许内部开发和测试，不形成发布承诺。

## 已冻结决策

| 领域 | 决策 |
|---|---|
| Python | 3.11+，CI 覆盖 3.11–3.13；本机开发使用 3.13.9 |
| 平台 | Windows NTFS 为首发验收平台；Linux 先做 CI 烟测；macOS 暂不承诺 |
| 依赖 | 核心运行时零第三方依赖；可选能力隔离 |
| MCP | 首发 stdio，固定协议版本；Streamable HTTP 另行决策 |
| 正文 | Markdown 文件是唯一权威来源 |
| 索引 | SQLite FTS5 派生索引，可删除重建，默认放置于 LOCALAPPDATA |
| 写入 | dry-run 默认开启，冲突拒绝，divergent 不自动覆盖 |
| Markdown | 只解析声明的 Frontmatter 子集，未知内容保留 |
| 自成长 | vault、审核、代码、授权会话进入 ChangeEvent；安全动作可直接执行，高影响变化进入 proposal 和 Agent 处理 |
| 自动化配置 | Skill 首次询问，Agent 宿主保存调度，kbkit 保存任务定义和审计，用户可后续修改 |
| 代码 | 见 `docs/engineering/CODE_STYLE.md` |

## E2 必须验证

1. Windows 文件锁、同卷 staging、替换、flush 和恢复。
2. TXN-01 至 TXN-07 故障注入。
3. Markdown 未修改区域的字节保留。
4. SQLite FTS5 的中文 tokenizer、增量同步和重建一致性。
5. stdio MCP 的 initialize、tools/list、tools/call、错误和取消。
6. 复制或移动 vault 后的 UUID、索引和路径行为。

## 追踪检查

- FR-001 至 FR-018 已映射至候选模块和测试编号。
- P0 事务、离线、路径安全和 round-trip 要求已列入测试策略。
- 候选模块仍需在 E2 原型后根据真实接口冻结名称和依赖。
- I8 缺口已保留为待确认项，不在实现中自行假设。

## 环境证据

- 本机 Python 3.13.9、SQLite 3.51.0。
- editable 安装通过。
- 3 个 bootstrap 测试通过。
- `python -m kbkit doctor` 报告 FTS5 可用。
- Python 3.11 本机未安装，由 CI 矩阵负责验证。

## 依据

- Python 3.11 引入标准库 `tomllib`，支持 3.11+ 可保持核心零依赖。<https://docs.python.org/3.11/whatsnew/3.11.html>
- SQLite FTS5 官方文档。<https://www.sqlite.org/fts5.html>
- MCP transport 规范和 stdio 约束。<https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>
