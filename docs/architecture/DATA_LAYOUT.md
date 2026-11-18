# 数据模型与目录布局

## 1. 三类数据必须分离

### A. 用户知识内容（权威数据）

用户指定的 vault 根目录内的 Markdown 和附件。目录结构由用户选择的范式决定，kbkit 不强制所有用户采用同一套内容目录。

### B. 库级配置与事务控制数据

候选结构：

    <vault>/
      .kbkit/
        profile.toml
        transactions/
        snapshots/
        trash/
        logs/

- profile.toml：库级配置和 schema 版本；是否纳入用户 Git 由初始化向导明确选择。
- transactions/：journal 和同卷 staging；用于恢复，不应进入用户知识 Git。
- snapshots/：本地恢复快照；默认不进入用户知识 Git。
- trash/：软删除回收区；清理需遵循保留策略。
- logs/：运行日志，不包含正文或密钥。

注意：原始方案把 .kbkit 整体描述为可删除重建的派生数据，但 profile 与未完成事务日志并非都能无条件丢弃。必须把“可重建索引”“可恢复事务数据”“可迁移配置”分开，不能一刀切删除。

### C. 外置索引与全局注册

候选 Windows 路径：

    %LOCALAPPDATA%\\kbkit\\indexes\\<vault_uuid>\\<location_key>.sqlite
    %LOCALAPPDATA%\\kbkit\\registry.sqlite

原始方案提出 %APPDATA%。建议比较 %APPDATA% 与 %LOCALAPPDATA%，因为索引属于可重建的本机缓存，通常不应随漫游配置同步；最终位置由 ADR 冻结，并允许用户配置。

## 2. Vault 身份

- profile 中保存 vault_uuid，不用绝对路径作为唯一身份。
- vault 移动后应能重新发现同一 UUID 并重建外置索引关联。
- 复制 vault 会产生 UUID 冲突；检测到相同 UUID 位于不同根路径时，必须询问用户是“移动后的原库”还是“复制出的新库”，不得自动合并索引。
- 索引位置键由规范化后的本机库路径生成，复制库即使尚未注册也使用独立索引。库 UUID 仍用于逻辑身份，迁移后可按新路径重建索引。
- 路径、大小写和 Unicode 规范化需按平台策略处理。

## 3. 索引数据原则

- 正文不进入 FTS 表；命中后回源读取。
- FTS 表保存 title、tokenized content、path/block locator、元数据过滤字段和内容指纹。
- path/breadcrumb 等是否进入普通列或 FTS 列需按查询使用频率决定。
- 索引 schema 有版本号；升级失败可回退或完整重建。
- 索引不写入用户 Git；损坏后可通过 index build 恢复。

## 4. 变更检测

原始方案使用 mtime + size / Git / sha1 三件套。需明确每种机制的成本与用途：

- mtime + size：快速初筛，不能作为内容一致性的最终证明。
- SHA-1：与历史方案兼容的内容指纹；需评估是否改用 SHA-256，安全用途不能把 SHA-1 当抗碰撞安全机制。
- Git 状态：可选增量线索，不可要求每个 vault 必须有 Git。
- 文件 rename/move：需识别旧路径与新路径关系，不能只当成删除+新建而丢失身份。

## 5. 运行时目录范式

初始化默认混合骨架候选：

    00-索引/
    10-主题/
    20-方法/
    30-运行时/
    90-归档/
    99-资产/

方向描述只产生建议；领域目录先展示清单，用户确认后才创建。运行时产物与知识内容物理分区；exclude 支持 allow 子路径白名单。用户可选择 PARA、领域主题、Johnny Decimal、Zettelkasten+MOC 或混合骨架。

## 6. Git 忽略策略

建议生成可审阅的 .gitignore 片段，而不是覆盖已有文件。至少区分：
- 忽略外置索引（本来不在 vault 内）；
- 忽略事务 staging、日志、临时缓存；
- profile 是否提交由用户选择；
- 用户正文、附件、模板和必要导航不应被默认忽略。

组件研发仓库的 .gitignore 与用户 vault 的 .gitignore 是两份不同策略。
