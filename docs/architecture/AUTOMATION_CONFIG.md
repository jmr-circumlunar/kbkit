# 自动化配置契约

## 配置原则

- kbkit 提供安全默认值，用户可以通过 Agent 修改。
- 首次启用自动化时，`kb-maintain` Skill 必须询问用户是否启用、执行频率、扫描来源、模型权限和写入确认策略。
- 定时任务的最终调度配置保存在对应 Agent 宿主中。kbkit 保存任务定义、默认值、扫描游标、执行结果和审计记录。
- 用户后续可以在 Agent 宿主中自行修改或暂停定时任务，kbkit 下次运行时读取最新配置。
- kbkit 在 `.kbkit/automation.json` 保存宿主名称、schedule、enabled、任务 ID 和配置版本，作为审计记录，不替代宿主的调度实现。
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

默认配置只用于首次建议。`auto_apply = "safe"` 表示自动执行幂等、可逆、带来源的安全动作。`generated_content = "disabled"` 在用户授权前关闭文件内容生成。它不覆盖用户已有的 Agent 定时任务，也不代表用户已经授权代码仓库、会话目录或外部模型。

## 首次配置对话

Skill 至少询问是否启用自动维护、运行频率和时区、扫描来源、artifact 保留期限、模型辅助和正文发送权限、自动执行级别，以及是否允许在指定生成目录自动创建派生页面。

Agent 将用户回答转换为宿主定时任务和 kbkit 任务定义，执行一次 dry-run 验证，并返回任务 ID、下次运行时间和修改方式。

## 修改和停用

用户可以说“暂停知识库自动维护”“改为每周日运行”“只扫描 vault 和代码”“禁止模型读取正文”“允许自动生成代码摘要到 _generated”等自然语言指令，由 Agent 修改宿主配置和 kbkit 任务定义。每次修改都记录配置版本和操作者。
