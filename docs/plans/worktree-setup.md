# Worktree setup — a role's tree is usable the moment it exists

**Status:** planned. Not started.

**Job:** `conveyor start` creates `.worktrees/<role>` and stops. For any
project whose tests need installed dependencies, that tree cannot run its own
gates until a human installs them — once per role, again after every lockfile
change, and again for every role that merges someone else's lockfile change
mid-pipeline. One configured command, run at the two moments it is actually
needed, closes that.

Not a build system, not a package-manager integration, not a cache. Conveyor
never learns what npm is; it runs an opaque command and refuses when it fails.

---

## Why

### The tree is born empty

`ensure_worktree` (`bin/conveyor:117-143`) does four things: `git worktree add`,
`mkdir tmp/`, write `.cursor/rules/conveyor-role.mdc`, inject skills. There is
no fifth. So on a JS/Angular project, immediately after a clean
`conveyor start`:

| Role | State |
| --- | --- |
| coder | `.worktrees/coder/node_modules` does not exist. The first gate — `npm test`, `nx affected -t test` — fails on a missing module, not on the task. |
| reviewer | Same, separately. Worktrees do not share `node_modules`. |
| ticket-reviewer | Same, and pointlessly, since it only reads and writes markdown. |

The operator's workaround is to `cd` into each worktree and install by hand,
and to remember to do it again whenever the lockfile moves. Nothing in the
runbook tells them to, because nothing in the product knows.

### The half that actually bites: mid-pipeline lockfile changes

This is why the fix is not "run something at `conveyor start`".

The coder adds a dependency. The lockfile lands in the commit. The reviewer's
loop merges that commit (`bin/role-loop.sh:160-167`) into a tree whose
`node_modules` predates it, runs the project gate, and gets a missing-module
error. The reviewer is a role whose entire job is to decide `pass` or
`findings` — so a stale tree becomes **a finding against the coder's
correct work**, and the coder is sent to fix something that is not broken.
Bounded by `max_retries`, that burns the whole retry budget before parking on
a reason that names none of this.

Every layer downstream of the merge assumes the tree is coherent. Nothing
makes it so.

### There is already a precedent for the shape

`[global] integration = command: <cmd>` (`lib/conveyor/queue.py:54-86`) is an
operator-supplied shell hook: env-passed context, a captured log, park on
nonzero exit (`done-command`). This plan is the same shape at the other end of
the pipeline, and deliberately copies it rather than inventing a second idiom.

---

## Locked decisions

1. **Two config keys, both in `[global]`:**

   ```
   worktree_setup       = pnpm install --frozen-lockfile
   worktree_setup_paths = pnpm-lock.yaml package.json
   ```

   A plain command string, not `command: <cmd>` — `integration` needs that
   prefix because it has three modes (`merge` / `hold` / `command`); this has
   one. Absent or empty `worktree_setup` means the feature is entirely off and
   nothing in the run path changes.

2. **It runs at exactly two moments:** when a worktree is created or its
   dependency inputs changed at `conveyor start`, and in the role loop after a
   successful `merge.sh` when the merge changed a watched path
   (`bin/role-loop.sh:160-167`, right after `crash_point("after-merge")`).
   The second is not an optimisation — without it the feature leaves in place
   the failure that produces false findings, which is the expensive one.

3. **Change detection is a content stamp, never mtime.** A git merge rewrites
   mtimes constantly; nothing about them is evidence. The stamp is
   `sha256(<blob oid of each watched path at HEAD, in configured order>
   + the command string)`.

4. **Blob oids come from git, not from reading files:**
   `git rev-parse HEAD:<path>` per watched path, `-` when the path is not at
   HEAD. It is exact, it is one cheap call per path, and it cannot disagree
   with what was actually merged.

5. **Including the command in the hash is deliberate.** Changing
   `worktree_setup` re-runs it everywhere, which is what an operator who just
   fixed their install command expects.

6. **The stamp lives at `.conveyor/roles/<role>/setup.stamp`**, written by
   `util.atomic_write` (rename, like `seq`). Per-role state belongs in the
   per-role directory; protocol §2.3's single-writer table gains the row, with
   the writer being "whoever ran setup".

7. **`conveyor start` skips setup for a role whose loop is already live**, and
   warns instead. This is not an edge case: `conveyor start` is re-runnable
   and is routinely run against a belt that is already up, and installing into
   a tree while an agent is working in it corrupts the run. The precedent is
   already in the code, with the reason in a comment: "a live loop must
   not be moved". The committed-`.gitignore` repair at
   `bin/conveyor:605-612` warns and defers to "stop the loop and re-run
   conveyor start" whenever `loop_pid` is set. Setup does exactly the same,
   which also makes the single writer in (6) true by construction: `start`
   only ever sets up trees with no loop, and the loop only ever sets up its
   own.

8. **Failure at `conveyor start` dies; failure in the loop parks
   `setup-failed`.** Same split the smoke test and `done-command` already use.
   A half-installed tree does not get an agent run: it produces findings about
   the environment instead of the task, which is worse than stopping (PRD
   §5.5, refuse rather than guess). `conveyor resume <task>` is the way out,
   as with every other park reason.

9. **A transient registry failure parking a task is the correct outcome**, not
   a wart to smooth over with retries. The loop has no notion of infra retry
   and should not grow one here; the operator re-runs and resumes.

10. **`worktree_setup_timeout`, default 1800 s**, because a cold install on a
   large monorepo legitimately takes minutes and `gate_timeout`'s 900 is the
   wrong shape for it.

11. **This plan introduces `util.run_bounded(...)` and is the first caller.**
    One helper that runs a shell command in its own process group with a
    deadline, TERM → 10 s → KILL on the group, and writes a gate-style log
    (`exit:` / `command:` / stdout / stderr). `docs/plans/run-deadlines.md`
    needs exactly this for gates, and `integrate_done`'s currently unbounded
    `subprocess.run` (`lib/conveyor/queue.py:77`) can adopt it in one line
    later. Whichever of the two plans lands first carries the helper; the
    second one uses it.

12. **Conveyor never detects a package manager.** No npm/pnpm/yarn sniffing,
    no generated default command, no lockfile heuristics. The command is
    opaque. What ships instead is a worked example at
    `bin/hooks/npm-worktree-setup`, exactly as `bin/hooks/bitbucket-pr` ships
    for the integration hook.

14. **Roles are set up serially, in belt order.** N roles × one install is
    slow, and the fix belongs in the operator's command — a package manager
    with a shared store, or a symlink to the main checkout's tree — not in a
    parallel-execution feature inside a product whose north star forbids one.
    Progress is printed per role so the wait is legible.

15. **No per-role `worktree_setup`.** One command; it branches on
    `$CONVEYOR_ROLE` if it wants to. This is what keeps the intake worktree
    (`bin/conveyor:1079`) from installing a JS toolchain it will never use,
    without adding a knob to say so.

16. **Env handed to the hook**, cwd = the worktree:
    `CONVEYOR_ROOT`, `CONVEYOR_ROLE`, `CONVEYOR_WORKTREE`,
    `CONVEYOR_REASON` (`create` | `changed`), and `CONVEYOR_COMMIT` (the
    merged commit; empty at `conveyor start`). Mirrors the integration hook's
    contract.

17. **A dirty tree after setup is warned about, loudly, and not refused.**
    If `git status --porcelain` in the worktree is non-empty after a
    successful run, print the first five paths and the total. This is the
    three-line diagnosis of an otherwise baffling failure: `handoff.sh`
    refuses `E_DIRTY` on an uncommitted tree, the agent cannot fix it, and
    every attempt burns until `max-attempts`. Conveyor cannot guess which
    paths an operator's install creates — `check_ignores` manages only its own
    four entries (`bin/conveyor:43`) — so it says what it sees and leaves the
    `.gitignore` to the operator.

18. **Setup is not a build step.** The contract is "make dependencies
    present". Nothing stops an operator building, but the default timeout and
    the run-on-lockfile-change cadence are chosen for installs, and the docs
    say so.

---

## Out

- Package-manager detection, default commands, lockfile heuristics.
- Parallel setup across roles (locked decision 13).
- Sharing or symlinking `node_modules` between worktrees as a Conveyor
  feature — it is one line in the operator's own command.
- Bounding `integrate_done` (`queue.py:77`). One line once `run_bounded`
  exists; not this plan's tests.
- Per-role commands, per-role timeouts, per-role path lists.
- Re-running setup on `conveyor resume` — resume moves a file, it does not
  touch the tree. The next merge re-checks the stamp.
- Warming build caches, prefetching, or anything that makes the first agent
  run faster rather than possible.
- Refusing to start when an operator's install artefacts are untracked
  (locked decision 16 warns instead).

---

## Operator surface

### `conveyor start`

```
coder: setup (create) … ok, 3m41s
reviewer: setup (create) … ok, 3m38s
ticket-reviewer: setup skipped (command exited 0, nothing to do)
coder: loop started (pid 41221)
```

On a second start with nothing changed, the setup lines are absent entirely —
a matching stamp is silence, not `skipped`.

Against a belt that is already up, a role whose loop is live is left alone
(locked decision 7):

```
warning: coder's loop is running (pid 41221); skipped worktree setup.
  Stop the loop and re-run conveyor start to install into that tree.
```

On failure, `conveyor start` dies before any loop launches:

```
conveyor start: worktree setup failed for coder (exit 1)
  see .conveyor/logs/coder/setup.log
```

On a dirty tree (locked decision 16):

```
warning: .worktrees/coder is dirty after setup — node_modules/.bin/nx,
  node_modules/.package-lock.json, … (4812 paths). handoff.sh refuses a dirty
  tree (E_DIRTY); add these to the committed .gitignore on conveyor-coder.
```

### `conveyor start --no-setup`

Skips it entirely, mirroring the existing `--no-smoke` (`bin/conveyor:619`).
The stamp is not written, so the next ordinary start still runs it.

### `conveyor setup [--role <role>] [--force]`

Runs the same hook outside `start`, for the operator who fixed a lockfile by
hand or wants to re-install one role. `--force` ignores the stamp. Pure
convenience over deleting `setup.stamp`, which is the alternative it exists to
avoid documenting.

### Mid-pipeline

In `loop.log`:

```
2026-09-09T14:22:08Z  add-login: merged a1b2c3d4e5
2026-09-09T14:22:08Z  add-login: setup (changed: pnpm-lock.yaml) …
2026-09-09T14:25:44Z  add-login: setup ok, 3m36s
```

And when it fails:

```
needs-human:
  add-login   setup-failed  worktree setup exited 1 after merging a1b2c3d4e5
```

---

## Implementation

### `lib/conveyor/util.py`

```python
run_bounded(command, cwd, env, timeout, log_path) -> (returncode, timed_out, seconds)
```

`Popen(command, shell=True, cwd=…, env=…, start_new_session=True,
capture)`; `communicate(timeout=…)`; on `TimeoutExpired`, `killpg` TERM → 10 s
→ KILL, drain what arrived, return `timed_out=True`. Always writes
`log_path` in the existing gate/integration shape (`exit:`, `command:`,
`--- stdout ---`, `--- stderr ---`), with `exit: timeout` when it timed out.

`shell=True` without the new session is the bug this helper exists to not
have: a plain `timeout=` kills the shell and orphans the install.

### `lib/conveyor/setup.py` (new, small)

```python
stamp(root, wt, cfg)         -> sha256 hex over blob oids + command
read_stamp(paths, role)      -> str | ""
needs_run(paths, root, wt, cfg, role) -> (bool, reason)   # "create" | "changed" | ""
run(paths, root, wt, cfg, role, reason, commit="") -> (ok, seconds, log_path)
dirty_paths(wt, limit=5)     -> (paths, total)
```

`run` writes `.conveyor/logs/<role>/setup.log` via `run_bounded`, and on
success writes `.conveyor/roles/<role>/setup.stamp`. The stamp is written
**only** after exit 0: a failed install must not look done.

### `lib/conveyor/config.py`

`worktree_setup` (string, default `""`), `worktree_setup_paths`
(`shlex.split`, default `[]`), `worktree_setup_timeout` (non-negative int,
default 1800, `0` = unbounded) parsed alongside `poll_seconds`. None are
emitted by `config.save` unless already present, so untouched configs stay
byte-identical and `presets.resolve` does not flip to `custom`.

A `worktree_setup_paths` with no `worktree_setup` is a `ConfigError` with
repair text — it means the operator expected something to run.

### `bin/conveyor`

- `cmd_start`: after `ensure_committed_gitignore`, before the smoke test, call
  `setup.needs_run` / `setup.run` per role; die on failure; warn on
  `dirty_paths`. Honour `--no-setup`.
- `cmd_intake`: same, around the `ensure_worktree` at `:1079`.
- `cmd_setup` + a `"setup"` entry in `COMMANDS`.

### `bin/role-loop.sh`

In `process()`, immediately after `crash_point("after-merge")` (`:167`): if
`setup.needs_run` says `changed`, run it; on failure
`park("setup-failed", …)`. Before the ceiling checks, so a stale tree never
reaches an agent.

The setup run happens **inside** the item's `max_minutes` budget, and that is
correct: an install that eats the task's whole budget is a real problem the
operator should see as `max-minutes`, not something to exempt.

### `bin/hooks/npm-worktree-setup` (new)

Worked example in the style of `bin/hooks/bitbucket-pr`: a docstring showing
the `conveyor.conf` wiring, branching on `$CONVEYOR_ROLE` to skip
`ticket-reviewer`, `npm ci` on `create` and `npm install` on `changed`, and a
comment naming the two cheap alternatives (a pnpm shared store; symlinking the
main checkout's `node_modules`) with their trade-offs.

### Docs

- Protocol: §2.3 single-writer row for `setup.stamp`; §6.3 the post-merge
  setup step and `setup-failed`; §6.10 park-reason list.
- Runbook §3 (project setup): the two keys, the `.gitignore` requirement, and
  the fact that the hook re-runs on lockfile changes. §7: `setup-failed`.
- `conveyor.conf.example`: commented `worktree_setup` block.
- `bin/README.md` Ambiguities: content stamp over mtime, command in the hash,
  stamp written only on success, dirty tree warns rather than refuses.
- `CLAUDE.md`: `setup` in the CLI verb list; `setup-failed` in the ceilings /
  park-reason list; `lib/conveyor/setup.py` in the layout.
- PRD: nothing. Worktrees are §3 scope; this is them working.

---

## Tests

`test/test_worktree_setup.py` (new — the fake agent is not involved in most of
these; a `touch`/`sh -c` command is enough):

1. No `worktree_setup` → nothing runs, no stamp file, `conveyor start`
   output byte-identical to today.
2. `conveyor start` runs the command once per role, cwd is the worktree, env
   carries `CONVEYOR_ROLE` / `CONVEYOR_REASON=create`.
3. Second `conveyor start`, nothing changed → does **not** run again, and
   prints no setup line.
4. Watched path's content changes on the branch → next start runs with
   `CONVEYOR_REASON=changed`.
5. Changing `worktree_setup` itself re-runs (locked decision 5).
6. A watched path absent at HEAD hashes as `-` and does not crash; adding it
   later counts as a change.
7. Failure at start: `conveyor start` exits non-zero, **no loop is launched**,
   no stamp is written, `setup.log` has the output.
8. `--no-setup` skips and writes no stamp; the following plain start runs it.
9. `conveyor setup --role coder --force` runs despite a matching stamp.
10. `worktree_setup_paths` without `worktree_setup` → `ConfigError` with its
    repair text.
11. Timeout: a sleeping command with `worktree_setup_timeout=1` is killed,
    `setup.log` first line is `exit: timeout`, and the command's own child is
    gone (the `shell=True` group case).
12. Dirty-tree warning fires when the command creates an unignored file, names
    at most five paths plus a total, and does **not** fail the start.
13. A role with a live loop is skipped at `conveyor start` with the warning,
    its stamp is unchanged, and the command did not run in that worktree
    (locked decision 7) — the tree an agent is working in is never installed
    into from underneath it.

`test/test_m4_ceilings.py` or `test_pipeline.py` (the mid-pipeline half — the
one that matters):

14. Coder's commit changes a watched path → the reviewer's loop runs setup
    after `merge.sh`, with `CONVEYOR_REASON=changed` and `CONVEYOR_COMMIT` set
    to the merged commit.
15. That setup failing parks `setup-failed` with the item in
    `needs-human/<task>/item.handoff`, board lane `needs-human`, and **no
    agent run** — assert no new `.jsonl` appeared.
16. `conveyor resume` after a `setup-failed` park behaves like every other
    reason: attempt reset to 1, counters preserved.
17. A merge that touches no watched path does not re-run setup.

`test/test_config_inbox.py` / `test_presets.py`:

18. The three keys round-trip; a config without them is byte-identical after
    `config.save` and still resolves to its preset slug.

`test/test_inv03_rename_only.py`:

19. `setup.stamp` is written by rename and never appended to.

---

## Verification

```
cd test && python3 -m unittest discover -p 'test_*.py'
```

Then against a real NX/Angular repo, which is the case this exists for and the
only one that proves it:

1. `worktree_setup = pnpm install --frozen-lockfile`,
   `worktree_setup_paths = pnpm-lock.yaml`. `conveyor start` on a clean clone:
   both worktrees end with a populated `node_modules`, and
   `nx affected -t test` runs in each **without a hand install**.
2. `git status --porcelain` in each worktree is empty. If it is not, test 12's
   warning fired and the `.gitignore` guidance in runbook §3 is what needs
   fixing.
3. A task whose coder step adds a dependency: the reviewer merges, setup runs
   for `changed`, and the reviewer's gate passes. Before this plan that gate
   fails on a missing module and the reviewer sends findings against correct
   work — reproduce that first, so the fix is measured against the real
   failure.
4. Second `conveyor start`: no setup runs, startup is as fast as today.
5. Time it. If N roles × a cold install is intolerable, that is locked
   decision 12 working as designed — switch the command to a shared store or a
   symlink and time it again. Record both numbers in the runbook so the next
   operator does not have to discover them.

---

## Order of work

1. `util.run_bounded` + its own tests (test 11's mechanics). Nothing else
   depends on config parsing.
2. `config.py` keys + tests 10, 17.
3. `lib/conveyor/setup.py` (stamp, needs_run, run, dirty_paths) + tests 1–6.
4. `cmd_start` wiring, `--no-setup`, the dirty warning + tests 7, 8, 12.
5. `conveyor setup` + test 9.
6. Role-loop post-merge hook + `setup-failed` + tests 13–16.
7. `bin/hooks/npm-worktree-setup`, protocol §2.3/§6.3/§6.10, runbook §3/§7,
   `conveyor.conf.example`, `bin/README.md`, `CLAUDE.md`.

Steps 1–5 are inert for every repo that sets no `worktree_setup` and can land
together. Step 6 introduces a new park reason and touches the live run path —
its own commit, with the mid-pipeline test written before the code.

---

## Tag

Unreleased, after `v0.4.0-rc1`. Independent of `docs/plans/run-deadlines.md`
except for `run_bounded` (locked decision 11), and independent of
`docs/plans/token-cost.md` entirely. **Land it before pointing Conveyor at any
project with a dependency install**, which in practice means before the NX
target — M3 on a small stdlib repo does not need it.
