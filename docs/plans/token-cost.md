# Token cost — what a task actually spent

**Status:** built. Steps 1–8 landed; step 0 (the live `cursor-agent` run) is still
outstanding and is now a **verification** step, not a prerequisite — see
[Verification](#verification). The parser was written to be honest about absence
exactly so the rest could land without it: until a real run confirms the shape,
`usage.ALIASES` is the table to extend, and nothing invents a number.

**Job:** every agent run records what it consumed, the operator can read it
per task and per role, and a task that burns its budget **parks** instead of
retrying until the bill arrives. PRD §2 names "a stuck task retries until the
bill arrives" as one of the four failure modes Conveyor exists to stop; today
only wall-clock and retry count are bounded, and nothing in `bin/` or `lib/`
mentions tokens at all.

This is PRD **B.7**, first half (metering + ceilings). Loop detection — park
when the same `(role, task, commit)` is seen twice — is the other half and is
**out**; it shares nothing with this work but the appendix entry.

---

## Why

The plumbing already exists and is unused:

| Surface | Today |
| --- | --- |
| Run log | `run_agent` already runs the agent with `--output-format stream-json` and tees every line, dated, into `.conveyor/logs/<role>/<task>_<id>_a<attempt>.jsonl` (`bin/role-loop.sh:290-331`). If Cursor reports usage, **it is already on disk**. |
| Post-run scan | The same function already re-reads that log and regexes it twice — `SESSION_RE` for the session id, `VALIDATOR_RE` for the last error (`bin/role-loop.sh:327-329`). A third scan is the whole feature. |
| Ceilings | `max_retries` / `max_minutes` / `max_attempts` are enforced at `bin/role-loop.sh:174-184`. There is no cost dimension. |
| Board | `audit_count` and `retry_count` are visible in `conveyor status`, so the operator can see *that* a task bounced — never what the bouncing cost. |

The money is in the invisible places. A `findings` bounce re-runs the coder on
a full context; an `AUDIT_REQUIRED` re-challenge re-runs it again. A task with
`audit 7  retry 4` on the board has paid for roughly eleven extra agent runs
and prints nothing to say so.

**The unknown this plan is designed around:** whether `cursor-agent`'s
`stream-json` reports usage at all, and under which keys. PRD B.7 deferred on
exactly that ("depends on what Cursor's stream-json reports") and it is still
unverified — there has been no live M3 run. So the parser is built to be
*honest about absence* rather than to guess, and step 0 of the work is one
command against a real log:

```
grep -o '"usage"[^}]*}' .conveyor/logs/coder/*.jsonl | head
```

---

## Locked decisions

1. **`board.tsv` does not grow a column.** `board.COLS` is a fixed 8-tuple and
   `board._load` treats any row whose cell count differs as malformed, keeping
   it verbatim and out of `read()` (`lib/conveyor/board.py:6,19-23`). Widening
   `COLS` makes every pre-existing board row invisible to `board.get`, which
   the role loop turns into `no-board-row` failures on live tasks. Protocol
   §8.1 fixes the column list. Usage lives in its own files.

2. **One file per agent run, beside its log:**
   `.conveyor/logs/<role>/<task>_<id>_a<attempt>.usage.json`, written by the
   loop via `util.atomic_write` after the run, never mutated afterwards. It is
   a derived index of exactly one `.jsonl`, so it belongs next to it: same
   key, same directory, no new lock, no new protocol directory. `cmd_log`
   filters on `.jsonl` (`bin/conveyor:761`) and does not see it.

3. **The number is auditable or it is absent.** `usage.scan` classifies what it
   found and records the rule that fired:
   - an event carrying `type: "result"` (or a final-`subtype` event) **with**
     usage **wins outright**; per-message events are ignored → `source: result`
   - otherwise per-message `usage` objects are **summed** → `source: messages`
   - nothing found → `source: none`, token fields `null`

   The two rules are mutually exclusive on purpose: cumulative totals must not
   be summed, per-message deltas must not be last-won, and there is no way to
   tell which a stream emits without looking. Writing `source` makes a wrong
   guess visible in the file instead of silently doubling a bill.

4. **A run with no usage still writes a file.** `source: none` plus
   `duration_s` and `exit`. An absent file means "the loop did not finish this
   run"; a file with nulls means "the agent told us nothing". Those are
   different and the operator must be able to tell them apart.

5. **Tokens first, money second.** Phase 1 records tokens and duration only.
   `cost_usd` is recorded **only if the agent reports it** and is `null`
   otherwise. Conveyor does not ship a price table: prices go stale, and a
   fabricated dollar figure on an operator's screen is worse than no figure.
   A `[prices]` config section is a later decision, not this plan.

6. **Ceilings are on tokens, not dollars.** `max_tokens=N` on a `role` line,
   same grammar as the existing `max_*` keys (`config._parse_role`), park
   reason **`max-tokens`**. `max_cost` waits for (5).

7. **The ceiling is task-wide, read from the current role's config** — exactly
   the existing `max_minutes` semantics (§6.6: "first `dequeued_at` for this
   `task_id`", compared against `self.me.max_minutes`). The total summed is
   every `.usage.json` for this task across all roles and attempts, so a
   coder-reviewer ping-pong is bounded as one budget.

8. **Checked at the start of §6.3 *and* between attempts.** This amends
   protocol §6.6 ("checked at the start of §6.3, never mid-run"). A task can
   spend its entire budget inside attempts 1 and 2 of a single item, and a
   ceiling that only fires on the next dequeue does not bound anything. "Never
   mid-run" is preserved: a running agent is never killed for cost; the check
   sits where `attempt > max_attempts` already sits (`bin/role-loop.sh:203-208`).

9. **`0` means unbounded, and unknown usage never parks.** `max_tokens` is
   absent by default. If every usage file for a task is `source: none`, the
   total is unknown and the ceiling cannot fire — Conveyor refuses rather than
   guesses (PRD §5.5), and `conveyor cost` says so in words.

10. **The loop writes a `usage` record into the run log too**, as
    `{"type":"conveyor","event":"usage","text":"…","input":…,"output":…}`,
    immediately before the existing `event: exit` record. `LOG_DETAIL_KEYS`
    already renders `event` and `text` (`bin/conveyor:750-751`), so
    `conveyor log` shows the run's spend with no change to `cmd_log`.

11. **`conveyor status` board rows gain one column.** Runbook §6 is normative
    and `test/test_m4_ceilings.py` snapshots it; both are updated in the same
    commit. The column prints `-` when the total is unknown, never `0`.

12. **`conveyor cost` is a pure read.** It writes nothing, takes no lock, and
    works on a stopped pipeline. Same posture as `conveyor log`.

---

## Out

- Dollar ceilings, a price table, any `[prices]` config (locked decision 5).
- Loop detection / duplicate-handoff parking (the other half of B.7).
- Per-tool or per-file attribution of spend. The unit is one agent run.
- Rewriting history: usage files are never written for runs that predate the
  feature, and no backfill command is provided. `conveyor cost` reports
  `-` for them.
- Any change to `handoff.sh`, the audit gate, or the delivery sweep.
- Budget display in the cockpit beyond the API (see Cockpit below).
- Killing a running agent on cost (locked decision 8).

---

## Operator surface

### `conveyor cost [<task>]`

No argument — one row per board task, newest first, then a total:

```
TASK          RUNS  IN        OUT      TOTAL     WALL
add-login       11  412.3k    38.1k    450.4k    47m
fix-cache        4  198.0k    12.7k    210.7k    18m
              ----  --------  -------  --------  -----
                15  610.3k    50.8k    661.1k    65m
2 tasks, 15 runs.  3 runs reported no usage.
```

With a task — one row per run, in the order they happened:

```
add-login   coder-000003
ROLE      ATTEMPT  IN        OUT      TOTAL     WALL   SOURCE
coder           1  88.1k     9.2k     97.3k     6m     result
coder           2  91.4k     7.8k     99.2k     5m     result
reviewer        1  63.0k     4.1k     67.1k     3m     result
reviewer        1  -         -        -         4m     none
                   --------  -------  --------  -----
                   242.5k    21.1k    263.6k    18m
max_tokens 500000 (coder) — 52% used.
```

`-` in a cell is "the agent reported nothing", distinct from `0`. The trailing
`max_tokens` line is printed only when the current lane's role sets one.

### `conveyor status`

The `board:` block gains a `tok` column. Everything else in runbook §6 is
byte-identical:

```
board:
  add-login   coder        audit 2  retry 1  tok 450.4k
  fix-cache   needs-human  audit 7  retry 4  tok -
```

### `conveyor log <role> [<task>]`

No code change. The new record renders through the existing detail keys:

```
14:18:07 [conveyor] usage in 88.1k, out 9.2k, 6m12s (result)
14:18:07 [conveyor] exit 0
```

### Parking

```
needs-human:
  add-login   max-tokens    661.1k tokens over max_tokens 500000
```

`conveyor resume` is the only way out, as with every other ceiling. It does
**not** reset the total — the same rule as `retry_count` and `audit_count`
(§6.10). An operator who wants a bigger budget raises `max_tokens`.

---

## Implementation

### `lib/conveyor/usage.py` (new)

```python
scan(text)        -> {"source": "result"|"messages"|"none",
                      "input": int|None, "output": int|None,
                      "cache_read": int|None, "cache_write": int|None,
                      "cost_usd": float|None}
record(paths, role, task, hid, attempt, scanned, duration_s, exit_code)
                  -> writes <task>_<id>_a<attempt>.usage.json, returns the dict
read_task(paths, task)  -> [run dicts], ordered by file mtime then attempt
total(runs)       -> {"runs", "input", "output", "total", "wall_s", "unknown"}
```

Field aliases `scan` accepts, in this order, first hit wins per field:

| Field | Keys |
| --- | --- |
| input | `input_tokens`, `prompt_tokens`, `inputTokens` |
| output | `output_tokens`, `completion_tokens`, `outputTokens` |
| cache_read | `cache_read_input_tokens`, `cached_tokens` |
| cache_write | `cache_creation_input_tokens` |
| cost | `total_cost_usd`, `cost_usd` |

A `usage` object is looked for at the top level of an event and under
`message`. Unknown keys are ignored, never summed. The alias table lives in
one dict so a live M3 run can extend it without touching the logic — and the
extension is recorded in `bin/README.md` Ambiguities, like the Jira
`customfield_*` allowlist.

### `bin/role-loop.sh`

- `run_agent`: wall-clock the `Popen`; after `stamper.wait()`, `usage.scan` the
  log text it already reads for `SESSION_RE`, write the `event: usage` record
  into the open log file, then `usage.record`. Return the scan alongside
  `(session, last_err)`.
- `process`: a `max_tokens` check next to the `max_minutes` check
  (`:180-184`), and a second one in the attempt loop beside
  `attempt > max_attempts` (`:203-208`). Both call
  `park("max-tokens", …)`.

### `lib/conveyor/config.py`

`_parse_role`'s regex gains `max_tokens` (`^(max_retries|max_minutes|max_attempts|max_tokens)=(\d+)$`),
`Role` gains `max_tokens: int = 0`, and `config.save` emits it **only when
non-zero** so an untouched two-pack `conveyor.conf` stays byte-identical and
`presets.resolve` does not flip to `custom`.

### `bin/conveyor`

`cmd_cost` + a `"cost"` entry in `COMMANDS`; one extra column in `cmd_status`'s
board loop. Number formatting (`450.4k`, `1.2M`) is one helper shared by both.

### `test/fake-agent`

A `usage <in> <out>` script verb emitting
`{"type":"result","usage":{"input_tokens":<in>,"output_tokens":<out>}}`, and
`usage-msg <in> <out>` emitting a per-message event, so both branches of
locked decision 3 are drivable without Cursor.

### Docs

- Protocol §6.6 ceilings table gains the `max_tokens` row and the amendment
  from locked decision 8; §6.9 gains the `usage.json` sidecar and the
  `event: usage` record; §6.10 gains `max-tokens` in the park-reason list.
- Runbook §6 status format, plus a §6.2 on reading `conveyor cost`.
- `conveyor.conf.example`: a commented `max_tokens=` on the coder line.
- `bin/README.md` Ambiguities: the `result`-wins-over-`messages` rule, the
  alias table, and "unknown usage never parks".
- PRD B.7: strike the metering half, leave loop detection.
- `CLAUDE.md` ceilings list gains `max-tokens`.

### Cockpit

`GET /api/cost` returning `read_task` + `total` per task, and nothing else in
phase 1. The board card's token badge is a Stage 5 item and is not in this
plan. **Do not land a badge before `conveyor cost` prints** — a UI that shows
a number the CLI cannot is the failure mode this product refuses.

---

## Tests

`test/test_usage.py` (new, pure unit — no agent, no worktree):

1. `scan` on a stream with a final `result` usage event → `source: result`,
   the result's numbers, per-message events present but ignored.
2. `scan` on per-message-only events → `source: messages`, summed.
3. `scan` on a stream with both → the `result` wins; the sum is **not** used
   (this is the double-billing guard).
4. `scan` on a log with no usage anywhere → `source: none`, fields `None`.
5. `scan` tolerates the non-JSON `{"type":"output"}` wrapper lines the stamper
   writes, and a truncated final line.
6. Every alias in the table maps to the right field.
7. `total` over a mixed list reports `unknown` = the count of `source: none`
   runs and does not treat them as zero.

`test/test_cost_cli.py` (new):

8. `conveyor cost` with no usage files at all → the empty-state line, exit 0.
9. `conveyor cost <task>` after a fake-agent run → one row, correct totals.
10. `conveyor cost` on an unknown task → dies like `conveyor log`.
11. `conveyor status` board row prints `tok -` when unknown, `tok 97.3k` when
    known (runbook §6 format).

`test/test_m4_ceilings.py` (extended — this is where ceilings live):

12. `max_tokens=1000` with a fake agent scripted to report 5000 → parks
    `max-tokens`; `needs-human/<task>/reason` first line is exactly
    `max-tokens`; board lane `needs-human`.
13. The park happens **between attempts** of one item, not only on the next
    dequeue (locked decision 8): a single item whose attempt 1 blows the
    budget parks without a second agent run.
14. `max_tokens` unset → no park however much the agent reports.
15. Usage `source: none` on every run → no park, even past the ceiling
    (locked decision 9).
16. The existing status-format assertion, updated for the `tok` column.

`test/test_inv03_rename_only.py`: the usage sidecar is written through
`util.atomic_write` (`.tmp` + rename) and never re-opened for append.

`test/test_config_inbox.py` or `test_presets.py`: a `conveyor.conf` with no
`max_tokens` round-trips through `config.save` byte-identically, and
`presets.resolve` still matches the built-in slug.

---

## Verification

```
cd test && python3 -m unittest discover -p 'test_*.py'
```

206 tests green before, plus the new ones after. Then, against a **live**
`cursor-agent` (this is the step the whole plan is hedged on):

1. Run one real task. `grep '"usage"' .conveyor/logs/coder/*.jsonl` — confirm
   the shape and whether it is cumulative or per-message.
2. `conveyor cost <task>` — does the total match what the vendor dashboard
   says for that window? If `source: result` and the numbers disagree, the
   alias table or the rule choice is wrong; fix the table, not the totals.
3. Force a `findings` bounce; confirm the second coder run appears as its own
   row and the task total climbs.
4. Set `max_tokens` just under the observed spend, re-run, confirm the park.

If step 1 finds nothing at all: land phases 1 and 2 anyway with
`source: none` everywhere — the sidecar, `duration_s`, `conveyor cost` and the
run-count column are still the wall-clock/attempt visibility that is missing
today — and record in `bin/README.md` that the agent reports no usage. Do
**not** substitute an estimate.

---

## Order of work

0. One live run; look at the log (above). This orders everything after it.
   **Not done** — no M3 run has happened. Steps 1–8 landed without it, on the
   `source: none` posture the plan was hedged on.
1. `lib/conveyor/usage.py` + tests 1–7. Pure, no wiring, no risk. **done**
2. Fake-agent `usage` verbs. **done** — `usage <in> <out>` and `usage-msg <in> <out>`.
3. `run_agent` writes the sidecar and the log record; test 9. **done**
4. `conveyor cost`; tests 8–10. **done**
5. `conveyor status` column + runbook §6 + test 11, 16. **done**
6. `max_tokens` in config + the two checks + tests 12–15. **done**
7. Protocol §6.6 / §6.9 / §6.10, PRD B.7, `bin/README.md`, `CLAUDE.md`,
   `conveyor.conf.example`. **done** — `bin/README.md` Ambiguities 49–52.
8. `GET /api/cost`. **done** — API only; no board badge, per Cockpit above.

Steps 1–4 are additive and land safely on their own: nothing parks, nothing
changes format, and the operator gets the number. Step 5 touches a normative
format and step 6 can park a live task — do not merge them into one commit.

---

## Built differently from the plan

Three places where the code does not match the text above. Each is a correction,
not a shortcut.

1. **The log record's token keys are `input_tokens` / `output_tokens`, not
   `input` / `output`.** The plan's record collides with `cmd_log`: `output` is
   already in `LOG_DETAIL_KEYS`, so a bare `output` key prints the raw number a
   second time after the formatted `text`. The sidecar keeps the short names.
2. **`run_agent` does not return the scan.** The plan has it returned alongside
   `(session, last_err)`, but nothing reads it: locked decision 7 makes the
   ceiling task-wide across every role and attempt, so `over_tokens` sums the
   sidecars on disk — including the one just written — rather than the run in
   hand. Returning it would be dead code.
3. **`usage.total` over runs that all reported nothing is `None`, not `0`.** The
   plan specifies `-` in the cells and an `unknown` count, but a summed `0` would
   have reached `conveyor cost` as a real number. Decision 4 only holds if the
   absence propagates through the sum. A test asserts it.

Two things the plan left implicit that the code fixes in one place: `usage.human`
(`450.4k` / `1.2M` / `-`) and `usage.clock` (`47m` / `2h11m`) live in `usage.py`,
not in `bin/conveyor`, because `role-loop.sh` needs the first one too and the same
number must never appear in two shapes.

---

## Tag

Unreleased, after `v0.4.0-rc1`. Does not block M3 or `v1.0.0` — but step 0
**depends** on an M3-style live run, so it is naturally sequenced after the
first real Cursor session. Copy a one-liner into the living tag plan when
steps 1–4 land.
