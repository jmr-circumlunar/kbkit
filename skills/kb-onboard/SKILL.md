---
name: kb-onboard
description: Initialize and inspect a local kbkit Markdown knowledge base.
metadata:
  kbkit-api-version: v1
---

# kbkit onboarding

Use the local kbkit checkout or virtual environment configured by the user.

1. Run `python -m kbkit doctor`.
2. Discover or initialize the vault only after showing the proposed path and layout.
3. Never overwrite an existing vault during initialization.
4. Report the vault identity, profile state, index state, and excluded paths.
5. Ask for explicit confirmation before creating directories or changing profile data.

Use MCP for structured operations when it is configured. Use CLI for diagnostics and setup.
