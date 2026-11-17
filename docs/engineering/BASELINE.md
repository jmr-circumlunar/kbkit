# Engineering Baseline

## Current bootstrap baseline

- Python 3.11+ is the current repository scaffold setting, not yet the final product compatibility decision.
- src/ package layout.
- Core runtime is intended to have zero third-party dependencies.
- Standard-library unittest for bootstrap tests.
- Windows is the first local development and validation platform.
- Linux is currently a CI compatibility smoke target, not yet a formal support promise.
- SQLite FTS5 availability is checked at runtime, not assumed.
- CLI, Python API, and MCP must call the same application/service layer.

## Dependency policy

The project requirement is zero third-party runtime dependencies in Core. Build-time dependencies are tracked separately. Optional adapters must not be imported by Core at import time. Any runtime dependency exception requires an ADR and a review of I3.

## Source of truth

Markdown files are authoritative. Search indexes and caches are rebuildable derived artifacts. Vault profile and transaction journal are not automatically disposable; their persistence and Git policy are defined in DATA_LAYOUT.md.

## Platform policy

Windows is the first-class development target. Filesystem durability, locking, atomic replacement, path handling, permissions, and file-handle semantics require Windows-specific tests. POSIX behavior must not be assumed to transfer.

## Quality gates

1. Unit and integration tests pass.
2. Core import does not load optional adapters.
3. FTS5 capability is detected and reported.
4. Package can be installed in a clean environment.
5. Architecture decisions are recorded before persisted formats or public APIs are frozen.
6. P0 safety tests pass before any write capability is released.
