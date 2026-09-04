"""Queue operations shared by the loops and the CLI: merge, delivery sweep,
park, dequeue, sequence numbers (protocol §3.4, §6.2, §6.5, §6.10, §7)."""
import glob
import os
import subprocess

from . import board, handoff, layout, util

REQUIRED = handoff.AGENT + handoff.VALIDATOR


def merge(commit, cwd, role):
    """Protocol §7.2. True = merged or already present; False = conflict (aborted)."""
    env = {**os.environ, "CONVEYOR_ROLE": role}
    if util.git_ok(["merge-base", "--is-ancestor", commit, "HEAD"], cwd):
        return True
    r = subprocess.run(["git", "merge", "--no-edit", commit], cwd=cwd, env=env,
                       capture_output=True, text=True)
    if r.returncode == 0:
        return True
    subprocess.run(["git", "merge", "--abort"], cwd=cwd, capture_output=True)
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
    board.update(paths, task, lane="needs-human")
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
        if board.get(paths, h["task"]) is None:
            fail(rp, src, "no-board-row")
            continue
        if h["to"] == "done":
            if not merge(h["commit"], paths.root, "operator"):
                park(paths, src, h["task"], "merge-conflict",
                     f"merging {h['commit']} into main conflicted; resolve on main, "
                     f"then run: conveyor resume {h['task']}")
                continue
            board.update(paths, h["task"], lane="done")
            os.rename(src, os.path.join(rp.sent, f))
            continue
        if h["to"] not in cfg.names():
            fail(rp, src, f"unknown recipient {h['to']}")
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
