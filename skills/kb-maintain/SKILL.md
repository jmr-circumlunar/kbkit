---
name: kb-maintain
description: Run a self-growth maintenance cycle for a local kbkit knowledge base.
metadata:
  kbkit-api-version: v1
---

# kbkit maintenance

Use this Skill when the user asks to update, review, audit or grow the knowledge base.

- On first setup, confirm the vault, frequency, and any local Git repository, ref, and source paths to bind. For an authorized repository, run `python -m kbkit knowledge bind-code <vault> <id> <repo> --ref <full-ref> --scope <path>`. The Agent host owns the schedule.
- Run `kb_maintain` or `python -m kbkit task run <vault>`. Routine runs refresh bound implementation maps and report stale dependents without asking for approval each time. Use the reported commit and source paths to inspect actual code.
- Read `code_sync`, `knowledge` and the report path. Escalate conflicts and unavailable refs. A stale or unreviewed page needs updated content or a new review of its evidence. Apply `python -m kbkit knowledge review <vault> <page> --depends-on <basis-page>` after verifying the page. Repeat the flag for each dependency. `knowledge history` retrieves prior reviewed design versions.
- Keep generated maps and human conclusions separate. Resolve factual conflicts before renewing a review, and preserve approved design history. External source and session change monitoring requires a separate decision.
