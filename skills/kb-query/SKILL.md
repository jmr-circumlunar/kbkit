---
name: kb-query
description: Search and read bounded knowledge with traceable citations.
metadata:
  kbkit-api-version: v1
---

# kbkit query

- Start with `kb_search`. Use `path` for a directory prefix and `kind`, `state` or `tags` when known. Inspect `kb_facet` for values. The default omits inactive, unknown and stale pages. Request `include_inactive` when investigating history and cite the state.
- Preserve `path`, `block_id`, `lines` and any freshness state or reason. Follow `next_offset` if more candidates are needed.
- Call `kb_read` with the returned `block_id` or a line range to verify the evidence in the source. Search again if the block ID belongs to an earlier version. For larger documents, pass the heading path obtained from `kb_outline`.
- For a reviewed historical design revision, use `kbc knowledge history <vault> <note>`. For a code claim, verify the file at the commit cited by the implementation map.
