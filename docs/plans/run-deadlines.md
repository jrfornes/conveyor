# Run deadlines — nothing hangs forever

**Status:** planned. Not started.

**Job:** a hung `cursor-agent` or a hung gate command must not stop the belt.
Today both do. `max_minutes` becomes a deadline that is *enforced* rather than
merely observed after the fact, and a gate that never returns becomes an
ordinary validator refusal the agent can act on.

Two fixes, one plan, because they are the same bug at two depths and share one
mechanism (process-group kill): **a subprocess with no timeout, holding a pipe
the loop is blocked on.**

This is not PRD B.2 (watchdog, tmux, wake-ups). Nothing new is supervised;
two existing `wait()` calls learn a deadline.

---

## Why

### The agent run is unbounded

`max_minutes` is checked **once**, before the attempt loop is entered
(`bin/role-loop.sh:180-184`), and never again — not between attempts, not
during one. The run itself is `rc = self.agent.wait()` with no timeout
(`bin/role-loop.sh:322`). So:

| Situation | Today |
| --- | --- |
| Agent wedges on attempt 1 | The loop blocks in `wait()` forever. `conveyor status` prints `in_process: <task> … age 900m` and nothing ever parks. |
| Three attempts of 40 min each under `max_minutes=60` | All three run. The ceiling is only consulted at the *next* dequeue, which never comes for this item. |
| Agent exits but leaves a child holding stdout | `stamper.wait()` (`:324`) blocks on an EOF that never arrives, even though the agent is gone. |

That last row is the one that makes this a process-group problem rather than a
`timeout=` problem. The agent is launched without `start_new_session`
(`:307`), its children inherit the stdout pipe, and the stamper only sees EOF
when **every** writer closes. Terminating the agent alone is not enough — and
`on_term` (`bin/role-loop.sh:115-119`), which is what `conveyor stop --now`
reaches, has exactly the same gap.

The protocol already promises what the code does not: §6.6 says `max_minutes`
is enforced; §6.7 says `stop --now` "sends TERM to the agent". Both are true
of one process and false of the tree it spawned.

### Gates are unbounded, one level deeper

`gates.run` is `subprocess.run(argv, shell=True, cwd=wt, capture_output=True)`
with no timeout (`lib/conveyor/gates.py:198`), called from inside `handoff.sh`
(`bin/handoff.sh:185-187`) — which is called by the agent, inside the run the
loop is blocked on. A gate wedged in watch mode, or an `nx` daemon that never
answers, hangs the agent, which hangs the loop, **below** the loop's own
ceiling logic. Three layers of blocking, no timeout anywhere.

`shell=True` makes the naive fix wrong: `subprocess.run(timeout=…)` kills the
shell, and the real command — the thing that is actually stuck — survives.

---

## Locked decisions

1. **The agent deadline is derived from `max_minutes`, not a new config key.**
   `max_minutes` already means "this task may not take longer than N minutes".
   The deadline for one run is the task's **remaining** budget:
   `max_minutes*60 − age(started_at)`, using the same task-wide `started_at`
   the pre-flight check uses (§6.6). No `max_run_minutes`, no second knob to
   keep consistent with the first.

2. **A floor of 60 seconds.** The deadline is `max(remaining, 60)`. Without it,
   `max_minutes=0` — legal, and what `test/test_m4_ceilings.py::M4Minutes`
   configures — would kill every run the instant it started, changing what
   that ceiling means today (the belt comment at `bin/role-loop.sh:181-182`
   is explicit: a just-started task still gets one attempt). The floor keeps
   that promise and is the only place a run may exceed the task budget.

3. **We do not second-guess the operator's number.** With `max_minutes=120` a
   wedged run is killed after two hours, not after ten minutes. That is slow,
   and it is still the operator's stated tolerance; guessing a tighter bound
   would kill legitimately long Angular/NX runs. The fix is that it terminates
   at all.

4. **The kill is a process-group kill, and it is the reason for everything
   else.** The agent is launched with `start_new_session=True`; the deadline
   sends `SIGTERM` to `os.getpgid(agent.pid)`, waits 10 s, then `SIGKILL` to
   the same group. Terminating only the agent leaves children holding the
   stdout pipe and the loop blocks in `stamper.wait()` — trading one hang for
   another.

5. **`start_new_session` lands before any `killpg`.** Today the agent shares
   the loop's process group; a `killpg` without (4) would kill the loop
   itself. These are one commit, never two.

6. **The outbox is re-checked after a kill, before parking.** An agent that
   already ran `handoff.sh` successfully and then wedged has done the work.
   The existing control flow gives this for free: on a kill, go back to the
   top of the `while True` in `process()`, where `n == 1` completes the item
   normally. Only `n == 0` parks. Killing a run must never discard a valid
   handoff — the outbox stays the only signal (PRD §5, "never parse agent
   prose").

7. **A killed run parks `max-minutes`; it is not a failed attempt.** No
   `attempt += 1`, no `--resume`, no retry. The budget is gone — retrying
   spends a budget that is already exhausted. Park reason is the existing
   `max-minutes`, so `conveyor resume` and the runbook are unchanged.

8. **`on_term` gets the same group kill.** `conveyor stop --now` currently
   terminates one process (`bin/role-loop.sh:115-119`); it should stop the
   tree. Protocol §6.7's "sends TERM to the agent" is amended to say the
   agent's process group. The handler still does no `wait()` — the comment at
   `:116` is right, it can run inside `Popen.wait()`.

9. **`stamper.wait()` gets a bounded wait too.** After the group is gone the
   stamper should see EOF immediately; if it does not, wait 5 s and kill it.
   A belt-and-braces bound on the one remaining `wait()` in the run path.

10. **Gate timeouts are a validator refusal, not a kill.** The agent deadline
    already bounds gates transitively, but it bounds them *opaquely* — the run
    dies and the agent learns nothing. `E_GATE_TIMEOUT` turns the same event
    into a normal `handoff.sh` failure with repair text, which the agent can
    read and act on within its remaining attempts. That is the actual value of
    this half.

11. **Gate timeout config: one default, one optional per-gate override.**
    `[global] gate_timeout = <seconds>` in `conveyor.conf` (default **900**;
    `0` = unbounded), overridden per gate by a new optional `## Gate timeouts`
    section in `project.md`, parsed exactly like `## Required on`:

    ```markdown
    ## Gate timeouts

    build: 1800
    lint: 300
    ```

    A separate section, not a token on the gate line: `_parse_gates_section`'s
    `^([a-z][a-z0-9:-]*):\s*(.*)$` and the fence handling stay untouched, and
    the new parser is a copy of one that already exists.

12. **Gates get their own process group, and `handoff.sh` cleans it up.**
    `gates.run` becomes `Popen(..., shell=True, start_new_session=True)` +
    `killpg` on timeout, because with `shell=True` a plain `timeout=` kills the
    shell and orphans the command. That group would then survive an agent kill,
    so `handoff.sh` installs a `SIGTERM` handler that `killpg`s the gate in
    flight before exiting. Without it, decision (4) leaves an `nx build`
    running forever.

13. **A timed-out gate writes the same log as a failed one**, with the partial
    output captured so far, `exit: timeout` on the first line, and the same
    path shape (`.conveyor/logs/gates/<role>-<task>-<commit>-<name>.txt`).
    Nothing new to learn when reading a failure.

14. **Every new error code gets a test asserting its exact repair text.**
    Repo hard rule, `bin/README.md` / CLAUDE.md. `E_GATE_TIMEOUT` goes in
    `test/test_errors.py` beside the rest.

---

## Out

- Any watchdog, supervisor, re-attach, or liveness probe (PRD B.2). The loop
  bounds its own children; nothing watches the loop.
- `max_run_minutes` or any second time knob (locked decision 1).
- Killing a run for cost — that is `docs/plans/token-cost.md`, which
  deliberately does **not** kill.
- Changing what `max_minutes` means, its task-wide scope, or `started_at`.
- Retrying a killed run (locked decision 7).
- Per-gate parallelism, gate caching, or gate result reuse across roles.
- Timeouts on `merge.sh`, the `[global] integration` command hook, or
  `agent.list_models` (which already passes `timeout=15`). Worth doing; not
  this plan.
- `conveyor stop` (without `--now`) killing anything. §6.7 stands: a plain
  stop never kills a running agent.

---

## Operator surface

### The loop log

A kill is loud, in `loop.log` and in the run's `.jsonl`:

```
2026-09-09T14:41:07Z  slow: attempt 1 running composer-2.5
2026-09-09T16:41:07Z  slow: attempt 1 killed after 120m0s (max-minutes deadline)
2026-09-09T16:41:17Z  parked slow: max-minutes (killed attempt 1 after 120m0s, exceeds max_minutes 120)
```

In the run log, before the existing `event: exit` record:

```
{"at":"…","type":"conveyor","event":"killed","reason":"max-minutes","after_s":7200,
 "signal":"TERM","escalated":true,"text":"killed after 120m0s (max-minutes deadline)"}
```

`escalated` is true when `SIGTERM` was not enough and `SIGKILL` followed —
that distinction is the difference between "the agent was busy" and "the agent
was wedged", and it is the first thing you want when deciding whether the
ceiling is too tight. `LOG_DETAIL_KEYS` already renders `event` and `text`
(`bin/conveyor:750-751`), so `conveyor log` shows it with no change.

### `conveyor status` / parking

Unchanged. The reason is the existing `max-minutes`:

```
needs-human:
  slow        max-minutes   killed attempt 1 after 120m0s, exceeds max_minutes 120
```

The detail line says `killed attempt N` when the deadline fired, and keeps
today's `task started <ts>, exceeds max_minutes N` when the pre-flight check
fired. Two ways in, one reason, distinguishable in the detail.

### `E_GATE_TIMEOUT`

```
E_GATE_TIMEOUT: gate test did not finish within 900s
  Make it terminate (no watch mode, no prompts), or raise its budget under
  ## Gate timeouts in project.md. Output so far: .conveyor/logs/gates/coder-add-login-a1b2c3d4e5-test.txt
```

### `conveyor gate run <name>`

Honours the same budget and dies with the elapsed time, so an operator
debugging a gate sees the bound before an agent hits it:

```
conveyor gate run: test timed out after 900s (see .conveyor/logs/gates/operator-manual-…-test.txt)
```

---

## Implementation

### `bin/role-loop.sh`

- `run_agent(…, deadline_s)`: `Popen(..., start_new_session=True)`; replace
  `self.agent.wait()` (`:322`) with a bounded wait — on `TimeoutExpired`,
  `os.killpg(os.getpgid(pid), SIGTERM)`, wait 10 s, `SIGKILL` the group, then
  write the `event: killed` record. `stamper.wait(timeout=5)` then kill.
  Returns `killed: bool` alongside `(session, last_err)`.
- `process()`: compute `deadline_s = max(60, self.me.max_minutes*60 - age(started))`
  next to the existing pre-flight check (`:180-184`); pass it in. When
  `run_agent` reports a kill, do **not** increment `attempt` — fall through to
  the top of the loop, and park `max-minutes` if the outbox is empty
  (locked decision 6).
- `on_term`: `killpg` instead of `terminate`, guarded by `ProcessLookupError`.

Note for whoever writes it: `signal.SIGTERM` to a group whose leader has
already exited raises `ProcessLookupError`, and `os.getpgid` on a reaped pid
raises the same. Both are the success case. Wrap, do not check-then-act.

### `lib/conveyor/gates.py`

- `Catalog` gains `timeouts: dict[str, int]`; `parse` reads the optional
  `## Gate timeouts` section with `_parse_timeouts_section` (shaped like
  `_parse_required_section`). A name not in `commands`, a non-integer, or a
  negative value is a `GateParseError`.
- `GateTimeoutError(seconds, log_path)` beside `GateFailedError`.
- `run(..., timeout)`: `Popen(argv, shell=True, cwd=wt, start_new_session=True,
  capture)` + `communicate(timeout=…)`; on `TimeoutExpired`, `killpg` TERM →
  10 s → KILL, drain, write the log with `exit: timeout`, raise.
- `timeout_for(catalog, name, default)` — one place resolving section over
  `[global]`.

### `lib/conveyor/config.py`

`[global] gate_timeout` parsed like `poll_seconds`; non-negative int or
`ConfigError` with repair text. Default 900. Not written by `config.save`
unless already present, so untouched configs stay byte-identical and
`presets.resolve` does not flip to `custom`.

### `bin/handoff.sh`

- `E_GATE_TIMEOUT` in `ERRORS`, text as above.
- `run_project_gates`: pass the resolved timeout; catch `GateTimeoutError` →
  `fail("E_GATE_TIMEOUT", …)`.
- A module-level `SIGTERM` handler that `killpg`s the gate currently in flight
  (a single module global set by `gates.run`, cleared in `finally`) before
  exiting — locked decision 12.

### `bin/conveyor`

`cmd_gate`'s `run` branch catches `GateTimeoutError` and dies with the elapsed
seconds and the log path.

### `test/fake-agent`

- `spawn-child <seconds>` — `Popen(["sleep", n])` inheriting stdout, so the
  orphan-holds-the-pipe case is drivable.
- `ignore-term` — install `SIG_IGN` for `SIGTERM`, so the TERM→KILL escalation
  is testable.

### Docs

- Protocol §6.6: `max_minutes` row gains "enforced by a deadline on the run;
  the run is killed and the item parks". §6.9: the kill sequence, the group
  semantics, the `event: killed` record, the 60 s floor. §6.7: `stop --now`
  sends TERM to the agent's **process group**. §4.4: `## Gate timeouts`.
  §4.5: `E_GATE_TIMEOUT`.
- Runbook §6/§7: what `killed attempt N` means, and that `escalated: true`
  means the agent ignored TERM.
- `project.md` template: a commented `## Gate timeouts` block.
- `conveyor.conf.example`: commented `gate_timeout = 900` under `[global]`.
- `bin/README.md` Ambiguities: the 60 s floor, killed-run-is-not-an-attempt,
  outbox-wins-over-kill, and why gates need their own group *and* a handler.
- PRD: nothing. This is §3 scope working as specified, not Appendix B.

---

## Tests

`test/test_m4_ceilings.py` (extended — ceilings live here):

1. `max_minutes` deadline kills a wedged run: coder scripted `sleep 600`,
   deadline forced short, loop returns within seconds, `parked_reason` is
   `max-minutes`, detail starts `killed attempt 1`.
2. Exactly one `.jsonl` exists — the kill did **not** become attempt 2
   (locked decision 7).
3. The run log's last two records are `event: killed` then `event: exit`.
4. `M4Minutes` as it stands today still passes: `max_minutes=0`,
   coder→reviewer→coder, parks on the *pre-flight* check with the old detail
   text. This is the regression guard for the floor (locked decision 2).
5. **Handoff wins over kill:** agent scripted `commit; draft; handoff;
   sleep 600`. The deadline fires, and the item **completes** — lane advances,
   nothing parks (locked decision 6). The most important test in the plan.
6. TERM→KILL escalation: `ignore-term` + `sleep 600` → killed anyway,
   `escalated: true` in the record.

`test/test_process_groups.py` (new):

7. Orphan holding the pipe: `spawn-child 600` then agent exits → the loop
   still returns (the group kill releases `stamper.wait()`), and the child is
   gone afterwards.
8. `conveyor stop --now` with a running agent kills the agent's children too
   (locked decision 8).
9. Invariant 11 unchanged: `kill -9` of the loop still leaves agent and
   stamper running and the output lands dated in the log — `start_new_session`
   must not have changed this. Cross-check against
   `test/test_inv11_restart.py`.

`test/test_gates.py` (extended):

10. `## Gate timeouts` parses; a name not in `## Gates` → `GateParseError`;
    non-integer → `GateParseError`; absent section → `[global]` default;
    `gate_timeout = 0` → no timeout.
11. A gate that sleeps past its budget raises `GateTimeoutError` and writes a
    log whose first line is `exit: timeout` with the partial output.
12. **The shell's child dies too:** gate command `sh -c 'sleep 600 & wait'`,
    timeout fires, the `sleep` is gone (this is the `shell=True` bug, and the
    reason for locked decision 12).

`test/test_errors.py`:

13. `E_GATE_TIMEOUT` with the exact problem and repair text, driven end to end
    through `handoff.sh` — repo hard rule.

`test/test_gate_command.py`:

14. `conveyor gate run` on a slow gate dies with the elapsed seconds and the
    log path.

`test/test_config_inbox.py` / `test_presets.py`:

15. `gate_timeout` round-trips; a config without it is byte-identical after
    `config.save` and still resolves to its preset slug.

Every test that kills something must bound its own wait — no unbounded
`fx.loop()` in this file, or a regression hangs the suite instead of failing
it.

---

## Verification

```
cd test && python3 -m unittest discover -p 'test_*.py'
```

206 tests green before, plus the new ones after — and the suite must not get
slower by more than the sleeps the new tests need. Then, by hand:

1. `CONVEYOR_FAKE_SCRIPT` with `sleep 600`, `max_minutes=1`: the loop returns
   in ~60 s, `conveyor status` shows the park, `conveyor log coder` shows the
   `killed` line. `ps` shows no orphan.
2. Same with `spawn-child 600`: still returns, and `ps` shows no `sleep`.
3. A `project.md` gate of `sleep 600` with `gate_timeout = 5`: the agent gets
   `E_GATE_TIMEOUT`, retries within `max_attempts`, and `ps` shows no `sleep`.
4. `conveyor stop --now` mid-run: agent and its children gone, item still in
   `in_process/`, `conveyor start` recovers it (§6.7).
5. Against a **real** `cursor-agent`, the one thing the fake cannot prove:
   that TERM to the group is enough for it to exit cleanly and that a killed
   session id is still resumable if the operator raises the ceiling and
   resumes. Record the result in `bin/README.md` Ambiguities either way.

---

## Order of work

1. `start_new_session=True` + group kill in `on_term` (locked decision 5 makes
   these one commit); tests 8, 9.
2. The deadline in `run_agent` / `process`, the `event: killed` record, the
   park detail; tests 1–6, 7.
3. `gates.py` timeout + `## Gate timeouts` + `[global] gate_timeout`; tests
   10–12, 15.
4. `E_GATE_TIMEOUT` in `handoff.sh` + the SIGTERM handler; tests 13, 14.
5. Protocol §6.6/§6.7/§6.9 and §4.4/§4.5, runbook, templates,
   `bin/README.md`.

Step 1 changes no behaviour an operator can see and makes step 2 possible;
step 2 can park a live task. Do not merge them. Steps 3–4 are independent of
1–2 and can land in either order, but `E_GATE_TIMEOUT` without step 3 has
nothing to raise it.

---

## Tag

Unreleased, after `v0.4.0-rc1`. **Should land before M3.** The first live
Cursor run is exactly the situation this plan exists for — an unbounded
`wait()` on a real agent, with no fake-agent script to guarantee it returns —
and a hang there costs a whole run of the milestone that has been waiting
longest.
