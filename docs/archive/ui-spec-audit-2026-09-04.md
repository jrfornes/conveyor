> **Archived 2026-09-04.** Superseded by
> [`design_handoff_conveyor/CONVEYOR-UI-SPEC.md`](../../design_handoff_conveyor/CONVEYOR-UI-SPEC.md),
> which is the current design source of truth. This copy predates the Workflow-CRUD,
> Roles-tab and Intake-module decisions and still uses the "pack" vocabulary. It is kept
> only for its **audit evidence** — the `file:line` citations proving which behaviours
> were already implemented as of this date. Do not implement from it.

# Conveyor UI — workflow spec

Source of truth for the behaviour shown in `Conveyor.dc.html`. Derived from the two design briefs and the prototype.

**Gap column status: audited, then closed.** The audit ran against the code on 2026-09-04; the gaps it found were then implemented (Phases 1–4). Rows below describe the code as it stands (`ui/src/app/`, `ui/server/`, `lib/conveyor/`, `bin/conveyor`). The `?` legend is retired — every row is now decided. Section 10 answers the open questions; section 12 lists the places where the code and this spec actually disagree.

Gap legend: **exists** · **partial** · **missing**

---

## 1. Ground rules

| Rule                               | Consequence in UI                                                             | Gap    |
| ---------------------------------- | ----------------------------------------------------------------------------- | ------ |
| Filesystem is the system of record | Every view is a projection of files; every action writes a file, nothing else | exists |
| UI polls every 2s                  | Live dot green while polls succeed; no websockets, no push                    | exists |
| Cards never dragged                | Lane changes only from pipeline                                               | exists |
| UI never auto-retries              | Parked tasks leave `needs-human/` only via Resume                             | exists |
| Agents never talk to the dashboard | No agent-triggered UI state; chime is derived from file diff between polls    | exists |
| Config applies on next Start       | Saving prompts / project.md / pack never hot-reloads running agents           | exists |

- Polling: `UiStateService.startPolling()` — `interval(2000)` over `GET /api/state`.
- No drag: `KanbanBoardComponent` has zero `cdkDrag` bindings; lane comes from `board.tsv`.
- Agents→UI: the server only *reads* the tree (`ui/server/state.py`); no agent writes to the UI. Marked partial only because the chime that this rule describes does not exist yet (see §6).
- Applies-on-next-Start is real: `roles/<role>.md` and `project.md` are concatenated into `.worktrees/<role>/.cursor/rules/conveyor-role.mdc` only by `ensure_worktree()` at `conveyor start` ([bin/conveyor:59-69](bin/conveyor#L59-L69)). Model/ceiling edits are refused with 409 while loops run.

---

## 2. Vocabulary

| Term            | Meaning                                                                  | Human label in UI                                                                          |
| --------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| role            | A job with one failure mode: specifier, coder, reviewer, ticket-reviewer | role name, lowercase                                                                       |
| pack / workflow | Ordered list of coding roles + whether the first handoff is human-gated  | **Review belt** (`coder → reviewer`), **Spec then build** (`specifier → coder → reviewer`) |
| agent           | One headless run of a role                                               | never surfaced as an entity                                                                |
| verdict         | Header on a handoff file                                                 | `ready`, `findings`, `pass`                                                                |
| operator        | The single human                                                         | `operator` node on belt                                                                    |
| task_id         | Per-role counter                                                         | `coder-000014`                                                                             |

Never show `2-pack` / `3-pack` in UI copy. The names come from `packs.STARTERS`; the CLI still takes `conveyor pack two|three`, which is operator-facing, not UI copy.

`spec` is **not** a verdict. `config.VERDICTS` is `("ready", "pass", "findings")`; the specifier's outbound verdict is `ready`, held for approval. Correct the brief.

---

## 3. Views and regions → components

| Region          | Component                                                                                             | Notes                                                                                                                                                    | Gap     |
| --------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| Header          | `HeaderComponent`                                                                                     | wordmark · repo · pack pill (name; tooltip = chain) · live dot · Inbox/Board/Pack toggle · loop status · Import · Start · Stop · New task               | exists  |
| Error line      | `AppShellComponent`                                                                                   | `.error-strip`, rendered when `ui.error()` is set                                                                                                        | exists  |
| Attention strip | `AttentionStripComponent`                                                                             | needs-human · intake approval · spec approval                                                                                                            | exists  |
| Kanban          | `KanbanBoardComponent`                                                                                | columns from `state.lanes`, each header carrying its lane avatar from `state.avatars`                                                                    | exists  |
| Work queue      | `WorkQueueComponent`                                                                                  | rendered inside the detail rail, one row per pack role                                                                                                   | exists  |
| Detail rail     | `DetailRailComponent`                                                                                 | Task · Log · Queues                                                                                                                                      | exists  |
| Pack            | `PackPageComponent` + `BeltDiagramComponent`, `RoleCardsComponent`, `EditorPaneComponent`             | full page exists                                                                                                                                         | exists  |
| Dialogs         | `NewTask`, `Import`, `IntakeReview`, `SpecApprove`, `Confirm`                                         | one `ConfirmDialogComponent` backs Stop, Delete, Switch pack and start-loops                                                                             | exists  |

- Kanban is partial: column headers render the lane name, not the role avatar. `packs.avatar()` is served on `/api/pack` but the board does not consume it.
- Work queue is partial: see §7.
- The Pack toggle exists ([header.component.ts:35](ui/src/app/header/header.component.ts#L35)) and routes to `/pack`.

---

## 4. State machines

### 4.1 Loops / connection

```
not-initialized ──Start──▶ stopped ──Start──▶ running ──Stop──▶ stopped
                                                 │
                                          poll fails ──▶ disconnected (last-known board shown)
                                                 ◀── poll ok
```

| State           | Live dot | Status text                 | Board                   | Start    | Stop            | Pack fields                                         | Gap    |
| --------------- | -------- | --------------------------- | ----------------------- | -------- | --------------- | --------------------------------------------------- | ------ |
| not-initialized | grey     | `not initialized`           | hidden, centred message | enabled  | disabled        | editable                                            | exists |
| stopped         | grey     | `loops stopped`             | visible                 | enabled  | disabled        | editable                                            | exists |
| running         | green    | `loops running`             | visible                 | disabled | enabled         | model/ceilings/starter **locked**; prompts editable | exists |
| disconnected    | grey     | `last known: loops running` | visible, opacity .6     | —        | —               | —                                                   | exists |

**Source of truth for "running" (Q1, answered):** `.conveyor/roles/<role>/loop.lock/pid`, cross-checked for liveness — `state.loop_pid()` reads the pid file inside the lock dir and calls `util._pid_alive(pid)`. `state.loops_running()` is `any(...)` over `cfg.names()`. `not-initialized` is simply `os.path.isdir(.conveyor)` (`state.build_state → initialized`). No daemon, no extra file: the UI distinguishes all three states from disk alone.

`HeaderComponent.statusText` derives all four labels from `initialized` + `running` + `stale`; Start is disabled while running and Stop while stopped. Stop now is a dialog choice when a role is busy, not a header button. `stale` is a computed on `UiStateService` (`!live() && state() !== null`) — a failing poll keeps the last good board on screen at `opacity .6` under a `last known: …` label, and recovers on the next successful poll with no reload.

### 4.2 Inbox ticket

```
imported ──Grade──▶ grading ──▶ graded ──(ticket-reviewer proposes)──▶ awaiting-approval ──Approve / Edit then approve──▶ ready ──Start──▶ started
   │                            │                                        │
   └── Skip ───────────────────┴──────── Skip ─────────────────────────┴── Skip ──▶ skipped
awaiting-approval ──Reject (comments)──▶ improving ──▶ awaiting-approval
```

| Status            | Grade | Improve | Approve | Start | Skip | Gap    |
| ----------------- | ----- | ------- | ------- | ----- | ---- | ------ |
| imported          | ✓     | ✓       |         |       | ✓    | exists |
| grading           | ✓     | ✓       |         |       | ✓    | exists |
| graded            | ✓     | ✓       | ✓       |       | ✓    | exists |
| improving         | ✓     | ✓       | ✓       |       | ✓    | exists |
| awaiting-approval | ✓     | ✓       | ✓       |       | ✓    | exists |
| ready             |       |         |         | ✓     | ✓    | exists |
| started           |       |         |         |       |      | exists |
| skipped           |       |         |         |       |      | exists |

`grading` and `improving` are real statuses (`inbox.STATUSES`) that the brief omitted; they are the in-flight states while the ticket-reviewer holds the item.

**Files (Q6, answered).** One directory per item, id-stable, never renamed on status change:

```
.conveyor/inbox/<id>/meta.txt          source, title, url, external_id, status, grade, created_at, task_name
.conveyor/inbox/<id>/source.md         the original ticket
.conveyor/inbox/<id>/grade.md          written by the delivery sweep from the intake commit
.conveyor/inbox/<id>/proposed-task.md  ditto
.conveyor/inbox/<id>/comments.txt      operator reject comments, written before re-enqueue
.conveyor/inbox/seq                    counter behind manual-NNNN ids
```

Grade and proposal are **not** produced by the UI: the ticket-reviewer commits `grade.md` / `proposed-task.md`, and `queue._apply_intake()` lifts them out of that commit with `git show <commit>:<file>` and drops them in the item dir, setting status to `awaiting-approval` when a proposal exists and `graded` when only a grade does. `inbox.parse_grade()` reduces the grade file to `Ready` / `Gaps` / `Unusable` for the table column.

### 4.3 Task lane

```
[specifier ──approve(human)──▶] coder ──ready──▶ reviewer ──pass──▶ done
                                  ▲                 │
                                  └─── findings ────┘
any role ──(max-retries | max-minutes | max-attempts | merge-conflict | multiple-handoffs | no-rules | no-task-file)──▶ needs-human ──Resume──▶ the role that was to receive it
needs-human | done ──Delete──▶ (board row + park entry + audit fingerprints removed; task file stays)
```

| Lane        | Dir                                  | Card actions   | Gap     |
| ----------- | ------------------------------------ | -------------- | ------- |
| specifier   | `.conveyor/roles/specifier/inbox/`   | —              | exists  |
| coder       | `.conveyor/roles/coder/inbox/`       | —              | exists  |
| reviewer    | `.conveyor/roles/reviewer/inbox/`    | —              | exists  |
| needs-human | `.conveyor/needs-human/<task>/`      | Resume, Delete | exists  |
| done        | *(board lane only)*                  | Delete         | exists  |

The seven park reasons in the diagram are exact — verified against `bin/role-loop.sh:104-147` and `queue.py:95`. A parked task is `needs-human/<task>/{item.handoff,reason}`; `reason` is two lines, `<reason>\n<detail>`, and both are surfaced.

**Resume target (Q5, answered):** the handoff's own `to` header — the role that was about to receive it — not always coder. `cmd_resume` does `to = args[--to] if given else h["to"]`, restamps `attempt=1`, renames into that role's `inbox/new`, updates the board lane, and removes the `reason` file and the directory. `--to done` routes back through the parking role's outbox instead. The UI calls `/api/resume` without `to`, so it gets the default. Snack copy that says "moved to `queues/coder/new`" is wrong for a 3-pack; use the CLI's own line, `<task> resumed to <role>`.

**Delete semantics (Q9, answered):** `conveyor task <name> --delete` removes the board row, every `audit_pending/<task>.fp` fingerprint, and — when the task is parked — `.conveyor/needs-human/<task>/` in full. The row and the park entry die together, because `needs-human/` is enumerated from the filesystem rather than the board. It keeps `tasks/<name>.md` and anything already in `sent/`: protocol §8.1 treats `--delete` as a board-row operation, and the task file is history. It refuses outright when the lane is one of the coding roles. `conveyor resume` refuses, before renaming anything, if a park directory has no board row.

### 4.4 Pack

```
Review belt ◀──Switch (confirm)──▶ Spec then build        only when loops stopped (UI and CLI)
```

| Starter         | Chain                        | Human gate                                  | Library                           | Gap    |
| --------------- | ---------------------------- | ------------------------------------------- | --------------------------------- | ------ |
| Review belt     | coder → reviewer             | none                                        | specifier (file present, not run) | exists |
| Spec then build | specifier → coder → reviewer | specifier's first `ready` held for approval | empty                             | exists |

**Pack config (Q2, answered): there is no `pack.json`.** The pack *is* the ordered `role` lines in `conveyor.conf`. `packs.active_pack(cfg)` infers identity by matching `tuple(cfg.names())` against `STARTERS[*].roles`, returning `two`, `three`, or `custom`. Per-role `model`, `max_retries`, `max_minutes`, `max_attempts` are tokens on the role line — not front-matter in `roles/<role>.md`, which holds only the prompt. `config.save()` rewrites the role lines and preserves `[global]` / `[inbox]` verbatim. `holds_first_ready()` is `len(self.roles) == 3` — derived, never stored. Every `.conveyor/pack.json` reference in the briefs is fiction; delete it from the copy.

**Worktrees on Start (Q3, answered): creation yes, removal no — deliberately.** `cmd_start` calls `ensure_worktree()` for each configured role, which `git worktree add -B conveyor-<role>` if missing and always rewrites `.cursor/rules/conveyor-role.mdc`. Nothing removes the worktree or `.conveyor/roles/<role>/` of a dropped role: `git worktree remove` would take the `conveyor-<role>` branch, which is the only record of that role's work. `conveyor pack` now names the leftovers in a warning instead, and refuses to run at all while a loop is live.

---

## 5. Actions

Precondition → write → resulting UI → feedback.

**Snack copy is not verbatim from the prototype.** Every mutation goes `component → /api/* → bin/conveyor` and the snack shows the CLI's stdout (`{message}` in the JSON envelope), falling back to `'OK'`. Real strings: `<handoff-id> queued for <role>` (task create), `<task> resumed to <role>`, `stopped`, `<role>: loop started (pid N)` per role, `pack set to two (coder → reviewer). Restart loops: conveyor stop && conveyor start`, `imported <id> …` per line. Either restate the prototype copy in the CLI or accept the CLI's wording — the Snack column below is the target, not the current behaviour.

| Action                         | Where               | Precondition                         | Writes                                                    | Result                                     | Gap                                    |
| ------------------------------ | ------------------- | ------------------------------------ | --------------------------------------------------------- | ------------------------------------------ | -------------------------------------- |
| New task → Create              | header              | name matches `^[a-z0-9][a-z0-9.-]*$` | `tasks/<name>.md`, git commit, board row, operator handoff | card in first role's lane                  | exists (card not auto-selected)        |
| Import (manual)                | header, empty inbox | title + body                         | `.conveyor/inbox/<id>/`                                    | inbox row `imported`                       | exists                                 |
| Import (jira)                  | header              | ≥1 key/URL                           | same; fetch failure → row with empty body                  | same                                       | partial (no creds warning surfaced)    |
| Grade                          | inbox               | not started/skipped                  | enqueue ticket-reviewer                                    | `grading` → `graded`/`awaiting-approval`   | exists                                 |
| Improve                        | inbox               | same                                 | `conveyor intake <id> --improve`                           | proposal rewritten                         | exists                                 |
| Approve (inbox / strip Review) | inbox, strip        | graded/awaiting                      | opens Intake review                                        | —                                          | exists                                 |
| Intake: Approve                | dialog              | —                                    | `conveyor inbox approve <id>`; writes `tasks/<name>.md`    | status `ready`                             | exists                                 |
| Intake: Edit then approve      | dialog              | edited proposal                      | `proposed-task.md` rewritten, then approve                 | `ready`                                    | exists                                 |
| Intake: Reject                 | dialog              | comments                             | `comments.txt`, then `intake --improve`                    | `improving`                                | exists                                 |
| Intake: Skip                   | dialog              | —                                    | `conveyor inbox skip`                                      | `skipped`                                  | exists                                 |
| Start (inbox row)              | inbox               | ready                                | `conveyor start-task <name>`                               | row `started`; card in first lane          | exists (offers to start loops too)     |
| Skip (inbox row)               | inbox               | not started/skipped                  | mark skipped                                               | `skipped`                                  | exists                                 |
| Spec approval: Approve         | strip Review        | held handoff in approvals/pending    | `conveyor approve <id>` → next role's `inbox/new`          | card moves to Coder                        | exists                                 |
| Spec approval: Reject          | dialog              | comments                             | `conveyor reject <id>` ← comments on stdin                 | card stays with specifier, task_id kept    | exists                                 |
| Resume                         | strip, card         | lane needs-human                     | `conveyor resume <task>` → handoff's own `to`              | card in that role's lane                   | exists                                 |
| Delete                         | strip, card         | needs-human or done                  | confirm dialog, then board row + park entry + audit fps    | card removed from board                    | exists                                 |
| Start (loops)                  | header              | not-init or stopped                  | worktrees, hook, rules, loops                              | running                                    | exists                                 |
| Stop                           | header              | running; dialog if any role is busy  | `stop` sentinel per role, waits                            | stopped after current task                 | exists                                 |
| Stop now                       | Stop dialog (warn)  | a role is busy                       | confirm, then `kill -TERM`                                 | stopped; in_process left as-is             | exists                                 |
| Card select                    | board               | —                                    | —                                                          | Task tab loads `tasks/<name>.md`           | exists                                 |
| Role click                     | work queue          | —                                    | —                                                          | Log tab, that role's newest `.jsonl`       | exists                                 |
| Switch starter                 | pack                | loops stopped                        | confirm, then `conveyor pack two\|three` → `conveyor.conf` | belt/roster/board columns change           | exists                                 |
| Save role prompt               | pack rail           | three headings present               | `roles/<role>.md`                                          | snack `roles/<role>.md saved`              | exists                                 |
| Save project rules             | pack rail           | —                                    | `project.md`                                               | snack `project.md saved`                   | exists                                 |
| Edit model / ceilings          | pack roster         | loops stopped                        | role line in `conveyor.conf`                               | snack `<role> runtime saved`               | exists                                 |

---

## 6. Attention strip

Shown only when at least one group is non-empty. Groups in this order:

| Group           | Source                                | Row content                            | Actions        | Gap     |
| --------------- | ------------------------------------- | -------------------------------------- | -------------- | ------- |
| Needs human     | `.conveyor/needs-human/*/item.handoff` | task · reason (mono) · one-line detail | Resume, Delete | exists  |
| Intake approval | inbox rows with `awaiting-approval`   | title · grade                          | Review         | exists  |
| Spec approval   | `.conveyor/approvals/pending/*.handoff` | task · from → to · sha10             | Review         | exists  |

Spec approval is fully wired: `queue.pending_approvals()` → `state.approvals` → strip → `SpecApproveDialogComponent` → `/api/approve` or `/api/reject`. Upgrade the brief's "partial" to exists.

Chime: **deferred**, not implemented (Q8). No `Audio`, `chime` or `beep` anywhere in `ui/`.

---

## 7. Detail rail

| Tab    | Content                                                                                                     | Gap    |
| ------ | ------------------------------------------------------------------------------------------------------------- | ------ |
| Task   | meta line (task_id · lane · audits · retries) then `tasks/<name>.md` rendered as headings + numbered list    | exists |
| Log    | newest `<task>_<n>.jsonl`, mono, auto-scrolled to the tail, role switcher and queue peek in the meta line    | exists |
| Queues | `new` / `in_process` / `sent` groups; row = task · from → to · verdict · sha10                                | exists |

The rail takes the selected `ConveyorTask` (not just its name) for the meta line. Markdown is rendered by a local `renderTask()` over the heading + ordered-list subset these files use — no library, since the CDN is not available to this build. Auto-scroll runs in `ngAfterViewChecked`, keyed on role/file/event-count so it only fires when the log actually grows.

**Work queue row.** Role (button) · Task with its sub-line (`attempt n/m` while busy, `last: <task>` when idle) · State dot (green busy / amber idle / grey stopped) · Age (`12s` / `4m` / `1h 3m`) · New count.

---

## 8. Pack tab

| Element                  | Behaviour in code                                                                                                      | Gap     |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ------- |
| Banner                   | Info banner, flips green to "Saved. Applies the next time you Start." after a save and back on the next edit; amber lock banner while running | exists  |
| Starter strip            | Two cards, active outlined, inactive opens the Switch confirm; locked = `opacity .72` + disabled button while running     | exists  |
| Belt                     | operator/role/done nodes with avatars, verdict-labelled edges, a `diamond` hold marker at the approve hop, a findings line, and a ticket-reviewer sidecar node | exists  |
| Roster: In this workflow | Card per role: avatar · owns · hop chips · model · retries · minutes · attempts · Save runtime; inputs disabled while running | exists  |
| Roster: Library          | Dashed card, "Not in this workflow.", click opens the prompt; no add button                                              | exists  |
| Roster: Sidecar          | ticket-reviewer card with an `intake sidecar` badge, always present when `roles/ticket-reviewer.md` exists               | exists  |
| Editor rail              | Tabs `roles/<role>.md` / `project.md` · textarea · Save (disabled until dirty) · helper naming the three headings        | partial |

- Editor rail stays partial by choice: the read-only stack lists only `constitution_files()` — `constitution.md` plus `constitution/*.md`. The brief's stack also ends in `project.md → roles/<role>.md`, but those two are the editable tabs right beside it, so repeating them in a read-only list would be noise.
- Prompt validation is enforced server-side, not just as a hint: `state.write_role()` regex-checks for `Owns`, `Does not own`, `Handoff contract` headings and returns 400 with `role file must include heading 'Owns'`. It also refuses reserved names (`operator`, `done`) and any file that does not already exist.

**Role avatars — the brief's icon table does not match `packs.AVATARS`.** Shipping values:

| Role            | Icon         | Color     | Owns                                    |
| --------------- | ------------ | --------- | --------------------------------------- |
| specifier       | `edit_note`  | `#5c6bc0` | Localize the task to this repository    |
| coder           | `code`       | `#00897b` | Implement and prove the task            |
| reviewer        | `fact_check` | `#ef6c00` | Verify the coder's commit               |
| ticket-reviewer | `inbox`      | `#7b1fa2` | Grade and rewrite incoming tickets      |
| operator        | `person`     | `#546e7a` | You. Tasks, intake, approve.            |
| done            | `check_circle` | `#2e7d32` | Merged to main                        |

`needs-human` was added (`back_hand`, `#c62828`) so the parked board column carries an icon like every other lane; `/api/state` now ships an avatar per lane in `state.avatars`. The brief's `build` / `verified` / `flag` for coder / reviewer / done were wrong and the table above is the shipping truth — `packs.py` is what the UI reads.

Per-role config defaults written by `conveyor pack`: coder 3/120/3, reviewer 3/60/2, specifier 3/60/2. (The brief says specifier 3/45/2; the code says 60.)

---

## 9. Dialogs

| Dialog           | Spec width | Actual                                    | Actions                                     | Gap     |
| ---------------- | ---------- | ----------------------------------------- | ------------------------------------------- | ------- |
| New task         | 560        | 520                                       | Cancel · Create (disabled until valid)      | exists  |
| Import           | 560        | 560                                       | Cancel · Import and grade                   | exists  |
| Intake review    | 900        | 900                                       | Skip · Reject · Edit then approve · Approve | exists  |
| Spec approval    | 620        | 640                                       | Cancel · Reject · Approve                   | exists  |
| Stop confirm     | 440        | 440, `ConfirmDialogComponent`             | Cancel · Stop · Stop now (warn, only if a role is busy) | exists  |
| Delete confirm   | 440        | 440, `ConfirmDialogComponent`             | Cancel · Delete (warn)                      | exists  |
| Switch pack      | 460        | 460, `ConfirmDialogComponent`             | Cancel · Switch                             | exists  |

All four confirmations — Stop (when a role is busy), Delete, Switch pack, and the start-loops prompt in `startWorking()` — go through one `ConfirmDialogComponent` (`{title, body, code?, items?, confirmLabel, secondaryLabel?, warn?}`), which renders the command it is about to run in a mono block. No `window.confirm` remains in `ui/src/`.

---

## 10. Open questions — answered

1. **Loop state on disk.** `.conveyor/roles/<role>/loop.lock/pid` + `_pid_alive()`; `initialized` = `.conveyor/` exists. All three states are readable without a daemon. (§4.1)
2. **Pack config.** No pack file. Ordered `role` lines in `conveyor.conf`; identity inferred by name-tuple match. Model and ceilings are tokens on the role line, never front-matter. (§4.4)
3. **Worktrees.** Start creates missing ones and always rewrites the rules file. Dropped roles' worktrees are deliberately never pruned — `git worktree remove` would take the role's branch — so `conveyor pack` warns about them instead. (§4.4)
4. **Spec approval hold.** A directory: `.conveyor/approvals/pending/<id>.handoff`. The sweep diverts the first role's outbound `ready` there when `cfg.holds_first_ready()`; `approve_pending()` renames it into the next role's `inbox/new`, `reject_pending()` returns it to the first role preserving `task_id`. Not a flag on the file. (§6)
5. **Resume target.** The handoff's own `to`, overridable with `--to`. Not hardcoded to coder. (§4.3)
6. **Grade/proposal storage.** `.conveyor/inbox/<id>/{grade.md,proposed-task.md}`, lifted out of the intake commit by `queue._apply_intake()`. Reject comments go to `comments.txt` before `intake --improve` re-enqueues. (§4.2)
7. **Prompt validation.** UI-side and hard: `POST /api/roles` returns 400 without the three headings and leaves the file untouched. `conveyor start` still only checks that `roles/<name>.md` exists, so a prompt edited outside the UI bypasses the rule — left as is, since the constitution, not the validator, is what makes a role file correct.
8. **Chime.** Defer. Nothing implements it, and the derived-from-diff design needs a first-paint guard that does not exist yet. Ship without it.
9. **Delete.** Board row + audit fingerprints + the park directory. The task file and `sent/` handoffs survive, per protocol §8.1. Recorded as ambiguity 20 in `bin/README.md`.
10. **Theme.** Already decided in code: Angular Material `azure-blue` prebuilt theme + Roboto (`ui/angular.json`, `ui/src/styles.scss`). The warm stone / steel-blue prototype theme was not carried over. Keep azure-blue unless someone wants to port the prototype palette deliberately.

---

## 11. Gap summary

| Status   | Items                                                                                                                                                                                                 |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| deferred | Chime (Q8) — nothing implements it and its first-paint guard does not exist                                                                                                                            |
| partial  | Editor rail read-only stack lists the constitution files only, by choice (§8)                                                                                                                          |
| exists   | Everything else: correctness of delete/resume/pack; confirm dialogs on all four destructive actions; header state gating and the disconnected view; work-queue attempt sub-line; Task-tab meta and rendered markdown; log auto-scroll and queue peek; kanban lane avatars; roster hop chips and library cards; pack banner states; the whole Pack page; spec approval; inbox lifecycle |

## 12. Resolved

Every disagreement the audit found has been closed. For the record:

| # | Was | Now |
|---|---|---|
| 1 | Deleting a parked task left `needs-human/<task>/`; Resume then moved the handoff into a live queue and threw `KeyError` on the missing board row, crashing the role loop at dequeue | `--delete` removes the park directory with the row; `resume` refuses before renaming anything. Tests: `test_task_delete.py` |
| 2 | `tasks/<name>.md` never deleted, contradicting the brief's `rm` copy | Kept deliberately (protocol §8.1); the UI copy now says so |
| 3 | `spec` listed as a verdict | Removed; `config.VERDICTS` is `ready`, `pass`, `findings` |
| 4 | `.conveyor/pack.json` referenced throughout | Removed; the pack is the `role` order in `conveyor.conf` |
| 5 | Avatar icons disagreed with `packs.AVATARS` | Spec matched to code; `needs-human` added and served per lane |
| 6 | Specifier ceilings quoted as 3/45/2 | Corrected to 3/60/2 |
| 7 | `conveyor pack` unguarded at the CLI | Refuses while any loop lock is live; warns about orphaned worktrees. Test: `test_pack.py` |
| 8 | Three `window.confirm` calls and a Stop now with none | One `ConfirmDialogComponent` behind all four |
