# Cursor CLI runtime — the loop owes nothing to the operator's CLI config

**Status:** built — live verification (steps 1–4) against a real `cursor-agent`
outstanding. Nothing here changes the protocol. It changes the fixed
argument list the loop passes to `cursor-agent`, what `conveyor start`'s smoke
test proves, and one runbook section.

**Job:** Conveyor was designed against Claude Code and switched to Cursor CLI
without re-asking what the new agent does on its own initiative. Three things
Cursor does by default can make a live run fail before the first handoff, and
today whether they fire depends on a file Conveyor has never heard of:
`~/.cursor/cli-config.json`. The loop must pass every flag it needs to run
correctly, and `conveyor start` must prove the handoff path works on this
machine before a task is ever dequeued.

Not a second backend (PRD B.1), not a permissions system, not a wrapper around
Cursor's own configuration.

---

## Why

### The launch command is right; the environment around it is unexamined

`run_agent` (`bin/role-loop.sh`) launches
`cursor-agent -p --force --model <m> --output-format stream-json [--resume <id>] "<prompt>"`.
Every flag exists with that meaning in the current CLI reference, `session_id`
is on every stream event, and `.cursor/rules/conveyor-role.mdc` with
`alwaysApply: true` is the documented way to load rules headlessly. The switch
itself landed.

What did not land is any account of three Cursor behaviours that Claude Code
did not have:

| Behaviour | Where it is decided today | What it does to a run |
| --- | --- | --- |
| **Sandbox.** Since Cursor 3.5, "Run in Sandbox" is folded into the allowlist approval mode with sandboxing on. A sandboxed shell command has read/write inside the workspace only; `.git/hooks` and `.git/config` are protected paths; network is off by default. | `sandbox.mode` in `~/.cursor/cli-config.json`, or `--sandbox enabled\|disabled` | The agent's workspace is `.worktrees/<role>`. `handoff.sh` writes to `$CONVEYOR_ROOT/.conveyor/roles/<role>/outbox/` — the parent. `git commit` writes through `.git/worktrees/<role>` and runs `commit-msg` from the shared `.git/hooks`. Any of those blocked means no handoff, or a commit with no byline. The agent sees a permission failure, tries something else, and the run ends with an empty outbox: `--resume` retry, then `max-attempts`. The park reason names none of this. |
| **Commit attribution.** `attribution.attributeCommitsToAgent` defaults to `true`: agent commits get a `Made with Cursor` trailer. | `~/.cursor/cli-config.json` only; no flag | `bin/hooks/commit-msg` appends `By <role>.` when the last non-empty line is not already the byline. `handoff.sh` rejects any HEAD whose last line is not the byline (`E_NO_BYLINE`, protocol §7.4, invariant 10). If Cursor adds its trailer to the message before `git commit` runs, the hook appends the byline after it and every commit is fine. If Cursor amends after the hook, every handoff fails `E_NO_BYLINE`. Which one it is has not been observed. |
| **Workspace trust.** `--trust`: "trust the workspace without prompting (headless mode only)". | `agent_args` in `conveyor.conf` — `config.save()` writes `agent_args = --trust` into a fresh `[global]`, but `conveyor.conf.example` does not carry it, so a hand-copied config has no `--trust` at all | Each `.worktrees/<role>` is a fresh directory. A trust prompt in print mode has no one to answer it. |

The common shape: Conveyor's correctness depends on a per-user file outside
the repository, and the failure surfaces two ceilings later under a reason
that points at the agent, not the environment.

### There is already a smoke test; it proves the wrong thing

`cmd_start` (`bin/conveyor`) runs `cursor-agent -p --force --model <m> "reply
with the word ok"` in each worktree and dies on nonzero exit. That proves the
binary runs, the model exists, and the login works. It does not touch a file
outside the worktree and it does not commit, so it passes on a machine where
the first real task cannot hand off. A smoke test that does not exercise the
two writes the pipeline lives on is not a smoke test of the pipeline.

---

## Locked decisions

1. **The fixed argument list is Conveyor's, not the operator's.** `run_agent`
   and the smoke test pass, in this order, before `agent_args` and the role's
   own `cli-args`:

   ```
   -p --force --trust --sandbox disabled --model <model> --output-format stream-json
   ```

   `--trust` moves from the default `agent_args` into the fixed list.
   `config.save()` stops writing `agent_args = --trust`; a config that still
   carries it keeps working because the command assembler drops any
   `agent_args` / `cli-args` token that is already in the fixed list (exact
   match on the flag, and on the value for `--sandbox`). Nothing else in
   `agent_args` is touched: it is still the operator's escape hatch.

2. **`--sandbox disabled`, not a `sandbox.json`.** The alternative — a
   `.cursor/sandbox.json` with `additionalReadwritePaths` — would need the
   absolute repo root in a per-worktree file, would not unprotect `.git/hooks`,
   and would still be overridable by the user-level file. Conveyor already
   isolates roles by worktree and branch; the sandbox adds nothing the pipeline
   relies on and removes two writes it does. Operators who want the sandbox back
   for a role can add `--sandbox enabled` to that role's `cli-args`; the
   assembler's dedupe is exact-match, so the later token wins in Cursor's own
   parsing. The runbook says what will then break.

3. **The byline rule does not bend.** `handoff.sh` keeps requiring `By <role>.`
   as the last line (invariant 10). Conveyor does not learn to tolerate a
   trailing `Made with Cursor` trailer — a byline that is not last is a byline
   another tool can push off the end. The fix for a misplaced trailer is the
   operator's `attribution.attributeCommitsToAgent: false`, and `conveyor
   start` is what tells them.

4. **The smoke test proves the handoff path, per role, before any loop starts.**
   The smoke prompt asks the agent to do three things in one run, and `start`
   checks each from outside:

   - reply `ok` (as today);
   - write the word `ok` to `$CONVEYOR_ROOT/tmp/smoke-<role>.txt` — a write
     outside the workspace. Not under `.conveyor/`: the constitution tells
     agents never to create files there, and a smoke that asks them to break
     a rule proves nothing. Root `tmp/` is already gitignored and belongs to
     no writer in protocol §2.3; `start` creates it;
   - make one empty commit on the role branch with message `conveyor smoke`.

   `start` records the branch tip before the run. After it: `smoke-<role>.txt` must
   contain `ok`; HEAD must be exactly one commit past the recorded tip; the
   last non-empty line of that commit's message must be `By <role>.`. Then
   `start` resets the branch to the recorded tip (`git reset -q --hard
   <tip>`), so the smoke leaves no commit behind. If HEAD moved by anything
   other than exactly one commit, `start` refuses without resetting and
   prints the two SHAs — it never guesses what to throw away.

   Each failure has its own message with repair text:

   | Check | Message |
   | --- | --- |
   | probe file missing or wrong | `smoke test: <role> could not write outside its worktree; the Cursor sandbox is on. Conveyor passes --sandbox disabled; check ~/.cursor/cli-config.json sandbox.mode and any --sandbox in cli-args` |
   | no commit | `smoke test: <role> did not commit; check ~/.cursor/cli-config.json approvalMode and permissions.deny for Shell(git)` |
   | byline not last | `smoke test: <role>'s commit does not end with "By <role>."; last line is <line>. Set attribution.attributeCommitsToAgent to false in ~/.cursor/cli-config.json` |
   | HEAD moved ≠ 1 | `smoke test: conveyor-<role> moved from <tip> to <head>; expected exactly one commit. Inspect and reset by hand, then re-run conveyor start` |

   `--no-smoke` still skips the whole thing. A role whose loop is live is
   skipped, as its worktree already is.

5. **`conveyor start` prints what it resolved.** One line before the model
   check: `agent: <absolute path> (<--version output>)`. The existing
   `agent_version` warning stays. This is the answer to "which binary did it
   actually run" when `agent` and `cursor-agent` diverge on a machine.

6. **The runbook gets a "Cursor CLI configuration" subsection under §1.** It
   lists the three `~/.cursor/cli-config.json` keys that matter
   (`approvalMode`, `sandbox.mode`, `attribution.attributeCommitsToAgent`),
   states which ones Conveyor overrides by flag (`--force`, `--sandbox
   disabled`, `--trust`) and which it cannot (attribution), and names the
   smoke-test message each misconfiguration produces. `CURSOR_API_KEY` stays
   where it is.

---

## Out

- Generating or editing `~/.cursor/cli-config.json`, `<repo>/.cursor/cli.json`,
  or any `sandbox.json`. Conveyor reads none of them and writes none of them.
- Per-role permission allowlists (`Shell(...)`, `Write(...)`). `--force` is the
  contract; finer control is the operator's, via `cli-args`.
- Renaming `agent_bin` to `agent`. `cursor-agent` remains the documented name;
  decision 5 makes a divergence visible rather than silent.
- Any change to `handoff.sh`, the byline hook, or invariant 10 (decision 3).
- A second backend (PRD B.1). The fixed list is Cursor's; a backend column
  would carry its own.
- Token usage shape. That is [token-cost-on-cursor.md](token-cost-on-cursor.md).

---

## Operator surface

### `conveyor start`

```
agent: /home/me/.local/bin/cursor-agent (2026.9.2-abc123)
coder: smoke ok
reviewer: smoke ok
coder: loop started (pid 41210)
reviewer: loop started (pid 41211)
```

On a machine with the sandbox forced on:

```
agent: /home/me/.local/bin/cursor-agent (2026.9.2-abc123)
conveyor start: smoke test: coder could not write outside its worktree; the Cursor
sandbox is on. Conveyor passes --sandbox disabled; check ~/.cursor/cli-config.json
sandbox.mode and any --sandbox in cli-args
```

No loop starts. Nothing is parked, because nothing was dequeued.

### `conveyor.conf`

`agent_args` is still honoured and still documented as the escape hatch. The
example file gains a comment naming the fixed list so nobody adds `--trust`
twice wondering why it is missing.

### Runbook §1

New subsection, "Cursor CLI configuration", between the login bullet and the
`agent_version` bullet. Three keys, one table, one sentence each on what breaks.

---

## Implementation

### `bin/role-loop.sh`

- `FIXED_ARGS = ["-p", "--force", "--trust", "--sandbox", "disabled"]` as a
  module constant beside `SESSION_RE`, and a `compose_agent_cmd(agent, model,
  extra)` helper that returns the full list with `extra` deduped against the
  fixed set. `run_agent` calls it and appends `--resume` / prompt as now.
- The helper lives in the loop, not `lib/`, until the smoke test needs it too —
  then it moves to `lib/conveyor/agent.py` so both call one function. Move it
  in this plan; the smoke test is in scope.

### `lib/conveyor/agent.py`

- `FIXED_ARGS`, `compose(agent, model, extra, *, output_format=None)`.
  `resolve(agent, cwd)` returning the absolute path the way `agent_binary()`
  in the loop resolves it, so `start` and the loop agree on which file ran.
- `version(agent)` wrapping `--version` with the same 15 s timeout as
  `list_models`.

### `lib/conveyor/config.py`

- `save()` default `[global]` block drops `agent_args = --trust`. Reading is
  unchanged.

### `bin/conveyor`

- `cmd_start`: print the `agent:` line; replace the smoke block with
  `smoke_test(root, paths, cfg, role, wt, agent)` implementing decision 4.
  The pre-run tip comes from `git rev-parse HEAD` in the worktree; the reset
  uses `git reset -q --hard <tip>`; the probe file is removed after a pass so
  a stale file cannot satisfy the next run.
- The smoke prompt is one string constant, `SMOKE_PROMPT`, with `{root}` and
  `{role}` substituted. It says explicitly "do not run handoff.sh" so an agent
  that has read its rules does not try to hand off a smoke.

### `conveyor.conf.example`

- Comment above `[global]` examples: the fixed list, and that `agent_args`
  adds to it.

### Docs

- `docs/runbook.md` §1: the new subsection; §3 step 4 (`conveyor start`
  bullets) gains "prove each role can write outside its worktree and commit
  with the byline" and drops "smoke test (`cursor-agent -p "reply with the word
  ok"`)".
- `docs/conveyor-handoff-protocol.md` §6.3 (line ~642): the launch line shows
  the fixed list. No semantic change; the section already says the loop owns
  the arguments.
- `bin/README.md` Ambiguities: one entry each for decision 2 (why a flag, not
  a sandbox file) and decision 3 (why the byline does not bend).

---

## Tests

`test/fake-agent` records its argv to `$CONVEYOR_FAKE_ARGV` when set (one
token per line). New verbs: `probe-write <path> <text>`, and
`commit-amend-trailer "<text>"` which runs `git commit --amend` after the hook
has fired, so the trailer lands after the byline.

New file `test/test_cursor_runtime.py`:

1. `run_agent` argv begins with the fixed list in order and ends with the
   prompt; `--resume <id>` sits between.
2. `agent_args = --trust` in `[global]` produces exactly one `--trust`.
3. `cli-args --sandbox enabled` on a role line produces `--sandbox disabled
   ... --sandbox enabled` — the role's token survives, after the fixed one.
4. Smoke pass: fake script `probe-write`, `commit "conveyor smoke"`, `exit 0`;
   `start` prints `<role>: smoke ok`; the branch tip is unchanged afterwards;
   the probe file is gone.
5. Smoke fails on missing probe file: exact message from the decision 4 table;
   no loop pid file exists.
6. Smoke fails on no commit: exact message.
7. Smoke fails on `commit-amend-trailer`: exact message including the
   offending last line.
8. Smoke fails when the fake makes two commits: exact message with both SHAs;
   the branch is **not** reset (both commits still there).
9. `--no-smoke` runs none of it; the probe file never appears.
10. `start` prints `agent: <path> (<version>)` where `<path>` is the resolved
    fake and `<version>` is what the fake's `--version` prints.
11. `config.save()` on a config with no `[global]` writes no `agent_args`.

`test/test_start_guards.py` keeps its existing smoke-failure test; its
expected text changes to the "did not commit" message, since a fake that exits
nonzero now fails the first check that runs after the run, and the exit code
itself is reported in the same message.

---

## Verification

1. Fresh clone of a target repo, `conveyor init`, real `cursor-agent`, default
   `~/.cursor/cli-config.json`. `conveyor start`. Expect `agent:` line, two
   `smoke ok` lines, both loops started, `git log conveyor-coder -1` equal to
   `main`.
2. Set `sandbox.mode` to enabled in `cli-config.json`. `conveyor start`.
   Expect the sandbox message and no loops. This is the case the plan exists
   for; if the smoke passes here, decision 2's premise is wrong and the plan
   stops until that is understood.
3. Set `attribution.attributeCommitsToAgent: true` explicitly, run the smoke.
   Record which of the two trailer orders Cursor actually produces, in
   `bin/README.md` Ambiguities, whichever way it comes out.
4. Remove `~/.cursor/cli-config.json` entirely. `conveyor start` on a
   never-trusted worktree path. Expect no hang.
5. Run `test/` — baseline stays green.

---

## Order of work

1. `agent.compose` / `resolve` / `version` + tests 1–3, 10. Pure; nothing
   observable changes for a config that already had `--trust`.
2. Loop uses `compose`. `config.save()` change + test 11.
3. Smoke test rewrite + fake-agent verbs + tests 4–9. This is the only step
   that can turn a previously-passing `conveyor start` into a refusal, and
   that is the point.
4. Runbook, protocol launch line, `conveyor.conf.example`, README Ambiguities.
5. Verification steps 1–4 against a real CLI. Step 3's outcome is written
   down either way.

---

## Tag

Before M3. This is the plan that makes M3's first live run fail at
`conveyor start` with a sentence instead of at `max-attempts` with a shrug.
