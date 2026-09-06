# Conveyor — User Manual & Build Checklist

A practical guide to what a multi-agent coding orchestrator must do, grounded in **Conveyor**
as implemented in this repo. The design principles come from
`docs/agent-orchestration-north-star.md`; the normative behavior is in
`docs/conveyor-handoff-protocol.md` and `docs/conveyor-prd.md`. For day-to-day operations see
`docs/runbook.md`.

**The whole thing in one sentence:** coordinate agents through the filesystem and git, keep
every mechanism boring and inspectable, and make each agent own exactly one way the work can
go wrong.

Each part explains a capability, then gives a checklist you can tick off. Status markers on
checklist items:

| Mark | Meaning |
|---|---|
| `[x]` | Implemented in Conveyor MVP |
| `[~]` | Present, narrowed vs the north star |
| `[ ]` | Not built; re-add path in PRD Appendix B |

A living mapping from this manual to PRD/protocol IDs lives in
`conveyor-conformance-matrix.md`.

---

## Conveyor at a glance

Conveyor runs a configurable pipeline of Cursor CLI agents (`cursor-agent -p`) against
one git repo. The default **Review belt** is `coder → reviewer`; an optional `gate <role>`
line can hold a role's first `ready` for operator approval (e.g. Spec then build:
`specifier → coder → reviewer`). Agents are isolated in git worktrees, run headless one
task at a time, and hand work to each other only through validated commit-bearing files
in inbox/outbox directories. A localhost UI under `ui/` is included in v0.3.0-rc1; CLI
alone is sufficient. There is no tmux, no daemon beyond one loop process per role, and no database.

**Operator CLI** (`bin/conveyor` on `PATH`):

| Command | Purpose |
|---|---|
| `conveyor init [<path>]` | Copy constitution, roles, intake, config example into a target repo |
| `conveyor import --source manual\|jira` | Create an inbox item (Jira body fetch needs `.conveyor/local/jira.json`) |
| `conveyor intake <id> [--improve]` | One-shot ticket-reviewer grade/rewrite |
| `conveyor intake config` | Print or set intake model / minutes / attempts |
| `conveyor intake jira` | Store or test Jira site / email / token |
| `conveyor start` | Create worktrees, write rules, launch one loop per role |
| `conveyor stop` / `stop --now` | Graceful or immediate shutdown |
| `conveyor task <name>` | Create `tasks/<name>.md`, enqueue to the first configured role |
| `conveyor task --delete <name>` | Remove a done or needs-human task |
| `conveyor status` | Print queue state and `board.tsv` (runbook §6 format) |
| `conveyor log <role> [<task>]` | Pretty-print the agent run log |
| `conveyor resume <task>` | Move a parked task back into a role's inbox |

**Environment identity** (set by loops, never by the agent):

- `CONVEYOR_ROLE` — whatever role the loop set (e.g. `coder`, `reviewer`, `specifier`)
- `CONVEYOR_WORKTREE` — absolute path to `.worktrees/<role>/`
- `CONVEYOR_ROOT` — repo root
- `CONVEYOR_AGENT_BIN` — override agent binary (tests use `./test/fake-agent`)

**State layout:** runtime lives under `.conveyor/` and `.worktrees/` (gitignored). The
**contract** — `conveyor.conf`, `constitution/`, `roles/`, `project.md`, `tasks/*.md` — is
committed to the host repo so agents can re-read authoritative task intent at merge time.

**Implementation:** Python ≥ 3.10 stdlib-only under `bin/` and `lib/conveyor/`; `.sh` names
kept because agents call `handoff.sh` by that name. See `bin/README.md`.

---

## How to read this manual

Three stances run through everything below. If a design decision ever feels ambiguous, fall
back to these:

1. **One strong agent with a good harness is the default.** Conveyor's second role (reviewer)
   exists because it owns one failure mode: unverified claims of completion. Add a third role
   only when you can name the failure the current two miss.
2. **Prefer existing tools to new abstractions.** Git already solves isolation and history. The
   filesystem already solves durable queues. Log files already solve observability. A message
   bus, a shared memory store, or an agent-spawning hierarchy each _add_ a failure mode rather
   than removing one.
3. **Process is enforced, not requested.** Anything that only lives in a prompt ("don't ask for
   approval in the pane") will eventually be ignored. Anything that lives in a script that
   refuses to proceed will not. Push rules from prompts into gates wherever you can.

---

## Part 0 — Core concepts

A quick shared vocabulary before the setup steps.

- **Agent** — one headless run of `cursor-agent -p` in a role loop (not a long-lived terminal
  session in the MVP).
- **Role** — the job an agent holds for one task (`coder`, `reviewer`). A role is context
  hygiene, not a different model: same model family with different instructions is allowed but
  discouraged; pick uncorrelated models for coder and reviewer.
- **Worktree** — a private git working copy and branch (`.worktrees/<role>/` on
  `conveyor-<role>`) that one agent owns. Isolation lives here.
- **Handoff** — a small, validated, durable message that moves work from one role to the next.
  The payload is a commit SHA; prose lives in the commit message and `tasks/<name>.md`, not the
  handoff headers.
- **Board** — `board.tsv`, one row per task: lane, `task_id`, `audit_count`, `retry_count`.
- **Pipeline** — the order in `conveyor.conf` (default Review belt: coder → reviewer → done).
  Not an agent's opinion.
- **Gate** — a point where tooling refuses to proceed until a condition is met (audit
  challenge, ceiling, validator error).
- **Constitution** — layered, versioned prompt files (`constitution.md`, `constitution/*.md`,
  `project.md`, `roles/*.md`) concatenated into `.cursor/rules/conveyor-role.mdc` per
  worktree.

---

## Part 1 — Installation & setup (plug into an existing repo)

The orchestrator drops into an existing codebase. **Runtime state** is gitignored; the
**contract files** are committed so task intent survives in git history.

**What Conveyor does**

- Read `conveyor.conf` (one `role` line per pipeline step) to define the pipeline.
- `conveyor init [<path>]` copies constitution, roles, and config example; appends
  `.gitignore` entries; never overwrites operator-owned files (`project.md`, `conveyor.conf`,
  existing tasks).
- On `conveyor start`, create one isolated worktree per role with
  `git worktree add -B conveyor-<role> .worktrees/<role> HEAD` (skipped if the worktree
  already exists — never force-reset a live branch).
- Designate the main checkout as the **integration tree** where merges land; no agent runs
  there.
- Write `.cursor/rules/conveyor-role.mdc` (constitution + role, concatenated) into each
  worktree; install the shared `commit-msg` byline hook.
- Prepend `bin/` to `PATH` for agent processes so `handoff.sh` is callable from the worktree
  root; scripts are not copied into worktrees.
- Gitignore `.worktrees/`, `.conveyor/`, `.cursor/rules/conveyor-role.mdc`, and `tmp/`.
- Export `CONVEYOR_ROLE`, `CONVEYOR_WORKTREE`, `CONVEYOR_ROOT`; every helper reads identity
  from env, never from agent arguments.
- Confine scratch to `./tmp/` inside the worktree; `handoff.sh` rejects draft paths outside
  the worktree (`E_DRAFT_PATH`) and dirty trees (`E_DIRTY`, including untracked files outside
  `tmp/`).

**Setup checklist**

- [x] One config file defines the pipeline; `conveyor init` copies contract files, not runtime.
- [x] Each role gets its own worktree and branch; exactly one integration tree (main).
- [x] Constitution and role prompts are injected into every worktree via `.cursor/rules/`.
- [x] `.worktrees/` and `.conveyor/` are git-ignored; contract files are committed.
- [x] Role identity comes from the environment; helper scripts never ask the agent who it is.
- [x] Scratch outside the worktree is rejected by tooling (`E_DRAFT_PATH`, `E_DIRTY`).
- [x] `conveyor init` + `conveyor start` set everything up from a fresh clone.

---

## Part 2 — Configuring the pipeline

The order of work is `conveyor.conf`, never an agent's opinion.

**What Conveyor does**

- **Configurable pipeline:** order and size live in `conveyor.conf`. Default Review belt is
  `coder` then `reviewer`; optional `gate <role>` holds a role's first `ready`. Batch mode
  for review roles is deferred (B.3).
- **Model per role:** each line is `role <name> <model> [max_retries=N] [max_minutes=N]
  [max_attempts=N] [cli-args…]`. Model names are passed verbatim to `cursor-agent --model`;
  `conveyor start` refuses unknown models.
- **Receive mode:** task-only (one handoff at a time). Batch mode for review roles is
  deferred (B.3).
- **Constitution as layers** with stated precedence (`constitution.md`): engineering → workflow
  → handoffs → `project.md` → role file.
- **Role prompts** (`roles/coder.md`, `roles/reviewer.md`) have explicit **Owns**, **Does Not
  Own**, and **Handoff contract** sections; re-injected at every task boundary via the loop
  prompt and `.cursor/rules/conveyor-role.mdc`.

**Configuration checklist**

- [x] Pipeline order and size live in `conveyor.conf`, not in agent instructions.
- [ ] Receive mode per role (task vs batch) — deferred (B.3).
- [~] Different backend per role — model-per-role via Cursor; second CLI backend deferred
      (B.1).
- [x] Layered constitution with explicit precedence order.
- [x] Every role prompt states what it owns, what it does not own, and where it hands off.
- [x] Role context is re-injected at every task boundary (fresh `-p` run per item).

---

## Part 3 — Creating and managing tasks

This is the primary thing a human does day to day.

**What Conveyor does**

- `conveyor task <name>` validates the name (`^[a-z0-9][a-z0-9.-]*$`), writes `tasks/<name>.md`
  from stdin or `$EDITOR`, commits it on main, adds a board row, and delivers an operator
  handoff to the first configured role's inbox.
- Task intent lives in the versioned `tasks/<name>.md` file; agents re-read it at dequeue; the
  inbound handoff body must be byte-identical to the committed file (invariant 6).
- Each task gets a stable `task_id` (`<role>-NNNNNN`) for the life of the board row;
  `conveyor resume` never resets `task_id`, `audit_count`, or `retry_count`.
- `conveyor task --delete <name>` removes a task in `done` or `needs-human` lane only.
- Deleting and recreating yields a new ID with counters reset.

**Task management checklist**

- [x] Creating a task validates the name, writes `tasks/<name>.md`, adds a board card, and
      enqueues to the first configured role — in one action.
- [x] Task intent is a versioned file the agents re-read, not a one-time prompt.
- [x] Each task has a stable ID that survives every lane move and retry.
- [~] Tasks can be deleted cleanly — `conveyor task --delete` for terminal lanes; audit
      fingerprint cleanup on delete not fully specified.

---

## Part 4 — Running the swarm

Launching is `conveyor start`; supervision is `conveyor status`, `conveyor log`, and
`tail -f .conveyor/logs/<role>/*.jsonl`.

**What Conveyor does**

- Launch one **headless loop process per role** (not interactive terminal panes). Each loop
  dequeues, runs `cursor-agent -p --model <M> --force "…"`, validates the outbox, and sweeps
  delivery. Fresh context per task is free; mid-task steering is not available (B.2).
- **Delivery** is folded into the sending role's loop: outbox → recipient `inbox/new`, copy
  to `sent/`, idempotent by handoff `id`. No separate daemon process.
- **Shutdown:** `conveyor stop` waits for in-flight agent runs; `conveyor stop --now` sends
  TERM, leaves items in `in_process/` for resume on next start.
- **No watchdog, no tmux, no caffeinate** in MVP (B.2, B.8).

**Run checklist**

- [x] One command launches all role loops (`conveyor start`).
- [~] Agent visibility — stream-json logs per run, not live terminal panes (B.2).
- [ ] Watchdog restores panes — deferred; headless by design (B.2).
- [x] Loops have a clean shutdown path (`conveyor stop` / `stop --now`).
- [ ] Keep machine awake during long runs — deferred (B.8).

---

## Part 5 — How work flows (handoffs and queues)

Work moves as commits plus tiny structured messages that are validated, durable, and
auditable.

**What Conveyor does**

- **One message type:** `git_handoff`. Payload is a commit SHA; body is the full commit
  message. The `note` type is dropped in MVP (B.10).
- **Agent draft:** exactly three headers — `to`, `task`, `verdict` (`ready` | `pass` |
  `findings`). Validator fills `type`, `id`, `from`, `commit` (10-hex), `task_id`,
  `created_at`, and the body from git.
- **Permitted routes** derived from `conveyor.conf` order, never hardcoded; two-role example:
  - operator → coder (`ready`)
  - coder → reviewer (`ready`)
  - reviewer → coder (`findings`) or reviewer → done (`pass`)
- **`handoff.sh`** is the only send path: atomic rename `outbox/tmp/<id>.tmp` →
  `outbox/<id>.handoff`; per-worktree sequence under `seq.lock/`; every error code in
  protocol §4.5 prints verbatim repair text.
- **Queue directories:** `outbox/` → `sent/`/`failed/`; recipient side
  `inbox/new/` → `inbox/in_process/` → `inbox/completed/`. `ls` is your monitoring tool.
- **Delivery idempotent:** id already in `sent/` is not re-delivered.
- **Merge idempotent:** `merge.sh` checks `git merge-base --is-ancestor` before merging.
- **Timestamps** (`created_at`, `enqueued_at`, `dequeued_at`, `completed_at`) in headers;
  each written by exactly one script.
- **No free-form agent-to-agent chatter.** Questions route to the operator via `BLOCKED:`
  commits and `needs-human/` parking, not pane chat (B.5).

**Pipeline flow rules (MVP)**

- Coder always forwards `ready` to reviewer after finishing (or after addressing findings).
- Reviewer sends `findings` back to coder (bounded by `max_retries`) or `pass` to `done`.
- **Done:** reviewer `to: done, verdict: pass` triggers merge into main as `operator`. The
  multi-recipient structural Done condition (last role lists every other role) is deferred
  until N > 2 (B.3).
- **Sync / back-propagation handoffs** (`non-forwarding` header) — not needed at N=2 (B.3).
- Loop **refuses ambiguity:** >1 file in `in_process/` → refuse start; >1 file in `outbox/`
  → park to `needs-human/`; recovery re-runs `in_process/` before touching `new/`.

**Flow checklist**

- [x] One validator is the only way to send; identity and SHA filled from env and git.
- [x] One message type; no free-form messaging.
- [x] Queue state is directory location; timestamps live in headers.
- [x] Delivery and merge are idempotent and survive replay (invariants 4, 5, 11).
- [x] Every state transition is an atomic rename (invariant 3).
- [~] Unconditional forwarding — true by construction at N=2; intermediate-role rule deferred
      (B.3).
- [ ] Sync vs forward handoffs — deferred (B.3).
- [~] Done is a structural condition — `to: done` checked by tooling; full set-recipient
      condition deferred (B.3).
- [x] Loop refuses ambiguous states instead of guessing (invariant 12).

---

## Part 6 — Human checkpoints at points of maximum leverage

**Conveyor decision:** a configurable **`gate <role>` hold** parks the gated role's first
`ready` in `.conveyor/approvals/pending/` until `conveyor approve` or `conveyor reject`.
For the default Review belt (two roles), the operator's task file is the pre-run gate. For
Spec then build, the specifier's `ready` is held for approval. The run is otherwise
autonomous from enqueue to merged code on `main`; the human is pulled in when a task parks
in `needs-human/` or when reviewing `git log main` after the fact. Structured clarification
channel is deferred (B.5).

**What Conveyor does instead**

- **Spec / gate hold:** first `ready` leaving the configured gate role waits in
  `.conveyor/approvals/pending/`; `conveyor approve` / `reject` are the only ways out.
- **Findings as structured rejection:** reviewer sends `findings` with a numbered list in the
  commit message; coder addresses each on retry; `task_id` and `audit_count` survive.
- **Blocked tasks:** coder commits with `BLOCKED:` prefix; reviewer routes to operator via a
  single finding.
- **Park, don't loop forever:** ceilings move stuck tasks to `.conveyor/needs-human/<task>/`
  with a `reason` file; `conveyor resume <task>` is the only way out.

**Checkpoint checklist**

- [x] Early human gate at spec/plan inside the run — configurable `gate <role>` hold in
      `.conveyor/approvals/pending/`; `conveyor approve` / `reject`.
- [ ] Structured clarifications with IDs — deferred (B.5); ambiguity parks instead.
- [x] Rejections deliver actionable findings; ID and audit count survive retry.
- [x] Human's task statement is a versioned file agents re-read.

---

## Part 7 — Verification & quality gates

The reviewer exists because the agent that claims "done" must never be the agent that decides
"done."

**What Conveyor does**

- **Separate produce from verify:** coder vs reviewer, ideally uncorrelated model families.
- **Two-call audit gate:** first `handoff.sh` call for a candidate (sha256 of
  commit+to+task+verdict) exits 2 with `AUDIT_REQUIRED`; identical resubmission passes; any
  change re-challenges. `audit_count` written only by `handoff.sh`, shown in
  `conveyor status`.
- **Reviewer runs the project test command** and traces each numbered requirement in
  `tasks/<task>.md` to code and test evidence. Does not edit code.
- **Commit byline enforced:** `commit-msg` hook appends `By <role>.`; `handoff.sh` rejects
  HEAD without it (`E_NO_BYLINE`); `--no-verify` forbidden.

**Verification checklist**

- [x] Producer ≠ verifier (coder / reviewer).
- [x] Two-call audit gate guards every handoff.
- [x] Audit count tracked per task and shown to the human.
- [ ] Named mandatory tools (mutation, CRAP, DRY) — deferred (B.4); project test command is
      the MVP gate.

---

## Part 8 — Supervising without a dashboard

The MVP has no required web UI. Supervision is file-backed:

- `conveyor status` — per-role queue state, board rows, audit/retry counts (runbook §6).
- `conveyor log <role>` — pretty-print stream-json agent logs.
- `cat .conveyor/board.tsv` — raw board.
- `ls .conveyor/roles/<role>/inbox/new/` — pending work.
- `git log conveyor-<role>` — every commit ends `By <role>.`

A read-only dashboard over these files is deferred (B.6; spec in
`docs/later/orchestration-dashboard-spec.md`). When added, the filesystem remains the system
of record; the dashboard polls files, agents never talk to it directly.

**Observability checklist**

- [x] Every screen is buildable from files alone; no durable server state.
- [~] Supervision via CLI and logs, not a web dashboard (B.6); partial Angular UI in [`ui/`](../ui/) (board, queues, logs, operator actions).
- [x] Agents interact only through files and helper scripts.
- [x] Board, queue directories, and per-run logs are present.
- [x] Controls (`task`, `resume`, `stop`) are thin file operations via CLI.
- [x] Malformed queue files are skipped, not fatal.

---

## Part 9 — Durability & cost control

Conveyor treats ceilings as first-class MVP features, not afterthoughts.

**What Conveyor does**

- **Restart = re-run the loop.** On start, resume `in_process/` before `new/`; deliver pending
  outbox; nothing duplicated (invariant 11, tested at every protocol boundary with fake-agent
  `crash`).
- **Wall-clock ceiling:** `max_minutes` per role; checked between attempts; parks with reason
  `max-minutes`.
- **Retry ceiling:** `max_retries` (reviewer→coder findings cycles); parks with
  `max-retries`.
- **Attempt ceiling:** `max_attempts` per role per task; parks when the agent fails to produce
  a valid handoff.
- **Other park reasons:** `merge-conflict`, `multiple-handoffs`, `no-rules`, `no-agent`, `no-task-file`.
- **`conveyor resume <task>`** moves the parked item back to a role's inbox; counters are
  **never reset** — raise ceilings in config or delete and recreate the task.
- **Token/cost ceiling** — deferred until Cursor stream-json exposes reliable usage (B.7).

**Durability checklist**

- [x] Orchestrator resumes cleanly after reboot (`conveyor start`; invariant 11).
- [ ] Per-task token/cost ceiling — deferred (B.7).
- [x] Per-task wall-clock ceiling (`max_minutes`).
- [x] Max-retry / max-attempt count parks stuck tasks in `needs-human/`.
- [~] Cost levers — model-per-role present; pipeline size configurable via `conveyor.conf`.

---

## Master checklist (the essentials)

**Isolation**

- [x] Worktree + branch per role; one integration tree (main).
- [x] Identity from the environment; scratch confined to the worktree by tooling.

**Setup**

- [x] One config file; runtime state gitignored, contract committed.
- [x] `conveyor init` + `conveyor start` set up and launch.

**Roles & prompts**

- [x] Layered, versioned constitution with precedence.
- [x] Owns / does-not-own / handoff contract per role, re-injected per task.

**Tasks**

- [x] Create task = validate name + write `tasks/<name>.md` + add card + enqueue to first role.
- [x] Stable task ID survives every move and retry.

**Handoffs**

- [x] One validator is the only send path; SHA and identity filled automatically.
- [x] One message type; no free-form chatter.
- [x] Directories as queue state; atomic renames; idempotent delivery and merge.

**Pipeline**

- [x] Order is config, not agent choice (default Review belt: coder → reviewer).
- [~] Forwarding and Done conditions simplified for N=2; full rules deferred (B.3).
- [x] Loop refuses ambiguity.

**Verification**

- [x] Producer ≠ verifier.
- [x] Two-call audit gate; audit count tracked and surfaced.
- [~] Project test command mandatory; mutation tooling deferred (B.4).

**Human gates**

- [x] In-loop spec approval — configurable `gate <role>` hold; intake approve for inbox items.
- [x] Findings carry actionable rejection; structured park/resume for stuck tasks.

**Observability**

- [~] Headless logs, not terminal panes (B.2).
- [x] Role byline in every commit; `--no-verify` forbidden.
- [x] File-backed board (`board.tsv`); `conveyor status` from `ls`.
- [ ] Web dashboard — deferred (B.6).

**Durability & cost**

- [x] Resumes after reboot.
- [x] Wall-clock and retry ceilings; stuck tasks park for a human.
- [ ] Token ceiling — deferred (B.7).

---

## Build order (what Conveyor shipped)

Milestones M0 → M4, gated by automated tests in `test/`:

1. **M0 — Harness:** `conveyor init` / `conveyor start` creates worktrees, rules file, hook;
   refuses unknown models.
2. **M1 — Protocol:** fake-agent run operator → coder → reviewer → merge on main; crash at
   every loop boundary → identical end state after restart.
3. **M2 — Gates:** audit two-call challenge; byline rejection on `--no-verify`.
4. **M3 — Real agents:** cursor-agent on a small repo; reviewer catches missing test coverage.
5. **M4 — Ceilings:** task that cannot succeed parks in `needs-human`; `conveyor status`
   matches runbook format.

Recommended order for _future_ features (from PRD Appendix B):

1. Interactive sessions + watchdog (B.2) — if mid-task steering matters.
2. More roles + batch mode + sync handoffs (B.3).
3. Structured clarifications (B.5).
4. Read-only dashboard (B.6) over existing files.
5. Token metering + loop detection (B.7).
6. Mandatory mutation/CRAP tooling (B.4).

---

## Design-review questions

Ask these at every milestone:

- Can two agents ever write to the same file at the same time? **Yes — prevented** (single-writer
  table, protocol §2.3; invariant 1).
- Is the agent that says "done" different from the agent that decides "done"? **Yes** (coder
  vs reviewer).
- Can each agent's full context fit on one screen of instructions? **Yes** (≤2 pages per role).
- Can a human read every handoff and know what was asked and delivered? **Yes** (commit SHA +
  commit message body).
- Can you `ls` your way to the current state of every task? **Yes** (queue dirs + `board.tsv`).
- Is there exactly one place a human must approve, and is it early? **Yes for gated
  pipelines** — `gate <role>` hold before coding starts; two-role belt uses the task file.
  Clarification chat is B.5.
- Is the order of work a config file or an agent's opinion? **Config** (`conveyor.conf`).
- If the machine reboots mid-run, what happens when you start it again? **Resume** — loops
  pick up `in_process/` and pending outbox (invariant 11).
- What stops a task that has retried nine times? **`max_retries`** parks it in
  `needs-human/`.

---

## What Conveyor deliberately left out

These are PRD Appendix B deferrals, not oversights. Each adds a failure mode or coordination
surface; add only when a concrete need justifies the cost:

- Web dashboard, chime, pane viewer, master chat (B.6)
- tmux, interactive sessions, wake-ups, watchdog (B.2)
- Structured clarification channel (B.5)
- Batch receive, back-propagation, pipeline templates (B.3)
- Non-Cursor backends (B.1)
- Mutation/CRAP/DRY mandatory tooling (B.4)
- Token/cost metering (B.7)
- Multi-project forge mode (B.9)
- `note` message type, priority headers, separate delivery daemon (B.10)

See `docs/conveyor-prd.md` Appendix B for the re-add path for each item.
