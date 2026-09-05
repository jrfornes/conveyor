# Implementation plans — design_handoff_conveyor

Staging for the UI/product changes described in [`design_handoff_conveyor/`](../../design_handoff_conveyor/).

One plan per stage, written when the stage starts. Stage 2 reshapes Stage 3, so
plans 3–6 are deliberately not written up front.

## Locked decisions

| Decision | Choice | Consequence |
| --- | --- | --- |
| Workflow storage | `conveyor.conf` stays the single source of truth for the **active** pipeline | `.conveyor/workflows/<slug>.json` are saved presets; `.conveyor/active` names the applied one; "Make active" regenerates `conveyor.conf` via `config.save()`. The validator and role loops are untouched. |
| Build order | Stage 0 → Stage 2 first | Riskiest work (config layer) lands while the invariant tests are fresh; everything after is additive. |
| Theme | Material Azure Blue + Roboto | Drop the prototype's warm-stone tokens. Keep the **semantic** colour roles: amber = attention/idle, green = live/busy, steel = audit, rust = retry/park. Use a real mono (Roboto Mono) for ids, SHAs, paths, counts. |

## Stages

| Stage | Scope | Depends on | Status |
| --- | --- | --- | --- |
| [0 · Reconcile](../archive/stage-0-reconcile.md) | Correct the handoff spec to real paths; strike already-built work; record decisions | — | **done** |
| [2 · N-role pipelines](../archive/stage-2-n-role-pipelines.md) | Lift the 2-or-3 role limit; make the gate explicit config, not `len()` | 0 | **done** — 120 tests |
| [1 · Vocabulary + view split](../archive/stage-1-vocabulary-and-view-split.md) | Pack→Workflow copy, 4th toggle, split `ui/src/app/pack/` into `workflow/` + `roles/`, file + identifier renames | 0, 2 | **done** |
| [3 · Workflow CRUD](../archive/stage-3-workflow-crud.md) | Presets, `.conveyor/active`, `gate none`, `conveyor workflow`, worktree pruning, list/detail/edit dialog | 1, 2 | **done** — 206 tests |
| [4 · Intake module](stage-4-intake-module.md) | `roles/ticket-reviewer.md` → `intake/`, rubric, `jira.json`, settings rail | 1 | **done** |
| 5 · Board fidelity | `held` badge, held group in Queues, chime, disconnected polish | 1 | not planned |
| 6 · Theme pass | Azure Blue + Roboto across all views, semantic roles preserved | 1–5 | not planned |

## Scans

| Doc | Use |
| --- | --- |
| [Moat and gap scan](moat-gap-scan.md) | Walk this repo (and the NX target) for enforced vs prompt-only vs overclaim. Not a stage; not the SwarmForge conformance matrix. |

## Baseline

`cd test && python3 -m unittest discover -p 'test_*.py'` → **206 tests, OK, ~165s** (104 → 120 → 206).
Every stage must leave this green.
