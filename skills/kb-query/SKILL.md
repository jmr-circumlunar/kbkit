---
name: kb-query
description: Search and read a local kbkit knowledge base with traceable citations.
metadata:
  kbkit-api-version: v1
---

# kbkit query

Use `kb_search` for retrieval and `kb_read` for source content.

- Preserve `path`, `block_id`, and any freshness state and reason.
- Default search omits inactive pages. Use `include_inactive: true` only when the task needs historical or potentially stale material, and cite the state.
- Use `knowledge history` to retrieve reviewed design revisions. Use the commit and path cited by a generated implementation map to verify an implementation claim.
- Read the Markdown source before presenting a high-confidence answer.
- Do not infer facts from an index snippet when the source file cannot be read.
