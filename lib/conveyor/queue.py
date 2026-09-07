"""Queue operations shared by the loops and the CLI: merge, delivery sweep,
park, dequeue, sequence numbers (protocol §3.4, §6.2, §6.5, §6.10, §7)."""
import glob
import os
import subprocess

from . import board, config, handoff, inbox, layout, util

REQUIRED = handoff.AGENT + handoff.VALIDATOR


UNTRACKED_MARK = "untracked working tree files would be overwritten"


def _untracked_names(out):
    """The indented paths git lists under its refuse-to-clobber error."""
    names, collecting = [], False
    for line in out.splitlines():
        if UNTRACKED_MARK in line:
            collecting = True
        elif collecting:
            if line[:1] in ("\t", " "):
                names.append(line.strip())
            else:
                break
    return names


def merge(commit, cwd, role):
    """Protocol §7.2. None = merged or already present. Otherwise a
    (park_reason, detail) pair: git refused, and *why* decides the repair, so the
    two refusals are not collapsed into one reason. A conflict needs the operator
    to reconcile two edits; an untracked file in the way needs it removed or
    untracked, and nothing was merged at all."""
    env = {**os.environ, "CONVEYOR_ROLE": role}
    if util.git_ok(["merge-base", "--is-ancestor", commit, "HEAD"], cwd):
        return None
    r = subprocess.run(["git", "merge", "--no-edit", commit], cwd=cwd, env=env,
                       capture_output=True, text=True)
    if r.returncode == 0:
        return None
    subprocess.run(["git", "merge", "--abort"], cwd=cwd, capture_output=True)
    names = _untracked_names(r.stdout + r.stderr)
    if names:
        return ("untracked-collision", f"would overwrite untracked {', '.join(names)}")
    return ("merge-conflict", "conflicted")


def _current_branch(root):
    """The branch checked out in the integration tree, or 'main' if detached."""
    return util.git(["symbolic-ref", "--short", "HEAD"], root, check=False) or "main"


def integrate_done(paths, cfg, src, h):
    """Apply the `done` integration policy (protocol §7.3). True = integrated (caller
    moves the item to sent); False = parked in place (caller continues)."""
    kind, command = cfg.integration_parts()
    if kind == "hold":
        return True
    if kind == "merge":
        fail = merge(h["commit"], paths.root, "operator")
        if fail is None:
            return True
        reason, detail = fail
        repair = "resolve on main" if reason == "merge-conflict" else "clear or untrack them on main"
        park(paths, src, h["task"], reason,
             f"merging {h['commit']} into main {detail}; {repair}, "
             f"then run: conveyor resume {h['task']}")
        return False
    # command: hand the reviewed commit to an operator-supplied hook (e.g. open a PR).
    base = cfg.integration_base or _current_branch(paths.root)
    log = os.path.join(paths.logs, "integration", f"{h['task']}-{h['commit']}.txt")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    env = {**os.environ, "CONVEYOR_ROOT": paths.root, "CONVEYOR_TASK": h["task"],
           "CONVEYOR_TASK_ID": h.get("task_id", ""), "CONVEYOR_COMMIT": h["commit"],
           "CONVEYOR_BRANCH": f"conveyor-{h['from']}", "CONVEYOR_BASE": base}
    r = subprocess.run(command, shell=True, cwd=paths.root, env=env,
                       capture_output=True, text=True)
    util.atomic_write(log, f"exit: {r.returncode}\ncommand: {command}\nbase: {base}\n"
                           f"--- stdout ---\n{r.stdout}--- stderr ---\n{r.stderr}")
    if r.returncode == 0:
        return True
    park(paths, src, h["task"], "done-command",
         f"integration command exited {r.returncode}; see logs/integration/"
         f"{h['task']}-{h['commit']}.txt, then run: conveyor resume {h['task']}")
    return False


def issue_seq(rp):
    """Protocol §3.4: next sequence number for a role, under seq.lock."""
    with util.lock(rp.seq_lock):
        try:
            n = int(util.read_text(rp.seq).strip() or 0)
        except FileNotFoundError:
            n = 0
        n += 1
        util.atomic_write(rp.seq, f"{n}\n")
    return n


def install(rp, headers, body):
    """Write a complete handoff into outbox/tmp, rename into outbox. Returns path."""
    name = handoff.filename(headers)
    tmp = os.path.join(rp.outbox_tmp, name)
    handoff.write(tmp, headers, body)
    dst = os.path.join(rp.outbox, name)
    os.rename(tmp, dst)
    return dst


def fail(rp, src, reason):
    name = os.path.basename(src)
    util.atomic_write(os.path.join(rp.failed, name + ".reason"), reason + "\n")
    os.rename(src, os.path.join(rp.failed, name))
    print(f"[{os.path.basename(rp.base)}] failed/{name}: {reason}", flush=True)


def park(paths, src, task, reason, detail):
    """Protocol §6.10. Reason is written first so a crash never leaves a bare item."""
    d = os.path.join(paths.needs_human, task)
    os.makedirs(d, exist_ok=True)
    util.atomic_write(os.path.join(d, "reason"), f"{reason}\n{detail}\n{util.now()}\n")
    os.rename(src, os.path.join(d, "item.handoff"))
    try:
        board.update(paths, task, lane="needs-human")
    except KeyError:
        pass
    print(f"parked {task}: {reason} ({detail})", flush=True)


def parked_items(paths):
    return glob.glob(os.path.join(paths.needs_human, "*", "item.handoff"))


def sweep(paths, cfg, role):
    """Protocol §6.5: deliver everything in <role>/outbox. Every step is re-runnable."""
    rp = paths.role(role)
    for f in layout.handoffs(rp.outbox):
        src = os.path.join(rp.outbox, f)
        try:
            h, body = handoff.read(src)
            missing = [k for k in REQUIRED if k not in h]
            if missing:
                raise handoff.ParseError(0, f"missing header {missing[0]}")
        except handoff.ParseError as e:
            fail(rp, src, f"parse-error: {e}")
            continue
        if handoff.filename(h) != f:
            fail(rp, src, "filename-header-mismatch")
            continue
        if os.path.exists(os.path.join(rp.sent, f)):
            os.remove(src)
            continue
        if h["from"] != config.INTAKE_ROLE and board.get(paths, h["task"]) is None:
            fail(rp, src, "no-board-row")
            continue
        if h["to"] == "done":
            if not integrate_done(paths, cfg, src, h):
                continue  # parked in place (conflict or hook failure)
            board.update(paths, h["task"], lane="done")
            os.rename(src, os.path.join(rp.sent, f))
            continue
        if h["to"] == "operator":
            if h["from"] != config.INTAKE_ROLE:
                fail(rp, src, f"unknown recipient {h['to']}")
                continue
            _apply_intake(paths, h)
            os.rename(src, os.path.join(rp.sent, f))
            continue
        if h["to"] not in cfg.names():
            fail(rp, src, f"unknown recipient {h['to']}")
            continue
        if role == cfg.gate_role() and h["verdict"] == "ready":
            os.makedirs(paths.approvals_pending, exist_ok=True)
            os.rename(src, os.path.join(paths.approvals_pending, f))
            board.update(paths, h["task"], lane=role)
            continue
        to = paths.role(h["to"])
        if handoff.find_id(h["id"], to.new, to.in_process, to.completed) or any(
                handoff.read(p)[0].get("id") == h["id"] for p in parked_items(paths)):
            os.rename(src, os.path.join(rp.sent, f))  # crashed after delivery
            continue
        tmp = os.path.join(to.inbox_tmp, f)
        handoff.write(tmp, {**h, "enqueued_at": util.now()}, body)
        util.crash_point("after-inbox-tmp")
        os.rename(tmp, os.path.join(to.new, f))
        util.crash_point("after-deliver")
        if h["verdict"] == "findings":
            board.update(paths, h["task"], lane=h["to"], retry_count="+1")
        else:
            board.update(paths, h["task"], lane=h["to"])
        util.crash_point("before-sent")
        os.rename(src, os.path.join(rp.sent, f))


def dequeue(paths, role, f):
    """Protocol §6.2. Returns the in_process path."""
    rp = paths.role(role)
    dst = handoff.move(os.path.join(rp.new, f), rp.in_process)
    h = handoff.stamp(dst, dequeued_at=util.now(), attempt=1)
    if role != config.INTAKE_ROLE:
        board.update(paths, h["task"], lane=role)
    return dst


def started_at(paths, row, h):
    """Protocol §6.6: earliest dequeued_at for this task_id, cached in the board."""
    if row["started_at"] != "-":
        return row["started_at"]
    earliest = h.get("dequeued_at")
    pattern = os.path.join(paths.roles, "*", "inbox", "*", "*.handoff")
    for p in glob.glob(pattern) + glob.glob(os.path.join(paths.roles, "*", "sent", "*.handoff")):
        try:
            other = handoff.read(p)[0]
        except (handoff.ParseError, OSError):
            continue
        d = other.get("dequeued_at")
        if other.get("task_id") == row["task_id"] and d and (earliest is None or d < earliest):
            earliest = d
    if earliest:
        board.update(paths, row["name"], started_at=earliest)
    return earliest


def _git_show(root, commit, rel):
    r = subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=root,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _apply_intake(paths, h):
    """Copy grade.md / proposed-task.md from the intake commit into the inbox item."""
    iid = h["task"]
    grade = _git_show(paths.root, h["commit"], "grade.md")
    proposed = _git_show(paths.root, h["commit"], "proposed-task.md")
    if grade:
        inbox.write_file(paths, iid, "grade.md", grade)
    if proposed:
        inbox.write_file(paths, iid, "proposed-task.md", proposed)
    status = "awaiting-approval" if proposed.strip() else "graded"
    inbox.update_meta(paths, iid, status=status, grade=inbox.parse_grade(grade))


def pending_approvals(paths):
    """Handoffs held in .conveyor/approvals/pending/."""
    out = []
    for f in layout.handoffs(paths.approvals_pending):
        p = os.path.join(paths.approvals_pending, f)
        try:
            h, body = handoff.read(p)
        except (handoff.ParseError, OSError):
            continue
        out.append({"file": f, "path": p, "headers": h, "body": body})
    return out


def find_pending(paths, hid):
    for item in pending_approvals(paths):
        if item["headers"].get("id") == hid or item["headers"].get("task") == hid:
            return item
    return None


def approve_pending(paths, cfg, hid):
    """Move a held specifier ready into the next role's inbox/new."""
    item = find_pending(paths, hid)
    if item is None:
        raise KeyError(hid)
    h, body, src = item["headers"], item["body"], item["path"]
    to = paths.role(h["to"])
    name = item["file"]
    tmp = os.path.join(to.inbox_tmp, name)
    handoff.write(tmp, {**h, "enqueued_at": util.now()}, body)
    os.rename(tmp, os.path.join(to.new, name))
    os.remove(src)
    board.update(paths, h["task"], lane=h["to"])
    return h


def reject_pending(paths, cfg, hid, comments):
    """Return a held ready to the gated role as findings-style notify. Preserves task_id."""
    item = find_pending(paths, hid)
    if item is None:
        raise KeyError(hid)
    h, src = item["headers"], item["path"]
    # Back to the role that produced the held handoff — the gated role. For a
    # three-pack that is names()[0], so this is a no-op there.
    target = cfg.gate_role() or h.get("from") or cfg.names()[0]
    if target not in cfg.names():
        target = cfg.names()[0]
    body = "Rejected by operator:\n\n" + (comments or "").rstrip() + "\n"
    stamped = {**h, "to": target, "verdict": "findings", "enqueued_at": util.now()}
    to = paths.role(target)
    name = handoff.filename(stamped)
    tmp = os.path.join(to.inbox_tmp, name)
    handoff.write(tmp, stamped, body)
    os.rename(tmp, os.path.join(to.new, name))
    os.remove(src)
    board.update(paths, h["task"], lane=target)
    return stamped   # stamped, not h: callers need the real recipient
