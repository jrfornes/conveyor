"""Throwaway target repo so `conveyor-ui --demo` can run without a real project."""
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONVEYOR = os.path.join(REPO, "bin", "conveyor")
_LIB = os.path.join(REPO, "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

TASK_DEMO = "# Demo\n\n1. Click through the cockpit.\n"
TASK_STUCK = "# Stuck\n\n1. This task is parked on purpose.\n"
TICKET = "# Sample ticket\n\n1. Grade or skip this from Inbox.\n"


class Demo:
    def __init__(self, tmp, root):
        self.tmp = tmp
        self.root = root

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _conveyor(root, *args, input_text=None):
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "Demo", "GIT_AUTHOR_EMAIL": "demo@example.com",
           "GIT_COMMITTER_NAME": "Demo", "GIT_COMMITTER_EMAIL": "demo@example.com"}
    env.pop("CONVEYOR_ROLE", None)
    r = subprocess.run([CONVEYOR, *args], cwd=root, input=input_text,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "command failed").strip())
    return r


def _park_task(root, name):
    from conveyor import config, handoff, layout, queue
    cfg = config.load(root)
    paths = layout.Paths(root)
    role = cfg.names()[0]
    new = paths.role(role).new
    for fname in layout.handoffs(new):
        src = os.path.join(new, fname)
        try:
            headers, _ = handoff.read(src)
        except handoff.ParseError:
            continue
        if headers.get("task") == name:
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
                queue.park(paths, src, name, "max-retries",
                           "demo fixture: sample parked item")
            return
    raise RuntimeError(f"demo: no inbox item to park for {name}")


def make_demo():
    """Initialized git checkout with a queued task, a parked task, and an inbox item."""
    tmp = tempfile.mkdtemp(prefix="conveyor-ui-demo-")
    root = os.path.join(tmp, "repo")
    os.makedirs(root)
    try:
        _git(root, "init", "-q", "-b", "main")
        _git(root, "config", "user.email", "demo@example.com")
        _git(root, "config", "user.name", "Demo")
        _conveyor(root, "init", root)
        _conveyor(root, "task", "demo", input_text=TASK_DEMO)
        _conveyor(root, "task", "stuck", input_text=TASK_STUCK)
        _conveyor(root, "import", "--source", "manual", "--title", "sample-ticket",
                  input_text=TICKET)
        from conveyor import config, inbox, layout, presets
        cfg = config.load(root)
        paths = layout.Paths(root)
        paths.ensure(cfg)
        presets.ensure_seeded(paths)
        inbox.create(paths, {
            "id": "proj-9",
            "source": "jira",
            "title": "Demo Jira ticket",
            "url": "https://example.atlassian.net/browse/PROJ-9",
            "external_id": "PROJ-9",
            "status": "imported",
        }, "# PROJ-9\n\n1. Fetched from Jira in the demo fixture.\n")
        _park_task(root, "stuck")
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return Demo(tmp, root)
