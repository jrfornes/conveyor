# Stage 1 — Vocabulary, file renames, and the Workflow/Roles split

**Goal:** "pack" leaves the UI and the module names; the one Pack tab becomes two tabs
with a clean division of responsibility.
**Depends on:** Stage 0, Stage 2.
**Exit:** four-way header toggle; `ui/src/app/pack/` gone; suite green.

## The division (spec §14)

| View | Owns | Shows |
| --- | --- | --- |
| **Workflow** | how work flows | banner · starter cards · belt diagram · compact "Roles on this belt" summary linking to Roles |
| **Roles** | what each job is | banner · one card per file in `roles/` with on/off-belt tags, editable model + ceilings · editor rail (Role prompt / Project rules + prompt stack) |

Clicking a belt node in Workflow navigates to Roles with that role selected.

## File renames

| From | To |
| --- | --- |
| `ui/src/app/pack/pack-page.component.ts` | split → `workflow/workflow-page.component.ts` + `roles/roles-page.component.ts` |
| `ui/src/app/pack/belt-diagram.component.ts` | `ui/src/app/workflow/belt-diagram.component.ts` |
| `ui/src/app/pack/role-cards.component.ts` | `ui/src/app/roles/role-cards.component.ts` |
| `ui/src/app/pack/editor-pane.component.ts` | `ui/src/app/roles/editor-pane.component.ts` |
| `lib/conveyor/packs.py` | `lib/conveyor/workflows.py` |
| `test/test_packs.py` | `test/test_workflows.py` |
| `test/test_pack.py` | `test/test_pipeline.py` |

## Identifier renames

| From | To |
| --- | --- |
| `PackPageComponent` | `WorkflowPageComponent` / `RolesPageComponent` |
| `PackState` | `WorkflowState` |
| `PackRole` | `RoleRecord` |
| `PackStarter` | `WorkflowStarter` |
| `PackRef` | `WorkflowRef` |
| `PackRoute` | `Hop` |
| `api.pack()` / `api.setPack()` | `api.workflow()` / `api.setWorkflow()` |
| `GET/POST /api/pack` | `GET/POST /api/workflow` |
| `packs.describe/avatar/starters/library_roles` | same names, `workflows` module |

## Deliberately NOT renamed

- **`conveyor pack two|three`.** Stage 3 replaces the verb with workflow CRUD; renaming
  it now means touching the runbook, `cli.py` and tests for something about to be deleted.
  It is a CLI surface, not UI copy, so it does not violate spec §2.
- **`packs/three-pack.conf.example`.** Stage 3 reseeds these as
  `.conveyor/workflows/<slug>.json`.
- **`state.holds_first_ready`.** Deprecated alias from Stage 2; drops in Stage 3.

## Tasks

1. `git mv` the four UI files into `workflow/` and `roles/`; delete the empty `pack/`.
2. Split `pack-page.component.ts`: shape parts → `WorkflowPageComponent`, job parts
   (`role-cards` + `editor-pane` + `saveRole` / `saveProject` / `saveRuntime`) →
   `RolesPageComponent`. Both keep the banner and the running-lock note, with the copy
   from the README (Workflow: "Stop the loops to switch workflow or change models and
   ceilings…"; Roles: "Loops running: models and ceilings are read-only. Prompts save now
   and apply on next Start.").
3. Routes: `/pack` → `/workflow` and `/roles`. Belt node click → `/roles?role=<name>`.
4. Header: four-value toggle **Inbox · Board · Workflow · Roles**.
5. `git mv lib/conveyor/packs.py lib/conveyor/workflows.py`; update importers
   (`ui/server/state.py`, tests).
6. Rename the models.ts interfaces and the API service methods; rename `/api/pack`.
7. Rename the two test files; update `test_ui_api.py` for the new route.

## Verification

- `grep -rn 'pack\|Pack' ui/src/app` returns nothing.
- `grep -rn 'packs' lib/ ui/server/` returns nothing.
- `ls ui/src/app/pack` fails.
- `cd ui && npx tsc -p tsconfig.app.json --noEmit` clean.
- Suite green (120 tests).
