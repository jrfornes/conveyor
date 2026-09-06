#!/usr/bin/env python3
"""Conveyor handoff validator and audit gate (protocol §4–5).

Usage: handoff.sh <draft-path>
Exit 0: queued. Exit 2: AUDIT_REQUIRED. Exit 1: any E_* error."""
import hashlib
import os
import subprocess
import sys

if sys.version_info < (3, 10):
    print(f"conveyor requires Python 3.10+ (found {sys.version.split()[0]} at {sys.executable})",
          file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from conveyor import board, config, gates, handoff, layout, queue, util  # noqa: E402

ERRORS = {
    "E_ENV": ("CONVEYOR_ROLE or CONVEYOR_WORKTREE not set",
              "You are not running inside a Conveyor role loop. Stop and report this."),
    "E_DRAFT_PATH": ("draft is outside ./tmp/",
                     "Write the draft to ./tmp/handoff.txt inside your worktree and run handoff.sh ./tmp/handoff.txt"),
    "E_DIRTY": ("worktree has uncommitted changes",
                "Commit or discard all changes, then retry. Handoffs carry commits, not working trees."),
    "E_WRONG_BRANCH": ("HEAD is not conveyor-{role}",
                       "Run: git checkout conveyor-{role}. Do not create or switch branches."),
    "E_NO_INBOUND": ("nothing in inbox/in_process",
                     "You have no task in process. Do not hand off. Finish your run."),
    "E_TASK_MISMATCH": ("draft task ≠ in-process task",
                        "Your in-process task is {task}. Set `task: {task}`."),
    "E_PARSE": ("line {n} is not `key: value`",
                "Each line must be `key: value` with lowercase key and a single space after the colon."),
    "E_DRAFT_HAS_BODY": ("draft has content after a blank line",
                         "Remove everything after the three header lines. Prose belongs in your commit message."),
    "E_RESERVED_HEADER": ("header `{key}` is filled by the system",
                          "Delete the `{key}` line. Never write from, commit, id, type, task_id or timestamps yourself."),
    "E_UNKNOWN_HEADER": ("header `{key}` is not recognised",
                         "Only `to`, `task` and `verdict` are allowed."),
    "E_MISSING_HEADER": ("`{key}` is required", "Add `{key}: <value>`."),
    "E_BAD_RECIPIENT": ("`{to}` is not a role", "Valid recipients: {list}, done."),
    "E_BAD_VERDICT": ("`{verdict}` is not valid", "Valid verdicts: ready, pass, findings."),
    "E_BAD_ROUTE": ("{role} may not send `{verdict}` to `{to}`",
                    "As {role} you may send: {rows}."),
    "E_TASK_FILE": ("tasks/{task}.md not at HEAD",
                    "The task file must be committed. Do not create task files; report this."),
    "E_NOT_MY_TASK": ("board lane for {task} is {lane}, not {role}",
                      "This task is not in your lane. Do not hand off. Finish your run and report this."),
    "E_NO_BYLINE": ("HEAD commit lacks `By {role}.`",
                    "Amend the commit without --no-verify: git commit --amend --no-edit"),
    "E_NO_CHANGE": ("HEAD equals the inbound commit",
                    "You have not committed anything. Commit your work (or, as reviewer, an empty commit carrying findings) and retry."),
    "E_AMBIGUOUS_SHA": ("10-char abbreviation is ambiguous",
                        "Report this to the operator; it requires a longer abbreviation."),
    "E_LOCK": ("could not acquire a lock within 30 s", "Retry once. If it fails again, report it."),
    "E_GATE_PARSE": ("project.md gate catalog is invalid",
                     "Fix ## Gates / ## Required on (or use only ## Test command). See docs/conveyor-handoff-protocol.md."),
    "E_GATE_UNKNOWN": ("required gate `{name}` has no command",
                       "Add `{name}` under ## Gates in project.md, or remove it from ## Required on."),
    "E_GATE_SUBST": ("gate command uses unknown placeholder {token}",
                     "Use only `{{inbound}}` and `{{head}}` in gate commands."),
    "E_GATE_FAILED": ("gate {name} failed (exit {n})",
                      "Fix the failures, commit, and retry. Output: .conveyor/logs/gates/{role}-{task}-{commit}-{name}.txt"),
}

AUDIT_TEXT = """AUDIT_REQUIRED: handoff for {task} not queued (audit {n})
  Before resubmitting, re-read tasks/{task}.md and your role file.
  For every requirement in the task, find the commit, test, or output that proves it is met.
  If anything is missing, fix it, commit, and run handoff.sh again with the new commit.
  If everything is proven, run exactly the same command again to queue this handoff."""


def fail(code, **kw):
    problem, repair = ERRORS[code]
    print(f"{code}: {problem.format(**kw)}")
    print(f"  {repair.format(**kw)}")
    sys.exit(1)


def inside(path, parent):
    path, parent = os.path.realpath(path), os.path.realpath(parent)
    return path == parent or path.startswith(parent + os.sep)


def main():
    role = os.environ.get("CONVEYOR_ROLE")
    wt = os.environ.get("CONVEYOR_WORKTREE")
    if not role or not wt or not inside(os.getcwd(), wt) or len(sys.argv) != 2:
        fail("E_ENV")
    try:
        root = layout.find_root()
        cfg = config.load(root)
        cfg.role(role)
    except config.ConfigError:
        fail("E_ENV")
    paths = layout.Paths(root)
    rp = paths.role(role)
    draft = sys.argv[1]
    intake = role == config.INTAKE_ROLE
    # §4.1 preconditions
    if not inside(draft, os.path.join(wt, "tmp")) or not os.path.isfile(draft):
        fail("E_DRAFT_PATH")
    if util.git(["status", "--porcelain"], wt):
        fail("E_DIRTY")
    if util.git(["rev-parse", "--abbrev-ref", "HEAD"], wt) != f"conveyor-{role}":
        fail("E_WRONG_BRANCH", role=role)
    items = layout.handoffs(rp.in_process)
    if len(items) != 1:
        fail("E_NO_INBOUND")
    inbound = handoff.read(os.path.join(rp.in_process, items[0]))[0]
    # §4.2 draft validation
    try:
        h, body = handoff.parse(util.read_text(draft))
    except handoff.ParseError as e:
        fail("E_PARSE", n=e.lineno)
    if body.strip():
        fail("E_DRAFT_HAS_BODY")
    for key in h:
        if key in handoff.VALIDATOR or key in handoff.LOOP:
            fail("E_RESERVED_HEADER", key=key)
        if key not in handoff.AGENT:
            fail("E_UNKNOWN_HEADER", key=key)
    for key in handoff.AGENT:
        if key not in h:
            fail("E_MISSING_HEADER", key=key)
    to, task, verdict = h["to"], h["task"], h["verdict"]
    if task != inbound["task"]:
        fail("E_TASK_MISMATCH", task=inbound["task"])
    allowed = list(cfg.names()) + ["done"] + (["operator"] if intake else [])
    if to not in allowed:
        fail("E_BAD_RECIPIENT", to=to, list=", ".join(cfg.names()))
    if verdict not in config.VERDICTS:
        fail("E_BAD_VERDICT", verdict=verdict)
    if (role, to, verdict) not in cfg.routes():
        rows = "; ".join(f"to: {t}, verdict: {v}" for f, t, v in sorted(cfg.routes()) if f == role)
        fail("E_BAD_ROUTE", role=role, to=to, verdict=verdict, rows=rows)
    if not intake and not util.git_ok(["cat-file", "-e", f"HEAD:tasks/{task}.md"], wt):
        fail("E_TASK_FILE", task=task)
    if not intake:
        row = board.get(paths, task)
        if row is None or row["lane"] != role:
            fail("E_NOT_MY_TASK", task=task, lane=row["lane"] if row else "absent", role=role)
    # §4.3 commit validation, §4.4 canonicalization
    message = subprocess.run(["git", "log", "-1", "--format=%B", "HEAD"], cwd=wt,
                             capture_output=True, text=True, check=True).stdout
    head = util.git(["rev-parse", "HEAD"], wt)
    commit = util.git(["rev-parse", "--short=10", "HEAD"], wt)
    if verdict != "pass" and head.startswith(inbound["commit"]):
        fail("E_NO_CHANGE")  # before E_NO_BYLINE: amending the inbound commit would be wrong
    last = [l for l in message.split("\n") if l.strip()]
    if not last or last[-1] != f"By {role}.":
        fail("E_NO_BYLINE", role=role)
    resolved = util.git(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"], wt, check=False)
    if len(commit) != 10 or resolved != head:
        fail("E_AMBIGUOUS_SHA")
    body = message.rstrip("\n") + "\n"
    run_project_gates(paths, wt, cfg, role, task, verdict, commit, inbound["commit"], intake)
    try:
        gate(paths, rp, role, task, to, verdict, commit, body, intake=intake)
    except util.LockTimeout:
        fail("E_LOCK")


def run_project_gates(paths, wt, cfg, role, task, verdict, commit, inbound_commit, intake):
    if intake or verdict == "findings":
        return
    path = os.path.join(wt, "project.md")
    text = util.read_text(path) if os.path.isfile(path) else ""
    try:
        catalog = gates.parse(text)
    except gates.GateParseError:
        fail("E_GATE_PARSE")
    head = util.git(["rev-parse", "--short=10", "HEAD"], wt)
    for name in gates.required(catalog, role, verdict, cfg.names()):
        if name not in catalog.commands:
            fail("E_GATE_UNKNOWN", name=name)
        argv = catalog.commands[name]
        if not argv.strip():
            continue
        try:
            expanded = gates.expand(argv, inbound_commit, head)
        except gates.GateSubstError as e:
            fail("E_GATE_SUBST", token=e.token)
        try:
            gates.run(paths, wt, role, task, commit, name, expanded)
        except gates.GateFailedError as e:
            fail("E_GATE_FAILED", n=e.exit_code, role=role, task=task, commit=commit, name=name)


def gate(paths, rp, role, task, to, verdict, commit, body, intake=False):
    # §5 audit gate
    fp = hashlib.sha256(f"{commit}\n{to}\n{task}\n{verdict}\n".encode()).hexdigest()
    fpfile = os.path.join(rp.audit_pending, f"{task}.fp")
    pending = handoff.read(fpfile)[0] if os.path.exists(fpfile) else {}
    if pending.get("fp") != fp:
        util.atomic_write(fpfile, f"fp: {fp}\ncommit: {commit}\nchallenged_at: {util.now()}\n")
        n = "1"
        if not intake:
            n = board.update(paths, task, audit_count="+1")["audit_count"]
        print(AUDIT_TEXT.format(task=task, n=n))
        sys.exit(2)
    # §4.6 installation
    seq = queue.issue_seq(rp)
    if intake:
        task_id = f"intake-{task}"
    else:
        with util.lock(paths.board_lock):
            task_id = board.get(paths, task)["task_id"]
    headers = {"to": to, "task": task, "verdict": verdict, "type": "git_handoff",
               "id": f"{role}-{seq:06d}", "from": role, "commit": commit,
               "task_id": task_id, "created_at": util.now()}
    queue.install(rp, headers, body)
    os.remove(fpfile)
    print(f"OK: {headers['id']} queued for {to}")


if __name__ == "__main__":
    main()
