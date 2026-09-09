# Conveyor — Product Requirements Document

**Product:** Conveyor, a local-first orchestrator for a pipeline of AI coding agents
**Status:** Draft v0.3 — MVP scope, synced with `conveyor-handoff-protocol.md`
**Date:** 3 September 2026
**Supersedes:** v0.2; v0.1 full scope preserved in Appendix B
**Inputs:** `agent-orchestration-north-star.md`, `later/orchestration-dashboard-spec.md`
**Normative companion:** `conveyor-handoff-protocol.md` wins on file formats, layout, and state transitions.

---

## 1. Summary

Conveyor runs a fixed coding pipeline of Cursor CLI agents against one git repository. The default pack is two roles (coder → reviewer); a three-pack (specifier → coder → reviewer) adds a spec-approval gate. Agents are isolated in git worktrees, run headless one task at a time, and hand work to each other only through validated commit-bearing files in inbox/outbox directories. Intake (manual or optional Jira) is a separate one-shot ticket-reviewer, not a coding role. Files remain the system of record; the UI wraps CLI commands.

The thesis is unchanged from the north star: **coordinate agents through the filesystem and git, keep every mechanism boring and inspectable, and make each agent own one way the work can go wrong.**

The MVP is a deliberate subset. Every north-star idea not built here is listed in Appendix B with the reason it was deferred and what it would take to add. Nothing in the MVP should make those additions harder.

---

## 2. Problem

Multi-agent coding setups fail in predictable ways: two agents mutate the same tree; the agent that wrote the code is the one that declares it done; one long session forgets its constraints; orchestration hides in a framework you can't watch or resume; and a stuck task retries until the bill arrives.

Conveyor's MVP addresses the first, second, third, and last of these with git worktrees, a forced second look, one fresh context per task, and a retry ceiling. Everything is a file you can `cat`.

---

## 3. MVP scope

### In
- Cursor CLI (`agent` / `cursor-agent`) as the only backend, run in print mode (`-p`) with `--force`.
- Two or three coding roles from `conveyor.conf` (default two-pack: **coder** then **reviewer**; optional three-pack: **specifier**, **coder**, **reviewer**), each on a configured model.
- One git worktree per role plus the main checkout as the integration tree.
- A file-based handoff protocol with a single validator script and a two-call audit gate.
- A single loop script per role that dequeues, runs the agent headless, validates the handoff, and forwards.
- Reviewer may pass (→ Done) or hand back to coder with findings, bounded by `max_retries`.
- A per-task retry ceiling and per-task wall-clock ceiling that park the task in `needs-human/`.
- One log file per agent run; a `conveyor status` command that prints queue state from `ls`.

### Out (see Appendix B)
- Any web dashboard, chat, chime, or pane viewer.
- tmux, interactive sessions, wake-ups, watchdogs.
- Clarification channel, review comments per document, batch receive, back-propagation, 4+/six-pack templates.
- Any backend other than Cursor.
- Mandatory mutation/CRAP/DRY tooling.
- Token/cost metering.
- Forge (multi-project) mode.

---

## 4. Users

| Persona | Need | Surface |
|---|---|---|
| Operator (you) | Write a task, start the run, read the branch, unstick parked tasks | `tasks/*.md`, `conveyor` CLI, `tail -f` |
| Agent | Receive one task, do it, hand off unambiguously | `.cursor/rules/`, handoff validator |

Single operator, single machine, single project.

---

## 5. Design principles (binding)

1. **One strong agent with a good harness is the default.** The reviewer exists because it owns one failure mode: unverified claims of completion. Add a third role only when you can name the failure the current two miss.
2. **Prefer existing tools to new abstractions.** Git for isolation and history, directories for queues, log files for observability, Cursor's own `.cursor/rules` for prompt injection.
3. **Process is enforced, not requested.** Rules live in scripts that refuse, not prompts that ask.
4. **Filesystem is the system of record.** Restart = re-run the loop.
5. **Refuse ambiguity.** A helper that guesses is worse than one that stops.

---

## 6. System overview

```
conveyor.conf ──► conveyor start
                     │
                     ├─ git worktree per role (.worktrees/<role>)
                     ├─ .cursor/rules/conveyor-role.mdc written per worktree
                     └─ one loop process per role
                            │
   loop: inbox/new ─► in_process ─► agent -p --model M --force "…" ─► validate handoff
                                                                      │
                                              ok ─► recipient's inbox/new  (+ merge into main on Done)
                                              audit ─► AUDIT_REQUIRED, rerun agent with --resume
                                              ceiling hit ─► needs-human/
```

Components (all shell or one small scripting language, a few hundred lines total):

| Component | Responsibility |
|---|---|
| `conveyor start` | Read config, create worktrees, write role rules, launch one loop per role. |
| `conveyor stop` | Signal loops; they finish the in-process item and exit. |
| `conveyor task <name>` | Create `tasks/<name>.md` from stdin or `$EDITOR`, enqueue to coder. |
| `conveyor status` | Print every queue directory and `board.tsv`. |
| `conveyor resume <task>` | Move a parked task back to a role's inbox after human fix. |
| `role-loop.sh` | The per-role daemon described in §7.4. |
| `handoff.sh` | The only way to send. Validator + audit gate (§7.3). |
| `merge.sh` | Merge a handoff's commit into the recipient worktree, idempotently. |

---

## 7. Functional requirements

**M** = must, **S** = should. All are MVP unless marked S.

### 7.1 Configuration (CFG)

| ID | Pri | Requirement |
|---|---|---|
| CFG-1 | M | `conveyor.conf`, one role per line in pipeline order: `role <name> <model> [max_retries=N] [max_minutes=N] [max_attempts=N] [cli-args…]`. Two or three coding roles. Default two-pack: `coder` then `reviewer`. Optional three-pack: `specifier`, `coder`, `reviewer`. An optional `[inbox]` section holds Jira adapter settings. |
| CFG-2 | M | Model names are strings passed straight to `agent --model`. At start, run `agent models` and fail if a configured model is not listed. |
| CFG-3 | M | Role names contain no underscores or path separators. |
| CFG-4 | M | Defaults: `max_retries=3`, `max_minutes=120`, `max_attempts=3`. |
| CFG-5 | S | A `[global]` line for the `agent` binary path and extra flags (e.g. `--trust`). |

### 7.2 Isolation (ISO)

| ID | Pri | Requirement |
|---|---|---|
| ISO-1 | M | `conveyor start` runs `git worktree add --force -B conveyor-<role> .worktrees/<role> HEAD` for each role. The main checkout is the integration tree; no agent runs there. |
| ISO-2 | M | Each worktree gets `.cursor/rules/conveyor-role.mdc` (gitignored) containing the constitution and role prompt. Cursor reads this automatically. Agents never read outside their tree. |
| ISO-3 | M | Loops export `CONVEYOR_ROLE` and `CONVEYOR_WORKTREE`; `handoff.sh` reads identity only from env. |
| ISO-4 | M | Scratch is `./tmp/` in the worktree. `handoff.sh` rejects draft paths outside the worktree. |
| ISO-5 | M | `.worktrees/`, `.conveyor/`, and `.cursor/rules/conveyor-role.mdc` are gitignored. |

### 7.3 Handoff protocol (HND)

| ID | Pri | Requirement |
|---|---|---|
| HND-1 | M | One message type: `git_handoff`. Payload is a commit SHA. Prose goes in the commit message and `tasks/<name>.md`. |
| HND-2 | M | Agent-authored draft has exactly three headers: `to`, `task`, `verdict` (`ready` \| `pass` \| `findings`; the validator enforces the permitted `(from, to, verdict)` triples from the protocol spec §3.2). Reserved headers (`from`, `commit`, `id`, `*_at`) are rejected. |
| HND-3 | M | `handoff.sh` fills `from` from env, `commit` from worktree HEAD canonicalized to 10 hex chars, `id` from a per-worktree locked sequence counter, `created_at` now. Agents never type SHAs. |
| HND-4 | M | Every validator error prints repair guidance an agent can act on. |
| HND-5 | M | Outbox write is atomic: `outbox/tmp/<id>.tmp` → rename → `outbox/<id>.handoff`. |
| HND-6 | M | Filename `<timestamp>_<seq>_from_<sender>_to_<recipient>.handoff`. Headers are authoritative. |
| HND-7 | M | The sending role's loop moves `outbox/*.handoff` to the recipient's `inbox/new/` (rename), stamping `enqueued_at`, and keeps a copy in `sent/`. Idempotent: an id already in `sent/` is not re-delivered. |
| HND-8 | M | Queue state is the directory: `inbox/new/` → `inbox/in_process/` → `inbox/completed/`. Each timestamp header is written by exactly one script. |
| HND-9 | M | `merge.sh` checks `git merge-base --is-ancestor` before merging, so re-delivery is a no-op. |
| HND-10 | M | Commit-msg hook appends `By <role>.` in each worktree. `handoff.sh` rejects a HEAD whose message lacks the byline. |

### 7.4 Role loop (LOOP)

| ID | Pri | Requirement |
|---|---|---|
| LOOP-1 | M | On start, resume any item in `in_process/` before touching `new/`. Refuse to start if more than one item is in `in_process/`. |
| LOOP-2 | M | Dequeue the oldest item in `new/` (rename to `in_process/`, stamp `dequeued_at`). |
| LOOP-3 | M | Build the prompt: `Re-read your role and constitution.` + task file text + inbound handoff headers + (for coder retries) the reviewer's findings from the previous commit message. |
| LOOP-4 | M | Run `agent -p --model <model> --force --output-format stream-json "<prompt>"` with `cwd` = worktree. Stream to `.conveyor/logs/<role>/<task>_<attempt>.jsonl`. |
| LOOP-5 | M | After the agent exits, expect exactly one file in `outbox/`. Zero → attempt failed; increment retry; rerun with `--resume <session>` and the validator's message. More than one → park (ambiguous). |
| LOOP-6 | M | Reviewer `pass` → merge into main checkout (`merge.sh`), mark `board.tsv` lane `done`, move item to `completed/`. Reviewer `findings` → deliver to coder's inbox. Coder → deliver to reviewer. |
| LOOP-7 | M | Stop signal: finish the current item, then exit. Never kill an agent mid-run. |
| LOOP-8 | S | A `--once` flag runs one item and exits, for testing. |

### 7.5 Verification (VER)

| ID | Pri | Requirement |
|---|---|---|
| VER-1 | M | Two-call audit gate: the first `handoff.sh` call for a candidate (commit + draft fingerprint) is refused with `AUDIT_REQUIRED` and instructions to re-read the task and trace each requirement to evidence. Fingerprint stored under `.conveyor/audit_pending/<role>/`. Only an identical resubmission is accepted; any change resets the challenge. |
| VER-2 | M | Each challenge increments `audit_count` in `board.tsv` under a file lock. Only `handoff.sh` writes this column. |
| VER-3 | M | The reviewer role prompt mandates: run the project's test command; read the diff against the task; verdict `findings` if any requirement lacks evidence. Reviewer never edits code. |
| VER-4 | M | Coder and reviewer are configured with models from different families by default (documented in the sample config), so the second look is uncorrelated with the first. |

### 7.6 Prompt constitution (CON)

| ID | Pri | Requirement |
|---|---|---|
| CON-1 | M | Layered files, all versioned in the repo: `constitution/engineering.md`, `constitution/workflow.md`, `constitution/handoffs.md`, `project.md`, `roles/coder.md`, `roles/reviewer.md`. `constitution.md` declares precedence. |
| CON-2 | M | `conveyor start` concatenates these into each worktree's `.cursor/rules/conveyor-role.mdc`. |
| CON-3 | M | Each role file ≤ 2 pages with `## Owns` and `## Does not own`. The handoff contract is generated from `conveyor.conf` into the rules file (CON-2) and is not part of the role file. |
| CON-4 | M | Task intent lives in `tasks/<name>.md`, committed by the operator, re-read by agents as operator intent. |

### 7.7 Board and ceilings (BUD)

| ID | Pri | Requirement |
|---|---|---|
| BUD-1 | M | `.conveyor/board.tsv`: `name  lane  created_at  updated_at  task_id  audit_count  retry_count  started_at`. Lanes: `coder`, `reviewer`, `needs-human`, `done`. Written only by `handoff.sh` and the loops, under a file lock. |
| BUD-2 | M | `retry_count` exceeds `max_retries` → move item to `.conveyor/needs-human/<task>/` with a `reason` file, lane `needs-human`, loop continues to next item. |
| BUD-3 | M | Elapsed time since first `dequeued_at` exceeds `max_minutes` → same parking, checked between attempts (not mid-run). |
| BUD-4 | M | `conveyor resume <task> [--to <role>]` moves a parked item back to a role's `inbox/new/`, preserving `task_id`, `audit_count`, `retry_count`. |

### 7.8 Observability (OBS)

| ID | Pri | Requirement |
|---|---|---|
| OBS-1 | M | `conveyor status` prints, per role: in-process item and its age, count in `new/`, last completed item; then parked tasks with reasons; then `board.tsv`. |
| OBS-2 | M | Every agent run has a stream-json log; a `conveyor log <role> [task]` command pretty-prints tool calls and final text. |
| OBS-3 | M | `git log` on any branch shows `By <role>.` on every commit. |

---

## 8. Non-functional requirements

- **Footprint:** shell (or one scripting language) + git + Cursor CLI. No daemon beyond the role loops. No database, no framework.
- **Durability:** every state change is an atomic rename; TSV writes take a lock; `conveyor start` after a kill -9 resumes with no duplicate delivery and no lost card.
- **Resilience:** malformed handoff or TSV row is moved to `failed/` and logged once; loops keep running.
- **Testability:** `role-loop.sh --once` and a fake `agent` binary (env `CONVEYOR_AGENT_BIN`) that writes a scripted commit and draft, so the full protocol runs under test without Cursor.
- **Portability:** macOS and Linux.
- **Security:** Cursor CLI manages its own auth. Confirm whether `-p` requires `CURSOR_API_KEY` on your plan; Conveyor never stores it.

---

## 9. Milestones

| Milestone | Scope | Exit criterion |
|---|---|---|
| **M0 — Harness** | CFG, ISO, CON | `conveyor start` creates two worktrees, each with role rules; `agent models` check passes. |
| **M1 — Protocol** | HND, LOOP with fake agent | A scripted coder → reviewer → done round-trip using only files; kill -9 mid-run resumes cleanly. |
| **M2 — Gate** | VER-1, VER-2, HND-10 | Fake agent's first handoff is refused; identical second passes; `audit_count` = 1; bylines present. |
| **M3 — Real agents** | LOOP-4, VER-3, VER-4 | A real task on a real repo completes with Cursor, reviewer issues findings at least once, coder addresses them. |
| **M4 — Ceilings** | BUD, OBS | A deliberately impossible task parks itself in `needs-human` within `max_retries`; `conveyor status` explains why. |

Ship after M4. Then pick from Appendix B.

---

## 10. Success metrics

- Zero merge conflicts from concurrent agent writes across 20 runs.
- ≥ 30% of first-submission handoffs are changed after the audit challenge.
- 100% of kill -9 interruptions resume with no duplicate delivery or lost card.
- No task exceeds its ceilings without being parked.
- Operator can state every task's status from `conveyor status` alone.
- Blank repo to working M1 in under one hour.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Cursor CLI is beta; flags or rules loading change | Pin the CLI version in `conveyor.conf`; a smoke test at `conveyor start` runs `agent -p "echo ok"` and checks that rules were loaded. |
| Headless `-p` needs an API key not covered by the plan | Verify before M3; documented in setup. |
| Agent ignores the validator and writes handoffs by hand | Files not created via `handoff.sh` lack `id`/`from`; loops move them to `failed/`. |
| Reviewer and coder converge on the same blind spots | Different model families by default (VER-4); measure audit-change rate. |
| Model roster changes under you | Model names in config; startup check against `agent models`. |
| Two roles turn out to be too few | Appendix B.3 is designed to slot in without changing the protocol. |

---

## 12. Open questions

1. Reviewer edits: strictly none (current), or allowed to fix trivial issues (formatting) and forward?
2. Should the coder be allowed to reply to findings with a rationale for *not* changing something, and does the reviewer then have to accept it?
3. ~~Merge into `main` on reviewer pass automatically, or leave the branch?~~ Resolved: configurable via `[global] integration` — `merge` (default), `hold` (leave the branch), or `command: <cmd>` (hand off to a hook, e.g. open a PR). See protocol §7.3.
4. Shell vs. one scripting language for the loops. Criteria: file locks and atomic rename ergonomics.

---

## Appendix A — Review checklist (from the north star)

- Can two agents ever write to the same file at the same time?
- Is the agent that says "done" different from the agent that decides "done"?
- Can each agent's full context fit in one screen of instructions?
- Can a human read every handoff and know what was asked and delivered?
- Can you `ls` your way to the current state of every task?
- Is there exactly one place a human must approve, and is it early?
- Is the order of work a config file or an agent's opinion?
- If the machine reboots mid-run, what happens when you start it again?
- What stops a task that has retried nine times?

MVP answers: yes to 1, 2, 3, 4, 5, 7, 8, 9. Item 6 is deferred (B.5): in the MVP the operator's task file is the spec, so the human decision happens before the run rather than as a gate inside it.

---

## Appendix B — Deferred scope, mapped to the north star

Everything from v0.1 and the north-star document that is not in the MVP. Each item states why it was deferred and what adding it touches. The MVP protocol is intended to accept every one of these without a redesign.

### B.1 More backends (north star: Design stance §2; v0.1 CFG-5, CON-5)
- **Deferred because:** Cursor's `--model` already gives model-per-role; a second CLI means a second prompt-injection mechanism and a second set of moving flags.
- **Adding it:** a `backend` column in `conveyor.conf`; a per-backend launch function; a per-backend rule-injection method (Claude Code: `--append-system-prompt-file`; Codex: `--rules`). `handoff.sh` and the queues are untouched.

### B.2 Interactive sessions: tmux, wake-ups, watchdog, pane capture (north star: Ideas 5, 7; v0.1 DUR-5, ISO-3 env, HND-7 wake)
- **Deferred because:** headless `-p` gives fresh context per task for free and removes a long-lived process per role. You lose the ability to steer mid-task.
- **Adding it:** a `session=interactive` option per role; loops send `You have new handoff mail…` into the pane instead of spawning `-p`; a `ready.sh` the agent runs itself; the watchdog re-attaches missing panes. `.cursor/rules` injection still works in interactive mode.

### B.3 More roles and pipeline templates (north star: Ideas 3, 7; v0.1 CFG-4, PIP-1..5, VER-5)
- **Partially in scope:** coding pipelines of any length (≥ 1); `conveyor workflow activate <slug>` over saved presets in `.conveyor/workflows/`; an optional `gate <role>` line holding that role's `ready` for the operator (a three-role pipeline with no `gate` line gates its first role, preserving the original three-pack behaviour; `gate none` states the ungated case explicitly); findings always go to the penultimate role, and a one-role pipeline has none.
- **Still deferred:** four+/six-pack, batch receive mode (PIP-4), `back-one` / `back-all` merge-only handoffs with a `non-forwarding` header (PIP-2), structural Done where the last role's `to:` lists every other role (PIP-3).

### B.4 Mandatory verification tooling (north star: Idea 2; v0.1 VER-4)
- **Deferred because:** it requires CRAP/DRY/mutation/spec-mutation tools wired into the target project first, and a hardener role with something to run.
- **Adding it:** `constitution/engineering.md` names the tools; differential mutation against a committed manifest, never `--mutate-all`, one tool at a time; Gherkin specs mutation-tested so decorative acceptance tests are caught. Coverage is a hint, mutation score is the truth.

### B.5 Human gates: approval and clarification (north star: Idea 6; v0.1 HUM-1..4, spec F3–F7)
- **Partially in scope:** human intake approval before the coding pack (`conveyor inbox approve`); three-pack specifier `ready` held in `.conveyor/approvals/pending/`; `conveyor approve <id>` / `conveyor reject <id>` with comments. Reject writes findings the specifier reads on retry; `task_id` and `audit_count` survive. No batch, no back-propagation.
- **Still deferred:** clarification chat (`conveyor-clarify` / `question` verdict); per-document review comments (spec §2.4 / F5).

### B.6 Dashboard (north star: Idea 5; `orchestration-dashboard-spec.md` F1–F16)
- **Deferred because:** the operator is at the machine and `conveyor status` + `tail -f` cover supervision; the dashboard is roughly half the total build.
- **Adding it:** exactly as specified. The spec's constraint "read-only view first, controls second" means `GET /api/state` can be built over the MVP's files with no protocol change; controls wrap `conveyor approve/reject/task/answer`. Decisions taken in v0.1 stand: `needs-human` is a lane rendered before Done; elapsed meter first, tokens later; pack mode before forge mode; tmux behind a thin adapter.

### B.7 Loop detection (north star: Idea 8; v0.1 BUD-3, BUD-4)
- **Metering and token ceilings are built** (`docs/plans/token-cost.md`): each agent run writes a `.usage.json` sidecar beside its log, `conveyor cost` reads it, and `max_tokens=N` on a role line parks the task `max-tokens`. Usage lives in its own files, not in a `board.tsv` column — widening `COLS` would make every pre-existing row malformed. Dollar ceilings are still out: Conveyor ships no price table.
- **Still deferred — loop detection.** Park when the same `(role, task, commit)` handoff is seen twice.
- **Deferred because:** it shares nothing with metering but this appendix entry, and the ceilings above bound the same failure by cost.

### B.8 Durability extras (north star: Idea 8; v0.1 DUR-3, DUR-4)
- **Deferred because:** MVP runs are short and the loops are the only processes.
- **Adding it:** PID files and a `stop` sentinel per loop; `caffeinate -dims` / `systemd-inhibit` with an opt-out env var; a container-per-agent isolation adapter as an alternative to worktrees.

### B.9 Forge mode (spec §2.7, F12, F13, F16)
- **Deferred because:** single project.
- **Adding it:** `projects/<name>/` each with its own config, board, queues, and `mission.md`; loops take a project argument; the dashboard renders one band per project.

### B.10 Protocol features dropped for MVP (v0.1 HND-1, HND-6, spec §2.3)
- `note` message type (one line, ≤ 80 chars). Dropped: never needed in a two-role forward chain. Re-add as a second `type` value in the validator.
- `priority` header and priority-sorted filenames. Dropped: a linear two-role pipeline has nothing to prioritize. Re-add when batch mode (B.3) needs equal-priority grouping.
- Separate delivery daemon with `sent/` / `failed/` and transactional multi-recipient delivery. Folded into the sending loop for MVP; split back out when a handoff can have multiple recipients (PIP-3 Done condition, back-propagation).
- `artifacts` header listing files in the commit. Needed only by the approval documents dropdown (B.5, B.6).

### B.11 Original v0.1 reference
The full v0.1 requirement tables (CFG, ISO, HND, PIP, VER, CON, HUM, BUD, DUR, DSH), milestones M0–M5 + v2, and risks remain valid as the target end state. This appendix is the diff between that end state and the MVP.
