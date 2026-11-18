# Contributing

## Project phase

kbkit is preparing its first release. The README describes verified user workflows. Record release evidence for the exact Git commit or tag in the E8 acceptance report.

## Development setup

Use the Python version currently configured in pyproject.toml, create a virtual environment, install the editable package, and run:

    python -m pip install -e .
    python -m unittest discover -s tests -v
    python -m kbkit doctor

## Change workflow

- Use a feature branch: feat/<short-name>, fix/<short-name>, docs/<short-name>, or test/<short-name>.
- Keep main buildable and tested.
- For architecture or persistence changes, add/update an ADR before implementation.
- Every behavior change must include tests and update the requirement-to-test traceability.
- Do not claim a performance target is met without reproducible benchmark evidence.
- Do not commit private vault content, real user knowledge bases, API keys, index files, transaction journals, or local logs.

## Design rules

- Markdown source files are authoritative; indexes/caches are derived.
- Core runtime has zero third-party dependencies unless an ADR explicitly changes the policy.
- CLI, Python API, and MCP call the same application services.
- Ambiguous writes fail closed; destructive operations require explicit authorization.
- Unknown Markdown syntax must not be silently rewritten or dropped.
- Git writes apply only to the chosen vault. Code knowledge bindings read authorized paths and refs from the named local repository.

## Commit convention

Use concise Conventional Commit-style messages, for example:
- docs(architecture): define transaction guarantees
- feat(search): add identifier matching
- fix(writer): reject ambiguous block selectors
- test(index): cover stale index detection

## Decision records

Material decisions and reversals belong in docs/adr/. Each ADR includes status, context, decision, alternatives, consequences, validation evidence, and migration implications.
