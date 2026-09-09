# Conveyor

A local-first orchestrator for a configurable pipeline of Cursor CLI coding agents (default: Review belt, `coder → reviewer`), coordinated entirely through git worktrees and a file-based handoff queue. An optional `gate <role>` line can hold a role's first `ready` for operator approval. No daemon beyond one loop per role, no database.

## Install

```bash
git clone <this repo> ~/conveyor
export PATH="$HOME/conveyor/bin:$PATH"
```

See [`bin/README.md`](bin/README.md) for language choice, PATH details, and `conveyor init`.

## Use

In a git checkout:

```bash
conveyor init              # copy bundle files; safe to re-run
# edit project.md and conveyor.conf (models)
conveyor start
conveyor task <name>       # create work; pipe or type the spec
conveyor status
conveyor log coder
conveyor log coder --prompt   # exactly what the agent was told
conveyor resume <task>     # after a needs-human park
conveyor import --source manual --title "..."
conveyor intake <id>
conveyor inbox approve <id>   # or inbox skip
conveyor approve <id>      # gated ready; or reject
conveyor workflow list
conveyor workflow activate <slug>
conveyor-ui                # optional localhost cockpit
conveyor stop              # or stop --now
conveyor uninstall --yes   # tear down runtime; add --bundle for init files too
```

Operator docs: [`docs/runbook.md`](docs/runbook.md).

## Test

```bash
cd test && python3 -m unittest discover -p 'test_*.py'
```

Runs the fake-agent suite (no Cursor required).

## Release

See [`docs/release-review.md`](docs/release-review.md) for the RC / official-usable checklist.
`v0.4.0-rc1` is tagged. See [`CHANGELOG.md`](CHANGELOG.md).

## Layout

```
bin/                   conveyor, handoff.sh, role-loop.sh, merge.sh
lib/conveyor/          Python stdlib implementation
docs/                  PRD, protocol, runbook
constitution.md        shipped into target repos
constitution/
roles/
project.md             per-project template
conveyor.conf.example
tasks/
test/                  protocol invariant + milestone tests
```

[`bin/conveyor-ui`](bin/conveyor-ui) launches an optional localhost cockpit ([`ui/`](ui/), Angular + Material). `conveyor-ui --demo` uses a throwaway fixture. The CLI is enough to operate the pipeline.

The reference behavior comes from SwarmForge (`github.com/unclebob/swarm-forge`, read September 2026). No code from it is used or should be; it had no licence file at that time.
