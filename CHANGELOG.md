# Changelog

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
