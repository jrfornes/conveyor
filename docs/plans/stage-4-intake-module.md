# Stage 4 — Intake becomes its own module

> **Implemented 2026-09-05.** Suite went 206 → ~245. What shipped matches the
> locked plan; deviations are noted inline as **[as built]**.

## Context

`ticket-reviewer` graded incoming tickets but lived in `roles/` next to coding
roles, took ceilings from a hardcoded fallback, and appeared in the UI as a
sidecar. It is not on the belt, never runs while loops run, and is unaffected
by switching workflows. Stage 4 gives it `intake/`, editable model/ceilings
from Inbox with no loop restart, and Jira credentials in a gitignored file
the UI can write.

## What shipped

- `intake/ticket-reviewer.md` + `intake/rubric.md` (TEMPLATED, operator-owned)
- `lib/conveyor/intake.py` — paths, tolerant rubric read, `init` migration
- `ensure_worktree` injects the rubric after `project.md` for intake only;
  coding-role `.mdc` files are unchanged
- `config.write_inbox()` — surgical `[inbox]` edit; `None` sentinel so `0` stays `0`
- Intake `max_minutes` is real; a park is unparked back to `imported`
- `lib/conveyor/jira.py` — `.conveyor/local/jira.json`, Basic auth, v3, `redact()`
- CLI: `conveyor intake config`, `conveyor intake jira` (no `--token` flag)
- `GET /api/intake` + `POST /api/intake/{prompt,rubric,config,jira}` (no `require_stopped`)
- Inbox settings rail; sidecar removed from Workflow and Roles

## [as built]

- Intake HTTP API is POST-only, same as roles/project/runtime. Spec §13.3 said GET/PUT.
- Intake one-shot uses `age >= max_minutes * 60` so `max_minutes=0` arms on the
  same pass. Belt roles keep `>` so a just-started task still gets one attempt (M4).
- `jira_token_env` alone no longer fetches a body (no email → no Basic header).
  Not a practical regression — Bearer never worked against Cloud.

## Verification

```
cd test && python3 -m unittest discover -p 'test_*.py'
cd ui && npx tsc -p tsconfig.app.json --noEmit && npx ng build --configuration development
```
