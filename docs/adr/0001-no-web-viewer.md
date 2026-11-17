# ADR-0001：不提供 Web Viewer 或自有渲染层

- 状态：Accepted
- 日期：2026-11-17
- 决策来源：用户明确确认

## 背景

原始总述的架构图曾出现 kbkit 自带本地 Web 查看器，但同一文档的对外接口章节又明确说视图层完全交给第三方。两处冲突。

## 决策

kbkit 不提供 Web Viewer、Web UI、Markdown 渲染器、浏览器预览或编辑器。Obsidian、VS Code、Typora 和其他第三方工具直接打开同一批 Markdown 文件，负责预览和人工编辑。

## 影响

- 删除自有 Web Viewer 的范围、依赖、测试和路线。
- 不为渲染功能设计 HTTP server。
- 兼容性测试聚焦 Markdown 文件格式和第三方工具可读性，不测试 kbkit 的 UI。
- 所有 Agent 能力由 CLI、Python API 和 MCP 提供。
