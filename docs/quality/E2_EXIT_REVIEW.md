# E2 退出评审

评审对象：高风险技术原型
当前 commit：工作区待提交变更

## 结果

E2 **通过原型门禁，可以进入 E3**。四类原型均有可重复测试，已验证的结论足以开始最小核心实现。Windows 断电耐久性、多文件事务和真实 MCP 客户端互操作仍属于 E4/E7 的扩展验证，不在本次原型中宣称完成。

## 原型证据

| 原型 | 实现 | 证据 | 结论 |
|---|---|---|---|
| FTS5 | `src/kbkit/prototype_index.py` | `test_fts5_probe_and_search` | 当前 Python/SQLite 可创建 FTS5，写入和检索路径可用 |
| Markdown round-trip | `src/kbkit/prototype_markdown.py` | `test_markdown_roundtrip_preserves_body` | BOM、CRLF、未修改正文和未知字段可保留，受控字段可局部更新 |
| 文件锁与 redo journal | `src/kbkit/prototype_lock.py`、`src/kbkit/prototype_transaction.py` | `test_file_lock_releases`、`test_transaction_recovery_detects_divergence` | 文件锁释放和 pending、applied、divergent 的最小判定可重复执行 |
| stdio MCP | `src/kbkit/prototype_mcp.py`、`kbc mcp stdio` | `test_mcp_contract_has_jsonrpc_error` | JSON-RPC initialize、tools/list 基础响应和未知方法错误边界可用 |

## E2 退出条件

- 原型测试通过。
- 原型结论已经写入架构和事务边界。
- 失败和未验证范围已记录。
- E3 的最小实现边界已经确定。

## E3 开始范围

E3 先实现 `init`、vault 注册、Markdown 读取、FTS5 索引、search、read，以及 ChangeEvent、TaskRun、Proposal 的基础持久模型。E3 不提前实现全部治理、模型重排、Git 自动提交或复杂 MCP 工具。

## 未宣称完成的能力

- Windows 断电级 durability。
- 多文件事务的全部故障注入点 TXN-01 至 TXN-07。
- 真实 Agent 宿主的 MCP 客户端互操作矩阵。
- 中文 bigram 的 golden set 性能门槛。
- 完整 Frontmatter YAML 兼容性。
