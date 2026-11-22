---
name: kb-author
description: Preview and apply precise, recoverable edits to a local kbkit vault.
metadata:
  kbkit-api-version: v1
---

# kbkit authoring

1. Use `kb_outline` to obtain a heading path or `kb_search` to obtain a block ID. For line edits, read the surrounding lines with `kb_read` first.
2. Preview with `kb_write_plan`. For a new note, send `{"operations":[{"operation":"create","path":"first-note.md","content":"# First note\n\nLocal knowledge\n"}]}`. For the CLI, write only the array to the operations file. The destination directory must exist.
3. To insert text into a section, use `append` with `{"path":"note.md","heading_path":["Parent","Child"]}` as the selector. A single `block_id` or `path` with a `line_range` also works. Review `previews`, including `position` and the surrounding text. Stop if the selection is missing, ambiguous, or incorrect.
4. Read all previews via `next_offset` and verify their `plan_hash` is unchanged. Pass the same operations and hash to `kb_write_apply`, with the first preview's `transaction_id` as the `request_id`. Confirm destructive edits when the user has not already authorized them. Compare the returned `positions` with the preview.
5. If a response is interrupted, call `kb_write_status` with the request UUID, or repeat the exact original request with that UUID. If it reports `divergent`, inspect the affected files and reconcile the conflict. Resume a pending transaction with `kbc recover <vault> --transaction-id <uuid>`. If `index_dirty` is true, fix the index problem and run `kb_index`.
6. Preserve the delete receipt. Use its `entry_id` with `kb_restore` to restore a deleted note when the original path is free.
