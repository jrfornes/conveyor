# Conveyor

A local-first orchestrator for a two-role pipeline of Cursor CLI coding agents (coder → reviewer), coordinated entirely through git worktrees and a file-based handoff queue. No UI, no daemon beyond one loop per role, no database.

This bundle is the specification and the shipped agent-facing files. There is no code yet.

```
README.md                          this file
IMPLEMENT.md                       brief for the agent or person building it
docs/
  conveyor-prd.md                  scope (v0.3); Appendix B = deferred features
  conveyor-handoff-protocol.md     normative: formats, directories, state machine, errors
  runbook.md                       install, configure, operate, recover
  agent-orchestration-north-star.md  the principles behind every choice
  later/orchestration-dashboard-spec.md  deferred (PRD Appendix B.6)
constitution.md                    shipped into target repos: precedence
constitution/{engineering,workflow,handoffs}.md
roles/{coder,reviewer}.md
project.md                         per-project template
conveyor.conf.example
tasks/                             operator task files live here
.gitignore
```

To build it: hand `IMPLEMENT.md` to an agent (or read it yourself). To use it once built: `docs/runbook.md`.

The reference behavior comes from SwarmForge (`github.com/unclebob/swarm-forge`, read September 2026). No code from it is used or should be; it had no licence file at that time.
