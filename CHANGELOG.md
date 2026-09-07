# Changelog

## Unreleased

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
