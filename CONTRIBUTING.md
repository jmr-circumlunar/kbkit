# Contributing

## Development setup

Use Python 3.11 or newer and create a virtual environment. The core package has no runtime dependencies.

```bash
python -m venv .venv
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Engineering rules

- Keep core runtime code in the Python standard library unless an ADR explicitly approves an exception.
- Keep optional integrations behind adapter boundaries; do not make them import-time requirements for the core.
- Add tests with every behavior change.
- Do not claim performance or reliability targets are met without reproducible benchmark or fault-injection evidence.
- Treat Markdown source files as authoritative and indexes/caches as rebuildable derived data.
- Destructive or ambiguous writes must fail closed and provide actionable diagnostics.

## Commit convention

Use concise Conventional Commit-style messages, for example:
- `feat(search): add identifier matching`
- `fix(writer): reject ambiguous block selectors`
- `test(index): cover stale index detection`
- `docs(architecture): record storage decision`

## Decision records

Material architectural choices and reversals belong in `docs/adr/`. Include context, decision, alternatives, consequences, and validation plan.
