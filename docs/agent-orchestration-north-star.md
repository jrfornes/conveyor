# Agent Orchestration: Principles and Reference Implementation

A north-star document for building multi-agent coding workflows. Each section states a principle, why it matters, how SwarmForge (Robert C. Martin, `github.com/unclebob/swarm-forge`, read September 2026) implements it, and how to port the idea to a new project independent of SwarmForge's stack.

The one-sentence summary: **coordinate agents through the filesystem and git, keep every mechanism boring and inspectable, and make each agent own one way the work can go wrong.**

---

## 0. Design stance

Before the individual ideas, three positions that shape all of them:

1. **One strong agent with a good harness is the default.** Add agents only when each new one owns a specific failure mode (spec ambiguity, untested code, structural drift, weak tests, unverified claims). More agents means more tokens and more supervision, and the evidence that it produces better code is thin.
2. **Prefer existing tools to new abstractions.** Git already solves isolation and history. The filesystem already solves durable queues. Terminals already solve observability. A message bus, a shared memory store, or an agent-spawning hierarchy each add a new failure mode.
3. **Process is enforced, not requested.** Anything that only lives in a prompt ("do not ask for approval in the pane") will eventually be ignored. Anything that lives in a script that refuses to proceed will not. Push rules from prompts into gates whenever possible.

---

## 1. Isolation is the foundation

### Principle
Nearly every multi-agent failure is two agents mutating the same state. Give every agent its own working copy, its own branch, and its own scratch space before anything else.

### SwarmForge implementation
- `swarmforge.conf` has one line per role: `window <role> <backend> <worktree> [task|batch] [forward-only|back-one|back-all] [cli-args]`.
- On startup, `prepare-worktrees!` runs `git worktree add --force -B swarmforge-<name> .worktrees/<name> HEAD` for every role except the one named `master` (which uses the main checkout). Exactly one `master` is required.
- Scripts, role prompts, and constitution files are copied into each worktree so agents never reach outside their tree.
- `.worktrees/` and `.swarmforge/` are added to `.gitignore`.
- Each agent is launched with `cd <worktree>` and `SWARMFORGE_ROLE=<role>` exported; helper scripts use these rather than trusting the agent.
- Scratch is `./tmp/` inside the worktree. `/tmp` is forbidden by prompt and rejected by the handoff script.
- The workflow article says: work only in your assigned worktree; do not inspect, diff, merge, or base work on another branch unless a handoff names it.

### Porting guidance
- Use `git worktree` (or a container per agent) rather than branches in one checkout. Branches alone still share the index and working tree.
- Encode identity in the environment (`AGENT_ROLE`, `AGENT_WORKTREE`), and have every helper script read it. Do not let the agent tell you who it is.
- Reject scratch outside the worktree at the tool level, not just in prompts.
- Keep one designated "integration" tree where merges land; everything else is a feeder.

---

## 2. Verification is worth more than parallelism

### Principle
The most valuable second agent is an adversary, not a second worker. The agent that claims "done" must never be the agent that decides "done." Add a forced second look before every claim of completion.

### SwarmForge implementation
- Separate roles for each quality gate in the six-pack: `cleaner` (DRY/CRAP review), `architect` (dependency direction), `hardender` (mutation testing), `QA` (runs the spec's end-to-end procedures). Each is a prompt file plus a hard-coded tool list in the launcher.
- The **audit gate** in `swarm_handoff.bb`: the first time a role runs `swarm_handoff.sh` for a `git_handoff`, the script refuses, prints `AUDIT_REQUIRED` with instructions to re-read the task and trace every requirement to verification evidence, stores a fingerprint of the candidate (commit + draft) under `.swarmforge/handoffs/audit_pending/`, and increments an audit counter on the board card. The handoff is queued only when the agent resubmits the *identical* candidate. Any change resets the challenge.
- Constitution tooling is prescriptive: install `crap4<lang>`, `dry4<lang>`, `mutate4<lang>`, `gherkin-mutator`; run them one at a time; mutation is differential against a committed manifest (never `--mutate-all`); never hand-edit manifests; never substitute homegrown proxies.
- Gherkin specs are themselves mutation-tested (`gherkin-mutator` perturbs example values) so decorative acceptance tests get caught.

### Porting guidance
- Split "produce" and "verify" into different agents or at minimum different sessions with fresh context.
- Implement a two-call gate on any "complete" action: first call records and rejects, second identical call proceeds. It is cheap and forces one re-read.
- Count audits per task and surface the count to the human. A task with six audit cycles is a signal.
- Make verification tools mandatory and named. "Run tests" is too vague; "run `mutate --diff manifest.json`" is checkable.
- Treat coverage as a hint and mutation score as the truth.

---

## 3. Roles are context hygiene, not division of labor

### Principle
A specifier and a coder are the same model. Roles are valuable because each session holds one job in a small, clean context instead of a forty-turn session that has forgotten its constraints.

### SwarmForge implementation
- Each agent gets a generated rules file: the constitution and everything it references, `project.md`, the role file, and its handoff contract, written to `.cursor/rules/conveyor-role.mdc` in the role's worktree and loaded by Cursor on every turn. The per-run prompt carries only the task, the inbound handoff, and any retry context.
- Role prompts have explicit `## Owns` and `## Does Not Own` sections (the hardener is told to ignore the QA suite entirely).
- Every delivered handoff body starts with `Re-read your role and constitution.` so each task re-anchors the role.
- **Batch receive mode**: review-type roles (`cleaner`, `architect`, `hardender`, `QA`) consume all queued equal-priority handoffs as a single unit, so one review pass covers one batch rather than the context accumulating across many tiny tasks.
- The constitution is layered: shared articles from `main` (`engineering`, `workflow`, `handoffs`), pack-local articles (`local-*.prompt`), and a per-project `project.prompt`. A top-level `constitution.prompt` declares precedence.

### Porting guidance
- Write each role prompt as owns / does-not-own / handoff contract. Under two pages.
- Re-inject the role at every task boundary rather than assuming it persists.
- Layer rules: global → workflow-specific → project-specific, with a stated precedence order, all versioned in the repo.
- Prefer many short sessions over one long one. Spawn a fresh context per task or batch.
- Give review roles batching so they see related changes together.

---

## 4. Handoffs are explicit artifacts, not chatter

### Principle
Work moves as commits and small structured messages that are validated, durable, and auditable. If a human cannot read the handoff and know exactly what was asked and delivered, the agents cannot either.

### SwarmForge implementation
- Agents write a four-line draft in `./tmp/`:
  ```
  type: git_handoff
  to: cleaner
  priority: 50
  task: task-1-cave-setup
  ```
- `swarm_handoff.sh` is the strict outbound gate. It validates every field with repair guidance, infers `from` from the environment, fills `commit` from the worktree HEAD (agents are told never to type a SHA), canonicalizes the abbreviation to exactly 10 hex chars resolving to one commit, rejects reserved headers (`id`, `from`, `role`, `recipient`, `*_at`), serializes a per-worktree sequence counter with a lock, and installs the file atomically (`outbox/tmp/x.tmp` → rename → `outbox/x.handoff`).
- Filenames sort by `<priority>_<timestamp>_<sequence>_from_<sender>_to_<recipients>.handoff`. Headers are authoritative; filenames are for audit.
- Only two message types exist. `git_handoff` has a generated body of `merge_and_process.sh <sender> <sha>`. `note` is one line, max 80 characters, and prompts forbid sending one unless explicitly directed.
- A Babashka daemon (`handoffd`) polls each outbox, copies the file into every recipient's `inbox/new/`, stamps `recipient` and `enqueued_at`, sends a generic tmux wake-up, and moves the original to `sent/` or `failed/`. Delivery is transaction-like and idempotent on retry.
- Queue state is directory location: `inbox/new/` → `inbox/in_process/` → `inbox/completed/`. Timestamps (`created_at`, `enqueued_at`, `dequeued_at`, `completed_at`) in the headers replace any logbook, each written by exactly one script.
- `merge_and_process.sh` checks `git merge-base --is-ancestor` before merging so re-delivery is a no-op.

### Porting guidance
- Define a tiny message schema (three to five headers) and one validator that is the only way to send. Make its error messages good enough for an agent to self-repair.
- The payload is a commit SHA. Prose goes in the commit message and the task document, not in the handoff.
- Fill identity, timestamps, and commit from the environment and git, never from the agent.
- Use atomic rename for every state transition. Use directories as queue states so `ls` is the monitoring tool.
- Make delivery and merge idempotent; you will replay after crashes.
- Ban free-form agent-to-agent messaging by default. Route questions to the human instead.

---

## 5. Legibility beats cleverness

### Principle
Orchestration you cannot watch is orchestration you will stop trusting. Every agent, every queue, and every decision should be visible with ordinary tools.

### SwarmForge implementation
- One tmux window per role, agent CLI in the foreground. Terminal adapters open real windows (Ghostty, iTerm2, Terminal.app, Windows Terminal, or none).
- A window watchdog re-attaches panes that disappear (three missing polls before action).
- A commit-msg hook appends `By <role>.` to every commit, so `git log` shows who did what. `--no-verify` is forbidden.
- Board state is a TSV (`.swarmforge/board/tasks.tsv`: name, lane, created, updated, task-id, audit-count) and a local web dashboard renders lanes per role, an Attention view, and chat.
- All state lives under `.swarmforge/` in the project. Nothing is in a database or a remote service.

### Porting guidance
- Choose file formats a human can `cat`: TSV, small text headers, one file per message.
- Keep an always-visible surface per agent (terminal, log tail, or pane). Hierarchies of agents spawning agents lose this fast; avoid them.
- Stamp provenance into git (author trailers, role bylines) so history explains itself.
- Build the dashboard as a read-only view over the files first; add controls (approve, reject, answer) second.

---

## 6. Human checkpoints at points of maximum leverage

### Principle
Approving a spec before code exists is cheap to review and expensive to get wrong. Approving every commit turns the human into a rubber stamp. Put one or two gates where a human decision changes the most, and route everything through them.

### SwarmForge implementation
- **Clarification**: `pack_dashboard_request.sh clarify ./tmp/question.txt` writes into `.swarmforge/chat/pending/`. The operator answers in the dashboard; the answer is injected into the agent's pane as `[id] text`, and the agent replies with `pack_dashboard_request.sh answer <id> ./tmp/answer.txt`. Agents are told never to ask in the pane.
- **Approval**: the master agent's (specifier's) `git_handoff` goes to a pending area and appears in the dashboard's Attention view. `approve!` moves it into the outbox; `reject` writes a notify file and can attach per-file review comments that the agent reads as findings on retry. The audit counter and task ID survive approve / reject / retry.
- **Task intent** lives in `tasks/<task-name>.md`, committed by the master agent, and agents are told to re-read it as operator intent.
- The pipeline's last role marks the card Done automatically; no human approval at the end by default.

### Porting guidance
- Identify the one artifact whose correctness gates everything downstream (spec, plan, interface). Gate there.
- Make "ask the human" a structured command with an ID, not a chat message. Track pending questions like tasks.
- Rejections should carry structured findings the agent can act on, not a re-prompt.
- Keep the human's task statement as a versioned file the agents re-read; do not let it live only in the initial prompt.

---

## 7. Linear pipelines beat free-form swarms

### Principle
Emergent negotiation among agents is unreliable and hard to debug. Start with a conveyor belt: fixed order, mandatory forwarding, one terminal condition.

### SwarmForge implementation
- Chain order is the order of lines in `swarmforge.conf`. Two-pack: coder → cleaner. Four-pack: specifier → coder → refactorer → architect. Six-pack: specifier → coder → cleaner → architect → hardender → QA.
- Every intermediate role must forward a `git_handoff` to the next role after completing an inbound task, even for formatting-only or manifest-only changes.
- `back-one` / `back-all` propagation queues merge-only (`non-forwarding`) copies to earlier roles so their trees stay current. `swarm_handoff.sh` refuses a forward while the inbound is `non-forwarding`, so back-propagation cannot create loops.
- A card is Done when the last role's handoff `to:` lists every other role (the set, not a count). Recipients merge and stop.
- Wake-ups are deliberately generic (`You have new handoff mail. If idle, run ready_for_next.sh.`) so agents process in sorted queue order and cannot cherry-pick.
- `ready_for_next_task.sh` refuses to accept new work while an item is in `in_process/`, and refuses ambiguous states (multiple in-process items) rather than guessing.

### Porting guidance
- Encode the pipeline as ordered configuration, not as agent decisions.
- Make forwarding unconditional so the pipeline never stalls on "nothing changed."
- Distinguish forward handoffs (move the card) from sync handoffs (merge only).
- Define termination as a structural condition the tooling can check, not as an agent's judgment.
- Refuse ambiguity. A helper that guesses is worse than one that stops and reports.

---

## 8. Durability and cost control

### Principle
Long runs must survive restarts, resume from state, and stop before they burn a budget. This is where most of the unglamorous engineering goes, and where most frameworks are weakest.

### SwarmForge implementation
- Restart state is the filesystem. On start, an agent runs `ready_for_next.sh`, which resumes any `in_process/` item before accepting new mail.
- Daemon delivery is transactional (copy to all inboxes → notify → move to `sent/`) with dedupe on retry. Daemon lifecycle is owned by the launcher (`TERM` trap, PID file, `stop` sentinel file).
- The host is kept awake with `caffeinate -dims` (macOS) or `systemd-inhibit` (Linux), disabled by `SWARMFORGE_PREVENT_SLEEP=0`.
- Cost levers: pack size (two / four / six roles), worker caps (`--max-workers 4`), differential mutation only, no concurrent verification tools, per-role backend choice (cheap model for cleanup, strong model for spec).
- Gaps: no token budget, no wall-clock limit, no loop detection beyond the audit counter.

### Porting guidance
- Make every helper idempotent and every state transition an atomic rename; then "resume" is just "run the loop again."
- Add what SwarmForge lacks: a per-task token or cost ceiling, a per-task wall-clock ceiling, and a max-audit / max-retry count that parks the card in a "needs human" lane.
- Run the orchestrator on an always-on machine if runs exceed an hour.
- Choose backends per role. Reviewers and cleaners rarely need the most expensive model.

---

## Minimum viable port

If building this from scratch on another project, the order that gets value earliest:

1. **Worktree per role + role environment variable.** (Idea 1)
2. **One validator script that is the only way to hand off**, with SHA filled from git and atomic outbox writes. (Idea 4)
3. **Inbox directories as queue state** and a `ready` / `done` helper pair that refuses ambiguity. (Ideas 4, 7)
4. **Fixed pipeline order in config**, unconditional forwarding, structural Done condition. (Idea 7)
5. **Two-call audit gate** before any handoff. (Idea 2)
6. **Layered prompt constitution** with owns / does-not-own per role, re-injected per task. (Idea 3)
7. **One human gate** at the spec or plan, via a structured clarify / approve command. (Idea 6)
8. **Terminal per agent + role bylines in commits + a file-backed board.** (Idea 5)
9. **Budgets and ceilings** that SwarmForge lacks. (Idea 8)

Everything above is a few hundred lines of scripts in any language plus git and a terminal multiplexer. Resist the pull toward a framework until these are working.

---

## Checklist for reviewing any orchestration design

- Can two agents ever write to the same file at the same time?
- Is the agent that says "done" different from the agent that decides "done"?
- Can each agent's full context fit in one screen of instructions?
- Can a human read every handoff and know what was asked and delivered?
- Can you `ls` your way to the current state of every task?
- Is there exactly one place a human must approve, and is it early?
- Is the order of work a config file or an agent's opinion?
- If the machine reboots mid-run, what happens when you start it again?
- What stops a task that has retried nine times?

---

## Source notes

- Repository: `github.com/unclebob/swarm-forge`, branches `main` (scripts, shared constitution, protocol doc) and `six-pack` (roles, config). No licence file was present as of September 2026; treat as all-rights-reserved and do not copy code without asking the author.
- Key files: `swarmforge/handoff-protocol.md`, `swarmforge/scripts/swarmforge.bb` (launcher), `swarm_handoff.bb` (validator and audit gate), `handoffd.bb` (daemon), `merge_and_process.bb`, `pack_web.bb` (dashboard), `constitution/articles/*.prompt`, `roles/*.prompt`.
- Vocabulary: Gherkin (Given/When/Then acceptance specs), CRAP (complexity × low coverage risk score), mutation testing (perturb code, expect tests to fail), property tests (rules over generated inputs).
