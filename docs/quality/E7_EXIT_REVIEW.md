# E7 退出评审进展

## 已验证

- 干净临时 venv 使用 `pip install --no-deps -e .` 安装成功。
- 干净 venv 中 `python -m kbkit doctor` 报告 FTS5 可用。
- 临时 zipapp 构建成功。
- 临时 zipapp 使用显式 Python 解释器运行 `--version` 和 `doctor` 成功。
- Skill 资源可发现并读取 `api_version`。
- MCP `initialize`、`tools/list`、schema 和 `tools/call` 参数错误边界已测试。

## 待完成

- 真实第三方 MCP 客户端互操作矩阵。
- Skill 在 Codex、Claude Code、Workbuddy 等宿主中的加载验证。
- 发布 tag、zipapp artifact 和版本兼容矩阵。
