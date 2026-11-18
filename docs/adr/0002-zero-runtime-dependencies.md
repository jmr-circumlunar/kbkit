# ADR-0002：核心零第三方运行时依赖

- 状态：Accepted
- 日期：2026-11-17

## 背景

原始独立性判据 I3 要求干净 Python 环境无新增第三方运行时包。项目同时需要 FTS5、MCP、Git、可选模型 HTTP 和计划任务。

## 提案

- Core、CLI、Python API、SQLite FTS5、Git subprocess、HTTP 客户端、Windows 任务调度适配器优先使用 Python 标准库。
- MCP 首发优先评估 stdio JSON-RPC 传输的标准库实现；协议版本固定并做真实客户端互操作测试。
- 不引入模型 SDK；模型服务只通过 urllib 等标准库 HTTP 客户端调用。
- 构建后端属于 build-time dependency，必须与 runtime dependency 分开披露。
- 若未来引入第三方 SDK，只能作为显式可选 extra，不得传染到 Core；是否仍满足 I3 需重新定义和经用户确认。

## 风险

- 自行维护 MCP 协议适配增加协议兼容和安全维护负担。
- Python 标准库构建/分发能力与 pip 安装体验之间存在权衡。
- 标准库没有完整 YAML 解析器，Frontmatter 必须严格限定受支持子集。

## 验证

干净 venv 依赖审计、断网流程、MCP 客户端互操作、模型端点超时和错误降级。

E1 决定：核心实现维持标准库方案。MCP 首发限定 stdio，互操作和协议细节在 E2 验证。


## MCP 传输补充

MCP 官方规范将 stdio 与 Streamable HTTP 列为标准传输。stdio 由客户端启动服务子进程，JSON-RPC 消息经 stdin/stdout 传递；服务不得向 stdout 输出非协议文本，日志可写 stderr。

官方规范（2026-07-28）：https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/index.mdx

因此，首发只做 stdio 是可行的范围控制提案；这并不等于“随便实现 JSON-RPC 就算 MCP”。必须固定协议版本，覆盖 initialize、capabilities、tools/list、tools/call、错误、取消和客户端互操作。Streamable HTTP 作为后续独立决策，不与 Web Viewer 混淆。
