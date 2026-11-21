---
name: kb-author
description: Preview and apply precise, recoverable edits to a local kbkit vault.
metadata:
  kbkit-api-version: v1
---

# kbkit authoring

1. Use `kb_outline` to obtain a heading path or `kb_search` to obtain a block ID. For line edits, read the surrounding lines with `kb_read` first.
2. Preview with `kb_write_plan`. For a new note, send `{"operations":[{"operation":"create","path":"first-note.md","content":"# First note\n\nLocal knowledge\n"}]}`. The destination directory must exist.
3. To insert text into a section, use `append` with `{"path":"note.md","heading_path":["Parent","Child"]}` as the selector. A single `block_id` or `path` with a `line_range` also works. Review `previews`, including `position` and the surrounding text. Stop if the selection is missing, ambiguous, or incorrect.
4. Pass the same operations and the returned `plan_hash` to `kb_write_apply`. Confirm destructive edits when the user has not already authorized them. Compare the returned `positions` with the preview.
5. If the tool reports `divergent`, use the transaction reference and `kbc recover <vault>` to inspect recovery. If `index_dirty` is true, check the transaction before retrying a write and run `kb_index` after correcting the index error.
6. Preserve the delete receipt. Use its `entry_id` with `kb_restore` to restore a deleted note when the original path is free.
