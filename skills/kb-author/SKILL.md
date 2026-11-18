---
name: kb-author
description: Write to a local kbkit knowledge base with preview, conflict checks and recovery semantics.
kbkit-api-version: v1
---

# kbkit authoring

Use `kb_write_plan` for preview and `kb_write_apply` for application. For a new Markdown note, the current service accepts an `append` operation with `path` and `content`. Ensure the destination directory exists.

1. Select a block or document with an explicit selector.
2. Call `kb_write_plan` first and inspect the returned change paths. Compare the intended content with the current file in the Agent when a textual diff is needed.
3. Require `expected_hash` for edits to existing content.
4. Ask for confirmation before applying a non-trivial write, move, rename or delete.
5. Stop on zero matches, multiple matches, parse ambiguity or a hash conflict.
6. Surface `rolled_back`, `partially_applied`, `unknown`, `completed` and `divergent` states.
7. Never silently rewrite unknown Markdown or Frontmatter syntax.
