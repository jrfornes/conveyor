"""Worktree dependency setup: `[global] worktree_setup` (protocol §2.3, §6.3).

A role's worktree is born empty. On any project whose gates need installed
dependencies, that tree cannot run them until something installs them — once
per role, and again every time a merge brings in a new lockfile. This module
runs one opaque operator-supplied command at those two moments and refuses
when it fails.

Conveyor never learns what a package manager is. The command is a string; the
paths that trigger a re-run are a list; everything else is the operator's.
"""
import collections
import hashlib
import os

from . import util

STAMP = "setup.stamp"
LOG = "setup.log"

# What run() reports back. The exit code and the timeout flag are separate
# because the operator-facing message differs: "exited 1" sends them to the
# log, "timed out" sends them to worktree_setup_timeout.
Run = collections.namedtuple("Run", "ok code timed_out seconds log")


def enabled(cfg):
    """False means the feature is entirely off and no run path changes."""
    return bool(cfg.worktree_setup)


def stamp_path(paths, role):
    return os.path.join(paths.role(role).base, STAMP)


def log_path(paths, role):
    return os.path.join(paths.logs, role, LOG)


def _blob(wt, rel):
    """The oid of rel at the worktree's HEAD, or '-' when it is not there.

    From git, never from reading the file: it is exact, it is one cheap call,
    and it cannot disagree with what was actually merged. A directory hashes
    as its tree oid, so a watched directory works too."""
    return util.git(["rev-parse", "--verify", "--quiet", f"HEAD:{rel}"], wt, check=False) or "-"


def stamp(wt, cfg):
    """Content stamp for a worktree: the watched blobs plus the command.

    Never mtime — a git merge rewrites mtimes constantly and none of it is
    evidence. The command is in the hash on purpose: an operator who just
    fixed their install command expects it to re-run everywhere.
    """
    lines = [f"{rel} {_blob(wt, rel)}" for rel in cfg.worktree_setup_paths]
    lines.append(f"command {cfg.worktree_setup}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def read_stamp(paths, role):
    try:
        return util.read_text(stamp_path(paths, role)).strip()
    except OSError:
        return ""


def needs_run(paths, wt, cfg, role):
    """(bool, reason) with reason in {"create", "changed", ""}.

    No stamp means the tree has never been set up; a different stamp means a
    watched path or the command itself moved under it."""
    if not enabled(cfg):
        return False, ""
    current = read_stamp(paths, role)
    if not current:
        return True, "create"
    if current != stamp(wt, cfg):
        return True, "changed"
    return False, ""


def blobs(wt, cfg):
    """{watched path: oid at HEAD}, for naming what moved across a merge."""
    return {rel: _blob(wt, rel) for rel in cfg.worktree_setup_paths}


def diff_names(before, after):
    """Watched paths whose blob changed between two blobs() snapshots.

    Cosmetic only: it names the lockfile in the loop log. The stamp, not this,
    decides whether setup runs — a stamp that went stale because the command
    changed simply yields no names."""
    return [rel for rel, oid in after.items() if before.get(rel) != oid]


def label(reason, names):
    """`create` or `changed: pnpm-lock.yaml`, for the loop log and start output."""
    if reason == "changed" and names:
        return f"changed: {', '.join(names)}"
    return reason


def run(paths, root, wt, cfg, role, reason, commit=""):
    """Run the setup command in wt. Returns a Run; writes the stamp only on exit 0.

    A failed install must never look done: the next start (or the next merge)
    has to try again rather than trust a stamp written over a half-populated
    tree."""
    log = log_path(paths, role)
    env = {**os.environ, "CONVEYOR_ROOT": root, "CONVEYOR_ROLE": role,
           "CONVEYOR_WORKTREE": wt, "CONVEYOR_REASON": reason,
           "CONVEYOR_COMMIT": commit}
    code, timed_out, seconds = util.run_bounded(
        cfg.worktree_setup, wt, env, cfg.worktree_setup_timeout, log)
    ok = code == 0 and not timed_out
    if ok:
        util.atomic_write(stamp_path(paths, role), stamp(wt, cfg) + "\n")
    return Run(ok, code, timed_out, seconds, log)


def dirty_paths(wt, limit=5):
    """(first paths, total) from `git status` in the worktree after a setup run.

    -uall so an install that drops 4000 files under an unignored directory is
    counted as 4000, not as one collapsed entry: the number is the point.
    Conveyor cannot guess which paths an operator's install creates, so it
    says what it sees and leaves the .gitignore to them."""
    out = util.git(["status", "--porcelain", "--untracked-files=all"], wt, check=False)
    names = [line[3:] for line in out.splitlines() if line.strip()]
    return names[:limit], len(names)


def format_dirty(wt, names, total):
    """The warning locked decision 17 asks for: what handoff.sh will refuse, and why."""
    shown = ", ".join(names)
    more = ", …" if total > len(names) else ""
    return (f"warning: {wt} is dirty after setup — {shown}{more} ({total} paths). "
            f"handoff.sh refuses a dirty tree (E_DIRTY); add these to the committed "
            f".gitignore on that branch.")
