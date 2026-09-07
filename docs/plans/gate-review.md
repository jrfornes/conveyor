# Gate review — diff against intent, reject carries findings

**Status:** planned. Not started.

**Job:** when a gated `ready` is held in `.conveyor/approvals/pending/`, the
operator can **see the change next to `tasks/<name>.md`** and **act once**:
Approve (no comments), Reject (comments become findings the gated role
reads on retry), or Delete (drop the held task). CLI is the contract; the
cockpit dialog wraps it.

This is the review-UX hole named in the field scan (inline diff + structured
reject). It is **not** PRD B.5 (per-document comments, clarification chat,
`artifacts` header).

---

## Why

The hold already works. `conveyor approve <id>` delivers to the next role;
`conveyor reject <id>` returns a `findings` notify to the gated role and
preserves `task_id` / `audit_count` (`queue.approve_pending` /
`queue.reject_pending`; `test/test_pipeline.py`).

The operator cannot **judge** the hold:

| Surface | Today |
| --- | --- |
| CLI | `approve` / `reject` are fire-and-forget. `conveyor status` does not list pending holds. There is no `git show` of the held commit. |
| Cockpit | `SpecApproveDialogComponent` shows only `tasks/<name>.md`. Reject comments sit on the same form as Approve. Empty comments still POST `/api/reject`; the CLI then dies (`comments required`). |
| Unused plumbing | `GET /api/commits/<sha>` already runs `git show --stat` (`state.git_commit_stat`). Nothing in `ui/src` calls `commitStat()`. |

The gated commit is in the shared object store (worktree SHA). `git show
<commit>` from the main checkout is enough; no merge, no worktree cd.

---

## Locked decisions

1. **CLI is the contract.** Every write the UI does already shells out to
   `bin/conveyor`. Reads for this surface go through one helper used by both
   `conveyor review` and `GET /api/approvals/<id>`. No second store.
2. **No per-file comments.** B.5 stays out. No `artifacts` header, no
   `path → comment` map, no Approve-disabled-until-file-comments-cleared.
   Comments are one textarea, become the reject body.
3. **Diff is `git show` of the held commit vs its first parent**, not vs
   `main`. The question is “what did this hop produce?” If the specifier
   edited `tasks/<name>.md`, that shows up in the patch; the left pane is
   still the operator’s intent file on the current checkout.
4. **`conveyor approve` stays one-shot.** Do not print the diff, do not
   require a prior `review`, do not add `--preview`. The read command is
   `conveyor review <id>`.
5. **Empty reject comments stay illegal.** CLI already refuses. The dialog
   must disable Reject while the textarea is blank, and disable Approve
   while it is non-empty (typed findings are not silently dropped).
6. **One dialog, not a reject modal on top.** Buttons: Cancel · Delete ·
   Reject · Approve. No separate “Accept unchanged” — that is Approve after
   clearing the textarea. (Dashboard spec F7 assumed a reject-only modal.)
7. **Delete of a held task is allowed.** Today `conveyor task <name> --delete`
   dies if `lane` is a role name. A hold keeps `lane` = gated role while the
   handoff sits in `approvals/pending/` and nothing is `in_process`. Extend
   `--delete` only for that case: remove the pending file, then the existing
   board / fp / park cleanup. `tasks/<name>.md` and `sent/` stay, as now.
8. **`conveyor status` grows an `approvals:` block**, same shape as
   `needs-human:` (always print the header; rows when held). Runbook §6 is
   normative; tests that snapshot status must be updated.
9. **Intake review is out of scope.** Ticket vs proposed-task is a different
   gate (`IntakeReviewDialogComponent`). Do not mix.
10. **Unsent comment drafts are in-memory only.** Do not add
    `.conveyor/approvals/<id>/comments.txt`.
11. **Do not block Approve on having opened Review.** A CLI operator who
    already ran `git show` must not be punished.

Record (8) and the held-delete exception in `bin/README.md` Ambiguities when
implementing.

---

## Out

- Per-document review comments, comment history, Approve-disabled-on-file-marks
  (dashboard spec F4–F5 / PRD B.5).
- `artifacts` header (PRD B.10).
- Clarification / `question` verdict (B.5).
- Master chat, pane injection, tmux viewer (B.2, B.6 F9–F10).
- Chime / held badge on the kanban (Stage 5).
- Token/cost gauges (B.7).
- Making `conveyor approve` interactive.
- Changing `reject_pending` body format (`Rejected by operator:\n\n` + comments).
  Role-loop already feeds the inbound handoff file into the prompt.

---

## Operator surface

### `conveyor review <id>`

Pure read. `<id>` is the handoff `id` or the task name (same lookup as
`find_pending`). Missing → die like `conveyor approve`.

Print, in this order:

```
# <id>  task <name>  <commit>
# <from> → <to>  verdict ready

## tasks/<name>.md
<file text or (missing)>

## git show <commit>
<git show --format=fuller --stat -p --no-color>
```

If the patch exceeds 100 KiB, print `--stat` plus the first 100 KiB and a
final line `truncated; git show <commit>`. `GIT_PAGER=cat`. Binary files stay
whatever `git show` does by default (usually “Binary files differ”).

The operator then runs `conveyor approve <id>` or
`conveyor reject <id>` (stdin / `--comments <file>`), unchanged.

### `conveyor status`

Insert after `needs-human:` and before `board:`:

```
approvals:
  specifier-000003  demo  abcdef1234  specifier → coder
```

Columns: id, task, 10-hex commit, `from → to`. Empty block is just the
header (same as an empty `needs-human:`).

Runbook §6 sample: add a three-role snippet *or* a one-line note under the
existing two-role sample that a gated belt also prints `approvals:`. Prefer
extending the sample with a gated row so the format is copy-pasteable.

### `conveyor task <name> --delete`

If `find_pending` matches this **task name**, delete that pending file first,
then today’s cleanup. Still refuse when the lane is a live role **and** there
is no hold (in-flight). Confirm copy in the cockpit already says board row +
fps; mention the pending handoff when one exists.

### Cockpit dialog

Replace the spec-approve dialog (keep the component name or rename to
`GateReviewDialog` — either is fine; copy should say **Gate review**, not
“Spec approval”, because the gated role need not be specifier).

Layout (same two-column idea as intake review):

```
Gate review · <task>     <id>  <commit>
<from> → <to>

┌ tasks/<name>.md (intent) ┬ git show (this hop) ┐
│ numbered markdown        │ patch, add/del tint │
└──────────────────────────┴─────────────────────┘
Reject comments (findings on retry)   [textarea]
Cancel    Delete    Reject    Approve
```

- Load via `GET /api/approvals/<id>` (task text + patch in one call).
- Approve: `POST /api/approve` as now. Disabled while comments are non-empty.
- Reject: `POST /api/reject` as now. Disabled while comments are empty.
- Delete: existing confirm → `POST /api/tasks/delete` once CLI allows held
  deletes.
- Cancel / Escape: no write.
- Patch pane: monospace, `pre-wrap`, add/del coloring from line prefix
  (`+` / `-`) is enough; do not pull a diff library.
- Attention strip button stays **Review** and opens this dialog.

`GET /api/commits/<sha>` may keep serving `--stat` for other callers; the
dialog should not depend on it.

---

## Implementation

### Helper

Add `queue.review_pending(paths, root, hid) -> dict` next to `find_pending`.
Reads the held handoff, `tasks/<name>.md` from `root` (empty string if
missing), runs `git show` via `util.git` with `check=False` / catch missing
SHA. Returns JSON-serializable fields: `id`, `task`, `from`, `to`, `verdict`,
`commit`, `task_id`, `task_text`, `patch`, `truncated` (bool), `subject`.

CLI `cmd_review` formats that dict. HTTP `GET /api/approvals/<id>` returns it
as JSON. 404 if `find_pending` misses.

Do not parse agent prose. The patch is git’s bytes as text.

### Protocol / docs

- Protocol §3.2 human-gate paragraph: operator **reads** with
  `conveyor review <id>` (`git show` of `commit` + `tasks/<name>.md`);
  **writes** remain `approve` / `reject`. Delete of a held task is
  `task --delete`.
- Protocol §10 table: add `review`, `approve`, `reject` (today they appear
  in the operator-role row at the top and not in §10).
- Protocol §2.3 writer table: unchanged (pending dir writers stay sweep /
  approve / reject).
- Runbook §4: `conveyor review <id>` on the approve/reject row.
- Runbook §6: `approvals:` block.
- `CLAUDE.md` CLI list: `review`.
- `bin/README.md`: held `--delete`; `approvals:` on status.
- `ui/README.md`: gate review shows the commit, not only the task file.
- PRD B.5 “still deferred” sentence stays true (per-doc comments). Optionally
  one line that gate *preview* is in.

### CLI / lib

| Change | Where |
| --- | --- |
| `review_pending` | `lib/conveyor/queue.py` |
| `cmd_review` | `bin/conveyor`; register in `COMMANDS` |
| `cmd_status` `approvals:` | `bin/conveyor` |
| held `--delete` | `cmd_task` |
| usage banners | `bin/conveyor`, `bin/README.md` Layout |

Reject / approve implementations stay as they are.

### UI server

| Change | Where |
| --- | --- |
| `GET /api/approvals/<id>` | `httpd.py` + `state.py` (thin wrap of `review_pending`) |
| `POST /api/approve` / `reject` / `tasks/delete` | unchanged |

### Cockpit

| Change | Where |
| --- | --- |
| Dialog: two panes, button enable rules, Delete | `spec-approve-dialog.component.ts` (or renamed) |
| Open path loads `/api/approvals/<id>` | `cockpit.component.ts` `openSpecApprove` |
| API client | `conveyor-api.service.ts` |
| Strip copy “Spec approval” → “Gate review” if you rename | `attention-strip.component.ts` |

No new poll fields. `/api/state` already lists `approvals[]`.

---

## Tests

CLI / protocol (extend `test/test_pipeline.py` or a small `test_gate_review.py`
on a spec-then-build fixture):

1. After specifier `ready` is held, `conveyor review <id>` exits 0, stdout
   contains `tasks/<name>.md` text and the commit subject from `git show`.
2. `review` unknown id dies with the same class of message as `approve`.
3. `conveyor status` contains `approvals:` and the id / task / 10-hex /
   `from → to` line; after `approve`, that row is gone.
4. `reject` with comments still returns `verdict: findings` to the gated
   role; body contains the comments; `task_id` / `audit_count` unchanged
   (existing test — keep).
5. `reject` with empty comments still dies (existing).
6. `task --delete` on a **held** task: pending dir empty, board row gone,
   fps gone; `tasks/<name>.md` remains. On an **in-flight** lane with no
   hold, still refused.

API (`test/test_ui_api.py`):

7. `GET /api/approvals/<id>` 200 with `task_text` and `patch` (or `truncated`).
8. 404 after approve.
9. UI reject with empty comments still 4xx via CLI (if the server surfaces
   the die).

Cockpit: no new unit-test framework. Manual: `bin/conveyor-ui --demo` does
not currently seed a held approval — either add a held file to the demo
fixture (`ui/server/demo.py`) so Review is clickable, or drive a
spec-then-build fixture by hand. Prefer seeding the demo.

`npx tsc -p ui/tsconfig.app.json --noEmit` clean.

---

## Verification

```
cd test && python3 -m unittest discover -p 'test_*.py'
cd ui && npx tsc -p tsconfig.app.json --noEmit
```

Browser (required — this is a dialog/layout change):

1. Spec-then-build (or demo with a seeded hold): strip shows the hold.
2. Review opens: left pane is the task file, right pane is the patch
   (additions visible for the specifier’s commit).
3. Approve with empty comments: row disappears, card moves to the next lane.
4. Type comments → Approve disabled, Reject enabled → Reject → card stays
   on the gated role, next specifier run sees the comments in the inbound
   handoff (or `cat` the new `inbox/new` file).
5. Hold again, Delete → confirm → board row gone, pending empty.
6. Two-pack Review belt: strip has no gate row; `conveyor review` dies
   “no pending”.

CLI-only operators: `conveyor status` → `conveyor review <id>` →
`approve` / `reject` without the UI.

---

## Order of work

1. `queue.review_pending` + `cmd_review` + tests 1–2.
2. `cmd_status` `approvals:` + runbook §6 + test 3.
3. Held `task --delete` + test 6.
4. `GET /api/approvals/<id>` + tests 7–8.
5. Dialog + strip copy + demo seed.
6. Browser pass; protocol §3.2 / §10 / CLAUDE.md / README Ambiguities.

Do not land the dialog before the CLI: a UI that shows a patch the CLI
cannot print is the failure mode this product refuses.

---

## Tag

Unreleased / next advertised snapshot after `v0.4.0-rc1`. Does not block
M3 or `v1.0.0`. Copy a one-liner into the living tag plan when you want it
in that tag.
