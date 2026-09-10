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
and (only if missing) `project.md` and `intake/`, creates `conveyor.conf` from the example
if missing, creates `tasks/`, and appends the required `.gitignore` entries.
It is safe to re-run: files the operator owns once they exist (`project.md`,
`intake/`, `conveyor.conf`, anything under `tasks/`) are never overwritten; the
shipped-as-is files are refreshed every time so they always match this
conveyor checkout. `roles/ticket-reviewer.md` is moved to `intake/` on first
re-init of a pre-Stage-4 repo. It never commits — review and commit yourself. Then edit
`project.md` and the two model names in `conveyor.conf`, and `conveyor start`.

## Layout

```
bin/conveyor          operator CLI: init | uninstall | start | stop | setup | task | status | log | resume
                      | import [--refresh/--replace] | intake [config|jira|<id>] | inbox list/show/approve/skip/attachments | start-task
                      | approve | reject | workflow …
bin/conveyor-ui       optional localhost cockpit (`--demo` throwaway fixture)
bin/handoff.sh        validator + audit gate (protocol §4–5)
bin/role-loop.sh      per-role loop (protocol §6); --once for tests
bin/merge.sh          protocol §7
bin/hooks/commit-msg  byline hook, copied into the shared .git/hooks by conveyor start
bin/hooks/npm-worktree-setup  worked example for [global] worktree_setup (copy and edit)
lib/conveyor/         util (timestamps, atomic write, locks, bounded commands), config, layout,
                      handoff (format), board (TSV), queue (merge, sweep, park, dequeue, seq),
                      setup (worktree dependency setup), intake, jira,
                      presets, workflows, inbox, adapters, agent
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
15. **Intake is a one-shot role** (`ticket-reviewer`) not listed in the coding
    `conveyor.conf` order. `conveyor start` does not launch it. The route
    `ticket-reviewer → operator, ready` is added by the implementation, not
    derived from coding order. After sweep, grade.md / proposed-task.md are
    copied from the commit into `.conveyor/inbox/<id>/`.
16. **Findings go to the penultimate coding role** (reviewer → coder in the default Review
    belt; same rule for longer pipelines), never to a gated first role.
17. **Gated role `ready` is held** in `.conveyor/approvals/pending/` when `cfg.gate_role()`
    is set (explicit `gate <role>` line, or — for backward compatibility — the first role
    when the pipeline has exactly three coding roles). Two-role Review belt has no hold unless
    the operator adds `gate`. `conveyor approve` / `reject` are the only ways out; reject
    preserves `task_id` and `audit_count`. Switching belts is
    `conveyor workflow activate <slug>`.
18. **Inbox status is a field in `meta.txt`** (lock + rewrite + rename). The
    item directory is not renamed on status change because the id is stable.
19. **`conveyor intake` resets the ticket-reviewer worktree to main HEAD**
    before each one-shot. Leftover `grade.md` / `proposed-task.md` from a
    previous intake must not merge-conflict with the current main tip; the
    payload is copied into `.conveyor/inbox/<id>/` before the next reset.

20. **`--delete` takes the park entry with the row.** `needs-human/` is
    enumerated from the filesystem, not the board, so deleting a parked task's
    row alone left a directory the strip still showed and `resume` would act
    on — renaming the handoff into a live queue and then failing on the missing
    row. `conveyor task --delete` now removes `needs-human/<task>/` in the same
    call, and `conveyor resume` refuses (before any rename) when the park
    directory has no board row. `tasks/<name>.md` and `sent/` are untouched:
    protocol §8.1 treats `--delete` as a board-row operation.
21. **`conveyor workflow activate` refuses while a loop is live** and never
    removes a worktree itself. Rewriting `conveyor.conf` mid-run would strand a
    loop on a role the new order drops, and `conveyor stop` iterates the *new*
    role list, so it could not stop it. Activate reports a dropped role's
    leftovers and leaves them; `conveyor start` is where worktrees are
    reconciled (invariant 25).

    *Corrected 2026-09-04:* this entry previously claimed `git worktree remove`
    "would take the role's `conveyor-<role>` branch with it". It does not —
    `worktree remove` deletes the working directory and git's admin files only,
    and branch deletion is `git branch -d/-D`, which Conveyor never runs.

22. **The design handoff's `queues/<role>/held/` is not built.** The UI design
    package (`design_handoff_conveyor/`) proposed a new per-queue `held/`
    directory for the spec-approval hold. Protocol §2.1 already fixes that hold
    at `.conveyor/approvals/pending/`, and it is implemented. Adding `held/`
    would create a second, parallel queue layout for the same state, so the
    design was reconciled to the protocol instead: `held` is a **UI label** for
    `approvals/pending/`, never a path segment. Same reasoning retired the
    design's `queues/`, `done/` and `inbox/<key>.md` paths.
23. **Workflows are saved presets over `conveyor.conf`, not a replacement for
    it.** The design wanted `.conveyor/workflows/<slug>.json` to be the workflow
    config. But `conveyor.conf` is what the role loops and `handoff.sh` read,
    and `config.routes()` derives the permitted `(from, to, verdict)` triples
    from its role order — the thing every invariant test leans on. So the
    presets are a layer above it: `.conveyor/workflows/<slug>.json` holds
    `{name, description, roles, gate}`, `.conveyor/active` names the applied
    preset, and "make active" regenerates `conveyor.conf` through
    `config.save()`. The protocol surface does not move. If `conveyor.conf` is
    hand-edited away from its preset, `.conveyor/active` is stale and the UI
    reports the real chain rather than reconciling.

24. **The gate is declared, not inferred from role count.** `conveyor.conf`
    takes an optional `gate <role>` line; the gated role's outbound `ready` is
    held in `.conveyor/approvals/pending/`. The gated role may not be the last
    one — its handoff goes to `done`, not to another role. Pipelines may now be
    any length ≥ 1; a one-role pipeline has no `findings` route, because there
    is no penultimate role to bounce to. **Backward compatibility:** a
    three-role pipeline with no `gate` line gates its first role, reproducing
    the old three-pack hold, so configs on disk keep working. Every other role
    count defaults to no gate. `config.save()` writes the resolved gate
    explicitly so a saved file never leans on that inference. Protocol §3.2 was
    updated to state the general rule rather than the three-pack special case.

25. **Workflows are saved presets over `conveyor.conf`.**
    `.conveyor/workflows/<slug>.json` holds `{name, description, roles, gate}`
    and `.conveyor/active` names the applied one; `conveyor workflow activate`
    regenerates `conveyor.conf` through `config.save()`. The slug is the
    filename and nothing else — allocated once at create, never moved on
    rename — so `.conveyor/active` can never dangle. `presets.resolve()` never
    trusts the marker blindly: a preset whose `(roles, gate)` actually match
    `conveyor.conf` wins, which self-heals a marker left stale by a crash
    between activate's two writes. Activate writes `conveyor.conf` first and
    the marker second, so a crash leaves the pipeline correct and only the
    cosmetic marker wrong.
26. **`gate none` is an explicit "no gate".** A three-role pipeline with no
    `gate` line still gates its first role (invariant 24's backward
    compatibility), which made "three roles, deliberately ungated" impossible
    to express — and the shipped `Spec, no gate` workflow needs exactly that.
    `gate none` says it outright, `none` is reserved so no role can be named
    it, and `config.save()` now always writes one form or the other, so only
    hand-written legacy files rely on the inference.
27. **The workflow HTTP API is POST-only**, against the design spec's
    `GET/PUT/DELETE /api/workflows/:slug` + `PUT /api/active`. `ui/server/httpd.py`
    implements only `do_GET`/`do_POST`; each new verb would need its own copy of
    the exception-to-status mapping, a widened CORS allow-list, and new test
    helpers, for no user-visible gain on a localhost single-operator UI. Every
    existing mutation is already POST-plus-suffix, deletion included
    (`POST /api/tasks/delete`). So: `POST /api/workflows`, `/api/workflows/save`,
    `/api/workflows/delete`, `/api/active`.
28. **Workflow presets are per-checkout, never shared.** `.conveyor/` is in
    `GITIGNORE`, so the workflows a teammate saves do not travel with the repo.
    That follows from the storage decision, but it surprises people.

29. **Intake is not a coding role.** `ticket-reviewer` lives under `intake/`,
    not `roles/`. It never appears in `cfg.names()`, is not started by
    `conveyor start`, and is unaffected by workflow switch. The old
    `roles/ticket-reviewer.md` is migrated by `conveyor init` (moved if it is
    the only copy; deleted if `intake/` already won and the old file is
    committed; refused if the old file is dirty and differs).
30. **`[inbox]` is written surgically.** `config.save()` renormalizes every
    role line and always emits a resolved `gate`, which would flip
    `presets.resolve()` from `active` to `custom`. Intake model/ceiling
    edits go through `config.write_inbox()` and do not require a loop stop.
    `0` is a legal ceiling (`None` is the "use default" sentinel; `x or 30`
    would rewrite an explicit `0`).
31. **Parked intake is unresumable.** `queue.park` swallows the missing board
    row; `conveyor resume` refuses without one. After a one-shot park,
    `cmd_intake` clears `needs-human/<id>/`, resets the item to `imported`,
    and dies with the reason.
32. **Jira Cloud auth is Basic, not Bearer.** `.conveyor/local/jira.json`
    holds `{site, email, token}` (mode 600). Email can only come from that
    file; `conveyor.conf.example` points operators there, not at
    `jira_base` / `jira_token_env` (those `[inbox]` keys remain fallbacks
    only). A repo with only `jira_base` + `jira_token_env` no longer fetches
    a body — Bearer never worked against Cloud. `conveyor import --source
    jira` refuses when site, email, or token is missing; HTTP fetch failures
    print `failed <KEY>  <status> <reason>` and do not create an inbox row;
    a fetched ticket with no spec text (empty description, no comments or
    allowlisted custom fields) creates a row and prints a separate
    empty-description notice (not a credentials hint). The token is
    never put on argv or in an HTTP response. In the cockpit, **Test
    connection** is write-then-check (same as CLI `--test`), not a probe of
    unsaved form fields; an empty POST tests the saved file only. Site URL
    must be `https://…` (`http://127.0.0.1` / `localhost` only for local
    Jira); bare hosts and `file:` are refused; a pasted `/browse/KEY` URL
    is canonicalized to the site root; cross-host redirects are not followed
    (Basic auth stays on the configured host).
33. **`config` and `jira` are reserved inbox ids** so `conveyor intake config`
    is never an item lookup. An imported ticket titled "jira" becomes `jira-2`.
34. **The intake HTTP API is POST-only**, same as roles/project/runtime, against
    the design spec's GET/PUT. `POST /api/intake/config` is 200 while loops
    run (not 409). Existing `POST /api/intake` (run the one-shot) is unchanged.
35. **Project gates live in `project.md`.** Either legacy `## Test command`
    only (implicit gate `test` on every belt `ready`/`pass`) or `## Gates` +
    `## Required on` — never both; missing Required-on with Gates is
    `E_GATE_PARSE`. `handoff.sh` reads the worktree copy; `conveyor start`
    validates the main checkout. Empty command skips that gate. Substitutions:
    `{inbound}`, `{head}` only. Log:
    `.conveyor/logs/gates/<role>-<task>-<commit>-<name>.txt`.
    `conveyor gate list|run` uses the same argv table.
36. **Skill assignment is not exclusive isolation.** `roles/<name>.skills`
    guarantees assigned skills are copied into the worktree and listed in
    `conveyor-role.mdc`; it does not hide other skill trees already tracked
    in git and merged into the worktree under `.agents/skills/` or
    `.cursor/skills/`. When the same name exists in both repo-root catalogs,
    `.agents/skills` wins for discovery, validation, and injection.
37. **`--refresh` / `--replace` only touch `imported` items.** After Grade the
    graded body is the source; Improve or re-Grade instead. `--refresh` also
    requires `source == jira` and a real `external_id`. Re-importing the same
    Jira key still allocates `proj-9-2` (never a silent overwrite) and prints
    a notice pointing at `conveyor import --refresh proj-9`.
38. **Jira import body is spec text, not metadata.** `GET /issue/{key}?expand=names`
    flattens the ADF description (lists, links, mentions, headings, code; no
    HTML or images), then appends `customfield_*` whose `names[id]` matches
    `(?i)acceptance|criteri|repro|expected|user story` and the embedded
    `fields.comment.comments` list (no extra `/comment` pagination). If that
    spec text is blank, `source.md` stays empty even when summary/type/status
    exist — metadata-only is not a body, so the empty-description notice
    still fires and Grade stays skipped, **unless** the ticket has attachments.
    Import writes `attachments.json` (list only) and a trailing
    `## Conveyor attachments` footer; default-selected small images
    (`image/png|jpeg|jpg|gif|webp` under 10 MB) are marked selected. Video,
    audio, and archives are listed but never downloaded (`--select` refused;
    watch video in Jira). Bytes are fetched on `conveyor intake` into
    `.conveyor/inbox/<id>/attachments/` and copied to the intake worktree
    `tmp/attachments/` for ticket-reviewer only. Cloud attachment content
    is requested with `redirect=false` so the file stays on the Jira origin
    (the default is 303 to the media host); a single cross-host 3xx is still
    followed without Authorization. `urlopen` never follows cross-host
    (Basic auth stays on the configured host). `conveyor inbox attachments
    <id> [--select ids|none]` lists or rewrites the selection. Refresh
    updates the list and keeps `selected` for ids that still exist. OCR,
    PDF-to-text, and video transcription are out.
39. **`conveyor uninstall` is runtime-only by default.** `--yes` is required;
    without it the command prints what would be removed and exits nonzero.
    Default removes worktrees, local `conveyor-*` branches, `.conveyor/`, and
    the byline hook only when its contents match the shipped copy. `--bundle`
    also deletes init files. Refused when run from the conveyor source checkout.
40. **The `Grade:` line is the only verdict.** `inbox.parse_grade` matches
    `Grade: Ready|Gaps|Unusable` anchored at the start of a line (leading `#`,
    `*`, `_`, whitespace tolerated) and takes the first hit. It previously
    searched anywhere in the first 30 lines, so an ordinary gap — "acceptance
    criteria are not ready" — graded the ticket `Ready`. Reading a decision out
    of prose is exactly what the outbox rule forbids. A `grade.md` with no such
    line is `unparsed`; no `grade.md` is `-`. The markdown tolerance is
    deliberate: `intake/` is operator-owned and `conveyor init` never re-copies
    it, so already-initialized repos keep parsing without a migration.
41. **`inbox approve` refuses a grade it cannot trust.** `Ready` and `Gaps`
    approve; `Unusable`, `unparsed`, and `-` each die with their own repair
    line and need `--force`. The grade used to be advisory — an ungraded ticket
    could go straight into `tasks/`. Approve still does not enqueue;
    `start-task` does.
42. **`conveyor intake` refuses `ready` and `started`.** Those are the two
    statuses whose `tasks/<name>.md` is committed, so a re-grade would
    desynchronize the inbox from `tasks/` and `board.tsv`. `grading` and
    `improving` stay re-runnable — the loop-lock preflight covers a live run,
    and a status left by a crashed one must not strand the item. `skipped`
    stays re-gradable, since un-skipping is ordinary.
43. **`comments.txt` is consumed exactly once.** A successful one-shot renames
    it to `comments-applied.txt`. It used to be left in place, so the next
    grade of the same item silently replayed feedback the reviewer had already
    acted on. A rename, not a delete: the text stays readable and the protocol's
    rename discipline holds.
44. **`conveyor status` omits `inbox:` when there are no items**, so a repo that
    never ran `conveyor import` prints exactly the runbook §6 sample and the M4
    format assertion keeps holding. `inbox list` and `inbox show` are pure
    reads: unlike the other `inbox` verbs they do not call `paths.ensure`, so
    listing an inbox never creates queue directories.
45. **`conveyor intake` re-creates the worktree's `tmp/` after the reset.**
    `git reset --hard` to main HEAD prunes `tmp/` when a previous run tracked
    it, which happens in a repo whose init files — `.gitignore` among them —
    are not committed yet. Without this the next line crashed writing
    `tmp/source.md`, leaving a traceback where a graded item should be.

40. **Operator commits are preflighted, and a half-written approve is undone.**
    `conveyor task`, `conveyor inbox approve`, and `conveyor start` refuse with
    the `git config user.name/user.email` repair text when
    `git var GIT_COMMITTER_IDENT` fails, instead of letting `git commit` exit
    128 mid-command (the cockpit surfaced that as a raw traceback). If the
    commit still fails, the path is unstaged and the file `inbox approve` just
    wrote is removed, so the item stays approvable. A `tasks/<task>.md` that is
    absent from HEAD and byte-identical to the text being approved is adopted
    as leftover from an interrupted attempt; anything else still refuses with
    `already exists`, because approve must never overwrite an operator's file.

46. **A refused merge is not always a conflict.** §7.2 says only "conflict",
    but `git merge` also refuses when an untracked file in the worktree would be
    overwritten, having merged nothing. The two need different repairs, so
    `queue.merge` returns the reason and the loop parks `untracked-collision`
    rather than folding it into `merge-conflict`.
47. **`.gitignore` is committed on start.** Role worktrees check out the committed
    file, so an entry `conveyor init` appended but nobody committed does not protect
    anything. `conveyor start` appends any missing ISO-5 entries and commits
    `.gitignore` on the integration tree (and on an existing idle role branch that
    still lacks them) before creating worktrees. A live loop is not moved: start
    warns and asks for `conveyor stop` first. A tracked
    `.cursor/rules/conveyor-role.mdc` is refused outright rather than patched:
    each role's copy differs, so merging a commit that carries one would run a role
    under another role's instructions.
48. **The run log is stamped by a separate process.** `role-loop.sh --stamp`
    reads the agent's stdout and writes each line back dated (§6.9), rather than
    the loop relaying the stream itself. A relaying loop would sit in the
    agent's output path, so `kill -9` of the loop would end the agent with
    `SIGPIPE` mid-run; the stamper keeps the killed-loop behaviour the plain
    redirect had — agent and log carry on, the run finishes, and the restarted
    loop finds its handoff (invariant 11). Lines are dated when read, which for
    an agent that buffers is the time Conveyor saw them, not the time the agent
    produced them.
49. **A killed run is not a failed attempt.** `max_minutes` is now a deadline on
    the agent process as well as a pre-flight check (§6.6, §6.9). When it fires,
    `attempt` does not advance and there is no `--resume` retry: the budget a
    retry would spend is the one that just ran out, so a killed run parks
    `max-minutes` straight away. The park detail says which check fired —
    `killed attempt <n> after …` for the deadline, the old
    `task started <ts>, …` for the pre-flight check.
50. **The outbox wins over the kill.** After a deadline kill the loop re-checks
    the outbox *before* parking, so an agent that queued a valid handoff and then
    wedged still has its item forwarded. Anything else would make the kill a
    second signal about whether work happened, and the outbox is the only one
    (PRD §5).
51. **A 60 s floor on the run deadline.** The deadline is
    `max(60, max_minutes × 60 − age(started_at))`. `max_minutes = 0` is legal and
    means "park on the next pass"; without the floor it would instead kill every
    run the instant it started, and §6.6 promises a just-started task one
    attempt. The floor is the only place a run may outlive the task budget.
    The operator's number is otherwise taken at face value: a wedged run under
    `max_minutes = 120` dies after two hours, because guessing a tighter bound
    would kill legitimately long builds.
52. **Kills are process-group kills.** The agent is launched with
    `start_new_session`, and the deadline — and `conveyor stop --now` — signal
    `os.killpg`, not the leader. A child that inherited the agent's stdout keeps
    the stamper blocked on an EOF that never arrives, so terminating the leader
    alone trades one hang for another. `start_new_session` had to land in the
    same change: without it the agent shares the loop's group and a `killpg`
    would kill the loop itself. Signalling a group whose members have all exited
    raises `ProcessLookupError` — that is the success case, so the calls are
    wrapped, never checked first.
53. **Gates need their own group *and* a handler in `handoff.sh`.** A gate runs
    under `shell=True`, where a plain `communicate(timeout=…)` kills the shell and
    orphans the command that is actually stuck — so gates get
    `start_new_session` too, and the timeout kills the group. That group is not
    the agent's, so it would survive the deadline kill above; `handoff.sh`
    therefore installs a `SIGTERM` handler that kills the gate in flight before
    exiting. Without it, decision 52 leaves an `nx build` running forever.
54. **A gate timeout is a refusal, not a death.** The run deadline already bounds
    gates transitively, but opaquely: the run dies and the agent learns nothing.
    `E_GATE_TIMEOUT` turns the same event into an ordinary `handoff.sh` failure
    with repair text the agent can act on inside its remaining attempts. The
    timed-out gate writes the same log shape as a failed one — same path, partial
    output, `exit: timeout` on the first line — so there is nothing new to learn
    when reading a failure.

55. **Worktree setup keys a content stamp, never mtime.** `setup.stamp` hashes
    the blob oid of each `worktree_setup_paths` entry at the worktree's HEAD
    (`git rev-parse --verify --quiet HEAD:<path>`, `-` when absent), not file
    contents and not mtimes. A merge rewrites mtimes constantly and none of it
    is evidence; the oids come from git, so they cannot disagree with what was
    actually merged.
56. **The setup command is part of the stamp.** Changing `worktree_setup`
    re-runs it in every tree — what an operator who just fixed their install
    command expects. The consequence is that a cosmetic edit to the command
    string costs one install per role.
57. **`setup.stamp` is written only on exit 0.** A failed or timed-out install
    leaves no stamp, so the next `conveyor start` or the next merge tries
    again rather than trusting a half-populated tree. `conveyor start
    --no-setup` likewise writes none.
58. **A dirty tree after setup warns, it does not refuse.** `handoff.sh`
    refuses an uncommitted tree (`E_DIRTY`) and no agent can fix that from
    inside, so the warning names the first five paths and the total. Conveyor
    cannot guess which paths an operator's install creates — `check_ignores`
    manages only its own four entries — so it says what it sees and leaves the
    `.gitignore` to the operator. `git status` is run with
    `--untracked-files=all` there: an install that drops 4000 files under one
    unignored directory should read as 4000, not as one collapsed entry.
59. **Setup is skipped, with a warning, for a role whose loop is live.**
    `conveyor start` is re-runnable and is routinely run against a belt that is
    already up; installing into a tree an agent is working in corrupts the run.
    The same precedent already governs the committed-`.gitignore` repair. It
    also makes protocol §2.3's single writer for `setup.stamp` true by
    construction: `start` only ever sets up idle trees, and a loop only ever
    sets up its own.
60. **A completed setup prints `ok, <duration>`, never `skipped`.** The plan's
    sketch showed a `setup skipped (command exited 0, nothing to do)` line for
    a role whose hook no-ops. Conveyor cannot know that — the command is
    opaque and exit 0 is exit 0 — so it reports what it observed. A hook that
    skips a role should say so on its own stdout.

61. **`run_bounded` is a second caller of `kill_group`, not a second mechanism.**
    The worktree-setup plan and `docs/plans/run-deadlines.md` both needed a
    bounded shell command in its own process group; whichever landed first was
    to carry the helper. Run deadlines landed `kill_group` (ambiguity 52), so
    `run_bounded` wraps it rather than repeating the TERM-then-KILL escalation,
    and there is one duration formatter (`util.duration`) rather than two.

62. **A `result` usage event wins over per-message ones; they are never mixed.**
    A stream can report usage as a cumulative total on its terminal event or as
    per-message deltas, and nothing in the stream says which. Summing a cumulative
    total double-bills; last-winning a delta under-bills. So `usage.scan` takes the
    terminal event's usage outright when there is one and ignores every per-message
    event, sums per-message usage only in its absence, and writes which rule fired as
    `source` in the sidecar. A wrong guess is then visible in the file instead of
    silently doubling a bill. The alias table (`input_tokens` / `prompt_tokens` /
    `inputTokens`, and the rest) lives in one dict, `usage.ALIASES`, so a live run
    against a new agent can extend it without touching the logic — the same shape as
    the Jira `customfield_*` allowlist. Unrecognised keys are ignored, never summed.
63. **Unknown usage never parks, and is never printed as `0`.** A task whose runs
    all report `source: none` has an *unknown* total, not a zero one, so `max_tokens`
    cannot fire on it (§5.5: refuse rather than guess) and every operator surface
    renders it `-`. A finished run always writes a sidecar even when it reported
    nothing: an absent file means the loop did not finish the run, which is a
    different fact. `cost_usd` is stored only when the agent reports one — Conveyor
    ships no price table, and ceilings are on tokens only.
64. **The usage record in the run log names its token keys `input_tokens` /
    `output_tokens`.** `output` is already in `cmd_log`'s `LOG_DETAIL_KEYS`, so a
    record with a bare `output` key would print the raw number a second time after
    the formatted `text`. The sidecar keeps the short `input` / `output` names; only
    the log record spells them out.
65. **Usage is a file per run, not a `board.tsv` column.** `board.COLS` is a fixed
    8-tuple and `_load` treats any row with a different cell count as malformed,
    keeping it out of `read()`. Widening it would make every pre-existing board row
    invisible to `board.get`, which the role loop turns into `no-board-row` failures
    on live tasks. The sidecar is a derived index of exactly one `.jsonl`, so it sits
    beside it under the same key: no new lock, no new protocol directory, and
    `cmd_log` filters on `.jsonl` and never sees it.
66. **A hand-written `## Handoff contract` warns, it is neither refused nor
    stripped.** The handoff contract is generated from `conveyor.conf` into the
    `.mdc` (`roles.render_contract`); the role file is craft only. An operator
    upgrading Conveyor under a target repo whose `roles/` still carries the old
    section must not have `conveyor start` fail on files `init` gave them last
    month, so `validate_role_text` requires only `Owns` / `Does not own` and the
    section is accepted. Conveyor does not rewrite operator-owned files and does
    not parse prose to decide what to drop, so it is not stripped either. The
    generated block's first sentence ("This section overrides any hand-written
    contract above it") resolves the ambiguity for the agent; `conveyor start`
    prints one warning per offending role for the operator.
67. **The `findings` empty-commit rule is mechanics; the `pass` empty-commit
    preference is craft.** `findings` from the last role *requires* a commit that
    is not the inbound one — that is `E_NO_CHANGE`'s repair text — so it is
    generated into the contract block. For `pass`, an empty commit is only
    *preferred* (the inbound commit unchanged is permitted), so it is a judgement
    call the operator may tune and stays in `roles/reviewer.md` under
    `## How to review`.
68. **The Cursor sandbox is turned off by a flag, not a `sandbox.json`.**
    Cursor's sandbox (`sandbox.mode` in `~/.cursor/cli-config.json`, on since
    3.5) confines a shell command to the worktree with `.git/hooks` protected and
    network off — but Conveyor's handoff writes to `.conveyor/` *above* the
    worktree and the byline hook runs from the shared `.git/hooks`, so a
    sandboxed run produces no handoff and no byline. The alternative, a
    per-worktree `.cursor/sandbox.json` with `additionalReadwritePaths`, would
    need the absolute repo root baked into each tree, still would not unprotect
    `.git/hooks`, and would still be overridable by the user-level file. Conveyor
    already isolates roles by worktree and branch, so the sandbox adds nothing it
    relies on; the loop passes `--sandbox disabled` in its fixed argument list
    instead (cursor-cli-runtime.md decisions 1–2). An operator who wants it back
    for a role adds `--sandbox enabled` to that role's `cli-args`; the assembler's
    dedupe is exact-match on flag *and* value, so the override survives after the
    fixed `--sandbox disabled` and Cursor's own parser takes the later one.
69. **The byline must be the last line; Conveyor does not learn to tolerate a
    trailer after it.** Cursor's `attribution.attributeCommitsToAgent` (default
    `true`) can append a `Made with Cursor` trailer. If it lands before `git
    commit`, the byline hook appends `By <role>.` after it and all is well; if
    Cursor amends after the hook, the byline is no longer last and `handoff.sh`
    rejects the commit `E_NO_BYLINE` (invariant 10). Conveyor does not relax that
    check — a byline that is not last is a byline another tool can push off the
    end. There is no flag for attribution, so the fix is the operator's
    (`attribution.attributeCommitsToAgent: false`), and `conveyor start`'s smoke
    test is what tells them, with that exact repair text (cursor-cli-runtime.md
    decision 3).
70. **Cursor reports no token usage in `stream-json`, so `max_tokens` is inert on
    it — the docs say so and `conveyor start` warns; the scanner is not changed.**
    (token-cost-on-cursor.md, decision 3.) Cursor's documented terminal event for
    `--output-format stream-json` is
    `{"type":"result","subtype":"success","duration_ms":…,"duration_api_ms":…,`
    `"is_error":false,"result":"…","session_id":"…","request_id":"…"}` — no `usage`,
    no token fields, and the same for `json`. No live Cursor smoke log was available
    when this was written (2026-09-10), so the branch rests on Cursor's own CLI
    reference rather than on numbers a run produced; the two grep lines in runbook
    §6.2 are exactly how an operator confirms it against a real `smoke.jsonl` and
    re-checks after a CLI update. `usage.scan` therefore writes `source: none` for
    every Cursor run, `conveyor cost` prints `-` and, when nothing in view reported
    usage, ends with `no run reported usage; see runbook §6.2`, and a `max_tokens`
    ceiling never fires (decision 63 — an unknown total cannot park). `conveyor
    start` tees each smoke run to `.conveyor/logs/<role>/smoke.jsonl` (overwritten
    per start) and warns when a role sets `max_tokens` and that log carried no usage;
    a warning, not a refusal, because the operator may be about to upgrade the CLI.
    Nothing is estimated from `duration_ms` (token-cost decision 4). The `ALIASES`
    table keeps its Claude-Code keys — a second backend may use them, and Cursor's
    docs note that "field additions may occur over time in a backward-compatible
    way", which the table absorbs the moment a usage field appears, with no config
    change. `RESULT_SUBTYPES` is left as-is: the extra subtypes are harmless and removing
    them would only break a future backend for tidiness (decision 5).

## Not built (PRD Appendix B)

Nothing from Appendix B is implemented except the partial B.3/B.5 pieces
described above (pipelines of any length, declared gate, intake approval) and the
metering half of B.7 (usage sidecars, `conveyor cost`, `max_tokens`; loop detection
is still out). Hook points
for the rest are marked with a single `# later: B.x` comment where a future
change would go.
