---
name: kb-query
description: Search and read bounded knowledge with traceable citations.
metadata:
  kbkit-api-version: v1
---

# kbkit query

- Use the index synchronized at the start of the session. If the host has no active SessionStart integration, run `kb_sync` once when starting work with the vault. Run it again if the user just edited Markdown outside kbkit.
- Start with `kb_search`. Use `path` for a directory prefix and `kind`, `state` or `tags` when known. Inspect `kb_facet` for values. The default omits inactive, unknown and stale pages. Request `include_inactive` when investigating history and cite the state.
- Preserve `path`, `block_id`, `lines` and any freshness state or reason. Follow `next_offset` if more candidates are needed.
- Call `kb_read` with the returned `block_id` or a line range to verify the evidence in the source. If an external edit invalidated the block ID, run `kb_sync` and search again before citing or writing. For larger documents, pass the heading path obtained from `kb_outline`.
- For a reviewed historical design revision, use `kbc knowledge history <vault> <note>`. For a code claim, verify the file at the commit cited by the implementation map.
