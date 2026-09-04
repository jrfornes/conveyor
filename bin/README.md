# Conveyor scripts

## Language decision

**Python ≥ 3.10, standard library only.** Every script in `bin/` and `test/` is
Python; the `.sh` names are kept because agents are told to call
`handoff.sh` by that name (IMPLEMENT.md). Bash was rejected because macOS
ships Bash 3.2, and because header parsing, SHA-256 fingerprints, TSV rewrites
under locks, and JSON log handling are all several times longer and easier to
get subtly wrong in shell. Python 3 is present on macOS (Xcode command line
tools) and every Linux distribution, so there is still no build step and no
dependency to install.

Atomic renames are `os.rename` / `os.replace`; locks are `mkdir` directories
with a `pid` file (protocol §8.2). `flock(1)` is not used.

## Install

```
git clone <this repo> ~/conveyor
export PATH="$HOME/conveyor/bin:$PATH"     # conveyor, handoff.sh, role-loop.sh, merge.sh
```

`conveyor start` does **not** copy scripts into worktrees: each role loop
prepends this `bin/` directory to `PATH` for the agent process, so an agent
can run `handoff.sh ./tmp/handoff.txt` from its worktree root. That means the
conveyor checkout above only needs to exist once per machine, on `PATH`; you
never copy `bin/` or `lib/` into a target project.

To point Conveyor at a project, run `conveyor init [<path>]` (default: cwd)
from inside a git checkout. It automates `docs/runbook.md` §3 step 1:
copies `constitution.md`, `constitution/`, `roles/`, `conveyor.conf.example`,
and (only if missing) `project.md`, creates `conveyor.conf` from the example
if missing, creates `tasks/`, and appends the required `.gitignore` entries.
It is safe to re-run: files the operator owns once they exist (`project.md`,
`conveyor.conf`, anything under `tasks/`) are never overwritten; the
shipped-as-is files are refreshed every time so they always match this
conveyor checkout. It never commits — review and commit yourself. Then edit
`project.md` and the two model names in `conveyor.conf`, and `conveyor start`.

## Layout

```
bin/conveyor          operator CLI: init [<path>] | start | stop [--now] | task <name> [--delete] | status | log | resume
bin/handoff.sh        validator + audit gate (protocol §4–5)
bin/role-loop.sh      per-role loop (protocol §6); --once for tests
bin/merge.sh          protocol §7
bin/hooks/commit-msg  byline hook, copied into the shared .git/hooks by conveyor start
lib/conveyor/         util (timestamps, atomic write, locks), config, layout, handoff (format),
                      board (TSV), queue (merge, sweep, park, dequeue, seq)
test/fake-agent       protocol §11 fixture
test/                 test_inv01..12_*.py (one per §9 invariant), test_m0..m4_*.py, test_errors.py
```

## Running the tests

```
cd test && python3 -m unittest discover -p 'test_*.py'
```

The suite runs entirely with the fake agent. Two test-only hooks exist in
production code, both inert unless the environment variable is set:
`CONVEYOR_CRASH_AT=<label>:<marker>` kills a loop once at a named step boundary
(for invariant 11), and `CONVEYOR_LOCK_TIMEOUT` shortens the 30 s lock wait
(for `E_LOCK`).

## Ambiguities resolved

Where the protocol left a choice, the refusing option was taken.

1. **`E_TASK_MISMATCH` ordering.** §4.1 lists it as a precondition, but it
   needs the draft's `task` header, so it is checked right after the draft's
   headers are parsed and found complete (§4.2 step 3) and before recipient
   and route checks.
2. **`max_retries` applies to every role's loop** using that role's own
   value (default 3). The coder's loop is always the first to see a new
   `retry_count`, so in practice it is the one that parks.
3. **Done-merge conflict.** §6.5 says "park + leave in outbox", §6.10 says
   rename the outbox file into `needs-human/`. The latter is implemented: the
   file moves to `needs-human/<task>/item.handoff` (otherwise every sweep would
   retry the conflicting merge). `conveyor resume <task>` for an item whose
   `to` is `done` puts it back in the sender's `outbox/`; the sender's loop
   sweeps its outbox on every iteration, so it is delivered without a second
   process touching that directory.
4. **`conveyor start` on an existing worktree never resets it.** Running
   `git worktree add --force -B ... HEAD` again would discard the role's
   branch. The worktree is created only when `.worktrees/<role>/.git` is
   absent; rules file, `tmp/`, hook, and queue directories are refreshed every
   time.
5. **Recovery re-run vs. an outbox file that already exists.** When a loop
   restarts with an item in `in_process/` and exactly one valid file already in
   `outbox/`, the agent is *not* run again; the item is completed and swept.
   This is what makes a crash between the agent's `OK` and the loop's rename
   harmless (invariant 11).
6. **Missing task file after merge** (`tasks/<task>.md` not at the worktree
   HEAD) parks with reason `no-task-file` rather than running an agent with an
   empty task.
7. **`conveyor stop --now`** sends `TERM` to the loop, which terminates the
   agent and exits with the item left in `in_process/` and its `attempt`
   header unchanged; the next `conveyor start` re-runs that attempt. Logs are
   opened in append mode so the re-run does not overwrite the killed run's log.
8. **Ceilings after `conveyor resume`.** Counters are never reset (§6.10), so a
   task parked for `max-retries` or `max-minutes` parks again on resume unless
   the operator raises the ceiling in `conveyor.conf` or deletes and recreates
   the task (`conveyor task --delete <name>`, then `conveyor task <name>`).
9. **`conveyor task --delete`** refuses while the task's lane is a role;
   deleting a row only makes sense for `done` or `needs-human` tasks.
10. **Last validator output for retries (§6.8 item 4)** is found by scanning the
    previous run's stream-json log for the last `E_...: ` or `AUDIT_REQUIRED: `
    line; agent prose is never interpreted.
11. **`conveyor status`** follows runbook §6 exactly and appends
    `last: <task>` (the most recent completed item, PRD OBS-1) at the end of
    each role line.
12. **Dirty means dirty.** `E_DIRTY` triggers on untracked files too, because
    `git status --porcelain` reports them and the constitution says scratch
    belongs only in the ignored `./tmp/`.

13. **`E_NO_CHANGE` is checked before `E_NO_BYLINE`** (§4.3 lists them the
    other way round). When HEAD is still the inbound commit its byline is
    necessarily another role's, and the `E_NO_BYLINE` repair (`git commit
    --amend`) would rewrite that inbound commit. Telling the agent to commit
    its work is the right instruction.
14. **Multiple handoffs in `outbox/`** park the item and move every outbox file
    to `needs-human/<task>/outbox-N.handoff`, so none of them is delivered by
    the next sweep. The operator deletes or resubmits them by hand.

## Not built (PRD Appendix B)

Nothing from Appendix B is implemented. Hook points are marked with a single
`# later: B.x` comment where a future change would go.
