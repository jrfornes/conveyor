# Changelog

## Unreleased

**Token cost**

- **Every agent run records what it spent.** `.conveyor/logs/<role>/<task>_<id>_a<attempt>.usage.json`
  is written beside each run log, derived from it and never mutated, and the same numbers go into
  the log itself so `conveyor log` shows a run's spend. PRD §2 names "a stuck task retries until the
  bill arrives" as one of the four failure modes Conveyor exists to stop; wall-clock and retry count
  were bounded, cost was not visible at all. PRD B.7, metering half. Protocol §6.9.
- **The number is auditable or it is absent.** A stream can report usage as a cumulative total on
  its terminal event or as per-message deltas, and nothing in it says which — summing a cumulative
  total double-bills, last-winning a delta under-bills. A `result` event carrying usage wins
  outright and per-message events are ignored; per-message objects are summed only in its absence;
  and the rule that fired is recorded as `source`, so a wrong guess is visible in the file instead
  of silently doubling a bill. Unrecognised keys are ignored, never summed.
- **Unknown is never zero.** A run whose agent reported nothing still writes a sidecar with
  `source: none` — an absent file means the loop did not finish the run, which is a different fact.
  Unknown reads `-` on every surface and never `0`, because `0` is an answer an agent can give, and
  a set of runs that all reported nothing sums to unknown rather than to zero.
- **`conveyor cost [<task>]`** — a pure read (no lock, no writes, works on a stopped pipeline):
  one row per board task, or one row per agent run for a single task with the `source` that
  produced each number. `conveyor status` board rows gain a `tok` column. Runbook §6, §6.2.
- **`max_tokens=N` on a role line parks the task `max-tokens`.** Task-wide and read from the
  current role's config, exactly as `max_minutes` is, so a coder ↔ reviewer ping-pong is one
  budget. Checked between attempts as well as before each item — a task can spend the whole budget
  inside one handoff — but it never kills a running agent; only `max_minutes` does that. Absent or
  `0` is unbounded, and a task whose runs all reported nothing never parks: Conveyor refuses rather
  than parking on a number it invented. `conveyor resume` does not reset the total. Protocol §6.6.
- **Tokens, never dollars.** `cost_usd` is stored only if the agent reports one. Conveyor ships no
  price table: prices go stale, and a fabricated dollar figure on an operator's screen is worse
  than no figure. Dollar ceilings and a `[prices]` section remain a later decision.
- Usage lives in its own files rather than a `board.tsv` column: `board.COLS` is a fixed 8-tuple
  and any row with a different cell count is malformed, so widening it would make every
  pre-existing row invisible to `board.get`. `GET /api/cost` serves the same figures.

**Worktree setup**

- **`[global] worktree_setup` makes a role's tree runnable.** Every role works in its own git
  worktree, and worktrees do not share `node_modules` / a virtualenv / `vendor/`. On any project
  whose gates need installed dependencies, one operator-supplied command now installs them, at the
  two moments they are actually needed: a tree that is new or whose dependency inputs moved at
  `conveyor start`, and — the half that bites — in the role loop right after a merge that moved a
  watched path. Without the second, the reviewer merges the coder's new lockfile into a tree whose
  `node_modules` predates it, its gate fails on a missing module, and that becomes a finding
  against correct work. Protocol §6.3.
- Three keys, all optional and all in `[global]`: `worktree_setup` (absent or empty = the feature
  does not exist and no run path changes), `worktree_setup_paths` (the paths whose content
  triggers a re-run), `worktree_setup_timeout` (default 1800 s, `0` = unbounded). Setting paths
  without a command is a `ConfigError`.
- **Change detection is a content stamp, never mtime.** `.conveyor/roles/<role>/setup.stamp` is a
  sha256 over the blob oid of each watched path at the worktree's HEAD plus the command string. A
  merge rewrites mtimes constantly and none of it is evidence; the oids come from
  `git rev-parse HEAD:<path>`, so they cannot disagree with what was merged. Changing the command
  re-runs it everywhere. The stamp is written **only** on exit 0 — a failed install must not look
  done.
- **Failure refuses rather than guesses.** At `conveyor start` it dies before a single loop
  launches; in a loop it parks the item `setup-failed` before the ceiling checks and before any
  agent runs, with `conveyor resume <task>` the way out. The command's output is captured to
  `.conveyor/logs/<role>/setup.log` in the gate/integration shape (`exit: <code>`, or
  `exit: timeout`).
- **A live loop's tree is never installed into.** `conveyor start` is re-runnable and is routinely
  run against a belt that is already up; a role whose loop holds a live pid is warned about and
  skipped, which also makes protocol §2.3's single writer for `setup.stamp` true by construction.
- **A dirty tree warns, loudly, and is not refused.** `handoff.sh` refuses an uncommitted tree
  (`E_DIRTY`) and no agent can fix that from inside, so `conveyor start` names the first five
  paths and the total. The `.gitignore` stays the operator's.
- `conveyor setup [--role <role>] [--force]` runs the same hook outside `start`;
  `conveyor start --no-setup` skips it for one run and writes no stamp. A start where nothing
  changed says nothing about setup at all.
- Conveyor never detects a package manager: no npm/pnpm/yarn sniffing, no generated default, no
  lockfile heuristics. The command is opaque, and `bin/hooks/npm-worktree-setup` ships as a worked
  example to copy and edit — with the two cheap alternatives (a shared store, a symlink) and their
  trade-offs named in its docstring.
- New `util.run_bounded`: one helper that runs a shell command in its own process group under a
  deadline and writes the gate-style log. `shell=True` with a plain `timeout=` kills the shell and
  orphans the install, which is the bug it exists to not have. It escalates through the
  `util.kill_group` that run deadlines landed, rather than repeating it.

**Run deadlines: nothing hangs forever**

- **`max_minutes` now kills the run, not just the next dequeue.** It was checked once, before the
  attempt loop, and the run itself was an unbounded `wait()` — so an agent that wedged on attempt 1
  stopped the belt indefinitely and never parked. The agent now runs under a deadline equal to what
  is left of the task's budget (floored at 60 s, so `max_minutes = 0` keeps parking on the
  pre-flight check as it always did). Protocol §6.6, §6.9.
- **Kills are process-group kills.** The agent is launched with `start_new_session`; the deadline
  sends `TERM` to its group, then `KILL`. Terminating only the agent left children holding its
  stdout, which kept the log stamper — and so the loop — blocked on an EOF that never came.
  `conveyor stop --now` now stops the tree for the same reason (§6.7).
- A killed run is **not** a failed attempt: no `attempt` increment, no `--resume` retry. It parks
  `max-minutes` immediately, with a detail beginning `killed attempt <n> after <n>m<n>s`. The
  pre-flight park keeps its old `task started <ts>, …` wording, so the two are distinguishable.
- The outbox is re-checked after a kill and before parking: an agent that queued a valid handoff and
  then wedged still has its item forwarded. The outbox stays the only signal.
- The run log gains an `event: killed` record before `event: exit`, with `after_s` and `escalated`
  (true when `TERM` was not enough and `KILL` followed — wedged, not merely busy).
- **Project gates are bounded too.** `[global] gate_timeout` in `conveyor.conf` (default 900 s;
  `0` = unbounded) sets the budget for any one gate, overridden per gate by an optional
  `## Gate timeouts` section in `project.md`. A gate that runs past its budget fails with the new
  `E_GATE_TIMEOUT` — an ordinary validator refusal with repair text the agent can act on within its
  remaining attempts, rather than an opaque death when the run deadline eventually fires.
- Gates get their own process group as well: under `shell=True` a plain timeout kills the shell and
  orphans the command that is actually stuck. `handoff.sh` installs a `SIGTERM` handler so the gate
  in flight goes down with a killed run instead of outliving it.
- A timed-out gate writes the same log as a failed one — same path, the output it had managed so
  far, and `exit: timeout` on the first line. `conveyor gate run` honours the same budget and dies
  with the elapsed seconds and the log path.

**Dated role logs**

- **Run logs carry the time of every line.** `.conveyor/logs/<role>/<task>_<id>_a<attempt>.jsonl`
  used to be a plain redirect of the agent's stream, with no clue when anything happened. Each line
  now gets an `at` header (UTC, the format used everywhere else) as its first key; the agent's own
  keys are untouched, and non-JSON output is wrapped so the file stays valid JSONL. Protocol §6.9.
- The stamping runs as its own process (`role-loop.sh --stamp`), not inside the loop, so a
  `kill -9` of a loop still leaves the agent running and its output landing in the log
  (invariant 11).
- The loop brackets each run with dated records of its own: `event: run` (attempt, model, whether
  the session was resumed) before launching, `event: exit` with the exit code after.
- `conveyor log <role>` prints the run's date in the header and a UTC clock column per line, with
  wrapped output indented into the same column. Logs written before this change still render, with
  a blank clock.
- **`.conveyor/logs/<role>/loop.log` is a timeline.** Every line a loop prints is prefixed with a
  timestamp, and the loop now says which item it picked up, each attempt it started and the agent's
  exit code, and how the item ended. Protocol §6.11.
- The cockpit's Log tab shows the same clock column and the run's start time.

**Intake: rubric UX**

- Split the operator checklist (`intake/rubric.md`, items only) from Conveyor's fixed grade
  contract (`Ready` / `Gaps` / `Unusable` and the `Grade:` first-line rule). The contract is
  injected into the ticket-reviewer worktree on every `conveyor start`, even when the rubric file
  is missing.
- Cockpit: grade chips with tooltips in the inbox table; review dialog shows verdict + checklist
  side by side (not a "Gaps" heading on Ready tickets); settings rail explains what is editable vs
  fixed.

**Intake: grade integrity**

- **Fixed: a ticket could be graded `Ready` by prose.** `inbox.parse_grade` searched the first 30
  lines of `grade.md` for the words ready/gaps/unusable anywhere, so an ordinary gap — "acceptance
  criteria are not ready" — became the verdict. The grade now comes only from a `Grade: Ready|Gaps|
  Unusable` line (leading `#`/`*`/`_`/whitespace tolerated); a grade file without one records
  `unparsed`, and no grade file records `-`.
- `conveyor inbox approve` refuses `Unusable`, `unparsed`, and `-` unless you pass `--force`. The
  grade was previously advisory: an ungraded ticket could go straight into `tasks/`.
- `conveyor intake` refuses an item that is `ready` or `started` — its task file is already
  committed. `skipped` items stay re-gradable.
- `conveyor intake` now prints the recorded verdict (`graded <id>  Ready`), and warns when
  `grade.md` carried no `Grade:` line.
- `comments.txt` is renamed to `comments-applied.txt` after a successful one-shot, so operator
  feedback reaches the ticket-reviewer once instead of being replayed on the next grade.
- Templates: `intake/ticket-reviewer.md` and `intake/rubric.md` now state that the first line of
  `grade.md` is the verdict. **These are operator-owned and `conveyor init` never overwrites them**,
  so an already-initialized repo keeps its copies and must merge the change by hand — see runbook
  §9. Nothing breaks if you don't: the parser tolerates the old wording.

**Intake: CLI visibility**

- `conveyor inbox list` and `conveyor inbox show <id>` — the CLI had no read surface for the inbox
  at all; listing existed only in the cockpit. Both are pure reads.
- `conveyor status` gains an `inbox:` block, omitted entirely when nothing has been imported so the
  runbook §6 format is unchanged for repos that do not use intake.
- **Fixed: `conveyor intake <id> --comments <file>` always died with the usage message.** The
  positional count ran before the flag was stripped, so the flag's value was read as a second id.
- **Fixed: `conveyor intake` could crash with `FileNotFoundError` on `tmp/source.md`.** The
  worktree reset prunes `tmp/` when a previous run tracked it (a repo whose init files are not
  committed yet); it is re-created after the reset.

**Docs**

- Protocol §2.4 gains the legal `grade` values, `comments-applied.txt`, and the inbox status
  transition table (promoted out of `docs/archive/`, where it was the only copy).
- Protocol §4.1/§4.2 document the `ticket-reviewer` exemptions that `handoff.sh` has always
  implemented — `to: operator`, no `tasks/<task>.md`, no board row — which §4.2 as written would
  have rejected.
- Protocol §9 gains invariant 13 (inbox items are whole, legal, and backed by their task file),
  covered by `test/test_inv13_inbox.py`.
- Protocol §10 gains rows for `import`, `intake`, `inbox`, `start-task`, `approve`, and `reject`;
  it previously documented no intake command. It now states that `inbox approve` does not enqueue.
- Runbook: `conveyor init` copies `intake/` (§3 was stale); new rows for `inbox list`/`show`,
  `--improve`, `--comments`, `--force`, and `start-task`; `inbox:` in the §6 status sample; a new
  §9 upgrade note.

**Fixes**

- **Fixed: Grade failed on Jira Cloud attachments with `303 refusing cross-host redirect`.** Cloud's `GET /attachment/content/{id}` answers 303 to `api.media.atlassian.com` (documented success, not an error). Download asked only for a 302 CDN hop, so Import-and-grade stopped after the first ticket that had a selected image. Intake now sends `redirect=false` so the bytes stay on the Jira origin, and still follows a single cross-host 3xx without Authorization if the origin redirects anyway.
- **Fixed: `conveyor start` warned that the committed `.gitignore` lacked runtime paths and then started anyway.** Role worktrees only see `HEAD:.gitignore`, so skipping the commit after `init` let generated `.cursor/rules/conveyor-role.mdc` reach a handoff (`untracked-collision`). Start now appends any missing entries and commits `.gitignore` (and the same on an existing idle role branch) before creating worktrees.
- Approving an inbox item in a repo with no git identity failed mid-command: the task file was already written and staged, the cockpit showed a raw `CalledProcessError` traceback, and the next click died with `tasks/<task>.md already exists`. `conveyor task`, `conveyor inbox approve`, and `conveyor start` now check `git var GIT_COMMITTER_IDENT` first and print the `git config user.name/user.email` repair; a failed commit unstages (and, for approve, deletes) what it wrote; and an uncommitted `tasks/<task>.md` identical to the text being approved is adopted instead of refused.

**Maintenance**

- Jira site URL validation: `https` required (`http://127.0.0.1` / `localhost` for local Jira only); `/browse/KEY` pasted URLs canonicalized; cross-host redirects refused so Basic auth cannot follow a redirect off-site.

**Features**

- Cockpit inbox rows link to `/inbox/<id>`. The item page shows status, grade, source, proposed
  task, comments, attachments, and the next operator step, with the Grade / Improve / Approve /
  Start / Skip actions as full buttons. The inbox table keeps Grade, Review, and Start.

- Jira import writes metadata, comments, and allowlisted custom fields into `source.md`; ADF lists/links/mentions survive flattening. Empty body still means no spec text (not “no summary”).
- `conveyor import --refresh <id>` re-fetches a Jira ticket in place; `--replace <id>` overwrites `source.md`. Only `imported` items; re-importing the same key still creates `proj-9-2` and points at `--refresh`. Cockpit item page: **Fetch again** / **Edit source**.
- Jira inbox attachments: import records a manifest (no blobs). Default-select small images; video/audio/archives are listed and never downloaded. `conveyor inbox attachments <id> [--select …]` chooses what ticket-reviewer may scan; Grade/Improve fetches those files into `tmp/attachments/`.

- Intake → Jira **Test connection** saves the form to `jira.json` then checks credentials (same as `conveyor intake jira --test`).
- `conveyor.conf.example` no longer documents `jira_base` / `jira_token_env`; operators set Jira in `.conveyor/local/jira.json` (`conveyor intake jira` or the cockpit settings rail). The `[inbox]` keys remain fallbacks only.

## 0.4.0-rc1 — 2026-09-06

**Thicker 0.x snapshot after `v0.3.0-rc1`. Live Cursor (M3) not verified.**

**In**

- Named project gate catalog (`## Gates` + `## Required on`) with `{inbound}` / `{head}` substitutions; legacy `## Test command` unchanged
- `conveyor gate list|run`; cockpit Run now on Roles project tab
- Role library CRUD (`conveyor role list|show|new|delete|skills`) and cockpit new-role dialog
- Role skills from repo-root `.agents/skills` or `.cursor/skills` (agents wins on duplicate names; worktree copy keeps source path)
- `conveyor uninstall [--yes] [--bundle]` — runtime teardown for test/dev consumer projects
- Fail fast with a clear message when any entrypoint is run under Python < 3.10
- `conveyor-ui` auto-builds the Angular cockpit on first launch when `npm` is on PATH
- Intake lock is checked before status flips; Grade/Improve disable while ticket-reviewer is busy; Jira import refuses missing credentials, skips inbox rows on HTTP failure, and reports empty descriptions separately (no auto-grade)

**Out**

- M3 (first live Cursor run) — still unverified until archived
- `v1.0.0` (official usable) — M3 archived + D2 documented
- Chime, async intake HTTP
- PRD Appendix B features

**Known limits**

- UI `Start` calls `conveyor start --no-smoke` — CLI smoke still runs on direct `conveyor start`
- Intake grade blocks the HTTP request until the one-shot finishes (no progress UI)
- Workflow presets live in gitignored `.conveyor/` (per-checkout, not shared via git)

## 0.3.0-rc1 — 2026-09-05

**Protocol-complete release candidate. Live Cursor (M3) not verified.**

**In**

Stage 4 — intake is its own module, not a sidecar role.

- `roles/ticket-reviewer.md` moved to `intake/ticket-reviewer.md`; `intake/rubric.md` is injected into the one-shot `.mdc` after `project.md`
- `[inbox]` now holds `ticket_reviewer_max_minutes` / `ticket_reviewer_max_attempts` (0 is legal). `conveyor intake config` and Inbox → Intake settings write them surgically — loops may keep running
- Jira credentials live in `.conveyor/local/jira.json` `{site, email, token}` (mode 600). Auth is Basic, API v3
- **`jira_token_env` alone no longer fetches a ticket body.** Cloud needs email for Basic auth; `conveyor import --source jira` prints a one-line notice when email is missing
- A parked intake item is unparked back to `imported` (it has no board row, so `conveyor resume` cannot)
- `conveyor init` migrates the old prompt file; intake files are templated (operator-owned) and are not clobbered on repeat init

Core UI cockpit (Inbox, Board, Workflow, Roles):

- `bin/conveyor-ui` launches the localhost Angular cockpit (`ui/`)
- `conveyor-ui --demo` serves the cockpit against a throwaway fixture (queued task, parked task, inbox item)

Workflow CRUD + n-role pipelines (also described under 0.2.0, never tagged):

- `conveyor workflow` (`list`, `show`, `new`, `edit`, `delete`, `activate`) — saved presets over `conveyor.conf`
- n-role pipelines and a declared `gate <role>` / `gate none`
- Inbox/intake CLI: `import`, `intake`, `inbox approve|skip`, `start-task`
- Spec-hold: `approve` / `reject`

**Out**

- M3 (first live Cursor run) — next validation step
- Chime, async intake HTTP, “Run now” gate runner
- PRD Appendix B features

**Known limits**

- UI `Start` calls `conveyor start --no-smoke` — CLI smoke still runs on direct `conveyor start`
- Intake grade blocks the HTTP request until the one-shot finishes (no progress UI)
- Workflow presets live in gitignored `.conveyor/` (per-checkout, not shared via git)

0.2.0 below was never tagged on git; it is kept as a historical narrative of the workflow/UI work that this RC also ships.

## 0.2.0

Workflow CRUD, n-role pipelines, inbox/intake, and the UI cockpit.

**In**

- `conveyor workflow` (`list`, `show`, `new`, `edit`, `delete`, `activate`) — saved presets over `conveyor.conf`
- n-role pipelines and a declared `gate <role>` / `gate none`
- Inbox/intake: `import`, `intake`, `inbox approve|skip`, `start-task`
- Spec-hold: `approve` / `reject`
- Optional localhost UI cockpit (`bin/conveyor-ui`, `ui/`)

**Out**

- M3 (first live Cursor run)
- Remaining PRD Appendix B features

## 0.1.0

First CLI release.

**In**

- Operator CLI: `init`, `start`, `stop [--now]`, `task`, `task --delete`, `status`, `log`, `resume`
- Handoff protocol milestones M0–M2 and M4 (fake-agent test suite)
- `conveyor init` for target-repo setup

**Out**

- M3 (first live Cursor run)
- PRD Appendix B features
- UI cockpit under `ui/` (preview only, not part of this release)

Patch releases (`0.1.x`) are for live-run fixes; behavior changes ship as `0.2`.
