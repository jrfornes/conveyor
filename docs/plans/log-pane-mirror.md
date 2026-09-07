# Log pane mirror — jsonl is the pane

**Goal:** close the F9 “read-only pane mirror per agent” UX gap without
tmux or interactive sessions (PRD B.2).
**Depends on:** current cockpit Log tab + `GET /api/logs/<role>` +
`conveyor log`.
**Exit:** `conveyor log -f` follows a role; the cockpit Log tab live-tails
the same pretty-print; a role can be popped out into its own dark window;
suite green; no tmux in `bin/` or `lib/`.

This is a **scoped slice of B.6**, not B.2 and not the rest of the
dashboard spec. Candidate for the next Unreleased / post-`0.4.0-rc1` tag.
Do not take it as license to build wake-ups, watchdogs, or pane inject.

---

## Locked decisions

| Decision | Choice | Consequence |
| --- | --- | --- |
| What is the pane? | Newest `.conveyor/logs/<role>/*.jsonl` | Same file `cursor-agent -p --output-format stream-json` already writes. No multiplexer, no second capture path. |
| Who pretty-prints? | One function in `lib/conveyor/` | `conveyor log`, `log -f`, and the UI all show the same text. |
| Live follow | Poll the file | CLI ~0.5 s, UI 2 s (same cadence as `/api/state`). No websockets. |
| Pop-out | Angular route `/agents/:role` outside the shell | F9’s “own window” without a second HTML stack. Python already falls back unknown paths to `index.html`. |
| Tmux | Out | B.2 stays deferred. If interactive sessions ever land, they implement the same `pane_text()` backend; the UI does not call tmux. |
| Task filter in the UI pane | Off | The pane is per-role newest file, matching `conveyor log <role>`. Optional `<task>` stays CLI-only. Today’s rail passing `selectedTask` into `/api/logs` is a footgun (empty view when the selected card is not that role’s current run). |

F9 in `docs/later/orchestration-dashboard-spec.md` assumed a tmux capture and
a no-framework single HTML page. The cockpit is already Angular. Implement
the **behavior** (dark, mono, follow, pop-out, read-only) against jsonl.
Do not add `GET /api/agents/<role>` as a second page, and do not add
`/api/agents/<role>/pane` until something besides the SPA needs raw text
(`conveyor log` is that something).

---

## Out of scope

- tmux, `session=interactive`, wake-up inject, pane watchdog (B.2)
- Master chat, chime, forge, token meters (rest of B.6 / Stages 5–6)
- Typing into an agent from the dashboard
- Websockets / SSE
- A `conveyor attach` that wraps `tail -f` in tmux
- Full JSON inspector, ANSI emulator, or log search
- Changing how the loop launches the agent (`bin/role-loop.sh` `run_agent`)

---

## Current gap (what the code does today)

- Loop writes `.conveyor/logs/<role>/<task>_<id>_a<attempt>.jsonl` and
  appends `{"type":"conveyor","exit":n}` when the process exits.
- `conveyor log <role> [<task>]` dumps the newest matching file once
  (`bin/conveyor` `cmd_log`). No follow.
- `GET /api/logs/<role>` returns `{filename, events}` (`ui/server/state.py`
  `read_logs`). Pretty-print is duplicated in the CLI and in
  `DetailRailComponent.formatLog()`.
- Log tab loads **once** on work-queue role click. `/api/state` polls every
  2 s; logs do not. Auto-scroll fires on event-count change only, so a
  sitting rail never moves.
- Light Material rail, `max-height: 360px`, no `window.open`, no
  `/agents/:role` route.
- `cmd_log` / `read_logs` reject any name not in `cfg.names()`, so
  `ticket-reviewer` (intake) cannot be watched even though it writes logs.

---

## Design

### Shared library — `lib/conveyor/logs.py`

Stdlib only. Callers: `bin/conveyor` `cmd_log`, `ui/server/state.py`.

```
newest(paths, role, task=None) -> (filename, path) | None
  # mtime sort of *.jsonl under paths.logs/<role>/, optional "<task>_" prefix

format_line(ev: dict | str) -> str | None
  # Current CLI rule: raw line if not JSON; else
  #   [kind] detail[:400]
  #   kind in (assistant, result, tool, tool_call, tool_result, conveyor) or detail
  #   else omit (same as today — do not start printing every stream-json noise line)

format_file(path) -> str
  # join format_line of each complete line, trailing newline

read(paths, cfg, role, task=None) -> {filename, events, text}
  # events keep the current JSON shape for the Angular type;
  # text is format_file() so the pane can bind one string

follow(paths, cfg, role, task=None, poll=0.5, out=sys.stdout, stop=None)
  # print "== filename" then existing text; then loop:
  #   hold a partial last line until "\n"
  #   print new complete lines as they appear
  #   if a newer matching file appears (new attempt), print "== <new>" and hop
  #   stop: threading.Event, or SIGINT → return (exit 0 from cmd_log)
```

Role check: `cfg.role(role)` (raises `ConfigError`), **not**
`role in cfg.names()`. That admits `ticket-reviewer` without putting intake
on the belt.

Keep the 400-char cap. This is a mirror of `conveyor log`, not a new
transcript format.

### CLI — `conveyor log [-f|--follow] <role> [<task>]`

Flag may appear anywhere among the args. Usage error if `-f` is the only
arg. `cmd_log` becomes a thin wrapper around `logs.read` / `logs.follow`.
Print with `flush=True`. Follow poll default 0.5 s; tests pass `poll=` and
a `stop` event so they do not sleep for wall time.

### API

`GET /api/logs/<role>?task=` stays. Response gains `text` (pretty-print).
`filename` / `events` unchanged so today’s UI does not break mid-PR.
Unknown role → 400; no file → `{filename: null, events: [], text: ""}`.

`state.read_logs` delegates to `logs.read`.

### UI

**`AgentPaneComponent`** (`ui/src/app/logs/agent-pane.component.ts`)

- Inputs: `role: string`.
- Polls `api.logs(role)` every 2 s while alive; `switchMap` so an in-flight
  request is dropped on the next tick. Unsubscribe on destroy.
- Replace the `<pre>` only when `text` (or `filename`) changed — same
  “don’t thrash the DOM” rule as F1.
- Dark pane local to this component (do not wait for Stage 6): background
  `#111`, ink `#e8e8e8`, Roboto Mono / `ui-monospace`, `white-space:
  pre-wrap`, full height of its host, overflow auto.
- Stick-to-bottom unless the operator has scrolled up more than ~32 px from
  the bottom. If they scroll back to the bottom, resume sticking. Do **not**
  use the current `ngAfterViewChecked` + event-count key.
- Read-only. No textarea, no inject.
- Empty: muted “no log yet” when `filename` is null.
- Header line: `role · filename` (filename is the jsonl basename).

**Rail:** Log tab hosts `<app-agent-pane [role]="logRole">` once a role is
chosen. Drop `loadLog` / `formatLog` / the 360 px cap so the pane fills the
tab. Keep queue peek in the meta line above the pane. Stop polling when the
Log tab is not selected (the component is still in the DOM under
`mat-tab-group` — either `*ngIf` the pane on `tabIndex === 1` or pass a
`active` input that skips the interval).

**Pop-out:** work-queue role cell gets a second control (icon button,
`aria-label="Open coder log in a window"`) that does

```
window.open(`/agents/${role}`, `conveyor-pane-${role}`,
            'width=720,height=900,resizable=yes,scrollbars=yes')
```

Same window name ⇒ a second click focuses the existing pop-out. Must run
from the click handler (popup blocker). Role *name* click still selects the
rail Log tab (today’s behaviour).

**Route** (sibling of the shell, not a child — no header, no live-dot
chrome):

```
{ path: 'agents/:role', component: AgentWindowComponent },
{ path: '', component: AppShellComponent, children: [ /* existing */ ] }
```

`AgentWindowComponent`: full viewport, `document.title = "<role> · conveyor"`,
hosts `AgentPaneComponent`, no start/stop/import. Unknown role: show the
API 400 message, don’t crash.

`AppShellComponent` view-toggle does not gain a fifth tab. Deep-linking
`/agents/coder` is a window, not a cockpit mode.

### Demo fixture

`ui/server/demo.py` writes one sample jsonl under
`.conveyor/logs/coder/` (a few `assistant` / `tool` / `conveyor` lines) so
`conveyor-ui --demo` has something to follow without starting loops.

---

## Tasks

1. Add `lib/conveyor/logs.py` with `newest`, `format_line`, `format_file`,
   `read`, `follow`. Move the pretty-print out of `cmd_log` and
   `state.read_logs` so those two cannot drift again.
2. `cmd_log`: parse `-f`/`--follow`; call `read` or `follow`; admit intake
   via `cfg.role()`. Update the module docstring usage line.
3. `state.read_logs` → `logs.read`; JSON body includes `text`.
4. `test/test_logs.py` (see Tests). Wire `test/test_ui_api.py` for `/api/logs`.
5. `AgentPaneComponent` + stick-to-bottom helper. Unit-test the helper
   (distance-from-bottom → shouldStick boolean) in `ui/src/app/logs/` or
   `util.spec.ts`.
6. Detail rail: host the pane, drop one-shot `loadLog`, don’t pass
   `selectedTask` into the log fetch.
7. Work-queue pop-out button; `app.routes.ts` `/agents/:role`;
   `AgentWindowComponent`.
8. Demo jsonl seed.
9. Docs: protocol §10 row, runbook “Watch an agent” row, `ui/README.md`
   deferred list (strike “tmux pane viewer” from the cockpit’s *own* gap;
   leave B.2 tmux in Appendix B), `CHANGELOG.md` Unreleased **Features**
   when the code lands (not in the plan PR).
10. `bin/README.md` **Ambiguities resolved**: jsonl-as-pane; `-f` hops to a
    newer file; Angular `/agents/:role` instead of spec F9’s
    `/api/agents/<role>` HTML; no tmux in this slice.

Implement in that order so the CLI/tests exist before the Angular pane, and
the pane exists before the pop-out.

---

## Tests

All new protocol/CLI tests are stdlib `unittest` under `test/`. Do not add
Playwright for this slice; browser-check the pop-out by hand against
`--demo` (see Verification).

`test/test_logs.py`

- Pretty-print: assistant/tool/conveyor lines formatted; empty-detail
  noise omitted; truncated at 400; invalid JSON passed through as raw.
- `newest`: picks the later mtime; `task=` prefix filters.
- `read`: unknown role raises; missing dir → empty filename/text.
- Intake: `ticket-reviewer` is accepted.
- Follow: start `follow(..., poll=0.05, stop=event)` in a thread; append a
  complete jsonl line; assert it appears; append a partial line, assert it
  does not; complete it, assert it does; write a newer `*_a2.jsonl`, assert
  a `==` hop; set `stop`.
- `cmd_log` via `Fixture.conveyor`: one-shot prints `==` + body; `-f`
  without a role is usage; `log -f coder` and `log coder -f` both follow.

`test/test_ui_api.py`

- `GET /api/logs/coder` after writing a jsonl → 200 with `text` matching
  `format_file`.
- Unknown role → 400.
- No logs dir → `filename` null, `text` `""`.

Angular: stick-to-bottom helper only (no HTTP). `npx tsc -p tsconfig.app.json
--noEmit` clean.

Do not add a protocol invariant. This is operator UX over existing files.

---

## Docs (when code lands)

| File | Change |
| --- | --- |
| `docs/conveyor-handoff-protocol.md` §10 | `conveyor log [-f] <role> [<task>]` — pretty-print; `-f` follows and hops files. Pure read. |
| `docs/runbook.md` §4 | Watch an agent: `conveyor log -f coder` (or the cockpit pop-out). Keep `tail -f` as the raw-file equivalent. |
| `ui/README.md` | Read list: live per-role log pane + pop-out. Deferred: drop “tmux pane viewer”; keep clarifications / master chat / forge / tokens. |
| `bin/README.md` | Ambiguities as in task 10. |
| `CHANGELOG.md` Unreleased Features | One bullet: live log pane + `log -f`. |
| `docs/later/orchestration-dashboard-spec.md` | Do **not** rewrite F9. At most a one-line note under F9 that Conveyor implements this against jsonl via `/agents/:role`. Spec stays the SwarmForge-shaped original. |
| `docs/conveyor-prd.md` B.2 / B.6 | Unchanged. This slice does not pull B.2 in. |

---

## Verification

```
cd test && python3 -m unittest discover -p 'test_*.py'
cd ui && npx tsc -p tsconfig.app.json --noEmit && npx ng build --configuration development
```

Browser (required for the UI half, `--demo`):

1. `bin/conveyor-ui --demo` → Board → click **coder** in the work queue →
   Log tab shows the seeded jsonl, dark, scrolled to the tail.
2. Append a line to that jsonl on disk → within ~2 s the pane grows and
   stays pinned to the bottom.
3. Scroll up → a further append does **not** yank the view down; scroll to
   bottom → pinning resumes.
4. Pop-out icon opens `/agents/coder` in a second window, no cockpit
   header, same text, independent follow. Second click focuses that window.
5. Pop-out and rail both update. Close the pop-out; rail still follows.
6. Inbox / Workflow / Roles unchanged. Log tab with no role selected still
   shows the empty hint.

CLI: `conveyor log -f coder` in the demo repo prints the seed, then a
hand-appended line, then hops when a newer `*_a2.jsonl` is created.
Ctrl-C exits 0.

---

## Ambiguities to record (when coding)

1. **jsonl is the pane.** F9’s multiplexer snapshot is not built. A later
   B.2 tmux backend would implement `pane_text` / `logs.read` with the same
   return shape; the Angular pane would not change.
2. **Follow hops to a newer matching file.** A new attempt is a new jsonl
   (`…_a2.jsonl`). Staying pinned to a finished `a1` would look dead.
   `task=` still restricts the match set.
3. **Partial last line is held.** stream-json is one JSON object per line;
   the agent may flush mid-line. Never pretty-print an incomplete line.
4. **F9 URL shape.** Spec wanted `GET /api/agents/<role>` as HTML. The
   cockpit is Angular, and `_static` already SPA-fallbacks, so the page is
   `/agents/:role`. Do not grow a second HTML renderer in `httpd.py`.
5. **Intake is a valid log role.** `cfg.role("ticket-reviewer")` already
   exists. Work queue does not list it; `conveyor log -f ticket-reviewer`
   and `/agents/ticket-reviewer` do.

If the protocol and this plan disagree, the protocol wins on file layout
and error text; this plan wins on “there is no tmux in this slice.”
