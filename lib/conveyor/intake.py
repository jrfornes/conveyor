"""Intake module: operator-owned prompt + rubric under intake/.

ticket-reviewer is not a coding role. Its prompt lives here, not in roles/.
"""
import os
import shutil
import subprocess

from . import util

DIR = "intake"
PROMPT_REL = "intake/ticket-reviewer.md"
RUBRIC_REL = "intake/rubric.md"


class IntakeError(Exception):
    pass


def prompt_path(root):
    return os.path.join(root, PROMPT_REL)


def rubric_path(root):
    return os.path.join(root, RUBRIC_REL)


def read_rubric(root):
    """Rubric text, or "" when the file is absent (pre-Stage-4 repos)."""
    path = rubric_path(root)
    if not os.path.isfile(path):
        return ""
    return util.read_text(path)


def _git_dirty(target, rel):
    r = subprocess.run(["git", "status", "--porcelain", "--", rel],
                       cwd=target, capture_output=True, text=True)
    return bool(r.stdout.strip())


def migrate(target):
    """Carry roles/ticket-reviewer.md → intake/ before init's copy loops.

    intake/ always wins where both exist (it is what ensure_worktree reads).
    The dirty case is the one place we must not delete: unstaged work is
    unrecoverable. Prints what it did. Raises IntakeError to refuse.
    """
    old_rel = "roles/ticket-reviewer.md"
    old = os.path.join(target, old_rel)
    new = prompt_path(target)
    if not os.path.isfile(old):
        return
    os.makedirs(os.path.join(target, DIR), exist_ok=True)
    if not os.path.isfile(new):
        shutil.move(old, new)
        print(f"moved {old_rel} → {PROMPT_REL} (your edits were kept)")
        return
    if util.read_text(old) == util.read_text(new):
        os.remove(old)
        print(f"removed {old_rel} (identical to {PROMPT_REL})")
        return
    if _git_dirty(target, old_rel):
        print(f"warning: {PROMPT_REL} is what runs; merge {old_rel} by hand, then re-run init")
        raise IntakeError(
            f"{old_rel} has uncommitted edits that differ from {PROMPT_REL}; "
            f"merge by hand, then re-run init")
    os.remove(old)
    print(f"removed {old_rel} (differed from {PROMPT_REL}; recoverable from git)")
