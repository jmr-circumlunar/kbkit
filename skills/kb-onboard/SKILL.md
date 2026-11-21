---
name: kb-onboard
description: Initialize and verify a local kbkit Markdown knowledge base.
metadata:
  kbkit-api-version: v1
---

# kbkit onboarding

1. Run `python -m kbkit doctor`. Confirm the existing vault path or the destination for a new vault with the user.
2. Run `python -m kbkit init <vault>` to initialize the selected vault. If the user wants metadata outside the vault, set `KBKIT_HOME` before initializing and use the same value in the Agent host.
3. Run `python -m kbkit doctor --vault <vault>` and `python -m kbkit index <vault>`. For structured operations, configure the same Python with `python -m kbkit mcp stdio` and pass `KBKIT_VAULT` to that process.
4. Check `kb_status` or `kbc status <vault>` for `initialized`, `profile`, `indexed_blocks` and `excluded_paths`. Confirm any initial schedule once and use the host scheduler.
