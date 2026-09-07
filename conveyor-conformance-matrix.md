# Conveyor ↔ Manual — Conformance Matrix

A living checklist mapping every essential from `swarm-orchestrator-manual.md` to the concrete
requirement that satisfies it in Conveyor's PRD (`conveyor-prd.md`) and normative protocol
(`conveyor-handoff-protocol.md`).

Use it two ways: as a **review artifact** (does the MVP cover the manual's essentials?) and as a
**burndown** (as Conveyor pulls an item out of PRD Appendix B, flip its status and tick the box).

**Sources checked:** PRD v0.3 (3 Sep 2026) · Handoff Protocol v0.1 · manual as of this review.
Requirement IDs (`CFG-1`, `HND-3`, …) refer to the PRD; `§n` refers to the protocol; `Bn` refers
to a PRD Appendix B deferral entry; `inv n` refers to a protocol §9 invariant.

---

## Status legend

| Mark | Meaning |
|---|---|
| `[x] full` | Present and specified to the manual's intent. |
| `[~] simplified` | Present, but narrowed vs the north star; grows later without redesign. |
| `[ ] deferred` | Not in the MVP; has a written re-add path in Appendix B. |
| `[!] diverges` | A deliberate design decision that departs from the manual — decide, don't just tick. |

---

## Scorecard

| Manual area | full | simplified | deferred | diverges |
|---|---|---|---|---|
| Isolation & setup | 6 | 1 | 0 | 1 |
| Pipeline config | 2 | 2 | 1 | 0 |
| Tasks | 3 | 1 | 0 | 0 |
| Handoffs & queues | 6 | 2 | 1 | 0 |
| Pipeline flow | 1 | 2 | 1 | 0 |
| Verification | 3 | 0 | 1 | 0 |
| Human gates | 3 | 0 | 1 | 0 |
| Observability | 2 | 2 | 1 | 1 |
| Durability & cost | 4 | 1 | 1 | 0 |

Two `[!]` items are the only ones that are decisions rather than deferrals; both are called out in
the "Decisions" section at the end.

---

## 1. Isolation & setup (manual Part 1)

- [x] **full** — One config file defines the pipeline → `CFG-1`; order derived from config, not hardcoded (§3.2).
- [!] **diverges** — "Installing changes nothing tracked" → runtime state is gitignored (`ISO-5`: `.worktrees/`, `.conveyor/`, rules file), but the *contract* (`conveyor.conf`, `constitution/`, `roles/`, `project.md`, `tasks/*.md`) is committed. Forced by `HND-2`/§4.2 (task file must exist at the commit). See Decision D1.
- [x] **full** — Worktree + branch per role; one integration tree → `ISO-1` (main checkout is integration; no agent runs there).
- [x] **full** — Prompts/scripts/constitution copied into each worktree → `ISO-2`, `CON-2` (`.cursor/rules/conveyor-role.mdc`); `handoff.sh` on the worktree path (IMPLEMENT.md).
- [x] **full** — Identity from environment, never the agent → `ISO-3`, §1 ("no script accepts identity as an argument"), `inv 7`.
- [x] **full** — Scratch confined to the worktree by tooling → `ISO-4`, `E_DRAFT_PATH`.
- [x] **full** — One command sets up from a fresh clone → `conveyor start` (§10).

## 2. Pipeline configuration (manual Part 2)

- [~] **simplified** — Pipeline order/size in config → `CFG-1` (config-driven per §3.2; default Review belt is two roles; n-role and explicit `gate` supported).
- [ ] **deferred** — Receive mode per role (task vs batch) → task-only now; batch review roles are **B.3**.
- [~] **simplified** — Different backend per role → model-per-role + different families by default (`CFG-1`, `VER-4`); backend fixed to Cursor, second backend is **B.1**.
- [x] **full** — Layered constitution with precedence → `CON-1` (engineering/workflow/handoffs + `project.md` + roles; `constitution.md` declares precedence).
- [x] **full** — Owns / does-not-own / handoff contract per role, re-injected per task → `CON-3` (≤2 pages, exact sections); "Re-read your role and constitution." prepended each run (§6.8).

## 3. Tasks (manual Part 3)

- [x] **full** — Create task = validate + write `tasks/<name>.md` + card + notify → `conveyor task` (§10): validate name, commit task file on main, board row, operator handoff to coder, immediate sweep.
- [x] **full** — Task intent is a versioned file agents re-read → `CON-4`; body is byte-identical to the commit message (`inv 6`).
- [x] **full** — Stable task ID survives every move and retry → `task_id` stable for the row's life (§8.1); `conveyor resume` never resets id/audit/retry (§6.10); counters monotonic (`inv 9`).
- [x] **full** — Tasks deleted cleanly → `conveyor task --delete` with new id + zeroed counters (§8.1); `audit_pending/<task>.fp` removed on delete so a recreated name is challenged again.

## 4. Handoffs & queues (manual Part 5)

- [x] **full** — One validator is the only send path; SHA + identity auto-filled → `handoff.sh`, `HND-3`, `inv 7`.
- [x] **full** — Message types minimal; no free-form chatter → **one** type `git_handoff` (`HND-1`); `note` dropped (**B.10**) — tighter than the manual's "two types".
- [x] **full** — Directories as queue state; timestamps in headers → `HND-8`, §2.3, §3.2 (each stamp written by exactly one script).
- [x] **full** — Delivery + merge idempotent, survive replay → `HND-7` (id-in-`sent/` dedupe), `HND-9`/§7.2 (`merge-base --is-ancestor`), `inv 4/5/11`; §6.5 "every step safe to repeat".
- [x] **full** — Every transition is an atomic rename → `HND-5`, `inv 3`, §8.3 (IMPLEMENT.md: grep for in-place writes, there must be none).
- [x] **full** — Ready/done helpers refuse ambiguity → `LOOP-1`, §6.1 (>1 in-process → refuse start), §6.3 (>1 outbox → park), `inv 12`.
- [~] **simplified** — Validator error messages good enough to self-repair → §4.5 full code table with verbatim repair text; scoped to the MVP's routes.
- [~] **simplified** — Separate transactional delivery daemon → folded into the sending loop's delivery sweep (§6.5); split back out for multi-recipient delivery (**B.10**).
- [ ] **deferred** — `priority` header / priority-sorted filenames → nothing to prioritise in a linear two-role belt (**B.10**); re-add with batch mode (**B.3**).

## 5. Pipeline flow (manual Part 7 — flow rules)

- [~] **simplified** — Unconditional forwarding; belt never stalls → true by construction at N=2 (coder→reviewer; reviewer→done|coder); intermediate-role `PIP-1` forwarding is **B.3**.
- [ ] **deferred** — Sync vs forward handoffs, no loops → not needed at N=2; the reviewer→coder findings edge is a normal handoff bounded by `max_retries`, not a merge-only sync handoff (**B.3**, `non-forwarding` header).
- [~] **simplified** — Done is a structural condition the tooling checks → `reviewer → done: pass`, loop checks `to==done` (§6.5); the "last role's `to:` lists every other role" set condition is `PIP-3` (**B.3**).
- [x] **full** — Wake-ups are generic / agents can't cherry-pick → moot under headless `-p` (fresh process per item, oldest-first dequeue §6.2); interactive wake-ups are **B.2**.

## 6. Verification & quality gates (manual Part 7)

- [x] **full** — Producer ≠ verifier → coder vs reviewer, uncorrelated model families (`VER-4`), reviewer never edits code (`VER-3`).
- [x] **full** — Two-call audit gate → `VER-1`, §5 (`sha256(commit+to+task+verdict)` fingerprint, challenge/accept, survives reboot); `inv 8` (no queueing without an accepted fingerprint).
- [x] **full** — Audit count tracked and surfaced → `VER-2` (only `handoff.sh` writes it), shown by `conveyor status` (`OBS-1`), `inv 9`.
- [ ] **deferred** — Named mandatory tools; mutation score is the truth → reviewer runs "the project's test command" + traces requirements to evidence (`VER-3`); CRAP/DRY/mutation/spec-mutation is **B.4**.

## 7. Human checkpoints (manual Part 6)

- [x] **full** — Early human gate at spec/plan → configurable `gate <role>` hold in `.conveyor/approvals/pending/`; `conveyor approve` / `reject`; intake approve for inbox items (`cfg.gate_role()`, `test/test_pipeline.py`).
- [ ] **deferred** — Structured clarifications with IDs → headless agents can't ask mid-task; ambiguity parks instead (`inv 12`); clarification channel is **B.5**.
- [x] **full** — Rejections carry actionable findings; id/audit survive retry → reviewer `findings` in the commit message, coder reads them on retry (§6.8 step 3); `task_id`/`audit_count`/`retry_count` preserved (§6.10).
- [x] **full** — Human's task statement is a versioned file agents re-read → `CON-4`, §6.8 step 2.

## 8. Observability (manual Parts 5-legibility, 8)

- [!] **diverges** — Terminal per agent; watchdog restores panes → headless `-p`, no panes, no watchdog (**B.2**); traded for free fresh-context-per-task, at the cost of mid-task steering. See note under Decision D2.
- [x] **full** — File-backed board a human can `cat` → `board.tsv` (§8.1); `conveyor status` prints queue state from `ls` (`OBS-1`).
- [x] **full** — Role byline in every commit; `--no-verify` forbidden → commit-msg hook (`HND-10`, §7.4), `E_NO_BYLINE`, `inv 10`.
- [~] **simplified** — Read-only dashboard first, controls second → substituted by `conveyor status`/`log` + `tail -f`; full dashboard is **B.6** (its "read-only first" constraint means it builds over these files with no protocol change).
- [~] **simplified** — Per-run logs → one stream-json log per run (`OBS-2`, §6.9); `conveyor log` pretty-prints.

## 9. Durability & cost control (manual Part 9)

- [x] **full** — Resumes cleanly after reboot → `inv 11` + M1 (`kill -9` at every boundary → identical end state); success metric: 100% of `kill -9` resume with no dup/lost card.
- [x] **full** — Per-task wall-clock ceiling → `max_minutes`, checked between attempts (`BUD-3`, §6.6).
- [x] **full** — Max-retry parks stuck tasks in a needs-human lane → `max_retries` → `.conveyor/needs-human/` + `reason` (`BUD-2`, M4); `conveyor resume` re-injects (§6.10).
- [x] **full** — Restart state is the filesystem; every helper idempotent → §6.1 resume-before-new, atomic renames throughout, `inv 3/11`.
- [ ] **deferred** — Per-task token/cost ceiling; loop detection → blocked on Cursor stream-json usage reporting (**B.7**); loop detection = park on repeated `(role, task, commit)` (**B.7**).
- [~] **simplified** — Cost levers (pack size, worker cap, backend per role) → model-per-role present; pipeline size configurable via `conveyor.conf`; no worker cap until batch mode (**B.3**).

---

## Ahead of the manual / SwarmForge

Not gaps — places Conveyor exceeds the reference:

- **Ceilings are first-class, not an afterthought.** `max_retries` / `max_minutes` / `max_attempts` with a `needs-human` lane are an MVP milestone (M4). The manual lists these as the part "frameworks usually skip"; Conveyor built them in.
- **Durability is a tested invariant.** Crash-at-every-boundary resume is `inv 11` and an M1 exit criterion, with a fake-agent `crash` primitive (§11) to exercise it.
- **"Enforced, not requested" is machine-checked.** 12 filesystem-detectable invariants (§9), an error-code table with verbatim repair text (§4.5), and the rule "never parse agent prose; the outbox is the only signal."

---

## Decisions (the two `[!]` items — resolve these explicitly)

**D1 — The contract files are committed to the host repo.**
The manual's Part 1 ("installing changes nothing tracked") contradicts its Part 3 ("task intent is a
committed file agents re-read"): `handoff.sh` requires `tasks/<task>.md` at the commit, so the task
file *must* be committed. Conveyor commits config, constitution, roles, and task files — consistent
with SwarmForge.
*Recommended resolution:* amend the manual to distinguish untracked **runtime state**
(`.worktrees/`, `.conveyor/`) from committed **contract** (config, constitution, roles, tasks), and
mark this row `[x] full` once the manual is fixed.

**D2 — Auto-merge to `main` on `pass`.**
The configurable `gate <role>` hold and intake approve are in (`gate <role>`,
`.conveyor/approvals/pending/`, `conveyor approve` / `reject`; three-role default gates the
first role). Structured clarification channel remains **B.5**. On `pass`, the last role still
auto-merges to `main` (§7.3), so the human reviews merged code after the fact unless the task
parks. The manual wanted the *early* gate as the point of maximum leverage — the gate hold
addresses that for gated pipelines; auto-merge is the remaining choice.
*Options:* (a) accept full autonomy for trusted, well-scoped tasks; (b) cheapest partial gate —
flip PRD open-question 3 to "leave the branch, don't auto-merge", making the human's
branch-read a de facto exit gate; (c) add a post-pass hold before merge.
*Resolved:* made configurable rather than fixed — `[global] integration = merge | hold | command`
(§7.3). `merge` keeps (a); `hold` is (b); `command: <cmd>` routes `done` to a hook (e.g. open a
PR) for a review-before-land gate. Default stays `merge`.

---

## How to keep this current

1. When an Appendix B item is implemented, change its status mark, tick the box, and replace the
   `Bn` pointer with the new requirement/section IDs.
2. Re-run the scorecard counts at the top.
3. On any protocol change, re-check the invariants column (`inv n`) — those are the properties that
   must not regress.
4. Revisit D1 and D2 at each milestone; move them out of "Decisions" once resolved in the docs.
