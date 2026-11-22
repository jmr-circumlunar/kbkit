# ADR-0006：平台支持策略

- 状态：Accepted
- 日期：2026-11-17

## 背景

当前维护者的本地研发环境为 Windows。原始产品定位强调本地可搬运，但没有明确 Windows/Linux/macOS 的正式支持承诺。

## 提案

- Windows 作为第一开发和发布验收平台。
- Linux 先做 CI 烟测，直到文件锁、事务恢复、路径和任务调度均有完整测试后再声明正式支持。
- macOS 以本地 APFS 为适配目标，Apple Silicon 与 Intel 在 CI 分别运行验收。
- 第一版优先支持本地 NTFS；网络共享盘、同步盘和云盘不作为事务保证范围。
- 所有平台相关行为通过 adapter 隔离，不在领域层散落 os.name 分支。

## 验证

Windows 版本矩阵、Python/SQLite/FTS5 版本、路径语义、文件锁、replace、任务调度、zipapp 运行行为。

E1 决定：Python 3.11、3.12、3.13 纳入支持矩阵。Windows NTFS、Linux 和 macOS APFS 均运行组件测试。macOS 默认索引位于用户 Library/Caches，注册数据位于用户 Library/Application Support。
