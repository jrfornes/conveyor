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
        self.gates = os.path.join(self.logs, "gates")
        self.worktrees = os.path.join(self.root, ".worktrees")
        self.inbox = os.path.join(self.conveyor, "inbox")
        self.inbox_lock = os.path.join(self.conveyor, "inbox.lock")
        self.approvals = os.path.join(self.conveyor, "approvals")
        self.approvals_pending = os.path.join(self.approvals, "pending")
        self.workflows = os.path.join(self.conveyor, "workflows")
        self.workflows_lock = os.path.join(self.conveyor, "workflows.lock")
        self.active = os.path.join(self.conveyor, "active")
        self.local = os.path.join(self.conveyor, "local")
        self.jira = os.path.join(self.local, "jira.json")

    def role(self, name):
        return RolePaths(os.path.join(self.roles, name))

    def worktree(self, name):
        return os.path.join(self.worktrees, name)

    def ensure_role_dirs(self, name, operator=False):
        for d in self.role(name).dirs(operator=operator):
            os.makedirs(d, exist_ok=True)
        if not operator:
            os.makedirs(os.path.join(self.logs, name), exist_ok=True)

    def ensure(self, cfg, extra_roles=()):
        self.ensure_role_dirs("operator", operator=True)
        for r in cfg.roles:
            self.ensure_role_dirs(r.name)
        for name in extra_roles:
            self.ensure_role_dirs(name)
        os.makedirs(self.needs_human, exist_ok=True)
        os.makedirs(self.inbox, exist_ok=True)
        os.makedirs(self.approvals_pending, exist_ok=True)
        os.makedirs(self.gates, exist_ok=True)
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


def loop_pid(paths, role):
    """Live pid from <role>/loop.lock/pid, else 0 (a stale pid file reads as 0)."""
    try:
        pid = int(util.read_text(os.path.join(paths.role(role).loop_lock, "pid")))
    except (OSError, ValueError):
        return 0
    return pid if util._pid_alive(pid) else 0


def running_roles(paths, cfg):
    """Configured roles whose loop is alive, in pipeline order."""
    if not os.path.isdir(paths.conveyor):
        return []
    return [n for n in cfg.names() if loop_pid(paths, n)]
