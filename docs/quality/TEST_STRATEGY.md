# 测试策略

## 1. 测试目标

测试必须验证用户可观察行为和失败语义，不以模块覆盖率代替正确性。重点覆盖原文保留、索引一致性、检索质量、事务恢复、路径安全和离线独立性。

## 2. 测试层级

1. Unit：纯函数、解析器、tokenizer、selector、规则、状态机。
2. Contract：CLI/Python/MCP 输入输出 schema、错误码和版本兼容。
3. Integration：临时 vault + SQLite + Git fixture + 多进程。
4. End-to-end：init → index → search → read → write → lint → optional commit。
5. Fault injection：在 journal、replace、index、Git 等关键边界 kill 进程并恢复。
6. Golden evaluation：固定查询集和人工标注，评估 Hit@K、MRR、Recall@K 与误召回。
7. Performance：固定数据生成器、随机种子、机器规格和冷/热缓存条件。
8. Platform：Windows 为第一必测平台；Linux/macOS 只有在支持政策确认后才纳入正式发布门禁。
9. Offline/dependency：断网运行；检查核心运行时无第三方依赖。
10. Security：路径穿越、symlink/junction、命令注入、密钥泄露、恶意 Markdown 和资源耗尽。

## 3. Fixture 原则

- 使用合成知识库和脱敏样本，不把真实私人 vault 放入 Git。
- 每个 fixture 标明文件数、字节数、块数、语法覆盖、生成器版本和 seed。
- Golden set 保存 query、expected block/file、相关等级、过滤条件和标注说明。
- 变更 chunking/tokenizer/schema 时必须运行全量 golden set。
- 真实错误样本可脱敏后进入 wrong-answer mine；需保留来源和隐私审批记录。

## 4. CI 门禁

每次 PR：
- Windows：安装、单元测试、集成测试、doctor、依赖审计。
- Linux：初期可做兼容性烟测；正式支持后升级为阻断门禁。
- 代码格式/静态检查工具若引入，必须作为开发依赖且不得成为核心运行依赖。
- 小规模 golden set 必跑；全量 10k benchmark 可按夜间或发布触发。
- 事务故障注入和多进程测试必须在 Windows runner 上跑。

## 5. 通过规则

- 任何数据丢失、静默覆盖、路径越界、事务恢复误判为通过：零容忍。
- 解析器写回必须通过未修改区域字节一致性检查。
- 检索改动必须报告指标差异，不能只报告测试通过。
- 性能回归阈值先按当前基线和硬件归一化；没有可复现环境数据前不设虚假的绝对门禁。
