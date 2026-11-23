---
name: kbkit-workbuddy
description: Connect, query, write, and maintain a user-selected local Markdown or Obsidian vault from WorkBuddy using kbkit CLI.
---

# kbkit for WorkBuddy

Use the connector installed by WorkBuddy. On macOS or Linux, invoke `"${KBKIT_WORKBUDDY_DIR:-$HOME/.kbkit-workbuddy}/kbc"`. On Windows PowerShell, read the installed runtime and invoke it as follows.

```powershell
$kbkitRoot = if ($env:KBKIT_WORKBUDDY_DIR) { $env:KBKIT_WORKBUDDY_DIR } else { Join-Path $env:USERPROFILE '.kbkit-workbuddy' }
$kbkitRuntime = Get-Content -LiteralPath (Join-Path $kbkitRoot 'connection.json') -Raw -Encoding UTF8 | ConvertFrom-Json
& $kbkitRuntime.python -I -X utf8 $kbkitRuntime.archive --version
```

In the workflows below, `kbc` means the platform invocation above. Pass paths as quoted absolute arguments. If the launcher or connection record is missing, ask the user to connect or reconnect the connector in WorkBuddy. In a scheduled task, read the current connection record or invoke the stable launcher each time so the task uses the installed revision.

- **Initialize.** Confirm the vault path for the current workspace. Use `kbc setup <vault> --host standalone`, then `kbc status <vault>`. For an existing vault, preserve its current metadata location. Use approved paths only. If creating a demo, choose a new or empty directory.
- **Search first.** For project rules, decisions or prior work, use `kbc sync <vault>` once before searching in a new session, then `kbc search <vault> <query> --json`. Use `kbc read <vault> <note> --lines <start> <end>` or pass the hit's `block_id` to `--block-id` to verify the result. Cite the source path and lines. Check current code for implementation facts. If evidence is missing, say so. Re-sync if the user edits a note in an external editor during the session.
- **Write.** Use the CLI with a JSON operations array. Choose `replace` for a targeted edit, `insert` at a heading start, and named templates for repeatable notes. Preview using `kbc write plan <vault> <operations.json>`, then use `kbc write apply <vault> <operations.json> --plan-hash <hash> --request-id <uuid>`. Keep the same UUID when retrying and inspect the receipt with `kbc write status <vault> <uuid>`. Stop on a changed plan or conflict. Preserve the original source when importing and record its provenance.
- **Maintain.** For recurring maintenance, confirm frequency, time zone, authorized sources, and permission for mechanical edits once. Create or update the schedule in WorkBuddy if the host offers it. Use `kbc task run <vault> --auto-apply safe` only when vault edits were authorized, or `--auto-apply none` for reports and pending fixes. Report the run ID and any conflicts. Archive nightly semantic findings with `kbc audit record <vault> <result.json>` and read pending items with `kbc audit report <vault> <run_id> --disposition pending`. Run `kbc check <vault>` and inspect the diff before authorized Git commits or pushes. If scheduling is unavailable, offer a manual run. Use `kbc sync <vault> --git` only for the vault's authorized remote and branch. Any use of conversation material by the Agent follows the user's agreed scope.
