# Conveyor UI

Localhost Angular + Material cockpit for supervising and operating a Conveyor pipeline.

## Prerequisites

- Node.js 18+ and npm
- Python 3.10+ (stdlib only for the API server)
- A git checkout with `conveyor.conf` (your target repo)

## Demo (no target repo)

From the Conveyor repo root:

```bash
bin/conveyor-ui --demo
```

Creates a throwaway checkout (queued task, parked task, inbox item), serves the API, and deletes the fixture on exit. On first run, `bin/conveyor-ui` builds the Angular app automatically (`npm install && npm run build`, needs Node.js 18+ on `PATH`) — open http://127.0.0.1:8765 once it finishes. If `npm` isn't available, it prints instructions and falls back to serving the API only; start the dev server in another terminal (`cd ui && npm start`) and open http://localhost:4200 instead.

`--demo` and `--root` cannot be combined.

## Development (two terminals)

**Terminal 1 — API server** (from the Conveyor repo root, pointing at your target repo):

```bash
PYTHONPATH=. python3 -m ui.server --root /path/to/your/repo --port 8765
```

**Terminal 2 — Angular dev server** (proxies `/api` to the Python server):

```bash
cd ui && npm install && npm start
```

Open http://localhost:4200

## Production (single server)

```bash
bin/conveyor-ui --root /path/to/your/repo --port 8765
```

Builds the Angular app on first run if it isn't built yet, then serves API + static files from one process. Open http://127.0.0.1:8765. To build manually instead: `cd ui && npm install && npm run build`.

## What the UI does

- **Read:** inbox, kanban board (`board.tsv`), spec approvals, per-role work queue, needs-human strip, task markdown, agent logs, handoff queue peek, workflow + roles (starters, routes, role prompts, `project.md`)
- **Write:** import (manual/Jira), grade/improve/approve/skip inbox items (Review opens a two-pane dialog with Approve and start), start-task, spec approve/reject, new task, delete, resume, start/stop loops, workflow starter switch, role runtime, role prompts, `project.md`

The **Workflow** and **Roles** pages edit contract files. Named starters are **Review belt** (`coder → reviewer`) and **Spec then build** (`specifier → coder → reviewer`). Saved prompts and `project.md` apply on next Start — they do not hot-patch a running loop’s `.mdc`. Workflow switch and model/ceiling edits return 409 while loops are running.

## Errors

No failure disappears on a timer. Three surfaces carry them:

- A failed **action** raises a red strip under the toolbar. It stays until you dismiss it with the ✕ or start the next action — the 2s state poll cannot clear it. It is also mirrored into a snackbar near where you clicked, which does fade after 12s so it stops covering the page; the strip behind it does not. A repeat of the same failure counts up (`×3`) instead of re-announcing itself.
- A failed **poll** raises a separate amber strip and clears itself the moment the poll recovers — the same news the live dot and `last known:` already carry. It can never clear an action error; that split is the whole point.
- The **history** behind the toolbar's history badge keeps the last 20 failures with timestamps, including the ones pages show inline next to their own fields, so a message you missed is still recoverable. **Clear** empties it.

State is read from `.conveyor/` via `lib/conveyor`. Mutations shell out to `bin/conveyor` so protocol rules stay in one place (file writes for role prompts and `project.md` are atomic).

## Deferred (PRD Appendix B)

Clarifications, master chat, tmux pane viewer, multi-project forge, token metering — see `docs/later/orchestration-dashboard-spec.md`.
