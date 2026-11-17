# 总体架构

## 1. 外部四层

### 视图层（完全交给第三方）

Obsidian、VS Code、Typora、任意 Markdown 编辑器直接打开知识库目录。kbkit 不提供 Web Viewer、渲染器、编辑器、插件或预览界面。

### 接口层

- CLI：人类、脚本和自动化入口。
- Python API：开发者入口。
- MCP Server：Agent 工具入口。
- 可选 HTTP 模型客户端：只用于用户显式配置的模型辅助，不是核心入口。

所有入口必须调用同一应用服务，不允许 CLI/MCP 各自复制业务逻辑。

### 引擎层

由领域模型、应用服务和能力模块组成，覆盖 workspace、Markdown、index、search、graph、writer/transaction、governance、Git、tasks、templates、registry 等能力。

### 存储层

- Markdown 原文和用户附件：权威内容。
- SQLite FTS5：可重建索引。
- 配置：可迁移的库级 profile。
- 事务日志、staging、快照和运行日志：恢复/运维数据，按策略排除出用户知识 Git。
- 用户 Git 仓库：可选版本层。

## 2. 内部依赖规则

建议采用 Ports and Adapters / Hexagonal 的约束：

1. Domain 不依赖 CLI、MCP、Git、SQLite 或具体文件系统实现。
2. Application 层编排用例，只依赖 Domain 和抽象端口。
3. Infrastructure 实现文件系统、SQLite、Git、计划任务、HTTP 模型等端口。
4. CLI、Python API、MCP 是入口适配器，只负责解析参数、调用应用服务和格式化结果。
5. 第三方编辑器不属于 kbkit 运行依赖，只通过共享 Markdown 文件交互。
6. 禁止跨层反向 import；禁止入口层直接写数据库或直接修改 Markdown。

## 3. 数据流

### 索引

文件扫描 → 路径策略 → Markdown 解析 → 块切分/元数据提取 → tokenizer → SQLite 索引写入 → 索引状态记录。

### 检索

查询解析 → 字段/状态/可见性过滤 → FTS5 召回 → 确定性规则排序 → 可选模型重排/裁剪 → 上下文预算打包 → 返回来源定位和可信标记。

### 写入

请求解析 → 结构化 selector → 预检 → 计划与 diff → 冲突检测 → dry-run/确认 → 事务日志与 staging → 应用文件 → 写后断言 → 局部索引同步 → 可选 Git 提交。

### 治理

扫描 → 规则检查/度量 → 风险分类 → 自动修复、提案或只报告 → 写入服务执行 → 审计与复核。

## 4. 真相源和派生数据

- Markdown 原文是唯一正文真相源。
- Frontmatter 中的显式字段是知识元数据来源。
- Profile 是库级配置来源；配置是否随用户 Git 版本化需在数据布局 ADR 中确认。
- SQLite、缓存、索引统计、模型评分均为派生数据。
- 索引损坏不得导致原文回滚或丢失；可重建并显式标记 index_dirty。

## 5. 可选能力边界

Git、模型服务、计划任务和 MCP 传输扩展均可选。未配置时，核心读写检索仍可用。可选适配器不能把依赖传染到核心包。

## 6. 架构冻结前的验证

- FTS5 在目标 Python/SQLite 发行版上实际可用。
- 中文 bigram 与 ASCII identifier tokenizer 的召回/误召回。
- Markdown 解析的字节保留与未知语法处理。
- Windows 文件锁、Replace/rename、崩溃恢复和文件句柄占用。
- SQLite 多进程访问和索引重建。
- MCP 首发传输的真实客户端互操作。
