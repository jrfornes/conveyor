# Orchestration Dashboard — Feature Specification

**Do not implement.** Superseded by `design_handoff_conveyor/` (PRD B.6).

Purpose: a local, single-page web dashboard for supervising a pipeline of AI coding agents. Modeled on the SwarmForge dashboard (`swarmforge/scripts/pack_web.bb` + `pack/dashboard.html`, read September 2026), rewritten here as a stack-independent spec so it can be implemented on another project.

This document is the source of truth for scope. Anything not listed under a feature is out of scope unless the "Open questions" section says otherwise.

---

## 1. Design constraints

These are requirements, not suggestions.

1. **The filesystem is the system of record.** The dashboard reads and writes plain files (TSV board, one-file-per-message queues, text chat entries). It holds no state of its own beyond in-memory UI state (open menus, unsent drafts). Restarting the server loses nothing.
2. **Read-only view first, controls second.** Every screen must be buildable from files alone. Controls are thin wrappers that create or move files, then let the next poll reflect the change.
3. **Single HTML page, no build step.** One HTML file with inline CSS and JS, served by the local server. No framework, no bundler, no external CDN dependencies.
4. **Local only.** Binds to localhost. No authentication, no remote access, no multi-user.
5. **Polling, not push.** The page polls `GET /api/state` on a fixed interval (default 2 s) and re-renders. Do not add websockets.
6. **Agents never talk to the dashboard directly.** Agents write files via helper scripts; the dashboard observes those files. The only agent-facing effects the dashboard has are (a) moving an approved handoff into an outbox and (b) writing text into an agent's terminal pane.

---

## 2. Domain model

The dashboard renders these entities. Field names are indicative; keep them stable once chosen because agents' helper scripts read the same files.

### 2.1 Role
- `name` — unique, no underscores (used in filenames).
- `order` — position in the pipeline (from the pipeline config).
- `receive_mode` — `task` or `batch`.
- `is_master` — exactly one role is the master (the one the human talks to; typically the specifier).
- `session_alive`, `busy` — derived from the terminal multiplexer (is the pane present, is the agent producing output).

### 2.2 Task (board card)
Stored as one row in a TSV: `name  lane  created_at  updated_at  task_id  audit_count`.
- `name` — short, stable, human-readable.
- `lane` — a role name or `done`.
- `task_id` — timestamped unique ID; survives lane moves, approve, reject, retry. A deleted-and-recreated task gets a new ID with `audit_count` reset to 0.
- `audit_count` — cumulative number of times the handoff audit gate challenged this task. Incremented atomically by the handoff script, never by the dashboard.
- `status` — optional free text line for display.
- Task intent lives in a committed file `tasks/<name>.md`, not in the TSV.

### 2.3 Handoff (queue item)
A text file with a header block, blank line, body. Queue state is the directory it sits in: `outbox/`, `sent/`, `failed/`, `inbox/new/`, `inbox/in_process/`, `inbox/completed/`, plus a batch directory under `in_process/` for batch-mode roles. Headers the dashboard reads: `id`, `from`, `to`, `recipient`, `priority`, `type`, `task`, `task_id`, `commit`, `artifacts`, `created_at`, `enqueued_at`, `dequeued_at`, `completed_at`, `non-forwarding`.

### 2.4 Approval
A handoff from the master role that is held in a pending directory instead of the outbox until a human approves it. Has `id`, `task`, `task_id`, `commit`, `artifacts` (list of file paths in the commit), and a per-document review map `path → comment text`.

### 2.5 Clarification
A question from an agent to the human. File in `chat/pending/` with `id`, `role`, `task`, `body`; moves to `chat/done/` once answered. `status` is `pending` or `answered`.

### 2.6 Chat turn
A human→master or master→human message with `id`, `direction`, `text`, optional `status_lines`, `created_at`.

### 2.7 Project (forge mode only)
A directory under `projects/<name>/` containing its own pipeline config, board, queues, and `mission.md`. Has `name`, `pack` (which pipeline template), `open` (are its agents running), `lanes`, `tasks`.

---

## 3. Server API

All responses are JSON unless noted. All POST bodies are JSON. Errors return a non-2xx status with `{ "error": "<message>" }`.

### 3.1 Read

| Method | Path | Returns |
|---|---|---|
| GET | `/` | The dashboard HTML page. |
| GET | `/api/state` | Everything the page needs in one call: `mode` (`pack`\|`forge`), `title`, `master_role`, `lanes[]`, `tasks[]`, `work[]` (one entry per role: `role`, `state` (`live`\|`idle`\|`none`), `task`, `tasks[]`, `batch_tasks[]`, `age_seconds`, `progress`), `approvals[]`, `clarifications[]`, `chat[]`, and in forge mode `projects[]` each with its own `lanes`, `tasks`, `open`. In forge mode, accepts `?project=<name>` to scope pane/doc lookups. |
| GET | `/api/agents/<role>` | HTML page: a dark, monospace, read-only viewer of that role's terminal pane. Self-refreshes. |
| GET | `/api/agents/<role>/pane` | `text/plain` snapshot of the pane content (last N lines captured from the multiplexer). |
| GET | `/api/doc?path=<p>&id=<approval-id>` | `{ text, has_diff, diff_lines[] (each {type: add\|del\|same, text}), history[] (each {at, text}) }`. Text of the artifact at the approval's commit; diff against the previous commit of the same file when one exists; history of prior review comments on that path for the task. |
| GET | `/api/mission` | `{ text }` from `mission.md`. |
| GET | `/task/<name>` | Plain rendering of `tasks/<name>.md`. |

### 3.2 Write

| Method | Path | Body | Effect |
|---|---|---|---|
| POST | `/api/tasks` | `{ name, text, project? }` | Validate name (non-empty, no whitespace or path separators, unique on the board). Append a row in the master lane with a new `task_id`. Write `tasks/<name>.md` with `text`. Inject `name` + `text` into the master agent's pane. |
| POST | `/api/tasks/delete` | `{ task_id, project? }` | Remove the board row, any pending approval for it, its review comments, and its audit-pending records. |
| POST | `/api/tasks/retry` | `{ task_id, comments, project? }` | Write a reject-notify file for the task, persist `comments` into the review history, and inject a retry instruction into the responsible agent's pane. Preserve `task_id` and `audit_count`. |
| POST | `/api/approvals/<id>/approve` | — | Refuse (409) if any document in the approval has non-empty review comments. Otherwise stamp `approved_at`, move the file from pending into the outbox atomically (write to `outbox/tmp/`, rename into `outbox/`), and drop the approval's review records. |
| POST | `/api/approvals/<id>/reject` | `{ comments }` | Same as retry, scoped to this approval; removes it from pending. |
| POST | `/api/approvals/<id>/comments` | `{ path, comments }` | Save or clear a per-document review comment. Also append to the task's cumulative review history. |
| POST | `/api/clarifications/<id>/answer` | `{ text }` | Move the question from `chat/pending/` to `chat/done/`, store the answer, and inject `[<id>] <text>` into the asking agent's pane. |
| POST | `/api/chat` | `{ text, project? }` | Append a human chat turn and inject the text into the master agent's pane. |
| POST | `/api/mission` | `{ text }` | Overwrite `mission.md`. |
| POST | `/api/projects` | `{ name, pack, mission, config, github? }` | Forge only. Create `projects/<name>/`, install the chosen pipeline template, write `mission.md` and the config, optionally init/clone a git repo, and start its agents. |
| POST | `/api/projects/open` | `{ name }` | Forge only. Start the project's agents. |
| POST | `/api/projects/close` | `{ name }` | Forge only. Stop the project's agents; keep files. |
| POST | `/api/teardown` | — | Stop all agents, the delivery daemon, and the multiplexer session for the current pack (or all projects in forge mode). |

Rules for every write:
- Every file move is an atomic rename.
- Every write is idempotent where possible (re-approving an already approved id is a no-op with 200).
- The dashboard never edits handoff bodies; it only adds headers.

---

## 4. Page layout

Fixed viewport "cockpit". No page scroll; regions scroll internally.

```
┌──────────────────────────────────────────────────────────────┐
│ Header: title · ●live · [Teardown]      [New Project][Open ▾][New Task] │
├──────────────────────────────────────────────────────────────┤
│ Attention strip (amber; hidden when empty)                    │
├────────────────────────────────┬─┬───────────────────────────┤
│ Board (kanban, one column per  │ │ Rail                      │
│ lane in pipeline order + Done) │s│  Work Queue table         │
│                                │p│  ─── drag splitter ───    │
│  forge mode: one collapsible   │l│  Master chat              │
│  band per project              │i│   history                 │
│                                │t│   composer                │
└────────────────────────────────┴─┴───────────────────────────┘
```

- Vertical splitter between board and rail, horizontal splitter inside the rail. Both draggable with pointer events; persist positions in memory only.
- A single error line under the header shows the last failed request's message; cleared on the next successful poll.

---

## 5. Features

Each feature lists behavior, then acceptance checks an implementing agent can verify.

### F1. Live state polling
- Poll `/api/state` every 2 s. Re-render only what changed (compare text before setting it) so open menus and text fields are not disturbed.
- The `● live` dot in the header goes grey if a poll fails, green when it succeeds.
- Accept: with the server stopped, the dot turns grey and the error line shows a message; restarting the server recovers without a page reload.

### F2. Kanban board
- Columns: each lane from `lanes[]` in order, then `done`. Column heading is the display name (capitalized, e.g. `QA` stays `QA`).
- A card shows: task name, an audit badge `✓ N` (tooltip "Audit count: N"), and an optional status line.
- Cards are not draggable. Lane changes come only from the files.
- Forge mode: a collapsible band per project with the project name as a toggle button, plus per-project `New Task` and `Close` buttons in the band header. Each band renders its own columns.
- Accept: editing the TSV lane by hand moves the card within one poll; audit badge reflects the TSV column.

### F3. Attention strip
- Visible only when there is at least one pending approval or pending clarification.
- Two row groups: approvals, then clarifications.
- **Chime**: when a new approval or pending clarification id appears that was not present in the previous poll, play a short synthesized tone (Web Audio, no audio files). Do not chime on first load.
- Accept: dropping a file into the pending approvals directory triggers a chime and a row within one poll; reloading the page does not chime.

### F4. Approval row
- Contents: `Approval` pill, `project/task` label (project omitted in pack mode), **Documents** dropdown (only if `artifacts` is non-empty), **Approve** and **Reject** buttons.
- **Documents** dropdown lists each artifact by file name with a mark: green ✓ if no comment saved for that path, red ✗ if a comment exists. Clicking opens the document window (F5).
- **Approve** is disabled while any document has a saved comment.
- **Approve** posts approve; row disappears on next poll.
- **Reject** opens the reject dialog (F7).
- Accept: save a comment on one document → Approve disables and ✗ appears; clear the comment → both revert.

### F5. Document review window
- Opens in a separate browser window (`window.open`) so multiple can be open at once; the same path+id reuses its window.
- Header: file name, and a "Diff" toggle shown only when `has_diff` is true.
- Body: the document text in a `pre`; when Diff is on, render `diff_lines` with add/del/same coloring.
- Below a draggable horizontal split: the comment **history** (each entry: timestamp separator + text), or "No previous comments".
- Bottom: **New comment** textarea, **Cancel**, **Save**. Save posts to `/api/approvals/<id>/comments` with the path and text (empty text clears the comment). Window closes on save.
- Accept: a comment saved here appears in the history the next time the same path is opened for the same task, including after a retry cycle.

### F6. Clarification row and window
- Row: `Question` pill, role name, `project/task`, first line of the question, an **Answer** button.
- Window: the full request text on top (read-only, pre-wrap), a draggable split, a **Response** textarea, **OK**. Drafts are kept per clarification id in memory so closing and reopening the window restores unsent text.
- OK posts the answer; the row disappears on next poll.
- Accept: an answered clarification writes `[<id>] <text>` into the agent's pane capture (visible in F9).

### F7. Reject / retry dialog
- Floating modal titled "Rejected task" with a **Comments** textarea ("Audit comments for retry…") and three buttons:
  - **Delete** — posts `/api/tasks/delete`; removes the card.
  - **Retry** — posts reject/retry with the comments; card stays in its lane, `task_id` and `audit_count` preserved; the responsible agent receives the comments as findings.
  - **Accept Unchanged** — posts approve (only enabled if no document comments exist); used to approve after opening the dialog by mistake.
- Escape or Cancel closes without action.
- Accept: after Retry, the board row's `task_id` is unchanged and `audit_count` is not reset.

### F8. Work Queue table
- One row per role in pipeline order. Columns: Task, Role, State, Age.
- **Task**: the current in-process item name. If the role is processing a batch with more than one item, show the first name and a `+` marker that reveals the full list on hover.
- **Role**: rendered as a button; click opens the agent pane window (F9).
- **State**: green dot = session alive and busy; yellow dot = alive and idle; no dot = no session. Tooltip carries the word.
- **Age**: human-friendly age of the in-process item's `dequeued_at` (`12s`, `4m`, `1h 3m`).
- A small progress bar per row if `progress` is provided (fraction of batch items completed); otherwise omitted.
- Accept: with a batch of three in `in_process/`, the row shows the first name, `+`, and all three names on hover.

### F9. Agent pane viewer
- Opens `/api/agents/<role>` in a resizable pop-up window. Dark background, monospace, pre-wrap, auto-scrolls to bottom unless the user has scrolled up.
- The page itself fetches `/api/agents/<role>/pane` every 2 s and replaces the text only if it changed.
- Read-only. No input to the agent from this window.
- Accept: text typed into the agent's real terminal appears here within one refresh.

### F10. Master chat panel
- Header: the master role's name and an **Open** button that opens its pane viewer (F9).
- History: chat turns rendered as bubbles with direction styling; assistant turns may carry a collapsible status block (`status_lines`). Auto-scroll to bottom only if the view was already at the bottom.
- Composer: textarea, Enter sends, Shift+Enter inserts newline, empty text is ignored. Posts `/api/chat`; the textarea clears on success.
- Accept: a sent message appears in history within one poll and in the master pane capture.

### F11. New Task dialog
- Fields: **Name** (`task-name` placeholder), **Task** textarea ("What the master agent should do…"), Cancel, OK.
- Helper note in the dialog: "Creates a card in the master lane and sends name + text to the master agent."
- Validation on the client mirrors the server: reject empty, whitespace, path separators, duplicates; show the server error inline.
- Forge mode: the band's New Task button pre-selects that project.
- Accept: after OK, a card appears in the master lane, `tasks/<name>.md` exists with the text, and the master pane shows the injected task.

### F12. New Project dialog (forge mode)
- Fields: **Name** (`my-app or owner/repo`), an inferred-name line under it (e.g. strips the owner prefix), a **github repo** checkbox, **Mission** textarea, **Pack** radio group (one radio per available pipeline template, fetched from the server), **Config** textarea pre-filled with the selected template's config and editable; changing the radio replaces the config unless the user has edited it (then prompt).
- OK posts `/api/projects`; the new project band appears and its agents start.
- Accept: the created project directory contains the config exactly as shown in the textarea.

### F13. Open / Close Project (forge mode)
- **Open Project** dropdown lists projects that exist but are not open. Selecting one starts it.
- Each project band has a **Close** that stops its agents but keeps files; the band collapses to a header showing "closed".
- Accept: close then open round-trips without losing board state.

### F14. Teardown
- Red button in the header. Confirm dialog ("Stop all agents and the session?"). Posts `/api/teardown`. The header dot goes grey and Work Queue states go to "no session".
- Accept: after teardown, no multiplexer session or daemon process remains.

### F15. Task document view
- Card name is a link to `/task/<name>`, which renders `tasks/<name>.md` as plain text in a new window.

### F16. Mission (forge mode)
- Project band header has a **Mission** link that opens a small window with the mission text and a Save button (`/api/mission`).

---

## 6. Non-functional requirements

- **Performance**: a full poll + render with 6 roles, 50 cards, and 10 attention items must complete in under 50 ms of main-thread time. Never rebuild DOM subtrees whose data is unchanged.
- **Resilience**: any malformed file (bad TSV row, handoff with missing header) is skipped and reported once in the server log; it never breaks the page.
- **Concurrency**: the server may be hit by the page and by helper scripts simultaneously. All file writes use write-temp-then-rename. TSV updates take a file lock.
- **Accessibility**: buttons are real `<button>`s, dialogs have `role="dialog"` and a labelled title, icons carry `aria-label`, everything reachable by keyboard, Escape closes dialogs and menus.
- **Styling**: one CSS custom-property palette at `:root` (background, panel, ink, muted, line, accent, amber, green, red). No dark mode required. Fonts: system UI for chrome, system monospace for panes and documents.
- **Testing**: the server exposes every write as a CLI test hook (`--test-new-task`, `--test-approve <id>`, etc.) that runs the same handler without HTTP, so the whole flow can be exercised from a shell. Provide a browser test (Playwright or equivalent) covering F3, F4, F7, F10, F11 against a fixture directory.

---

## 7. Explicit non-goals

Do not build these without a decision from the owner:

- Drag-and-drop of cards between lanes.
- Editing role prompts, constitution, or pipeline config from the UI after launch.
- Per-commit or per-role approval (the only approval gate is the master's handoff).
- Token, cost, or wall-clock budgets and their display. (Wanted eventually; separate spec.)
- Sending arbitrary input to non-master agents. The only channels are New Task, chat to master, clarification answers, and retry comments.
- Authentication, HTTPS, or remote access.
- Persisting UI preferences (splitter positions, collapsed bands).
- Any database, message broker, or background worker beyond the existing delivery daemon.

---

## 8. Open questions for the owner

1. Should the audit counter have a ceiling that automatically parks a card in a "needs human" lane? (SwarmForge does not; the north-star document recommends it.)
2. Should the Work Queue show a token or elapsed-time meter per role once budgets exist?
3. Forge mode on day one, or pack mode only?
4. Terminal multiplexer: tmux only, or abstract behind an adapter?

---

## 9. Reference mapping to SwarmForge

For an agent wanting to compare against the original: header and dialogs → `dashboard.html` lines ~130–245; state assembly → `pack_web.bb` `handle-request` GET `/api/state`; approvals → `approve!`, `save-review!`, `write-reject-notify!`; clarifications → `answer-clarification!` and `chat_wake`; pane capture → `pane-content` / `/api/agents/<role>/pane`; board persistence → `pack_board.bb` (`create`, `move`, `done`, `increment-audit`). The repository has no licence file; use it for behavior reference only and do not copy code.
