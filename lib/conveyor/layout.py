"""Directory layout (protocol §2)."""
import os
import subprocess

from . import util


class RolePaths:
    def __init__(self, base):
        self.base = base
        self.outbox = os.path.join(base, "outbox")
        self.outbox_tmp = os.path.join(base, "outbox", "tmp")
        self.sent = os.path.join(base, "sent")
        self.failed = os.path.join(base, "failed")
        self.inbox = os.path.join(base, "inbox")
        self.inbox_tmp = os.path.join(base, "inbox", "tmp")
        self.new = os.path.join(base, "inbox", "new")
        self.in_process = os.path.join(base, "inbox", "in_process")
        self.completed = os.path.join(base, "inbox", "completed")
        self.seq = os.path.join(base, "seq")
        self.seq_lock = os.path.join(base, "seq.lock")
        self.audit_pending = os.path.join(base, "audit_pending")
        self.loop_lock = os.path.join(base, "loop.lock")
        self.stop = os.path.join(base, "stop")

    def dirs(self, operator=False):
        d = [self.outbox_tmp, self.sent]
        if not operator:
            d += [self.failed, self.inbox_tmp, self.new, self.in_process,
                  self.completed, self.audit_pending]
        return d


class Paths:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.conveyor = os.path.join(self.root, ".conveyor")
        self.board = os.path.join(self.conveyor, "board.tsv")
        self.board_lock = os.path.join(self.conveyor, "board.lock")
        self.roles = os.path.join(self.conveyor, "roles")
        self.needs_human = os.path.join(self.conveyor, "needs-human")
        self.logs = os.path.join(self.conveyor, "logs")
        self.worktrees = os.path.join(self.root, ".worktrees")

    def role(self, name):
        return RolePaths(os.path.join(self.roles, name))

    def worktree(self, name):
        return os.path.join(self.worktrees, name)

    def ensure(self, cfg):
        for d in self.role("operator").dirs(operator=True):
            os.makedirs(d, exist_ok=True)
        for r in cfg.roles:
            for d in self.role(r.name).dirs():
                os.makedirs(d, exist_ok=True)
            os.makedirs(os.path.join(self.logs, r.name), exist_ok=True)
        os.makedirs(self.needs_human, exist_ok=True)
        if not os.path.exists(self.board):
            util.atomic_write(self.board, "")


def find_root():
    """CONVEYOR_ROOT, else the parent of git's common dir (works from a worktree)."""
    root = os.environ.get("CONVEYOR_ROOT")
    if root:
        return root
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return os.path.dirname(r.stdout.strip())
    return os.getcwd()


def handoffs(directory):
    """Sorted *.handoff filenames in a directory (missing dir → [])."""
    try:
        return sorted(f for f in os.listdir(directory) if f.endswith(".handoff"))
    except FileNotFoundError:
        return []
