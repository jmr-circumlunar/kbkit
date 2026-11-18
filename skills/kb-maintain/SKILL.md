---
name: kb-maintain
description: Run a self-growth maintenance cycle for a local kbkit knowledge base.
kbkit-api-version: v1
---

# kbkit maintenance

Use this Skill when the user asks to update, review, audit or grow the knowledge base.

1. Confirm the authorized vault, code repositories, session sources and scan scope when the scope is first configured.
2. Run deterministic checks first. Collect file changes, index state, lint results, Git changes, test/CI evidence and pending transactions.
3. Apply configured safe actions directly. Safe actions are idempotent, reversible, source-linked and limited to derived indexes, reports, metadata normalization and new generated pages in the configured generated area.
4. Record every direct action with the task run, source hash, before/after hash, diff and result. A later review reads this audit trail and does not gate routine maintenance.
5. If model assistance is enabled, create candidates with source references, confidence, retention and proposed destination. Generated pages may be written directly only when the user has enabled generated-content mode and the destination is an isolated generated area.
6. Escalate authority changes, conflicting facts, merges, rewrites of existing canonical pages, moves, archival and deletion for user or Agent handling.
7. Apply direct writes through dry-run, expected-hash checks and the transaction service. Stop on a conflict or divergent journal.
8. Run post-write indexing and verification, then report applied, conflicted, failed, expired and deferred items.

The same flow is used for manual requests and scheduled maintenance.
