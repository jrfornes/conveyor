# Intake review UX — approve and start in one place

**Status:** implementing on `cursor/intake-review-ux-7fc9`.

**Job:** when an inbox item is `graded` or `awaiting-approval`, the operator reviews the
ticket-reviewer’s proposal and either improves it again or commits `tasks/<name>.md` and
optionally enqueues it — without bouncing through a detail page and without losing textarea
edits on Approve.

CLI stays the contract (`inbox approve` then `start-task`). The cockpit composes those steps.

---

## Locked decisions

1. **One Approve path.** The dialog textarea is always what gets committed. Remove “Edit then
   approve”; Approve and “Approve and start” both send `text` to `POST /api/inbox/approve`.
2. **Primary action is Approve and start.** Secondary: Approve only (stock `tasks/` without a
   board row). After Approve only, close with a snack — do not leave the operator on a page
   whose only job is Start.
3. **Reject → Improve again.** Same as `conveyor intake <id> --improve` with comments.
   Skip stays Skip.
4. **Mutually exclusive actions.** Approve disabled while Improve notes are non-empty; Improve
   again disabled while notes are empty.
5. **Force approve in the UI.** Checkbox when grade is `Unusable`, `unparsed`, or `-`; maps
   to existing `--force` on `inbox approve`.
6. **No proposal warning.** When `proposed-task.md` is empty, show that Approve commits stripped
   `source.md`, not a numbered rewrite.
7. **Review opens the dialog directly** from the attention strip and inbox table Review buttons
   (not only from the detail page).
8. **Improve keeps the dialog open.** Show a busy state until the intake HTTP call returns,
   then reload the item in place.
9. **Layout:** header (title, grade chip, task name), gaps strip from `grade.md`, two columns
   (original | editable proposal), attachment summary, Improve notes, actions.
10. **Quoted / invented** markers from the ticket-reviewer prompt are highlighted in a read-only
    preview under the proposal textarea (editing stays in the textarea).
11. **Full rubric stays in Intake settings** — dialog shows a one-line Ready-requires summary only.

Out: gate/spec review (`gate-review.md`), per-line comments, clarification chat.

---

## Files

| Area | Path |
| --- | --- |
| Plan | `docs/plans/intake-review-ux.md` |
| Helpers + opener | `ui/src/app/intake/intake-review.ts` |
| Tests | `ui/src/app/intake/intake-review.spec.ts` |
| Dialog | `ui/src/app/dialogs/intake-review-dialog.component.ts` |
| API client | `ui/src/app/services/conveyor-api.service.ts` (`force` on approve) |
| Strip / table / cockpit / detail | wire `openIntakeReview` |

---

## Verification

```bash
cd test && python3 -m unittest discover -p 'test_*.py'
cd ui && npx tsc -p tsconfig.app.json --noEmit
```

Manual (`bin/conveyor-ui --demo`):

1. Inbox → Review on `cave-lights` opens the dialog (not detail-only).
2. Edit a line in the proposal → Approve and start → board shows the task with your edit.
3. Type Improve notes → Approve disabled, Improve again enabled → dialog stays open, proposal refreshes.
4. Attention strip Intake approval → Review opens the same dialog.
