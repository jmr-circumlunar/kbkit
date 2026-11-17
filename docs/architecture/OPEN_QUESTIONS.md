# Architecture Questions Requiring Decisions

These questions are deliberately left open in the bootstrap repository. They must be resolved with focused prototypes and ADRs before the corresponding implementation phase.

## A. Product and runtime boundaries

1. Is the built-in local web viewer actually in scope? The overview diagram includes one, while the interface summary says the view layer is fully delegated to third-party editors and that kbkit provides no rendering layer. Choose one consistent product boundary.
2. Which MCP transport and protocol version are targeted? A standards-compliant MCP server may require an optional SDK or a separately maintained adapter; reconcile this with the zero-third-party-dependency acceptance criterion.
3. Is Python 3.11+ the supported baseline, or should the package target a wider range? Confirm against the intended deployment environments.

## B. Storage and indexing

4. Where does the external index live on each supported OS, and how is a vault identity derived without path collisions or accidental cross-user leakage?
5. How are multiple processes coordinated when the index is external to the vault? Define locking, stale detection, crash recovery, and rebuild behavior.
6. What is the exact block identity contract? Define stable IDs, duplicate headings, block moves, heading edits, and fallback selectors.
7. What tokenizer contract is used for Chinese bigrams, ASCII identifiers, punctuation, mixed-language text, and query normalization? How are phrase, AND/OR, and identifier matching represented?

## C. Markdown compatibility

8. Which frontmatter YAML subset is accepted? Define quoting, lists, nested maps, booleans, nulls, dates, duplicate keys, invalid YAML, line endings, and byte-preserving edits.
9. How are wikilinks, aliases, headings, block IDs, embeds, callouts, tags, and escaped syntax parsed and round-tripped?
10. How are symlinks, path traversal, case sensitivity, Unicode normalization, and files changing during a read handled?

## D. Write consistency and recovery

11. The proposed multi-file redo journal is a recoverable sequence of replacements, not a globally atomic filesystem transaction. Which visibility guarantee is promised to concurrent readers?
12. How are writer locks acquired and released across process crashes? What happens if a user/editor modifies a target during recovery?
13. What are the exact journal state transitions, fsync policy, Windows durability behavior, and recovery idempotency rules?
14. Which data belongs in the journal, snapshots, Git, and the external index? Define retention, privacy, and cleanup rules.
15. Does a failed index update leave correct source content committed with an explicit dirty marker, or is the user operation considered incomplete? Define API response semantics.

## E. Git, automation, and security

16. Is Git optional for normal use, and which operations require a repository?
17. How are credentials, hooks, unsafe Git configuration, and untrusted repositories handled?
18. Which scheduled-task mechanisms are supported on Windows/Linux, and how are duplicate jobs, missed runs, logs, and uninstall handled?
19. What is the permission model for private/internal/public content, and where are secrets excluded from indexing and model calls?

## F. Distribution and acceptance

20. Is pip the primary distribution? Is zipapp a supported promise or an experimental target? Clarify the build-time dependency and native DLL constraints.
21. Which MCP/client compatibility matrix is required?
22. Publish golden retrieval datasets, relevance labels, metric definitions, benchmark hardware, and reproducibility instructions before claiming Hit@K/MRR or latency targets.
23. Define backup/restore acceptance and fault-injection cases per operating system.

## Initial recommendation

Do not block the bootstrap repository on all answers. Keep interfaces small, write ADRs when a decision affects persisted formats or public APIs, and prototype high-risk assumptions before implementing the full module inventory.
