# Generated handoff contract — role files are craft, the belt is config

**Status:** planned. Amends PRD CON-3 and protocol §2 / §6.3's description of
the rules file. No queue, validator, or state-machine change.

**Job:** Every `roles/<name>.md` must carry a `## Handoff contract` section
that restates, by hand, the routes `handoff.sh` already derives from
`conveyor.conf`. The copy is wrong for any belt other than the one it was
written for, and it makes the role file look like pipeline machinery a user
should not touch — when the rest of the file is exactly what a team should
tune. Generate the contract from the config at `conveyor start`, drop the
requirement from role files, and leave them as pure craft.

Not hiding role prompts, not moving the constitution out of the target repo,
not a role-file schema.

---

## Why

### The contract in the role file is already wrong

`roles/coder.md`:

> Receives: `ready` from operator (new task) or `findings` from reviewer.

In the three-role belt (`specifier → coder → reviewer`), and in every custom
workflow with a role before `coder`, the coder receives `ready` from its
predecessor, not the operator. `roles/reviewer.md` says `Sends: to: coder,
verdict: findings` — right only while `coder` is the penultimate role. Protocol
§3.2 generalized belts to N roles on 2026-09-04 and `conveyor workflow
activate` reorders them at will; a static section cannot follow. It has not
been noticed because `handoff.sh` ignores the prose and enforces
`Config.routes()`, so a wrong contract costs an `E_BAD_ROUTE` and a retry, not
correctness. It is still a prompt that lies to the agent about its own
neighbours.

The stub for a new role (`roles._ROLE_STUB`) is worse: it hands the user
`- (describe handoff contract)` and asks them to write, from memory, mechanics
that the validator will enforce regardless of what they write.

### It is duplicated in the layer that is supposed to own it

`constitution/handoffs.md` already carries the draft format, the audit rule,
every error code, and a two-pack routing table labelled as an example. The
process layer exists and ships verbatim. The role file's section is a second
copy of part of it, specialized to one belt shape.

### The blend is the real cost

A role file today is two things interleaved: mechanics (`Sends:`, `Receives:`,
empty-commit-for-findings) and craft (`Owns`, `Does not own`, the reviewer's
`Bias to guard against`). The mechanics make the whole file read as
conveyor-internal, so teams leave the craft alone too — and the craft is the
one part worth tuning per stack. Skills (`roles.inject_skills`) can only add a
capability tree; they cannot make a reviewer stricter about the requirements
the coder's message discusses least. Separating the layers is what makes the
role file safe to edit and obviously so.

### Why not hide the prompts instead

The instinct behind "users shouldn't change how conveyor works" is right, and
it is already satisfied by `handoff.sh`. Hiding the prompt would freeze the
craft layer behind a release cycle, would cut against a product whose pitch is
that every instruction to an agent is a file you can read, and would not
actually delete the mechanics — they would still have to reach the agent, just
from somewhere the operator cannot see. Generating the mechanics into the
`.mdc` keeps them visible, correct, and out of the file a user edits.

---

## Locked decisions

1. **`ensure_worktree` appends a generated `## Handoff contract` after the
   role file and before `## Assigned skills`.** It is computed from
   `cfg.routes()` filtered to this role, plus `cfg.gate_role()`. The rules
   file is now `constitution + project.md + role + contract + skills`, in that
   order. The role file itself is not modified on disk.

2. **The block is derived, never templated per role name.** For role `r` in
   `cfg.names()`:

   - **Receives:** `ready` from `operator` if `r` is first, else from its
     predecessor; `findings` from the last role if `r` is penultimate.
   - **Sends:** `ready` to its successor if not last; `pass` to `done` and
     `findings` to the penultimate role if last. A one-role belt has no
     `findings` line at all (protocol §3.2).
   - **Gate:** if `cfg.gate_role() == r`, one line: your `ready` is held in
     `.conveyor/approvals/pending/` until the operator approves it; a
     rejection comes back as a `findings`-style body beginning `Rejected by
     operator:`.
   - **Commit rule for `findings`:** for the last role only — `findings`
     requires a commit that is not the one you received; an empty commit
     (`git commit --allow-empty`) whose message is the findings list is the
     expected form. This is `E_NO_CHANGE`'s repair text, restated where the
     agent reads it before it needs it.
   - **Draft format:** the three-line `./tmp/handoff.txt` and the exact
     `handoff.sh ./tmp/handoff.txt` invocation, so the agent's most-read
     section is self-contained.

   Rendered for `coder` in `coder → reviewer`:

   ```
   ## Handoff contract

   Generated from conveyor.conf at conveyor start. This section overrides any
   hand-written contract above it.

   | You are | to | verdict | When |
   |---|---|---|---|
   | coder | reviewer | ready | Task done and verified |

   You receive `ready` from operator (new task) and `findings` from reviewer
   (rework).

   Write exactly this to ./tmp/handoff.txt, then run handoff.sh ./tmp/handoff.txt:

       to: <role or done>
       task: <task name from your prompt>
       verdict: <ready | pass | findings>
   ```

   For `coder` in `specifier → coder → reviewer` the second sentence reads
   "You receive `ready` from specifier and `findings` from reviewer." For
   `reviewer` (last, two-pack) the table has two rows (`coder`/`findings`,
   `done`/`pass`) and the empty-commit rule follows it. For a gated
   `specifier` the gate line follows the table.

3. **`REQUIRED_ROLE_HEADINGS` becomes `("Owns", "Does not own")`.** A role file
   that still contains `## Handoff contract` is accepted, and `conveyor start`
   prints `warning: roles/<name>.md carries a hand-written Handoff contract;
   the generated one overrides it — delete the section`. The same text
   appears as a non-blocking note in the cockpit's role editor. Not refused:
   an operator upgrading Conveyor under an existing target repo must not have
   `start` fail on files `init` gave them last month. Not stripped: Conveyor
   does not rewrite operator-owned files and does not parse prose to decide
   what to drop. The generated block's first sentence handles the agent's
   side of the ambiguity.

4. **Shipped role files lose the section.** `roles/coder.md`,
   `roles/reviewer.md`, `roles/specifier.md`: `## Handoff contract` is
   removed. The reviewer's "for `pass`, an empty commit stating what you
   verified is preferred; the inbound commit unchanged is permitted" moves to
   step 6 of `## How to review` — it is a preference, so it is craft, so it
   stays in the file. The `findings` empty-commit rule is mechanics and moves
   to the generated block (decision 2). The coder's `## On findings` and
   `## On a task you cannot complete`, and the specifier's `## On reject`,
   stay: they are about how to respond to content, not about routing.
   `_ROLE_STUB` drops the section. `conveyor init` does not overwrite an
   existing `roles/` — decision 3's warning is how existing repos learn.

5. **`ticket-reviewer` is untouched.** Its contract is fixed
   (`to: operator, verdict: ready`) and already generated into the `.mdc` by
   `intakelib.GRADE_CONTRACT`. `ui/server/state.py`'s `write_intake_prompt`
   uses the same two headings as `roles.validate_role_text` after this change,
   via the shared constant it already imports.

6. **The contract is exposed read-only where roles are edited.** `GET
   /api/roles/<name>` gains a `contract` string (the rendered block for the
   current `conveyor.conf`), and the role-detail dialog shows it beneath the
   editor as a non-editable panel titled "Handoff contract (generated from
   the active workflow)". This is the legibility half of the change: the
   operator sees the boundary between what they edit and what the belt
   dictates. `conveyor role show <name>` prints the same block after the file.

7. **PRD CON-3 and the protocol are amended, not worked around.** CON-3
   becomes: "Each role file ≤ 2 pages with `## Owns` and `## Does not own`.
   The handoff contract is generated from `conveyor.conf` into the rules file
   (CON-2) and is not part of the role file." Protocol §2 (the `.mdc` line)
   and §6.3's "Role instructions themselves are not in the prompt" paragraph
   describe the five-part composition and reproduce the rendered block for
   the two-pack. `constitution/handoffs.md` is **not** changed: its table is
   already labelled a two-pack example and its generic paragraph is correct.

---

## Out

- Hiding role prompts, reading the constitution from the Conveyor install
  instead of the target repo, or any re-sync of shipped files into existing
  repos.
- Stripping or rewriting a hand-written contract section (decision 3).
- A role-file schema beyond the two headings. `Owns` / `Does not own` stay
  required because the validator has required them since Stage 3 and the
  cockpit editor keys on them.
- Changing `Config.routes()`, `handoff.sh`, or any error code. The block is
  a rendering of `routes()`; if they ever disagree, the test in §Tests
  catches it.
- Changing the intake prompt composition (decision 5).
- The `## Assigned skills` block or `inject_skills`.

---

## Operator surface

### `conveyor start`

Silent when role files are clean. Otherwise, once per offending role:

```
warning: roles/coder.md carries a hand-written Handoff contract; the generated one overrides it — delete the section
```

### `conveyor role show <name>`

```
$ conveyor role show coder
# roles/coder.md
<file contents>

# Handoff contract (generated from conveyor.conf: coder → reviewer)
<rendered block>
```

### Cockpit

Role detail dialog: editor unchanged; hint text becomes "Headings required:
Owns, Does not own."; below the editor, the read-only generated block with the
title from decision 6. When the file carries its own `## Handoff contract`,
the decision 3 warning shows above the panel.

### `.cursor/rules/conveyor-role.mdc`

```
---
description: Conveyor rules for role coder
alwaysApply: true
---

<constitution.md>
<constitution/engineering.md>
<constitution/workflow.md>
<constitution/handoffs.md>
<project.md>
<roles/coder.md>

## Handoff contract
<generated>

## Assigned skills
<if any>
```

---

## Implementation

### `lib/conveyor/roles.py`

- `REQUIRED_ROLE_HEADINGS = ("Owns", "Does not own")`.
- `_ROLE_STUB` loses the section.
- `has_handwritten_contract(text) -> bool`: the same regex shape as
  `validate_role_text`, for the warning.
- `render_contract(cfg, name) -> str`: decision 2. Pure function of
  `cfg.routes()`, `cfg.names()`, `cfg.gate_role()`, and `name`. Raises
  `RoleError` for a name not on the belt — `ensure_worktree` only calls it
  for belt roles, but the UI endpoint may be asked about a library role that
  is off-belt; that returns `contract: null` and the panel says "not on the
  active workflow".

### `bin/conveyor`

- `ensure_worktree(root, paths, cfg, role_name)`: takes `cfg`, appends
  `render_contract` output between the role text and `skills_block`. Emits
  the decision 3 warning when `has_handwritten_contract` is true. The intake
  branch is unchanged.
- `cmd_role show`: append the block (or "not on the active workflow").

### `ui/server/state.py`

- Role GET payload: `contract` (string or null), `handwritten_contract`
  (bool).
- `write_intake_prompt`: unchanged code, new constant value.

### Cockpit

- `ui/src/app/dialogs/role-detail-dialog.component.ts`: hint text; read-only
  panel; warning banner.
- `ui/src/app/intake/intake-settings-rail.component.ts`: hint text.

### Shipped files

- `roles/coder.md`, `roles/reviewer.md`, `roles/specifier.md` per decision 4.

### Docs

- `docs/conveyor-prd.md` CON-3.
- `docs/conveyor-handoff-protocol.md`: §2 tree comment on the `.mdc` line;
  §6.3 composition paragraph with the rendered two-pack block.
- `docs/runbook.md` §3 step 4: "write `.cursor/rules/conveyor-role.mdc` into
  each (constitution + project + role + generated handoff contract + skills)".
- `bin/README.md` Ambiguities: why warn rather than refuse or strip
  (decision 3); why the empty-commit rule is mechanics and the `pass`
  preference is craft (decision 4).
- `CLAUDE.md` "Isolation" bullet: add the generated contract to the list of
  what `start` writes.

---

## Tests

New `test/test_role_contract.py`:

1. **Rendering agrees with `routes()`.** For belts of length 1, 2, 3, and 4
   with generated names, every `(from, to, verdict)` in `cfg.routes()` whose
   `from` is the role appears as a table row in `render_contract`, and no row
   appears that is not in `routes()`. Intake's `(ticket-reviewer, operator,
   ready)` never appears.
2. One-role belt: no `findings` anywhere in the block.
3. Two-pack `coder`: receives from `operator`; three-pack `coder`: receives
   from `specifier`. Exact sentences.
4. Last role: the empty-commit rule is present; non-last roles: absent.
5. Gated role: the gate line present; `gate none`: absent everywhere.
6. `ensure_worktree` output order: role text, then `## Handoff contract`,
   then `## Assigned skills` when a skill is assigned. Byte-level check on
   the section order in the written `.mdc`.
7. A role file with `## Handoff contract` is accepted by
   `validate_role_text`, and `conveyor start` prints the exact warning once.
8. A role file with only `Owns` and `Does not own` passes; missing either
   fails with the existing message.
9. `_ROLE_STUB` has no `Handoff contract`; `conveyor role new x` produces a
   file that passes validation.
10. `GET /api/roles/coder` carries `contract` matching `render_contract`;
    a library role off the belt carries `null`.
11. `conveyor role show` output ends with the rendered block.

Existing tests that change: `test/test_roles.py` (the `all(h in text …)`
helper follows the constant), `test/test_ui_api.py` line ~247 (fixture no
longer needs the third heading; keep one variant that still has it to cover
test 7 through the API).

`test/fake-agent` scripts are unaffected: they read `to` / `verdict` from the
script, not from the `.mdc`.

---

## Verification

1. `conveyor start` on the two-pack, then `cat
   .worktrees/coder/.cursor/rules/conveyor-role.mdc | sed -n '/## Handoff
   contract/,/## Assigned/p'`. Compare with decision 2's rendering by eye.
2. `conveyor workflow activate <three-role preset>`, `conveyor start`, same
   command on `.worktrees/coder`: receives from `specifier`.
3. Point a target repo that still has the old `roles/coder.md` at the new
   Conveyor. `conveyor start` prints the warning and starts. Delete the
   section, `start` again, silent.
4. Cockpit: open the coder role; the panel shows the block; edit the file to
   add a `## Handoff contract`; the banner appears.
5. `test/` green.

---

## Order of work

1. `render_contract` + tests 1–5. Pure; nothing wired.
2. `ensure_worktree` + warning + tests 6–7. This is the moment the agent's
   rules change; do it in its own commit.
3. Constant change, stub, shipped role files, tests 8–9.
4. `role show`, API field, cockpit panel, tests 10–11.
5. PRD, protocol, runbook, README, `CLAUDE.md`.

Steps 1–2 land safely on a repo whose role files still carry the section:
the agent sees both, the generated one says it wins, and the warning names
the file. Step 3 is what lets new repos never see the old shape.

---

## Tag

Independent of M3; small enough for the next rc. It changes what every agent
reads on its first turn, so it should land before a live run rather than
between two.
