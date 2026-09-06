# Implementation brief

**Status:** M0–M2 and M4 are implemented under `bin/` and `lib/conveyor/`; M3 awaits the first live Cursor run. `v0.4.0-rc1` is tagged (gates catalog, role skills, uninstall; live-run unverified). Run M3 against a tag before `v1.0.0`.

You are implementing Conveyor from this bundle. Read in this order:

1. `docs/conveyor-prd.md` — scope. Sections 3, 7, 9 are what you build. Appendix B is what you do NOT build; do not let its mechanisms leak into the MVP.
2. `docs/conveyor-handoff-protocol.md` — normative. Every file format, directory, error message, and state transition. Where it and the PRD differ, it wins.
3. `docs/runbook.md` — the operator's view; the `conveyor` CLI must match it.
4. `constitution.md`, `constitution/`, `roles/`, `project.md` — these are shipped as-is into target repos. Do not edit them to make implementation easier; if the protocol and these disagree, fix the protocol doc and say so.
5. `docs/agent-orchestration-north-star.md` — the why. Consult when a design choice is open.

## Decision record

**Language:** implement the scripts in a single language of your choice under `bin/` and `lib/`, subject to: one-command install with no build step on macOS and Linux; atomic rename and `mkdir` locks as described in protocol §8.2; no dependency on `flock(1)`. Bash ≥ 4 with `set -euo pipefail` or Python ≥ 3.10 stdlib-only are both acceptable. State the choice and the reason in `bin/README.md`. Do not use both.

**No framework, no daemon beyond the role loops, no database.** If you find yourself wanting one, re-read north-star §0.

## Deliverables

```
bin/conveyor            operator CLI: start | stop [--now] | task | status | log | resume
bin/handoff.sh          validator + audit gate (protocol §4–5). Named handoff.sh regardless of language; agents call it by this name.
bin/role-loop.sh        per-role loop (protocol §6)
bin/merge.sh            protocol §7
bin/hooks/commit-msg    byline hook (protocol §7.4)
test/fake-agent         protocol §11
test/                   invariant tests, one file per protocol §9 invariant, plus the M1/M2 scenarios below
bin/README.md           language decision, install instructions
```

`conveyor start` must copy `bin/handoff.sh` (and anything it needs) into each worktree's `./tmp/../` reachable path or put `bin/` on PATH for the agent process, so an agent can run `handoff.sh ./tmp/handoff.txt` from its worktree root. Document which.

## Order of work and exit criteria

Follow PRD §9 exactly. Do not start a milestone before the previous one's exit criterion passes as an automated test.

- **M0** — `conveyor start` on a fixture repo creates both worktrees with `conveyor-role.mdc` present and the hook installed; refuses an unknown model when `cursor-agent models` is stubbed.
- **M1** — with the fake agent: operator task → coder `ready` → reviewer `pass` → merged on main, board lane `done`. Then the same run with `crash` inserted at every step boundary of protocol §6.3 and §6.5; after `conveyor start`, the end state is identical (invariant 11).
- **M2** — fake agent's first `handoff` gets `AUDIT_REQUIRED`, second identical gets `OK`, `audit_count` is 1; a changed draft between them makes it 2. A commit made with `--no-verify` is rejected with `E_NO_BYLINE`.
- **M3** — real `cursor-agent` on a small real repo: a task with three numbered requirements where one is deliberately not covered by the coder's tests; the reviewer must send `findings` and the coder must fix it. Record the run logs in `test/fixtures/m3/`.
- **M4** — a task file that says "make the test suite fail" parks in `needs-human` with reason `max-retries` within the configured ceiling; `conveyor status` output matches runbook §6 format.

## Rules for you, the implementer

- Every error code in protocol §4.5 must be produced by a test with the exact repair text.
- Every state change is a rename. Grep your code for in-place writes to queue directories; there must be none.
- Never parse agent prose to make a decision. The outbox is the only signal.
- If the protocol is ambiguous, choose the option that refuses rather than guesses, implement it, and add a note under "Ambiguities resolved" in `bin/README.md`.
- Do not implement anything from PRD Appendix B, however small it looks. Leave a `# later: B.x` comment where a hook point would go, at most one line.
- Keep the total under about 1,500 lines excluding tests. If you are over, you are building something the north star says not to build.
