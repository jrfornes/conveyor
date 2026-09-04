# Engineering

## Commits

- Commit early and often on your own branch. Every handoff carries a commit; nothing else moves.
- Write the commit message for the next role and for the human. First line: what changed, under 60 characters. Body: what was done, how it was verified, and anything the next role must know. This body becomes the handoff body verbatim.
- Never use `--no-verify`, `--no-hooks`, or any flag that skips hooks. The byline hook appends `By <role>.` and the validator rejects commits without it.
- Never amend, rebase, force-push, or rewrite commits that have already been handed off.
- Never edit `.git/`, hooks, or `.conveyor/` by hand.

## Code

- Make the smallest change that satisfies the task. Do not refactor, rename, or reformat code the task does not touch.
- Every behavior the task requires must be covered by a test that fails without the change. A test that cannot fail is not a test.
- Run the project's test command (see `project.md`) before every handoff. If it fails, you are not done.
- Do not add dependencies unless the task requires it, and say so in the commit message if you do.
- Do not delete or skip existing tests to make the suite pass. If a test is wrong, fix it and explain why in the commit message.

## Scratch and output

- Scratch files go in `./tmp/` inside your worktree only. Never write to `/tmp`, `$HOME`, or anywhere outside your worktree.
- Do not commit anything under `./tmp/`.
- Do not print secrets, tokens, or environment variables into commits or logs.
