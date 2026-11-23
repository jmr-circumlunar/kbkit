---
name: kb-maintain
description: Run a local knowledge maintenance cycle and inspect its findings.
metadata:
  kbkit-api-version: v1
---

# kbkit maintenance

- On first setup, confirm the vault, frequency and authorized sources. For a local repository, run `python -m kbkit knowledge bind-code <vault> <id> <repo> --ref <full-ref> --scope <path>`. Create the schedule in the Agent host when supported. Future scheduling edits belong to that host.
- Run `kb_maintain` or `python -m kbkit task run <vault>`. For scheduled or manual runs already authorized to make mechanical edits, pass `auto_apply: safe` or `--auto-apply safe`. Use `none` for report-only lint. Safe mode appends missing final newlines and repairs verified links configured by the user in active areas. It preserves history, tracked notes and generated pages. Routine runs also update bound implementation maps. Use `kb_maintenance_report` with the returned `run_id` and `collection: automatic_fixes` or `collection: code_sync` to inspect results.
- To refresh external Markdown edits on demand, call `kb_sync` or run `kbc sync <vault>`. To sync the vault's own Git repository, confirm the configured remote and branch with the user and run `kbc sync <vault> --git` when requested or covered by the host schedule. Resolve uncommitted changes, branch divergence or pending vault transactions before retrying. Keep business code repository updates with their respective projects.
- Inspect `kb_status` for stale or unreviewed notes. Verify the changed evidence and update the Markdown before renewing its review with `python -m kbkit knowledge review <vault> <page> --depends-on <basis-page>`. Repeat the flag for each dependency.
- For a nightly semantic review, record stale, incomplete or incorrect findings with `kb_audit_record`, or `kbc audit record <vault> <result.json>`. Keep uncertain findings pending and link an applied finding to its `transaction_id`. Use `kb_audit_report` to read the receipt. Before an authorized vault Git commit or push, run `kb_check` or `kbc check <vault>` and inspect the diff and blockers.
- Use `kb_proposals` to inspect remaining executable fixes. Use `kb_proposal_apply` for a manually approved low-risk proposal. Agent-curated session summaries use only sources authorized for the schedule.
