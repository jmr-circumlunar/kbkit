# E4 安全写入进展

## 已实现

- 结构化 append operation
- move、rename、delete 的统一 operation plan
- delete 的 trash manifest、hash 校验和恢复
- fault injection 后 pending journal 恢复
- application service 已接入 write plan/apply，并在写入后重建索引
- 写入后正文 hash、索引记录和文档存在性一致性检查
- TXN-01 至 TXN-07 机器可执行故障矩阵
- 本机 Windows 独立进程锁竞争和释放
- MCP tools 已达到冻结的 8 个工具上限
- bulk 多操作计划
- vault 根目录和 Markdown 后缀校验
- expected_hash 并发校验
- dry-run plan，不修改文件
- 多文件计划和统一 transaction_id
- apply 前再次校验所有目标
- pending/applied journal 记录
- 同卷 after-image staging 和 pending journal 恢复
- `recover` CLI 扫描并恢复待处理事务
- 并发编辑时停止，不继续写入

## 当前限制

- 目前只实现 append operation。
- journal 恢复已具备基础实现，跨进程故障注入仍需实现。
- 多文件 apply 的回滚和再次崩溃恢复仍需 TXN-01 至 TXN-07 验证。
- move、rename、delete、bulk 和 selector 语义仍需继续扩展。
