# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Conveyor is a local-first orchestrator for a configurable pipeline of Cursor CLI coding agents (default: Review belt, `coder → reviewer`), coordinated only through git worktrees and a file-based handoff queue. An optional `gate <role>` line can hold a role's first `ready` for operator approval. Implementation lives under `bin/` (entrypoints) and `lib/conveyor/` (Python ≥ 3.10, stdlib only). Agent-facing files (`constitution.md`, `constitution/`, `roles/`, `project.md`) ship verbatim into target repos via `conveyor init`.

## Reading order

1. `docs/conveyor-prd.md` — scope. Build §3, §7, §9. Appendix B is explicitly **not** to be built; leave at most a one-line `# later: B.x` comment at hook points.
2. `docs/conveyor-handoff-protocol.md` — **normative**. Every file format, directory, error code, repair text, and state transition. Wins over the PRD on anything but scope.
3. `docs/runbook.md` — the operator's view; the `conveyor` CLI output must match it (esp. §6 `conveyor status` format).
4. `constitution.md`, `constitution/*.md`, `roles/*.md`, `project.md` — shipped as-is into target repos. `intake/` is templated (operator-owned after first copy). **Do not edit these to make implementation easier.** If protocol and these disagree, fix the protocol doc and say so.
5. `docs/agent-orchestration-north-star.md` — the why; consult when a design choice is open.
6. `docs/later/orchestration-dashboard-spec.md` — deferred (PRD B.6); do not implement.

## Layout

```
bin/conveyor            operator CLI: init | start | stop [--now] | task [--delete] | status | log | resume
                        | import | intake | inbox | approve | reject | workflow
bin/handoff.sh          validator + audit gate (protocol §4–5); agents call this exact name
bin/role-loop.sh        per-role loop (protocol §6); supports --once for tests
bin/merge.sh            protocol §7
bin/hooks/commit-msg    byline hook (protocol §7.4)
bin/conveyor-ui         optional localhost cockpit launcher (`--demo` throwaway fixture)
bin/README.md           language decision, install, "Ambiguities resolved"
lib/conveyor/           board, config, handoff, layout, queue, util, presets, workflows, inbox, adapters, agent, intake, jira
intake/                 ticket-reviewer.md + rubric.md (operator-owned; not a coding role)
ui/                     optional Angular cockpit (not protocol)
test/fake-agent         scripted agent (protocol §11)
test/                   one file per protocol §9 invariant (1–12), plus M1/M2/M4 scenario tests
```

## Tests

```bash
cd test && python3 -m unittest discover -p 'test_*.py'
```

Run without Cursor by pointing the loop at the fake agent:

```
CONVEYOR_AGENT_BIN=./test/fake-agent CONVEYOR_FAKE_SCRIPT=<script> bin/role-loop.sh --once
```

Milestones are gated by automated tests, in order M0 → M4 (PRD §9). M3 (first live Cursor run) is manual.

## Architecture essentials

Everything is a file or a git object; state is the directory a file sits in.

- **Identity** comes only from env: `CONVEYOR_ROLE`, `CONVEYOR_WORKTREE`, `CONVEYOR_ROOT`, `CONVEYOR_AGENT_BIN`. No script accepts identity as an argument.
- **Isolation**: `conveyor start` creates `.worktrees/<role>` on branch `conveyor-<role>`, writes the concatenated constitution + role file to `.cursor/rules/conveyor-role.mdc` in each worktree, and installs the shared `commit-msg` byline hook. Main checkout is the integration tree; no agent runs there.
- **Queues** live in `.conveyor/roles/<role>/`: `outbox/{tmp,}`, `sent/`, `failed/`, `inbox/{tmp,new,in_process,completed}/`, `seq`, `audit_pending/`, plus `.conveyor/board.tsv`, `.conveyor/needs-human/<task>/`, `.conveyor/logs/<role>/`. Protocol §2.3 has a single-writer table per directory; honor it.
- **Handoff = commit SHA + tiny validated file.** Agents write a three-line draft (`to`, `task`, `verdict`) to `./tmp/handoff.txt` and run `handoff.sh`. The validator fills `type`, `id`, `from`, `commit` (10-hex), `task_id`, `created_at`, and the body (full commit message). Permitted `(from,to,verdict)` triples are derived from `conveyor.conf` order, never hardcoded.
- **Audit gate**: first `handoff.sh` call for a candidate (sha256 of commit+to+task+verdict) exits 2 with `AUDIT_REQUIRED`; identical resubmission passes; any change re-challenges. `audit_count` in the board is written only by `handoff.sh`.
- **Role loop**: recover `in_process/` first (refuse if >1), dequeue oldest from `new/`, `merge.sh <commit>`, check ceilings, run the agent, then decide purely by counting `outbox/*.handoff` (1 = success, 0 = retry attempt with `--resume`, >1 = park). Delivery sweep moves outbox → recipient `inbox/new` and keeps `sent/`; idempotent via id lookup. `done` runs the `[global] integration` policy (default `merge` into main as `operator`; also `hold` and `command: <cmd>`, protocol §7.3).
- **Ceilings** park to `needs-human/` with a `reason` file: `max-retries`, `max-minutes`, `max-attempts`, `merge-conflict`, `untracked-collision`, `multiple-handoffs`, `no-rules`, `no-agent`, `no-task-file`, `done-command`. `conveyor resume` is the only way out.
- **Locks** are `mkdir` directories with a `pid` file, 30 s timeout, stale-pid recovery. Board writes: lock, rewrite whole file to `.tmp`, rename.

## Hard rules

- Every error code in protocol §4.5 must be produced by a test with the **exact** repair text.
- Every state change is a rename. No in-place writes to queue directories or `board.tsv`.
- Never parse agent prose to make a decision. The outbox is the only signal.
- When the protocol is ambiguous, refuse rather than guess, and record it under "Ambiguities resolved" in `bin/README.md`.
- No framework, no daemon beyond the role loops, no database. Applies to `bin/` and `lib/`; the Angular cockpit under `ui/` is optional and is not protocol.
- Commit-msg hook must be honored: `handoff.sh` rejects any HEAD whose last line is not `By <role>.` (`E_NO_BYLINE`).
