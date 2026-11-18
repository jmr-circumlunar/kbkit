# ADR-0004：多文件写入采用可恢复 redo 协议

- 状态：Accepted
- 日期：2026-11-17

## 背景

Agent 一次写入可能修改多个 Markdown 文件及其链接、元数据。单文件 replace 不等于多文件全局原子事务。

## 提案

采用 write-ahead + image-based redo：
- 预检、锁、before hash、after-image、staging、journal 先行；
- 逐文件应用前再次检查 before hash；
- applied/pending/divergent 三态恢复；
- divergent 永不自动覆盖；
- 索引失败只标 index_dirty，不回滚正确正文；
- Git commit 在内容事务之后执行，失败不伪称正文回滚。

## 保证边界

目标是进程崩溃后可恢复、重复恢复幂等、kbkit API 读写可通过锁隔离。第三方编辑器不遵循锁协议，因此不承诺其在多文件逐个替换期间看到全局原子快照。Windows 断电耐久性在专项原型前不作保证。

## 验证

TXN-01 至 TXN-07，Windows 文件句柄占用、锁释放、journal durability、目录元数据持久性和恢复期间再次崩溃。

E1 决定：对外只承诺进程崩溃后的可恢复协议和幂等恢复。断电级耐久性必须通过 E2 Windows 原型后再确定。
