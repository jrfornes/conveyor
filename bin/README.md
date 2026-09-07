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
bin/conveyor          operator CLI: init | uninstall | start | stop | task | status | log | resume
                      | import [--refresh/--replace] | intake [config|jira|<id>] | inbox approve/skip | start-task
                      | approve | reject | workflow …
bin/conveyor-ui       optional localhost cockpit (`--demo` throwaway fixture)
bin/handoff.sh        validator + audit gate (protocol §4–5)
bin/role-loop.sh      per-role loop (protocol §6); --once for tests
bin/merge.sh          protocol §7
bin/hooks/commit-msg  byline hook, copied into the shared .git/hooks by conveyor start
lib/conveyor/         util (timestamps, atomic write, locks), config, layout, handoff (format),
                      board (TSV), queue (merge, sweep, park, dequeue, seq), intake, jira,
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
    still fires and Grade stays skipped. Attachments are out.
39. **`conveyor uninstall` is runtime-only by default.** `--yes` is required;
    without it the command prints what would be removed and exits nonzero.
    Default removes worktrees, local `conveyor-*` branches, `.conveyor/`, and
    the byline hook only when its contents match the shipped copy. `--bundle`
    also deletes init files. Refused when run from the conveyor source checkout.

## Not built (PRD Appendix B)

Nothing from Appendix B is implemented except the partial B.3/B.5 pieces
described above (pipelines of any length, declared gate, intake approval). Hook points
for the rest are marked with a single `# later: B.x` comment where a future
change would go.
