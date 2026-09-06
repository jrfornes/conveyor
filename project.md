# Project

<!-- Edit this file for your project. Agents read it after the shared constitution. Keep it short. -->

Use **either** the legacy single fence **or** a named gate catalog — not both.

## Test command

```
<!-- e.g. make test / npm test / pytest -q -->
```

When this is the only gate section, it runs as implicit gate `test` on every belt `ready` and `pass`. An empty fence (or only an HTML comment) is skipped.

<!-- Or replace the Test command section with:

## Gates

test:
```
make test
```

lint:check:
```
npm run lint
```

## Required on

coder ready: test, lint:check
reviewer pass: test

Gate names: `^[a-z][a-z0-9:-]*$`. Substitutions: `{inbound}` (in-process handoff commit), `{head}` (worktree HEAD). -->

Must be run from the worktree root. Must exit non-zero on any failure.

## Language and layout

<!-- e.g. Python 3.12, src/ layout, tests in tests/. -->

## Conventions that count as requirements

<!-- Only things the reviewer should treat as findings if violated, e.g. "all public functions have docstrings", "no new dependencies without a note in the commit". Leave empty if none. -->

## Things agents must not touch

<!-- e.g. migrations/, generated/, vendored code. -->
