# Conveyor — moat and gap scan

A living checklist to walk this repo (and the first NX target) and mark what is
enforced, what is only a prompt, and what we must not claim.

This is **not** a second SwarmForge-manual matrix. Use
[`conveyor-conformance-matrix.md`](../../conveyor-conformance-matrix.md) for that.
Use this for: *does the tree still match the moat we said we have, and have we
accidentally claimed Appendix B?*

UI stage plans live in [`README.md`](README.md). Stage 0–2 and the Workflow/Roles
split are **done**; do not treat those plan files as open gaps.

**How to run:** mark each row. Do not flip a row to Done from a plan file. Grep
or a test must show it.

| Mark | Meaning |
| --- | --- |
| Done | In code + a test or a one-line proof (path + behavior) |
| Prompt-only | Constitution / role / `project.md` asks; no script refuses |
| Missing | Not in the tree |
| Docs-drift | Code and docs disagree |
| Out | Appendix B / not this scan — do not build from a "gap" feeling |
| N/A | Does not apply to this target repo |

Proof column: file, test, or command you used. Empty proof = not Done.

**Scan of 2026-09-04 — this repo** (not the NX target). 120 tests OK (~135s).
`npx tsc -p ui/tsconfig.app.json --noEmit` clean.

---

## 0. Before you start

- [x] `cd test && python3 -m unittest discover -p 'test_*.py'` — suite green
      Proof: 120 tests, OK, 134.9s (2026-09-04)
- [x] `cd ui && npx tsc -p tsconfig.app.json --noEmit` — clean if you touch UI
      Proof: exit 0, no output
- [x] You know which tree you are scanning: **this repo** vs **first NX target**
      This pass: **this repo**. §7 is N/A.
- [x] Conformance matrix D2 rewritten — gate hold is in; auto-merge on `pass` is the
      remaining recorded choice (not "no in-loop gate").
      Proof: `conveyor-conformance-matrix.md` D2; `cfg.gate_role()` + `test/test_pipeline.py`.

---

## 1. Positions we claim (must stay true)

These are the moat. A miss here is a product hole, not a feature request.

### 1.1 Coordination is git + filesystem

- [x] **Done** Every board / queue / handoff / audit / park state is a file or git object
      Proof: `lib/conveyor/layout.py` (`.conveyor/`, `board.tsv`, role queues);
      grep `websocket|sqlite|redis` under `bin/` `lib/` `ui/server/` empty
- [x] **Done** UI and CLI only read or write those files
      Proof: `ui/server/state.py` + `ui/server/cli.py` wrap `bin/conveyor`;
      role/`project.md` writes are `util.atomic_write` to the repo. No parallel store
- [x] **Done** You can explain a stuck task with `ls`, `cat`, `git log` only
      Proof: `bin/conveyor` `cmd_status` prints `layout.handoffs` + `needs-human/reason`
      + `board.tsv`; runbook §6 sample still matches (`test_m4_ceilings.py` asserts the
      `needs-human:` block)
- [x] **Done** No new hidden backend added (websocket push, session DB, vendor dashboard)
      Grep: `websocket`, `sqlite`, `redis` under `bin/` `lib/` `ui/server/` — no matches.
      UI poll is HTTP GET `/api/state`

### 1.2 Verification is structural, not a self-report

- [x] **Done** Coder cannot send `to: done` / `verdict: pass`
      Proof: `config.routes()` last-role-only `(n[-1], "done", "pass")`;
      `test_errors.Errors.test_E_BAD_ROUTE` (`coder may not send pass to done`)
- [ ] **Prompt-only** Reviewer does not edit the worktree (prompt **and** no write path in loop)
      Proof: `roles/reviewer.md` "You do not edit code, tests, or docs." Loop never
      `git commit`s (agent does). No script refuses a reviewer who edits and commits
      (`E_DIRTY` only until they commit; byline becomes `By reviewer.`).
- [x] **Done** Two-call audit gate still in `handoff.sh` (change resets fingerprint)
      Proof: `bin/handoff.sh` `gate()`; `test/test_m2_gate.py`; `test/test_inv08_audit_first.py`
- [x] **Done** Outbox is the only success signal (loop does not parse agent prose)
      Proof: `bin/role-loop.sh` `valid_outbox_count()` counts `layout.handoffs(self.rp.outbox)`
- [x] **Done** (thin) Project test command: `handoff.sh` runs the `## Test command`
      fence on `ready`/`pass` before audit; empty fence skipped; `E_GATE_FAILED`
      + `.conveyor/logs/gates/`
      Proof: `bin/handoff.sh` `run_test_command`; `test/test_errors.py`
      `test_E_GATE_FAILED`; `test/test_gate_command.py`

### 1.3 Human leverage is concentrated

- [x] **Done** Task file is the pre-run decision (`conveyor task` / inbox approve)
      Proof: `bin/conveyor` `cmd_task` / `cmd_inbox`; `test/test_inbox.py`
      `test_intake_grade_and_approve_writes_task_not_board`
- [x] **Done** First `ready` leaving the configured `gate` role is held in
      `.conveyor/approvals/pending/`
      Proof: `cfg.gate_role()` + `queue.sweep` hold; `test/test_pipeline.py`
      `test_specifier_ready_held_then_approve`; `test/test_pipeline_shape.py`
- [x] **Done** Parked work leaves only via `conveyor resume` (UI never auto-retries)
      Proof: `bin/conveyor` `cmd_resume`; UI `resume()` → `POST /api/resume` only
      (`ui/src/app/cockpit/cockpit.component.ts`). No auto-retry timer
- [x] **Out** No mid-task clarification channel — **Out** (B.5) unless you pull it
      Proof: no `clarify` / `question` verdict in `config.VERDICTS`; listed deferred
- [x] **Done** Auto-merge to main on `pass` is still an explicit choice (matrix D2)
      Proof: `queue.sweep` `h["to"] == "done"` → `merge(..., "operator")`. D2 text is
      stale on the *gate* (see §0), not on auto-merge itself

### 1.4 Idempotent and resumable

- [x] **Done** Every queue move is rename, not in-place write
      Proof: `lib/conveyor/queue.py` `os.rename`; `board.py` "lock, rewrite, rename";
      `handoff.move` / `util.atomic_write` (tmp + rename)
- [x] **Done** `in_process/` > 1 refuses (inv 12)
      Proof: `test/test_inv02_one_in_process.py` `test_two_in_process_refuses_to_start`
      (inv 12 file is `test_inv12_ambiguity_parks.py` for park-on-ambiguity)
- [x] **Done** Crash-at-boundary resume still tested (inv 11 / M1)
      Proof: `test/test_inv11_restart.py`
- [x] **Done** Ceilings park with a `reason` file (`max-retries`, `max-minutes`, …)
      Proof: `test/test_m4_ceilings.py` (`max-retries`, `max-minutes`, `max-attempts`);
      `test/test_inv12_ambiguity_parks.py` (`multiple-handoffs`, `no-rules`, `merge-conflict`)
- [x] **Done** `task --delete` removes board row, park dir, and `audit_pending/*.fp`
      Proof: `test/test_task_delete.py`

### 1.5 Identity and routing are not the model's

- [x] **Done** No script accepts role identity as an argv (`CONVEYOR_ROLE` only)
      Proof: `bin/handoff.sh` / `bin/role-loop.sh` / `bin/hooks/commit-msg` read env;
      `handoff.sh` fails `E_ENV` if unset. Operator CLI `log <role>` / `resume --to` are
      selectors, not agent identity
- [x] **Done** Routes derived from `conveyor.conf` order, not hardcoded triples
      Proof: `config.routes()`; `test/test_pipeline_shape.py`
- [x] **Done** `handoff.sh` fills `from` / `commit`; draft is only `to`, `task`, `verdict`
      Proof: `handoff.sh` `headers = {..., "from": role, "commit": commit}`;
      `E_RESERVED_HEADER` / `E_UNKNOWN_HEADER` in `test_errors.py`

---

## 2. Do not claim (scan for overclaim)

Mark **Docs-drift** if README, UI copy, or a plan says these are done.

- [x] **Done** (not claimed) Second agent backend (Claude/Codex CLI) — **Out** B.1
      Proof: PRD §3 Cursor only; `bin/role-loop.sh` launches `CONVEYOR_AGENT_BIN` as
      cursor-agent (`-p --force --model`). `lib/conveyor/adapters.py` is inbox (Jira),
      not an agent backend
- [x] **Done** (not claimed) tmux / pane / mid-task steer — **Out** B.2
- [x] **Done** (not claimed) Batch receive, back-propagation, `non-forwarding` — **Out** B.3
      (N-role pipelines and explicit `gate` **are** in; do not conflate)
- [x] **Done** (not claimed) CRAP/DRY/mutation as mandatory tools — **Out** B.4
- [x] **Done** (not claimed) Clarification chat / per-doc review comments — **Out** B.5
      Spec *approve* is in; do not conflate with clarification chat
- [x] **Done** (not claimed) Token/cost ceiling, loop detection — **Out** B.7
- [x] **Done** (not claimed) Forge / multi-project — **Out** B.9
- [x] **Done** (not claimed) "Any CLI-drivable agent" as a shipped feature
      Proof: README / PRD name Cursor CLI. `CONVEYOR_AGENT_BIN` is a test hook, not a pitch
- [x] **Done** (not claimed) "No model cost" (harness is local; turns still bill Cursor)
      Grep of README / pitch: no "no model cost"
- [ ] **Missing** Subagents / skills as belt roles (attachments only, and they are Missing)
      Not claimed as belt roles. No skills / `.cursor/agents` / MCP wiring in `bin/` `lib/`

---

## 3. Protocol and CLI (regression)

- [x] **Done** All §4.5 error codes still have a test with **verbatim** repair text
      Proof: `test/test_errors.py` `REPAIR` / `PROBLEM` maps match `bin/handoff.sh` `ERRORS`
      (22 codes)
- [x] **Done** Commit-msg hook: last line `By <role>.` or `E_NO_BYLINE`
      Proof: `bin/hooks/commit-msg`; `test_errors.test_E_NO_BYLINE`; `test_m2_gate.py`
- [x] **Done** `conveyor status` format matches `docs/runbook.md` §6
      Proof: `cmd_status` layout; `test_m4_ceilings.py` asserts
      `needs-human:\n  fix-cache   max-retries   ...`
- [x] **Done** `conveyor init` does not overwrite operator-owned `project.md` / conf
      Proof: `TEMPLATED = ["project.md"]`; `test_init.py`
      `test_idempotent_and_never_clobbers_operator_files`
- [x] **Done** M3 still **Missing** (first live Cursor run) — changelog 0.1.0 Out list
      Proof: `CHANGELOG.md` 0.1.0 Out: "M3 (first live Cursor run)"
- [x] **Done** Fake-agent path still works: `CONVEYOR_AGENT_BIN=./test/fake-agent`
      Proof: the 120-test suite; `docs/runbook.md` §8

---

## 4. Deterministic gates (known hole)

Expected end state: `project.md` names commands; the belt says which hop
requires which name; `handoff.sh` or the loop execs them; UI can "Run now".

- [ ] **Missing** Structured `## Gates` (or equivalent) in `project.md` — else one fence
      Proof: `project.md` has `## Test command` only
- [ ] **Missing** Substitutions `{inbound}` `{head}` documented
- [x] **Done** `handoff.sh` runs required gates **before** audit
      Proof: `bin/handoff.sh` calls `run_test_command` after SHA check, before
      `gate()`; `test/test_gate_command.py`
- [x] **Done** `E_GATE_FAILED` + log under `.conveyor/logs/gates/`
      Proof: `test_errors.Errors.test_E_GATE_FAILED`; `test/test_gate_command.py`
- [ ] **Missing** Start refuses if a hop requires a gate name with no command
- [ ] **Missing** Check vs write separated (`format:check` vs `format:write`)
- [ ] **Missing** Operator "Run now" uses the **same** argv table
      Grep `Run now` in `ui/src`: empty
- [x] **Done** e2e is not on the default coder→reviewer hop
      Proof: no hop-gate table exists, so e2e is not wired to that hop
- [x] **Done** Conveyor does not parse `nx.json` / `project.json`
      Grep under `bin/` `lib/` `ui/server/`: no matches

Hop table, substitutions, start-refusal, check-vs-write, and "Run now" remain
Missing. The thin `## Test command` fence is Done (runs before audit).

---

## 5. Configuration UI (substrate vs skin)

Skin (theme, chat, skill marketplace) is not a gap. Substrate is.

- [x] **Done** Workflow switch writes `conveyor.conf`, 409 if loops running
      Proof: `cmd_pack` → `config.save`; `ui/server/httpd.py` `require_stopped` → 409;
      `test_ui_api.py` `test_workflow_409_while_running`
- [x] **Done** Role prompt save is atomic; applies on next Start (banner still true)
      Proof: `state.write_role` → `util.atomic_write`; no `.mdc` rewrite on save
      (`ensure_worktree` concatenates at `start`). Banner:
      `ui/src/app/roles/roles-page.component.ts` "Applies the next time you Start."
- [x] **Done** `project.md` editable; constitution listed read-only
      Proof: `POST /api/project`; editor "Constitution (read-only)" list;
      no write endpoint for constitution. `test_ui_api.py` `test_runtime_and_project_write`
- [x] **Done** Model list from `cursor-agent --list-models`, free text still allowed
      Proof: `lib/conveyor/agent.py` `list_models`; `GET /api/models`;
      `role-cards.component.ts` autocomplete + free-text `ngModel`;
      `test_agent_models.py` + `test_ui_api.py` `test_models_list`
- [x] **Done** Header copy: no "2-pack" / "3-pack" / "Pack" tab in UI
      Stage 1 done: Inbox · Board · Workflow · Roles
      Proof: `header.component.ts` toggles; `app.routes.ts`. `grep PackPage ui/src` empty;
      `ui/src/app/pack/` absent on disk; `ui/README.md` — Workflow / Roles pages.
- [x] **Done** Cards not dragged; lane only from pipeline
      Proof: `kanban-board.component.ts` has no `cdkDrag` / `cdkDropList`
- [x] **Done** `ui/src/app/pack/` gone; `grep -rn 'PackPage' ui/src` empty
      Proof: `ls ui/src/app/pack/` → No such file; routes import Workflow/Roles pages

Attachments (Missing unless you find code):

- [ ] **Missing** Skills per role persisted (not just leftover `role.args`)
      Proof: `Role.args` is leftover CLI tokens in `config.py`, not skills
- [ ] **Missing** Custom `.cursor/agents/*.md` shipped per worktree
- [ ] **Missing** Per-role sandbox / MCP allowlist
- [ ] **Missing** Named recipes beyond Review belt / Spec then build
      Proof: `lib/conveyor/workflows.py` `STARTERS` is only `two` / `three`

---

## 6. Cursor features — allowed vs forbidden

**Allowed** (attachments on an isolated role):

- [ ] **Missing** (except rules) Skills, rules, `--mode=ask` sidecar, `--sandbox`, MCP allowlist
      Rules **Done**: `ensure_worktree` writes `.cursor/rules/conveyor-role.mdc`.
      Skills / `--mode=ask` / `--sandbox` / MCP: grep empty under `bin/` `lib/`
- [ ] **Missing** Readonly custom subagent **on reviewer only**

**Forbidden** (treat as a bug if present):

- [x] **Done** (absent) Coder-spawned verifier that can complete the task
- [x] **Done** (absent) CLI `--worktree` / Cursor swarm worktrees next to `.worktrees/<role>`
      Proof: grep `--worktree` / `in-cloud` in `bin/conveyor` empty; worktrees are
      `git worktree add .worktrees/<role>`
- [x] **Done** (absent) Parent session that decides `pass`
      Proof: `routes()` only last role may `pass` to `done`; loop counts outbox
- [x] **Done** (absent) Cloud `/in-cloud` as the queue

---

## 7. First NX Angular target (scan that repo)

- [x] **N/A** `project.md` Test command is `nx affected`, not `npm test` / full farm
- [x] **N/A** `--base` can be the inbound handoff SHA (or you accepted `main`)
- [x] **N/A** Install story per worktree written (node_modules / NX daemon / cache)
- [x] **N/A** Lint / test / format check commands known; e2e off the default belt
- [x] **N/A** Module-boundary lint is inside `lint` or a named gate
- [x] **N/A** Clean checkout: the test command exits 0 before first `conveyor start`
- [x] **N/A** `.worktrees/` and `.conveyor/` gitignored
      (This *repo's* `init` does append those — `test_init.py` — but that is not
      the NX target.)
- [x] **N/A** One task with a named NX project if you will add `{project}` later

Worktree disk/daemon cost is an operator note, not a Conveyor bug.

This pass did not open a target repo. Re-walk §7 there before first live NX run.

---

## 8. Honesty pass (readme / pitch / plans)

- [x] **Done** README does not say "no code yet" / "no UI" incorrectly
      Proof: `README.md` — UI exists, "not part of v0.1"; `conveyor-manual.md` glance — preview UI.
- [x] **Done** UI is still labeled preview unless you released it
      Proof: `CHANGELOG.md` 0.1.0 Out: "UI cockpit under `ui/` (preview only)";
      `README.md` same. No 0.2 release
- [x] **Done** Stage 3+ plans (workflow CRUD, intake module, chime, theme) are not
      treated as Done
      Proof: `docs/plans/README.md` Stage 3 = next; 4–6 = not planned
- [x] **Done** Pitch uses: inspectable harness, producer≠verifier, refuse, resume
      Proof: README opening sentence + `conveyor resume` in Use
- [x] **Done** Pitch does not use: finished agent, smarter model, Devin sandbox,
      backend-agnostic, structured chat
      Grep of README / `docs/conveyor-prd.md` summary: those phrases absent

---

## 9. Scorecard (fill when the scan is done)

| Section | Done | Prompt-only | Missing | Docs-drift |
| --- | --- | --- | --- | --- |
| 1 Moat positions | 21 | 1 | 0 | 0 |
| 2 Overclaim | 9 | 0 | 1 | 0 |
| 3 Protocol/CLI | 6 | 0 | 0 | 0 |
| 4 Gates | 4 | 0 | 5 | 0 |
| 5 Config UI | 7 | 0 | 4 | 0 |
| 6 Cursor attach | 4 | 0 | 2 | 0 |
| 7 NX target | 0 | 0 | 0 | 0 |
| 8 Honesty | 5 | 0 | 0 | 0 |

§1 also has 1 **Out** (clarification). §7 is 8× **N/A**. §2 "Done" = confirmed not claimed.
§6 "Done" on forbidden rows = confirmed absent. §4 thin test command is Done
(called out under §1.2); hop table / Run now still Missing.

**Ship-blocker:** any §1 row that is Missing or Prompt-only if you claimed it as
enforced.

This pass:

1. **Project test command** — Done (thin); `handoff.sh` execs the fence on ready/pass.
2. **Reviewer does not edit** — Prompt-only. Isolation + role file; no refuse.

**Known wrap-up hole:** hop table, substitutions, start-refusal, check-vs-write,
and "Run now" remain Missing. The thin fence-before-audit slice is Done.

**Do not open from this scan:** chat, generic node-graph builder, plugin
marketplace, hosted VM.

---

## How to keep this current

1. After a protocol or UI stage, re-walk §1 and §5; flip marks with proof.
2. When an Appendix B item is pulled in, move it from §2 to a Done row in §1
   or §4 — do not leave it in both.
3. When gates land, replace the "known hole" note and add the test names to
   the §4 proofs.
4. Revisit conformance-matrix D2 when you next edit that file — D2 rewritten (gate in; auto-merge choice recorded).
5. Re-walk §7 in the first NX Angular target before calling M3 done.
