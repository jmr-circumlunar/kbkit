# 写入一致性与恢复协议

状态：高风险核心设计，必须先做 Windows 原型和故障注入，不得仅凭协议图宣称 all-or-nothing。

## 1. 要防范的失败

- 漂移：修改到错误块或错误文件。
- 覆盖：用户在预检后手工修改，Agent 把它覆盖。
- 半成品：bulk 操作只应用一部分。
- 崩溃：进程退出或系统异常时留有中间状态。
- 派生数据不一致：正文已写入但索引未同步。
- 外部并发：第三方编辑器不遵守 kbkit 锁协议。

## 2. 候选事务流程

1. 校验请求、权限、路径和 selector。
2. 获取 vault 写锁；读取目标文件并记录 before_hash。
3. 生成完整 after-image、影响清单和写后断言。
4. dry-run 返回 diff；用户确认后继续。
5. 在目标卷内写 staging 文件，flush 文件内容。
6. 写入 journal，记录事务 ID、目标路径、before_hash、after_hash、after-image 位置、状态和 schema 版本；确认 journal 可恢复后才修改目标。
7. 逐文件应用替换；每个目标应用前再次核对当前 hash。
8. 写后读取并校验 after_hash、Markdown 结构和业务断言。
9. 标记内容已应用；执行局部索引更新。
10. 索引失败时保留正确正文，设置 index_dirty，提供重建入口。
11. 可选 Git commit 在内容事务之外执行；提交失败不回滚已正确写入的正文。
12. 清理 staging/journal 前确认恢复信息已安全归档或按保留策略处理。

## 3. 恢复三态

- applied：目标内容已等于 after-image，跳过。
- pending：目标仍等于 before-image，允许按 journal 前滚。
- divergent：目标既不等于 before-image，也不等于 after-image，绝不自动覆盖；保留 journal 并要求人工解决。

恢复必须幂等：重复运行不会二次破坏数据。

## 4. 必须区分的保证

| 保证 | 含义 | 当前状态 |
|---|---|---|
| 单文件替换原子性 | 单个文件替换时读者不会看到半个文件 | 需按 Windows API/文件句柄行为验证 |
| 进程崩溃后可恢复 | 重启后 journal 可识别并完成前滚或报告冲突 | 设计目标 |
| kbkit API 读写隔离 | kbkit 读者不会在事务应用中读到混合版本 | 需要读锁/事务状态门禁原型 |
| 第三方编辑器全局原子可见 | Obsidian 等在多个文件逐个替换时永远只见旧版或新版 | 不承诺，除非另有实现与证据 |
| 断电/硬件故障耐久性 | OS/磁盘缓存和目录元数据在掉电后仍满足保证 | Windows 需专项验证，不能仅凭 Python flush/fsync 推断 |

## 5. 锁与外部编辑器

- kbkit 内部采用单 vault 单写者锁；读者锁策略需明确。
- 外部编辑器不参与锁协议，依靠写前 hash 和写后断言发现冲突。
- 事务期间检测到 divergent，停止该文件自动覆盖，保留 journal。
- Windows 本地 NTFS 为首要验证环境；网络共享盘、同步盘和云盘暂不承诺相同语义。

## 6. 七个故障注入点（源自原始方案）

| ID | 注入位置 | 恢复预期 |
|---|---|---|
| TXN-01 | staging 写到一半时 kill | 目标文件未改；残留 staging 可安全清理 |
| TXN-02 | journal 完成、目标尚未改时 kill | 恢复识别 pending，前滚到 after-image |
| TXN-03 | 替换到第 N 个文件时 kill | 恢复后全部目标达到 after-image，或明确进入人工冲突处理 |
| TXN-04 | 局部索引更新中 kill | 正文不回滚；index_dirty 可检测并重建 |
| TXN-05 | Git 提交前/中失败 | 正文状态保持已应用；Git 状态可诊断，不伪称提交成功 |
| TXN-06 | 第二个写请求并发进入 | 写锁串行化或明确返回 busy/conflict |
| TXN-07 | 事务中第三方修改目标文件 | divergent；绝不覆盖外部新内容；journal 保留 |

## 7. 需要原型验证的 Windows 风险

- os.replace 对已打开文件、杀毒软件和编辑器文件句柄的行为。
- staging 与目标是否确保同卷。
- msvcrt/Win32 文件锁的跨进程行为与崩溃释放。
- 文件 FlushFileBuffers、目录元数据持久化和断电保证。
- 长路径、权限、只读属性、杀毒软件短暂占用和重试策略。
- journal 原子更新和恢复时的再次崩溃。

## 8. 错误契约

写入返回错误不能证明回滚已发生。必须区分 rolled_back、partially_applied、unknown、completed_with_index_dirty 等结果；不确定时明确告知目标路径和恢复动作，不能说“已回滚”。
