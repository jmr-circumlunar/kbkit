# ADR-0003：Vault 配置、事务数据与外置索引分区

- 状态：Accepted
- 日期：2026-11-17

## 背景

原始方案提出索引外置到 %APPDATA%，同时将 .kbkit 描述为索引/快照/日志派生目录。但 profile、未完成 journal 和快照并非都可直接删除重建。

## 提案

- Markdown 和附件保留在用户 vault。
- profile 与 schema version 放在 vault 内的可迁移位置；是否纳入用户 Git由用户确认。
- transaction journal/staging 与目标文件同卷，确保替换和恢复策略可验证。
- SQLite 搜索索引放在本机应用数据目录，以 vault_uuid 隔离。
- 索引、缓存、运行日志默认不进入用户 Git。
- 比较 %APPDATA% 与 %LOCALAPPDATA%；当前倾向 %LOCALAPPDATA% 存放可重建索引，但需以 Windows 多用户/漫游场景测试决定。
- 组件研发仓库与用户 vault 的 Git 仓库完全隔离。

## 验证

移动 vault、复制 vault、UUID 冲突、删除索引重建、用户 Git 状态、同卷 staging 和目录清理策略。

E1 决定：可重建 SQLite 索引默认位于 `%LOCALAPPDATA%\\kbkit\\indexes\\<vault_uuid>`。profile 和事务数据仍留在 vault 的 `.kbkit` 内，最终清理规则由 E2 原型验证。

E8 补充：同一 UUID 的不同本机路径使用不同索引文件。旧索引可保留，运行时从 Markdown 重建当前路径的索引。重复注册需显式选择迁移或副本。迁移保留原 UUID，副本得到独立 UUID。
