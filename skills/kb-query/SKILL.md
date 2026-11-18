---
name: kb-query
description: Search and read a local kbkit knowledge base with traceable citations.
kbkit-api-version: v1
---

# kbkit query

Use `kb_search` for retrieval and `kb_read` for source content.

- Preserve `relative_path`, `block_id`, line range, freshness and provenance fields.
- Treat `stale`, `index_dirty` and `partial` as visible result states.
- Use field, lifecycle and visibility filters when the request implies them.
- Read the Markdown source before presenting a high-confidence answer.
- Do not infer facts from an index snippet when the source file cannot be read.
