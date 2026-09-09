# Cursor docs alignment — two files still describe the Claude-era delivery

**Status:** planned. Text only; no code, no tests beyond the existing doc
greps.

**Job:** Conveyor was designed against Claude Code and runs on Cursor CLI.
Every file under `bin/` and `lib/` made the switch. Two documents did not: one
tells a reader the wrong mechanism for how instructions reach an agent, and the
repository's own development guidance is loaded only by the agent Conveyor no
longer uses.

---

## Why

### The north star names a flag Conveyor never passes

`docs/agent-orchestration-north-star.md`, line 67:

> Each agent gets a generated instruction file: read `constitution.prompt` and
> everything it references recursively, read `roles/<role>.prompt`, then a
> tool-startup block. Delivered via `claude --append-system-prompt-file`, or as
> the initial prompt / `--rules` for codex, copilot, grok.

The real mechanism is `.cursor/rules/conveyor-role.mdc` with
`alwaysApply: true`, written per worktree by `ensure_worktree` and loaded by
Cursor from the worktree root; the prompt carries only the task, the inbound
handoff, and the retry context (protocol §6.3: "Role instructions themselves
are not in the prompt"). The north star is the "why" document, and it is the
one place a reader would be misled about the "how". The file extensions
(`.prompt`) are also from the earlier design.

`docs/conveyor-prd.md` line 274 (Appendix B.1) also mentions
`claude --append-system-prompt-file` — correctly, as the rule-injection method
a *future second backend* would need. That line stays.

### `CLAUDE.md` is read by the wrong agent

`CLAUDE.md` is the development guidance for this repository (reading order,
layout, hard rules). Claude Code reads it automatically. Cursor's agent and
CLI read `AGENTS.md`; they do not read `CLAUDE.md`. Anyone developing Conveyor
with Cursor gets none of it — including the hard rules about not editing
shipped files and recording ambiguities in `bin/README.md`.

---

## Locked decisions

1. **North star line 67 is rewritten to the shipped mechanism**, keeping the
   sentence's job (what the agent is given) and dropping the flag list:

   > Each agent gets a generated rules file: the constitution and everything it
   > references, `project.md`, the role file, and its handoff contract,
   > written to `.cursor/rules/conveyor-role.mdc` in the role's worktree and
   > loaded by Cursor on every turn. The per-run prompt carries only the task,
   > the inbound handoff, and any retry context.

   "and its handoff contract" assumes
   [generated-handoff-contract.md](generated-handoff-contract.md); if that plan
   is not taken, drop the four words. Nothing else in the north star changes —
   the document is allowed to be aspirational everywhere except where it
   states a mechanism as fact.

2. **`AGENTS.md` is added at the repository root as a pointer, not a copy.**
   Its whole content:

   ```
   # AGENTS.md

   Development guidance for this repository lives in `CLAUDE.md`. Read it
   first; it is the single source and is not duplicated here.
   ```

   A copy would drift; a symlink is not honoured on every checkout. `CLAUDE.md`
   is not renamed: it is referenced by name from `docs/plans/*.md`,
   `docs/conveyor-handoff-protocol.md` §3.2, and `bin/README.md`, and the
   name is what Claude Code looks for.

3. **`conveyor init` does not ship `AGENTS.md`.** It is guidance for
   developing Conveyor, not for a target repo. `SHIPPED` in `bin/conveyor` is
   untouched.

---

## Out

- Renaming `CLAUDE.md`.
- Any other edit to the north star. Its remaining Claude-era vocabulary
  (`.prompt` files elsewhere, `approve!`) describes the earlier design's
  intent and is labelled as such by the document's own framing.
- Touching PRD B.1 line 274.

---

## Implementation

- `docs/agent-orchestration-north-star.md`: decision 1.
- `AGENTS.md` (new): decision 2.

## Tests

None new. `rg -n "append-system-prompt-file" docs/` should return only the
PRD B.1 line afterwards.

## Verification

Open the repository in Cursor; confirm the agent surfaces `AGENTS.md` and, via
it, `CLAUDE.md`.

## Tag

Any time. Bundle with whichever of the other plans lands first.
