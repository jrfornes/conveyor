# Conveyor — Setup and Operations Runbook

## 1. Prerequisites

- macOS or Linux, git ≥ 2.30, and one scripting language for the `conveyor` scripts (see `IMPLEMENT.md` decision record).
- Cursor CLI. Installed separately from the editor:
  ```
  curl https://cursor.com/install -fsS | bash
  cursor-agent --version
  ```
  The installer links both `agent` and `cursor-agent`. Use `cursor-agent` in config; `agent` collides with other binaries.
- Log in once interactively (`cursor-agent`, then `/login`) or set `CURSOR_API_KEY`. **Verify before first real run:** some plans require `CURSOR_API_KEY` for print mode (`-p`). Test with:
  ```
  cd /tmp/scratch && git init -q && cursor-agent -p --force "create a file hello.txt containing hi"
  ```
- Pin the CLI version you tested against in `conveyor.conf` `[global] agent_version =` and let `conveyor start` warn when it differs.

## 2. Models

```
cursor-agent --list-models
```

(`cursor-agent models` still works.) Copy two names into `conveyor.conf`, from different model families. `conveyor start` refuses any name not in that list. Effort is encoded in the model name on Cursor (`-low`, `-high`, `-max` suffixes where offered), not as a flag.

## 3. Project setup

1. From the target repo root (with `conveyor` on `PATH`): `conveyor init`. This copies `constitution.md`, `constitution/`, `roles/`, `intake/` (the ticket-reviewer prompt and grading rubric), `conveyor.conf.example`, and (only if missing) `project.md`; creates `conveyor.conf` from the example when missing; creates `tasks/`; and appends the required `.gitignore` entries. Safe to re-run — operator-owned files are never overwritten. Review and commit.
2. Edit `project.md`: test command, language, anything the reviewer should treat as a requirement.
3. Edit `conveyor.conf` and fill in the two model names.
4. Make sure the project's test command passes on a clean checkout. On `ready` and `pass`, `handoff.sh` runs the required gates from the worktree's `project.md` (legacy `## Test command` fence or `## Gates` + `## Required on`). An empty fence or command is skipped. A nonzero exit is `E_GATE_FAILED`; `cat .conveyor/logs/gates/<role>-<task>-<commit>-<name>.txt` for the output. Run a gate manually with `conveyor gate run <name>` (add `--role <role>` to use that worktree and inbound commit).
5. `conveyor start`. It will:
   - create one `.worktrees/<role>` per configured role on branch `conveyor-<role>` (e.g. `.worktrees/coder`, `.worktrees/reviewer` for the default Review belt)
   - write `.cursor/rules/conveyor-role.mdc` into each (constitution + role, concatenated)
   - copy assigned skill trees from `roles/<role>.skills` into each worktree at the same relative path under `.agents/skills/<name>/` or `.cursor/skills/<name>/` (repo root; `.agents/skills` wins when both exist)
   - install the byline `commit-msg` hook
   - create `.conveyor/` queue directories and `board.tsv`
   - run a smoke test (`cursor-agent -p "reply with the word ok"` in each worktree) and check the rules file loaded
   - launch one loop per role

## 4. Day to day

| You want to | Run |
|---|---|
| Give the pipeline work | `conveyor task <name>` then type or pipe the task text (`conveyor task add-login < spec.md`) |
| See where everything is | `conveyor status` |
| Watch an agent | `conveyor log coder` — dated, §6.1 (or `tail -f .conveyor/logs/coder/*.jsonl`) |
| See what a loop did and when | `tail -f .conveyor/logs/coder/loop.log` — one dated line per item, attempt, and outcome |
| See what a role produced | `git log conveyor-<role>` — every commit ends `By <role>.` |
| Read a finished task | it's merged on `main`; `git log main` |
| Unstick a parked task | read `.conveyor/needs-human/<task>/reason`, fix the cause, `conveyor resume <task>` |
| Stop cleanly | `conveyor stop` (waits for in-flight agent runs) |
| Stop now | `conveyor stop --now` (kills agents; items stay in `in_process/` and resume on next start) |
| Import a ticket | `conveyor import --source manual` (or `jira`; set Jira creds with `conveyor intake jira --site … --email … --token-stdin` or Inbox → Intake settings → Jira — failures print `failed <KEY>  <status> <reason>` and skip the row). Jira attachments are listed on import (not downloaded); video/audio print a watch-in-Jira notice. Empty description skips Grade only when there are also no attachments. |
| Re-fetch a Jira inbox item | `conveyor import --refresh <id>` (only `imported`; overwrites `source.md` in place; refreshes the attachment list, keeps selection by id) |
| Replace inbox source text | `conveyor import --replace <id>` (body on stdin; only `imported`; Conveyor rewrites the attachments footer) |
| See the inbox | `conveyor inbox list` (id, source, status, grade, title) or `conveyor inbox show <id>` for one item's documents |
| Choose intake attachments | `conveyor inbox attachments <id>` or `… --select 10001,10002` / `--select none` |
| Grade an inbox item | `conveyor intake <id>` — prints `graded <id>  <grade>`. Downloads selected scannable files into the intake worktree `tmp/attachments/`. Refused when the item is `ready` or `started` (its task file is already committed); a `skipped` item can still be re-graded |
| Rewrite an inbox item into a task | `conveyor intake <id> --improve` (add `--comments <file-or-text>` to send the reviewer your notes; they are consumed once, then kept as `comments-applied.txt`) |
| Accept or skip a graded ticket | `conveyor inbox approve <id> [--name <task>]` or `conveyor inbox skip <id>`. Approve writes and commits `tasks/<task>.md` but does **not** enqueue it |
| Approve a ticket the grade does not support | `conveyor inbox approve <id> --force` — needed when the grade is `Unusable`, `unparsed`, or `-` |
| Send an approved ticket to the pipeline | `conveyor start-task <name>` (creates the board row and the first handoff) |
| Approve or reject a gated handoff | `conveyor approve <id>` or `conveyor reject <id>` |
| List or switch workflows | `conveyor workflow list` or `conveyor workflow activate <slug>` |
| Create a coding role | `conveyor role new <name>` (optional `--from <other>`); then add it with `conveyor workflow edit` |
| Assign skills to a role | `conveyor role skills <name> --set a,b,c` (from `.agents/skills/*/SKILL.md` or `.cursor/skills/*/SKILL.md`; agents wins on duplicate names) |
| Open the localhost cockpit | `conveyor-ui` (or `conveyor-ui --demo` for a throwaway fixture) |
| List or run project gates | `conveyor gate list` or `conveyor gate run <name> [--role <role>]` |
| Tear down runtime state (test/dev) | `conveyor uninstall --yes` (add `--bundle` to also remove init files) |

Task names: `^[a-z0-9][a-z0-9.-]*$`, unique for the life of the board.

## 5. Writing a good task file

The task file is the spec, and the reviewer grades against it literally. Numbered requirements review better than prose. Include:

- what must be true when done, as testable statements
- what is explicitly out of scope
- any acceptance command beyond the standard test command

The reviewer will not credit anything not written here, and the coder will not build anything not written here.

## 6. Reading `conveyor status`

```
coder      in_process: add-login (coder-000003)  age 4m   attempt 1/3   new: 0
reviewer   idle                                            new: 1
needs-human:
  fix-cache   max-retries   reviewer sent findings 4 times
board:
  add-login   coder        audit 2  retry 1
  fix-cache   needs-human  audit 7  retry 4
inbox:
  proj-9      awaiting-approval  Gaps
  proj-12     imported           -
  (1 started, 1 skipped)
```

The `inbox:` block is omitted entirely when nothing has been imported, so a repo that does not use
intake sees exactly the first three sections. Items already past your decision (`started`,
`skipped`) are counted on the last line rather than listed. The third column is the grade:

- `Ready` / `Gaps` — the ticket-reviewer's verdict; both can be approved
- `Unusable` — the ticket is missing the problem itself; `inbox approve` refuses without `--force`
- `unparsed` — `grade.md` exists but has no `Grade: Ready|Gaps|Unusable` line, so there is no
  verdict to trust. Re-grade it; `conveyor inbox show <id>` prints what the reviewer actually wrote
- `-` — not graded yet

High `audit` with low `retry` means the coder is being challenged and fixing things itself: healthy. High `retry` means coder and reviewer disagree: read the findings in `git log conveyor-reviewer` and probably sharpen the task file.

### 6.1 Reading `conveyor log`

```
== add-login_operator-000001_a1.jsonl  2026-09-03T14:15:02Z
14:15:02 [conveyor] run attempt 1, model composer-2.5
14:15:04 [tool] git commit 0
14:16:31 [tool] handoff.sh AUDIT_REQUIRED: handoff for add-login not queued (audit 1)
           Before resubmitting, re-read tasks/add-login.md and your role file.
14:18:07 [tool] handoff.sh OK: coder-000001 queued for reviewer
          0
14:18:07 [conveyor] exit 0
```

The header names the log file and when the run started; each line is dated with the UTC clock —
same timezone as `board.tsv` and every handoff header — so gaps show you where an agent spent its
time. A wrapped line continues in the clock's own column. Lines from before Conveyor dated its logs
show a blank clock instead.

`loop.log` in the same directory is the loop's own timeline (item picked up, attempt started, agent
exit code, `forwarded`/`merged`, parks), one dated line each.

## 7. Recovery

- **Machine rebooted / loops killed:** `conveyor start`. Anything in `in_process/` resumes; anything in `outbox/` is delivered; nothing is duplicated.
- **`untracked-collision`:** git refused to merge because a file it would write is present in that worktree but untracked; **nothing merged**, and there is no conflict to resolve. The `reason` file names the files. Almost always `.cursor/rules/conveyor-role.mdc` reaching a commit because the ignore entry was never committed — check with `git show conveyor-<role>:.gitignore`. Untrack it (`git rm --cached <file>`) and commit **on every branch that carries it** — `conveyor start` refuses until they are all clean and names them — then `conveyor start` to regenerate each worktree's rules, then `conveyor resume <task>`. The parked handoff still points at the old commit, so if the resume trips again, re-run the task from a clean base (`conveyor task <name> --delete`, then re-create it).
- **Merge conflict between roles:** parked with reason `merge-conflict` when the receiving role could not merge the inbound commit into `conveyor-<role>`. The loop aborts the merge, so that worktree looks clean — nothing is left conflicted to inspect. Reproduce it in `.worktrees/<role>` with `git merge --no-commit --no-ff <commit>` (the commit is on the second line of `.conveyor/needs-human/<task>/reason`), then resolve it as a real merge with `CONVEYOR_ROLE=<role>` set so the merge commit is signed `By <role>.`, and `conveyor resume <task>`.
- **Merge conflict on `pass`:** parked with reason `merge-conflict`. Resolve on `main` by hand (commit gets `By operator.`), then `conveyor resume <task>`.
- **Two files in `in_process/`:** the loop refuses to start and says so. Move one back to `new/` by hand; this only happens after manual edits.
- **Agent keeps failing to hand off:** read the log; usually a validator error it did not follow. After `max_attempts` it parks. Fix the prompt or the task, `conveyor resume`.
- **Wipe and restart:** `conveyor stop --now && conveyor uninstall --yes`. Sequence numbers reset; `sent/` history is gone. Add `--bundle` for a full scratch reset (also removes `constitution/`, `roles/`, `conveyor.conf`, `tasks/`, and the Conveyor `.gitignore` entries). Does not rewrite history on `main`.

## 8. Testing without Cursor

Set `CONVEYOR_AGENT_BIN=./test/fake-agent` and `CONVEYOR_FAKE_SCRIPT=<script>`. The fake agent replays a script of `commit`, `draft`, `handoff`, `sleep`, `crash`, `exit` lines (protocol spec §11). The test suite runs every protocol invariant this way.

## 9. Upgrading an already-initialized repo

`conveyor init` templates `intake/ticket-reviewer.md` and `intake/rubric.md` and never overwrites
them, so a repo initialized before the grading contract was tightened keeps its own copies. Nothing
breaks: the grade parser tolerates the wording those files produce. To pick up the change, diff
your copies against the ones in the Conveyor checkout and merge by hand:

```
diff -u intake/ticket-reviewer.md <conveyor>/intake/ticket-reviewer.md
diff -u intake/rubric.md          <conveyor>/intake/rubric.md
```

Shipped templates are **items-only**: `intake/rubric.md` is the operator checklist for Ready.
The three grades (`Ready` / `Gaps` / `Unusable`) and the `Grade:` first-line rule live in Conveyor
code and are injected into the ticket-reviewer worktree on every `conveyor start` — deleting or
trimming the rubric file cannot remove them.

The only substantive addition is that `grade.md`'s first line must be `Grade: Ready`, `Grade: Gaps`,
or `Grade: Unusable`. Without it a grade is recorded as `unparsed` and `conveyor inbox approve`
refuses it — which is the intended behavior, not a regression.
