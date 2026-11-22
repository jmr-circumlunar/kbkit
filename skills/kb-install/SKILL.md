---
name: kb-install
description: Install kbkit from Git, connect a local Markdown or Obsidian vault to the current Agent project, and verify lookup and optional scheduled maintenance.
metadata:
  kbkit-api-version: v1
---

# Install kbkit

1. Use the Agent's execution host. Check Git and Python 3.11–3.13, selecting an already usable Python when possible. Use the current project unless the user specified another. Ask for the path only if an existing vault is requested and the path is unknown. For a demo or a new vault, use the project's `knowledge/` directory if it is absent or empty. If it already contains content, confirm the intended vault before connecting it.
2. Clone the public `main` branch into a durable checkout outside the target vault. Reuse an existing clean checkout of the same upstream. Build the self-contained runtime and run its doctor:

   ```sh
   git clone --branch main https://github.com/jmr-circumlunar/kbkit.git <checkout>
   python <checkout>/scripts/build_zipapp.py <checkout>/dist/kbkit.pyz
   python <checkout>/dist/kbkit.pyz doctor
   ```

   Replace placeholders with quoted absolute paths. Use the discovered Python executable (on macOS or Linux this may be python3). Keep this executable and archive available after setup. Reuse a compatible runtime already configured for kbkit in the project. Report configuration conflicts so the user's existing runtime and vault choice are preserved.
3. Run `python <checkout>/dist/kbkit.pyz setup <vault> --project <project> --host <host>`, using `--host codex`, `--host claude`, or `--host standalone`. For an existing vault, pass `--context-note` only for a specific vault-relative Markdown page the user has authorized as session context. For another host with stdio MCP support, use its project MCP configuration to run `python <checkout>/dist/kbkit.pyz mcp stdio` with absolute `KBKIT_VAULT`, and put the [query policy](https://github.com/jmr-circumlunar/kbkit/blob/main/skills/kb-query/SKILL.md) in its project guidance. iPhone users can direct Codex on a paired Mac or Windows host.
4. Check `status <vault>`, `search <vault> <query> --json`, and `read <vault> <note>` with this runtime. For the starter, search for `知识库备份`. On Codex or Claude Code, verify the project integration in a trusted new session when available. Follow the host's project, MCP and Hook approval flow. Confirm whether the host actually lists `kb_search` and `kb_read` and uses them for a project knowledge question.
5. To enable recurring maintenance, confirm frequency, time zone and authorized sources once, then use the host's scheduler. Save the absolute runtime, vault and working directory with the task. Run `python <checkout>/dist/kbkit.pyz task run <vault>` or call `kb_maintain`, and use the returned run ID to verify the maintenance report. Apply routine safe changes in the run and summarize findings. If the host cannot create a recurring task, report that scheduling is pending and keep manual maintenance available. Leave schedule editing in the host.
6. Report the installed commit, execution host, project and vault paths, routing note if used, and what passed for lookup and maintenance.
