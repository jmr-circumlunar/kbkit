# 自动化配置契约

## 配置原则

- kbkit 提供安全默认值，用户可以通过 Agent 修改。
- 首次启用自动化时，`kb-maintain` Skill 必须询问用户是否启用、执行频率、扫描来源、模型权限和写入确认策略。
- 定时任务的最终调度配置保存在对应 Agent 宿主中。kbkit 保存任务定义、默认值、扫描游标、执行结果和审计记录。
- 用户可在宿主中修改或暂停任务，并随任务保存执行参数。授权机械修复后用 `kbc task run <vault> --auto-apply safe` 或 `kb_maintain` 的 `auto_apply: safe`。用 `none` 仅报告巡检提案。
- 当调用未显式选择模式时，启用的既有 `automation.json` 提供 `auto_apply` 设置。未保存或已停用时采用 `none`。该文件位于已配置的库元数据目录。
- 宿主不可用时，用户可以手动触发 Skill 或使用 kbkit runner。
- 已执行 `knowledge bind-code` 的来源随 `task run` 或 `kb_maintain` 一起处理。绑定授权该来源的固定实现索引页。下方通用生成和模型配置属于扩展策略。

## 默认配置

```toml
[maintenance]
enabled = false
schedule = "daily"
run_on_session_start = true
run_on_session_end = true
sources = ["vault", "audit"]
model_assistance = false
auto_apply = "safe"
generated_content = "disabled"
generated_root = "_generated"
retention_days = 30
```

默认配置只用于首次建议。已授权的 `auto_apply = "safe"` 自动补齐末尾换行，并按用户配置修复活跃区已验证的普通链接。已登记审阅、绑定生成或针对当前内容已拒绝修复的笔记跳过。先核对原文哈希，再用写入事务应用。每次运行记录修复结果，可用 `collection=automatic_fixes` 查看。`generated_content = "disabled"` 在用户授权前关闭文件内容生成。它不覆盖用户已有的 Agent 定时任务，也不代表用户已经授权代码仓库、会话目录或外部模型。

## 首次配置对话

Skill 至少询问是否启用自动维护、运行频率和时区、扫描来源、artifact 保留期限、模型辅助和正文发送权限、自动执行级别，以及是否允许在指定生成目录自动创建派生页面。

Agent 根据用户选择保存宿主定时任务。首次可执行单次维护并检查运行报告。向用户返回宿主提供的任务 ID、下次运行时间和修改方式。

夜间语义审核由宿主 Agent 执行。组件接收范围、结论、待确认项与已应用事务，生成可归档运行回执。用户绑定 Git 后可授权 Agent 执行提交和推送。组件提供提交前门禁，宿主可将其纳入夜间任务。

## 修改和停用

用户可以说“暂停知识库自动维护”“改为每周日运行”“只扫描 vault 和代码”“禁止模型读取正文”“允许自动生成代码摘要到 _generated”等自然语言指令，由 Agent 修改宿主中的任务和执行参数。
