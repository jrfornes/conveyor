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

Creates a throwaway checkout (queued task, parked task, inbox item), serves the API, and deletes the fixture on exit. If the Angular app is built (`cd ui && npm run build`), open http://127.0.0.1:8765. Otherwise start the dev server in another terminal (`cd ui && npm start`) and open http://localhost:4200.

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

Build the Angular app, then serve API + static files from one process:

```bash
cd ui && npm run build
PYTHONPATH=. python3 -m ui.server --root /path/to/your/repo --port 8765
```

Open http://127.0.0.1:8765

## What the UI does

- **Read:** inbox, kanban board (`board.tsv`), spec approvals, per-role work queue, needs-human strip, task markdown, agent logs, handoff queue peek, workflow + roles (starters, routes, role prompts, `project.md`)
- **Write:** import (manual/Jira), grade/improve/approve/skip inbox items, start-task, spec approve/reject, new task, delete, resume, start/stop loops, workflow starter switch, role runtime, role prompts, `project.md`

The **Workflow** and **Roles** pages edit contract files. Named starters are **Review belt** (`coder → reviewer`) and **Spec then build** (`specifier → coder → reviewer`). Saved prompts and `project.md` apply on next Start — they do not hot-patch a running loop’s `.mdc`. Workflow switch and model/ceiling edits return 409 while loops are running.

State is read from `.conveyor/` via `lib/conveyor`. Mutations shell out to `bin/conveyor` so protocol rules stay in one place (file writes for role prompts and `project.md` are atomic).

## Deferred (PRD Appendix B)

Clarifications, master chat, tmux pane viewer, multi-project forge, token metering — see `docs/later/orchestration-dashboard-spec.md`.
