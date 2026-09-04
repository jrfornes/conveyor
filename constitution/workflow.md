# Workflow

## Where you work

- Your worktree is `CONVEYOR_WORKTREE`. Your branch is `conveyor-<role>`. Work only there.
- Do not `cd` outside your worktree. Do not read, diff, checkout, merge, or base work on any other branch or worktree. What you need has already been merged into your branch before your run started.
- Do not create branches, tags, or stashes.

## What you work on

- You have exactly one task in process. It is named in the prompt and described in `tasks/<task>.md`. That file is the operator's intent; re-read it before deciding you are done.
- The inbound handoff in your prompt tells you who sent the work and why. For a `findings` handoff, the body lists what the reviewer found; address every item or explain in your commit message why you did not.
- Do not start, plan, or partially do any other task, even if you notice it needs doing. Mention it in your commit message.

## Asking questions

- You cannot ask the operator anything mid-run. If the task is ambiguous, choose the most conservative reading, do that, and state the assumption clearly at the top of your commit message body.
- If the task cannot be done as written (contradictory, impossible, requires access you do not have), do not fake it. Commit what you have with a message that starts with `BLOCKED:` and explains why, then hand off normally. The next role will route it to the human.

## Finishing

1. Run the project test command. It must pass.
2. Commit everything. Working tree must be clean.
3. Write `./tmp/handoff.txt` (see `constitution/handoffs.md`).
4. Run `handoff.sh ./tmp/handoff.txt`.
5. If it prints `AUDIT_REQUIRED`, do the audit it describes, then run the exact same command again.
6. If it prints any `E_...` code, do what the repair text says and retry.
7. Stop only when it prints `OK`.
