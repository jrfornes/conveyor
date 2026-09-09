# Token cost on Cursor — close step 0, either way

**Status:** planned. This is step 0 of [token-cost.md](token-cost.md), which
shipped every other step on the hedge that a live run would come later and say
what `cursor-agent` reports. It has not. This plan makes the hedge pay out in
one of two directions and forbids a third.

**Job:** `lib/conveyor/usage.py` reads token counts under Claude Code's key
names. Cursor's documented `stream-json` terminal event carries no usage object.
Until someone looks at a real log, `conveyor cost` and `max_tokens` are either
silently inert or silently one alias away from working, and the runbook
advertises both as if they work. Look at the log; then make the code and the
docs say the same thing.

Not a price table, not loop detection, not an estimate (token-cost decisions 4,
5, and the B.7 split still hold).

---

## Why

### The alias table is Claude Code's result event

`usage.ALIASES`:

| Field | Aliases |
| --- | --- |
| `input` | `input_tokens`, `prompt_tokens`, `inputTokens` |
| `output` | `output_tokens`, `completion_tokens`, `outputTokens` |
| `cache_read` | `cache_read_input_tokens`, `cached_tokens` |
| `cache_write` | `cache_creation_input_tokens` |
| `cost_usd` | `total_cost_usd`, `cost_usd` |

`cache_read_input_tokens`, `cache_creation_input_tokens`, and `total_cost_usd`
are the fields of Claude Code's `type: result` event, verbatim. `RESULT_SUBTYPES`
(`error_max_turns`, `error_during_execution`) are its subtypes. The scanner is
shaped around an agent Conveyor no longer runs.

### Cursor's documented terminal event has no usage

The CLI reference for `--output-format stream-json` gives the terminal event as:

```json
{"type":"result","subtype":"success","duration_ms":…,"duration_api_ms":…,
 "is_error":false,"result":"…","session_id":"…","request_id":"…"}
```

No `usage`, no token fields, and the same for the `json` format. The docs add
that "field additions may occur over time in a backward-compatible way", which
is exactly what `ALIASES` was built to absorb — but absorbing a field that may
never arrive is not the same as having the feature.

### The code already degrades honestly; the docs do not

Token-cost decision 9 means a run that reports nothing writes `source: none`,
`conveyor cost` prints `-`, and `max_tokens` never parks. So nothing is wrong
in the loop. What is wrong is `docs/runbook.md` §6.2, `conveyor.conf.example`,
and `bin/README.md` describing `max_tokens` as a working ceiling, and
`test/fake-agent` emitting the Claude shape so `test_usage.py` proves the
scanner against events the real agent never produces.

---

## Locked decisions

1. **One live run decides, and it is the smoke test.** With
   [cursor-cli-runtime.md](cursor-cli-runtime.md) in place, `conveyor start`
   already runs the agent once per role with `--output-format stream-json`.
   That output is tee'd to `.conveyor/logs/<role>/smoke.jsonl` (new; the smoke
   currently discards it). The operator then runs:

   ```
   grep -o '"usage"[^}]*}' .conveyor/logs/*/smoke.jsonl | head
   grep -o '"[a-zA-Z_]*[tT]okens*"[^,}]*' .conveyor/logs/*/smoke.jsonl | sort -u
   ```

   Either something prints or nothing does. No M3 task is needed to find out.

2. **If usage is present under keys `ALIASES` lacks, extend `ALIASES` and
   nothing else.** The table exists for this. The fake agent's `usage` and
   `usage-msg` verbs switch to emitting the observed Cursor shape; the Claude
   keys stay in `ALIASES` (a second backend may use them) but the fixture
   stops pretending they are what Cursor sends. The `bin/README.md`
   Ambiguities entry that hedged on the shape is updated with the observed
   event, quoted.

3. **If usage is absent, say so in every place that currently implies
   otherwise, and add one runtime hint.**

   - `conveyor.conf.example`: the `max_tokens` comment gains "Cursor CLI does
     not report usage in `stream-json` as of <version>; on Cursor this ceiling
     never fires and `conveyor cost` shows `-`. Use `max_minutes`."
   - `docs/runbook.md` §6.2: same sentence, plus the two grep lines from
     decision 1 so an operator can re-check after a CLI update.
   - `bin/README.md`: an Ambiguities entry recording the observed event and
     the date.
   - `conveyor start` warns once when any role line sets `max_tokens` and the
     smoke log for that role carried no usage: `warning: <role> sets
     max_tokens but the agent reported no usage in its smoke run; the ceiling
     will not fire`. A warning, not a refusal: the operator may be about to
     upgrade the CLI.
   - `conveyor cost`, when every run in view is `source: none`, prints one
     trailing line: `no run reported usage; see runbook §6.2`. The `-` cells
     stay.

4. **Nothing is estimated.** Not from `duration_ms`, not from prompt length,
   not from a price list. Token-cost decision 4 stands: a fabricated bill is
   worse than no bill.

5. **`RESULT_SUBTYPES` is left alone.** The extra subtypes are harmless and
   cost nothing. Removing them would only break a future backend for tidiness.

---

## Out

- Pulling usage from anywhere other than the agent's own stdout: no Cursor
  dashboard scraping, no `agent about`, no API.
- Dollar ceilings, `max_cost`, prices (token-cost decision 5).
- Changing the sidecar format, `conveyor cost` columns, or `conveyor status`.
- Deciding the outcome in this plan. The plan has two branches on purpose; the
  smoke log picks one.

---

## Operator surface

Decision 3 only. Decision 2 changes nothing an operator sees except that the
numbers appear.

### `conveyor start` (usage absent, `max_tokens` set)

```
coder: smoke ok
warning: coder sets max_tokens but the agent reported no usage in its smoke run; the ceiling will not fire
```

### `conveyor cost` (usage absent)

```
TASK          RUNS  IN        OUT      TOTAL     WALL
add-login        4  -         -       -         1h12m
              ----  --------  -------  --------  -----
                 4  -         -       -         1h12m
1 task, 4 runs.  4 runs reported no usage.
no run reported usage; see runbook §6.2
```

The existing `N runs reported no usage` summary already counts them; the new
line only appears when the count equals the total, and tells the operator
where to read why.

---

## Implementation

### `bin/conveyor`

- Smoke: tee the agent's stdout to `.conveyor/logs/<role>/smoke.jsonl`
  (overwrite per start; it is diagnostic, not history). After the run,
  `usage.scan(path)` — if `source == "none"` and `cfg.role(role).max_tokens`,
  print the decision 3 warning.
- `cmd_cost`: after the table, if every row's `source` is `none`, print the
  trailing line.

### `lib/conveyor/usage.py`

- Decision 2 branch only: new tuples in `ALIASES`. No logic change.

### `test/fake-agent`

- Decision 2 branch: `usage` / `usage-msg` emit the observed Cursor keys.
- Both branches: a `smoke-json` verb is unnecessary; the existing `exit 0`
  path already emits a `result` event without usage, which is the Cursor shape.

### Docs

- Per decision 3, or per decision 2's README entry. Never both.

---

## Tests

1. `conveyor start` with a fake that reports no usage and a role line carrying
   `max_tokens=1000` prints the exact warning; without `max_tokens`, no warning.
2. `conveyor cost` over sidecars that are all `source: none` prints the trailing
   line; with one `source: result` row it does not.
3. Decision 2 branch: `usage.scan` on a fixture log copied from the real smoke
   output (checked in under `test/fixtures/cursor-smoke.jsonl`, secrets and
   paths scrubbed) returns the observed numbers under `source: result`.
4. `smoke.jsonl` exists after `conveyor start` and is replaced, not appended,
   on the next `start`.

---

## Verification

1. `conveyor start` against the real CLI. Run the two grep lines. Write the
   result — the raw event, or "nothing" plus `cursor-agent --version` — into
   `bin/README.md` Ambiguities before touching anything else.
2. Follow decision 2 or 3 accordingly.
3. `test/` green.

---

## Order of work

1. Smoke tee + `smoke.jsonl` (depends on cursor-cli-runtime.md's smoke rewrite;
   if that plan is not taken, tee the existing smoke instead — the file is the
   point, not the prompt).
2. Verification step 1. This is the whole reason the plan exists; nothing
   after it is written until this is.
3. Decision 2 **or** decision 3, plus tests 1–4 as applicable.

---

## Tag

With [cursor-cli-runtime.md](cursor-cli-runtime.md), before M3. Cheap: the
expensive part was done in token-cost; this is the one step it could not do
without an agent to look at.
