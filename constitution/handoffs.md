# Handoffs

Work moves between roles as commits plus a small validated file. You write a three-line draft; the script fills in everything else. This article is the agent-facing summary of `docs/conveyor-handoff-protocol.md`.

## The draft

Write exactly this to `./tmp/handoff.txt`:

```
to: <role or done>
task: <task name from your prompt>
verdict: <ready | pass | findings>
```

Nothing else. No blank line followed by text, no other headers. Your commit message is the body.

Which `(to, verdict)` pairs you may use depends on your role and on `conveyor.conf` order — never invent a recipient. The validator computes permitted triples from the coding-pack order (operator → first; adjacent `ready`; last → `done`/`pass`; last → penultimate/`findings`). Intake is separate: `ticket-reviewer` sends `to: operator`, `verdict: ready`.

Two-pack example (`coder` then `reviewer`):

| You are | to | verdict | When |
|---|---|---|---|
| coder | reviewer | ready | Task done and verified |
| reviewer | coder | findings | Something is missing or wrong |
| reviewer | done | pass | Every requirement is proven |

## The script

```
handoff.sh ./tmp/handoff.txt
```

It reads your role from the environment, takes the commit from your branch HEAD, validates everything, and queues the handoff. Never type a commit SHA anywhere. Never write `from`, `commit`, `id`, `type`, `task_id`, or any timestamp; the script rejects drafts that contain them.

## The audit

The first time you submit a candidate, the script refuses with `AUDIT_REQUIRED`. This is not an error. It means: stop, re-read `tasks/<task>.md` and your role file, and for every requirement find the commit, test, or output that proves it is met.

- If everything is proven, run the exact same command again. It will be accepted.
- If anything is missing, fix it, commit, and run the script again with the new commit. You will be challenged again for the new candidate. That is expected.

The number of times you are challenged is recorded and visible to the operator.

## Errors

Every error prints a code, one line describing the problem, and repair text. Follow the repair text literally. The ones you are most likely to see:

- `E_DIRTY` — you have uncommitted changes. Commit or discard them.
- `E_GATE_FAILED` — the project test command failed. Fix the failures, commit, and retry. Output is in `.conveyor/logs/gates/`.
- `E_NO_BYLINE` — you committed with hooks disabled. `git commit --amend --no-edit` (without `--no-verify`).
- `E_NO_CHANGE` — HEAD is the same commit you received. Commit your work. As reviewer sending `findings`, an empty commit (`git commit --allow-empty`) carrying the findings is the expected form.
- `E_BAD_ROUTE` — that `(to, verdict)` is not permitted for your role. Use the triples from `conveyor.conf` (two-pack example in the table above).
- `E_TASK_MISMATCH` — the task name is not the one in your prompt.
- `E_RESERVED_HEADER` — delete that line; the script fills it.
- `E_DRAFT_HAS_BODY` — remove everything after the three lines.

If you see `E_ENV`, `E_NOT_MY_TASK`, `E_TASK_FILE`, or `E_AMBIGUOUS_SHA`, something is wrong with the pipeline, not with you. Commit what you have with a `BLOCKED:` message describing the error and end your run.

## What you never do

- Hand off work you have not run the tests on.
- Hand off a task other than the one in process.
- Write handoff files anywhere except `./tmp/`, or create files under `.conveyor/` yourself.
- Send more than one handoff per run. If the script printed `OK`, you are finished.
