# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Conveyor is a local-first orchestrator for a two-role pipeline of Cursor CLI coding agents (coder → reviewer), coordinated only through git worktrees and a file-based handoff queue. **There is no code yet.** The repo is a specification bundle plus the agent-facing files that get shipped verbatim into target repos. The job of an implementer here is to build the scripts described in `IMPLEMENT.md`.

Not a git repository at the time of writing; `git init` before doing anything that assumes history.

## Reading order (from IMPLEMENT.md)

1. `docs/conveyor-prd.md` — scope. Build §3, §7, §9. Appendix B is explicitly **not** to be built; leave at most a one-line `# later: B.x` comment at hook points.
2. `docs/conveyor-handoff-protocol.md` — **normative**. Every file format, directory, error code, repair text, and state transition. Wins over the PRD on anything but scope.
3. `docs/runbook.md` — the operator's view; the `conveyor` CLI output must match it (esp. §6 `conveyor status` format).
4. `constitution.md`, `constitution/*.md`, `roles/*.md`, `project.md` — shipped as-is into target repos. **Do not edit these to make implementation easier.** If protocol and these disagree, fix the protocol doc and say so.
5. `docs/agent-orchestration-north-star.md` — the why; consult when a design choice is open.
6. `docs/later/orchestration-dashboard-spec.md` — deferred (PRD B.6); do not implement.

## Deliverables and layout to create

```
bin/conveyor            operator CLI: start | stop [--now] | task | status | log | resume
bin/handoff.sh          validator + audit gate (protocol §4–5); this exact name regardless of language
bin/role-loop.sh        per-role loop (protocol §6); supports --once for tests
bin/merge.sh            protocol §7
bin/hooks/commit-msg    byline hook (protocol §7.4)
bin/README.md           language decision + reason, install steps, "Ambiguities resolved" section
test/fake-agent         scripted agent (protocol §11): commit / draft / handoff / sleep / crash / exit
test/                   one file per protocol §9 invariant (1–12), plus M1/M2 scenario tests
test/fixtures/m3/       logs from the real-agent run (M3)
```

Language: one of Bash ≥ 4 (`set -euo pipefail`) or Python ≥ 3.10 stdlib-only. Not both. No build step, one-command install on macOS and Linux, no `flock(1)`. Keep non-test code under ~1,500 lines.

## Commands (once implemented)

Run without Cursor by pointing the loop at the fake agent:

```
CONVEYOR_AGENT_BIN=./test/fake-agent CONVEYOR_FAKE_SCRIPT=<script> bin/role-loop.sh --once
```

Milestones must be gated by automated tests, in order M0 → M4 (PRD §9, IMPLEMENT.md). Do not start a milestone before the previous one's exit criterion passes as a test.

## Architecture essentials

Everything is a file or a git object; state is the directory a file sits in.

- **Identity** comes only from env: `CONVEYOR_ROLE`, `CONVEYOR_WORKTREE`, `CONVEYOR_ROOT`, `CONVEYOR_AGENT_BIN`. No script accepts identity as an argument.
- **Isolation**: `conveyor start` creates `.worktrees/<role>` on branch `conveyor-<role>`, writes the concatenated constitution + role file to `.cursor/rules/conveyor-role.mdc` in each worktree, and installs the shared `commit-msg` byline hook. Main checkout is the integration tree; no agent runs there.
- **Queues** live in `.conveyor/roles/<role>/`: `outbox/{tmp,}`, `sent/`, `failed/`, `inbox/{tmp,new,in_process,completed}/`, `seq`, `audit_pending/`, plus `.conveyor/board.tsv`, `.conveyor/needs-human/<task>/`, `.conveyor/logs/<role>/`. Protocol §2.3 has a single-writer table per directory; honor it.
- **Handoff = commit SHA + tiny validated file.** Agents write a three-line draft (`to`, `task`, `verdict`) to `./tmp/handoff.txt` and run `handoff.sh`. The validator fills `type`, `id`, `from`, `commit` (10-hex), `task_id`, `created_at`, and the body (full commit message). Permitted `(from,to,verdict)` triples are derived from `conveyor.conf` order, never hardcoded.
- **Audit gate**: first `handoff.sh` call for a candidate (sha256 of commit+to+task+verdict) exits 2 with `AUDIT_REQUIRED`; identical resubmission passes; any change re-challenges. `audit_count` in the board is written only by `handoff.sh`.
- **Role loop**: recover `in_process/` first (refuse if >1), dequeue oldest from `new/`, `merge.sh <commit>`, check ceilings, run the agent, then decide purely by counting `outbox/*.handoff` (1 = success, 0 = retry attempt with `--resume`, >1 = park). Delivery sweep moves outbox → recipient `inbox/new` and keeps `sent/`; idempotent via id lookup. `done` triggers merge into main as `operator`.
- **Ceilings** park to `needs-human/` with a `reason` file: `max-retries`, `max-minutes`, `max-attempts`, `merge-conflict`, `multiple-handoffs`, `no-rules`. `conveyor resume` is the only way out.
- **Locks** are `mkdir` directories with a `pid` file, 30 s timeout, stale-pid recovery. Board writes: lock, rewrite whole file to `.tmp`, rename.

## Hard rules for implementers (from IMPLEMENT.md)

- Every error code in protocol §4.5 must be produced by a test with the **exact** repair text.
- Every state change is a rename. No in-place writes to queue directories or `board.tsv`.
- Never parse agent prose to make a decision. The outbox is the only signal.
- When the protocol is ambiguous, refuse rather than guess, and record it under "Ambiguities resolved" in `bin/README.md`.
- No framework, no daemon beyond the role loops, no database.
- Commit-msg hook must be honored: `handoff.sh` rejects any HEAD whose last line is not `By <role>.` (`E_NO_BYLINE`).
