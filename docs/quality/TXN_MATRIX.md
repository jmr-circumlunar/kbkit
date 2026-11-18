# E4 事务故障矩阵

| 用例 | 注入点 | 当前证据 |
|---|---|---|
| TXN-01 | staging/journal 后、apply 前 | `TransactionMatrixTests.test_txn_01_staging_and_pending_journal` |
| TXN-02 | journal pending 状态 | `TransactionMatrixTests.test_txn_02_pending_before_apply` |
| TXN-03 | 多文件第 N 个目标后 | `TransactionMatrixTests.test_txn_03_partial_multi_file_apply` |
| TXN-04 | 正文已应用、索引边界 | `TransactionMatrixTests.test_txn_04_index_failure_boundary_is_recoverable` |
| TXN-05 | Git commit 边界 | `TransactionMatrixTests.test_txn_05_external_commit_boundary_keeps_content` |
| TXN-06 | 并发写入 | `TransactionMatrixTests.test_txn_06_concurrent_write_is_rejected` |
| TXN-07 | 外部编辑导致 divergent | `TransactionMatrixTests.test_txn_07_external_edit_after_plan_is_divergent` |
| TXN-08 | 恢复期间再次重启 | `TransactionMatrixTests.test_recovery_is_idempotent_after_second_restart` |

当前矩阵验证的是进程级故障和 hash 语义。系统崩溃、断电耐久性和真实 Windows 多进程锁竞争仍需专门环境测试。

本机 Windows 已通过 `test_file_lock_blocks_between_processes` 验证两个独立进程的锁竞争和释放。系统崩溃与断电耐久性仍需专门设备或受控环境。
