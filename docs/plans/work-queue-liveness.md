# Work-queue liveness — busy / idle / stopped / stalled / dead

**Status:** planned. Not started.

**Job:** one glance answers “is anything stuck?” Per role: current task,
liveness word, age of the in-process item against `max_minutes`, attempt
over ceiling. `conveyor status` is the contract; the work-queue table
mirrors it. Recovery is still `conveyor start` (dead) or `stop --now`
then start (hung). No watchdog, no auto-park mid-run.

This is item 4 from the field scan (Gas Town Stalled / Zombie). It is
**not** the log pane ([`log-pane-mirror.md`](log-pane-mirror.md)), not
the gate-review dialog ([`gate-review.md`](gate-review.md)), and not
PRD B.2 (tmux / wake-ups / pane watchdog).

Follows gate review in the “must-have” order: the hold is how you act on
a spec; this is how you spend the 2–5 minutes while an agent is supposed
to be working.

---

## Why

The files already distinguish live from dead. `layout.loop_pid` returns 0
when the pid file is missing or the process is gone. `in_process/` still
holds the handoff after `kill -9` or `conveyor stop --now`. Protocol
§6.7 / runbook §7: next `conveyor start` resumes it.

The operator cannot **see** that:

| Surface | Today |
| --- | --- |
| CLI | `cmd_status` prints `idle` whenever `in_process/` is empty, including after a clean stop. When `in_process/` is occupied it prints the task and age, **with no live/dead word**. A killed loop looks the same as a running agent. |
| Cockpit | `state.role_state`: if `in_process/` is occupied and the loop pid is gone, `state` is **`idle`**. Green/amber/grey dots never include dead. Header Start is disabled when **any** loop is alive, so a mixed belt (reviewer live, coder dead) cannot be repaired from the UI even though `cmd_start` already skips live pids and starts the rest. |
| Ceilings | `max_minutes` is checked at the start of `process()`, never mid-run (protocol §6.6). A hung `cursor-agent` stays `busy` until it exits. No “over budget, still running” signal. |
| Tests | `test_m4_ceilings.py` asserts `coder      idle` after loops have exited. That snapshot is the lie this plan removes. |

Gas Town’s split, mapped onto files Conveyor already has:

- **Dead** (Zombie) — `in_process/` has a file, `loop_pid` is 0.
- **Stalled** — loop is alive, `in_process/` is occupied, task wall-clock
  (`started_at`) exceeds that role’s `max_minutes`. The next `process()`
  entry would park; the current agent run has not finished.
- **Busy / idle / stopped** — the honest versions of today’s dots.

---

## Locked decisions

1. **CLI is the contract.** One helper builds the per-role row. `cmd_status`
   prints it; `GET /api/state` `work[]` is the same dict. No second store,
   no heartbeat file, no extra daemon.
2. **Five words, derived only from files + `kill(pid,0)`.**

   | Word | `loop_pid` | `in_process/` | Extra |
   | --- | --- | --- | --- |
   | `busy` | live | occupied | `started_at` age ≤ `max_minutes` (or `started_at` is `-`) |
   | `stalled` | live | occupied | `started_at` age > `max_minutes` |
   | `idle` | live | empty | — |
   | `dead` | 0 | occupied | — |
   | `stopped` | 0 | empty | — |

   Do not use the `stop` sentinel as a state. It is transient (written by
   `conveyor stop`, deleted when the loop exits). Do not use jsonl mtime
   as a stall signal (buffered writes would guess).
3. **Hop age vs ceiling clock.** OBS-1 age is the in-process item’s
   `dequeued_at` (this hop). Stalled uses board `started_at` vs
   `max_minutes` (same clock as the park). Status shows both:
   `age <hop> / <max_minutes>m`. If `started_at` is `-`, never `stalled`.
4. **Visibility only.** Do not park, kill, or restart from this helper.
   Dead → operator runs `conveyor start` (already resumes `in_process/`).
   Stalled → wait, or `conveyor stop --now` then start. Protocol §6.6
   “never mid-run” stays.
5. **`conveyor start` already repairs mixed belts.** It skips roles with a
   live pid and starts the rest (`cmd_start` loop). The cockpit bug is
   Start disabled when `state.running` is true. Enable Start when **any
   configured role has pid 0**. Header copy: `2/3 loops` when mixed, not
   a boolean “loops running”.
6. **Dead belongs on the attention strip; stalled does not.** Dead is a
   human decision (start the missing loop). Stalled is still a live agent;
   the row turning rust is enough. No chime (Stage 5).
7. **`stopped` replaces post-exit `idle`.** After `conveyor stop` with
   empty `in_process/`, status says `stopped`. `idle` is reserved for a
   live loop waiting on `new/`. Update runbook §6 and M4 snapshots.
8. **Stop dialog treats `busy` and `stalled` as in-flight.** `dead` is not
   in-flight (nothing to TERM). Do not offer Stop now solely because a
   row is dead.
9. **Batch progress is out** (B.3). One in-process item per role (inv 2).
10. **Intake is out of this table.** `work[]` stays coding roles from
    `cfg.names()`. Ticket-reviewer busy is already Inbox copy.

Record (2), (7), and the Start-when-partial rule in `bin/README.md`
Ambiguities when implementing.

---

## Out

- Watchdog that kills hung agents or auto-parks mid-run (B.2 / B.8).
- Heartbeat / extra pid file for the agent child. The loop pid is the
  liveness bit; the agent is a child of that loop.
- Log-mtime stall heuristic.
- tmux / pane capture (B.2). Role click still opens logs; live tail is
  [`log-pane-mirror.md`](log-pane-mirror.md).
- Token / cost gauges (B.7).
- Chime, held kanban badge (Stage 5).
- Changing `max_minutes` to interrupt `Popen.wait()`.
- A new `conveyor restart` verb. `start` already does the job.

---

## Operator surface

### `conveyor status`

Per-role line, pipeline order. Liveness word in a fixed column so `awk`
can find it. Then the existing payload.

```
coder      busy      in_process: add-login (coder-000003)  age 4m/120m  attempt 1/3   new: 0  last: -
reviewer   idle                                                                             new: 1  last: add-login
coder      dead      in_process: add-login (coder-000003)  age 12m/120m attempt 1/3   new: 0  last: -
coder      stalled   in_process: add-login (coder-000003)  age 130m/120m attempt 2/3  new: 0  last: -
coder      stopped                                                                          new: 0  last: -
```

Rules:

- Word is one of `busy|stalled|idle|dead|stopped`.
- `in_process:` / `age` / `attempt` only when the directory is occupied
  (busy, stalled, dead).
- `age` is hop `dequeued_at` as today (`4m`, not seconds) plus `/` and
  that role’s `max_minutes`.
- `last:` stays on every line (today it is already there).
- `needs-human:` / `board:` / (once gate review lands) `approvals:`
  unchanged.

Runbook §6 sample: replace the two-role block so at least one line is
`busy` with `age 4m/120m`, and add one `dead` line in §7 recovery (machine
rebooted) pointing at this format.

OBS-1: still “in-process item and its age, count in `new/`, last
completed”; add “and whether the loop is live”.

### Cockpit work queue

Same columns: Role · Task · State · Age · New.

- State word + dot:
  - `busy` green
  - `idle` amber
  - `stalled` rust (attention, still alive)
  - `dead` rust, stronger (e.g. outline / `aria-label` “dead”)
  - `stopped` grey
- Task subline unchanged: `attempt n/m` while occupied, `last: <task>`
  when idle/stopped.
- Age: reuse `formatAge`; when occupied, append `/ {max_minutes}m`.
- Add `max_minutes` (and `started_at` age if useful) on `WorkEntry`.

### Attention strip

New group, after needs-human, before intake:

```
Dead loop   coder  add-login  age 12m   [Start]
```

Start calls existing `POST /api/start` → `conveyor start` (starts only
missing pids). Multiple dead roles: one Start is enough (it is
all-missing, not per-row). Per-row Start is fine too if cheaper; both
hit the same CLI.

Do not list `stalled` here.

### Header

- `statusText`: `loops stopped` | `N/M loops` | `loops running` (N=M).
  If any row is `dead`, prefer `N/M loops` even when N>0.
- Start enabled when `busy` is false **and** some configured role has
  pid 0 (not initialized still disables or stays “not initialized”).
- Stop enabled when some pid is live (unchanged idea; not `state.running`
  as “all”).

---

## Implementation

### Helper

Add `layout.work_row(paths, cfg, role)` (or `lib/conveyor/observe.py` if
`layout.py` should stay path-only). Pure read.

Returns JSON-serializable:

```
role, state, running,           # running = bool(loop_pid)
task, task_id, handoff_id,      # from in_process[0] if any
age_seconds,                    # dequeued_at; omit if empty
max_minutes, attempt, max_attempts,
started_at,                     # board row or "-"
ceiling_seconds,                # age of started_at, or null
new_count, last_completed
```

`state` computed from the table in decision 2. `role_state` in
`ui/server/state.py` becomes a thin wrap. `cmd_status` formats the same
object. Do not parse agent prose or jsonl.

`in_process/` with more than one file: still refuse at loop start (inv 2).
The helper reports the first filename only and does not invent a sixth
state; the loop will not run.

### CLI

| Change | Where |
| --- | --- |
| Format `work_row` | `bin/conveyor` `cmd_status` |
| Start already skips live pids | no change |
| usage / runbook §6–7 | `docs/runbook.md` |
| OBS-1 sentence | protocol §10 `status` row; PRD OBS-1 if you touch it |

### API / cockpit

| Change | Where |
| --- | --- |
| `work[]` uses `work_row` | `ui/server/state.py` |
| `WorkEntry.state` union adds `stalled` \| `dead` | `models.ts` |
| dots + age `/Nm` | `work-queue.component.ts` |
| strip Dead loop group | `attention-strip.component.ts` + cockpit bindings |
| Start enable / header copy | `header.component.ts`, `app-shell` `running` derivation |
| Stop dialog in-flight filter | `app-shell.component.ts` `busy \|\| stalled` |

No new endpoints. `/api/state` already has `work[]`.

### Demo

`ui/server/demo.py` currently queues `demo`, parks `stuck`, does not start
loops. After this plan every row is `stopped`. Plant one handoff in
`coder` `in_process/` (copy or dequeue without a loop) so the table and
strip show **dead**. Document it as a fixture, not a crashed demo.

---

## Tests

New `test/test_work_liveness.py` (or extend M4) with a two-role fixture,
loops stopped:

1. Empty `in_process/`, no pid → `stopped`. Status stdout contains
   `coder      stopped`.
2. Live loop, empty `in_process/` → `idle`. (Start with `--no-smoke`,
   no task, `poll_seconds` high; or mock pid if that is less flaky.
   Prefer real `loop_pid` over a fake: `fx.start("--no-smoke")` then
   status before `task`.)
3. Live loop + `in_process/` → `busy`. Drive `--once` into
   `after-dequeue` crash point, leave the loop running if possible; or
   stamp `in_process/` and a live pid file whose pid is `os.getpid()` of
   the test process (documented as a test-only pid). Prefer crash-at
   `after-dequeue` + not calling `stop`.
4. Occupied `in_process/`, pid file present, process gone → `dead`.
   Write a stale pid, `loop_pid` already returns 0.
5. Occupied `in_process/`, live pid, board `started_at` older than
   `max_minutes` → `stalled`. Use `max_minutes=0` plus a stamped
   `started_at` in the past, or `max_minutes=0` and `started_at` equal
   to now: belt roles park on `>` not `>=`, so `max_minutes=0` stalls
   once age is ≥1 s. Do not change the park inequality.
6. `conveyor start` with reviewer live and coder dead starts only coder
   (existing behaviour; assert stdout `coder: loop started` and
   `reviewer: loop already running`).
7. Status after M4 park with loops exited: `stopped`, not `idle`. Update
   `test_m4_ceilings.py` regex.

API: `GET /api/state` `work[0].state` is `dead` for the stale-pid fixture.

Cockpit: no new framework. Demo seed (dead row) + browser:

1. Demo: coder `dead` on the table and on the strip; Start enabled.
2. Start: dead row becomes `busy` or `idle` (resumes `in_process/`).
3. Two-pack, both stopped: Start enabled, Stop disabled, no strip group.
4. Stop dialog while `stalled`: still offers Stop now.
5. Mixed live/dead: header `1/2 loops`, Start enabled, Stop enabled.

`npx tsc -p ui/tsconfig.app.json --noEmit` clean.

---

## Verification

```
cd test && python3 -m unittest discover -p 'test_*.py'
cd ui && npx tsc -p tsconfig.app.json --noEmit
```

CLI-only: kill a loop (`kill $(cat .conveyor/roles/coder/loop.lock/pid)`),
`conveyor status` shows `dead` and the in-process task, `conveyor start`
prints `coder: loop started` without touching a live reviewer.

Browser: required for strip, dots, and Start enablement.

---

## Order of work

1. `work_row` + unit tests 1, 4, 5 (no live loops needed).
2. `cmd_status` format + runbook §6 + M4 snapshot (test 7).
3. Wire `state.role_state`; tsc + API test.
4. Table dots + age `/Nm`.
5. Header Start / `N/M loops` + test 6.
6. Attention strip Dead group + demo seed.
7. Browser pass; Ambiguities entries.

Do not land the strip before `status` prints `dead`. A UI that shows a
zombie the CLI calls `idle` is the failure mode this product refuses.

Independent of [`gate-review.md`](gate-review.md) and
[`log-pane-mirror.md`](log-pane-mirror.md). If both land in one tag,
status gains `approvals:` from gate review and a liveness word from here;
keep the per-role line parseable (word is column 2).

---

## Tag

Unreleased / next advertised snapshot after `v0.4.0-rc1`. Does not block
M3 or `v1.0.0`. Copy a one-liner into the living tag plan when you want
it in that tag.
