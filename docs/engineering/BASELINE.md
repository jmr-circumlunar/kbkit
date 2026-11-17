# Engineering Baseline

## Initial baseline

- Python 3.11+
- `src/` package layout
- Standard-library-only core runtime
- `unittest` for bootstrap tests
- Windows and Linux as first-class development/CI platforms
- SQLite FTS5 capability is checked at runtime rather than assumed
- CLI, Python API, and future MCP transport must call the same application/service layer

## Dependency policy

The current project requirement is zero third-party runtime dependencies in the core. This does not mean every optional distribution format or protocol adapter can be implemented without dependencies. Each exception must be isolated, optional, documented, and approved through an ADR.

The build backend is a development/build-time dependency, not a runtime dependency. The initial package metadata uses setuptools; the build environment may download it when building/installing the package.

## Source of truth

Markdown documents are authoritative. Search indexes, caches, and other derived artifacts must be reproducible from source documents and must not be committed to a user's knowledge-base repository by default.

## Platform policy

CI should test supported Python versions on Windows and Linux. Filesystem durability, locking, atomic replacement, path handling, and permission semantics require platform-specific tests; POSIX guarantees must not be assumed to hold identically on Windows.

## Quality gates

1. Unit tests pass.
2. Importing the core package does not import optional integrations.
3. FTS5 capability is detected and reported.
4. Package can be installed in a clean environment.
5. Architecture decisions are recorded before irreversible coupling is introduced.
