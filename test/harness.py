"""Shared test fixture: a target repo with the bundle files, the fake agent, and
helpers to drive loops synchronously (`--once`) or via `conveyor start/stop`."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TEST_DIR)
BIN = os.path.join(REPO, "bin")
FAKE = os.path.join(TEST_DIR, "fake-agent")
sys.path.insert(0, os.path.join(REPO, "lib"))
from conveyor import board, handoff, layout  # noqa: E402

BUNDLE = ["constitution.md", "constitution", "roles", "project.md", "intake", ".gitignore"]
CODER_OK = 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nhandoff\n'
REVIEWER_PASS = 'commit --empty "Verified $TASK"\ndraft done $TASK pass\nhandoff\nhandoff\n'
REVIEWER_FINDINGS = ('commit --empty "Review: $TASK\\n\\n1. requirement 1 - not proven"\n'
                     'draft coder $TASK findings\nhandoff\nhandoff\n')
FINAL_LANES = {"done", "needs-human"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Fixture:
    def __init__(self, coder="max_retries=3 max_minutes=120 max_attempts=3",
                 reviewer="max_minutes=60 max_attempts=2"):
        self.tmp = tempfile.mkdtemp(prefix="conveyor-test-")
        self.root = os.path.join(self.tmp, "repo")
        self.scripts = os.path.join(self.tmp, "scripts")
        os.makedirs(self.scripts)
        os.makedirs(self.root)
        for f in BUNDLE:
            src = os.path.join(REPO, f)
            (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(self.root, f))
        with open(os.path.join(self.root, "conveyor.conf"), "w") as f:
            f.write(f"role coder composer-2.5 {coder}\nrole reviewer gpt-5 {reviewer}\n"
                    "[global]\npoll_seconds = 0.2\n")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Bundle")
        self.env = {**os.environ, "CONVEYOR_AGENT_BIN": FAKE, "CONVEYOR_FAKE_SCRIPT": self.scripts,
                    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@example.com"}
        self.env.pop("CONVEYOR_ROLE", None)
        self.env.pop("CONVEYOR_CRASH_AT", None)
        self.paths = layout.Paths(self.root)

    def cleanup(self):
        self.conveyor("stop", check=False)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- process helpers ---------------------------------------------------
    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True,
                              text=True, check=True).stdout.strip()

    def conveyor(self, *args, input=None, check=True, env=None):
        r = subprocess.run([os.path.join(BIN, "conveyor"), *args], cwd=self.root, input=input,
                           capture_output=True, text=True, env={**self.env, **(env or {})})
        if check and r.returncode != 0:
            raise AssertionError(f"conveyor {' '.join(args)} failed ({r.returncode}):\n{r.stdout}{r.stderr}")
        return r

    def start(self, *args):
        return self.conveyor("start", *args)

    def task(self, name, text="# Task\n\n1. Do the thing.\n"):
        return self.conveyor("task", name, input=text)

    def script(self, role, text):
        with open(os.path.join(self.scripts, role), "w") as f:
            f.write(text)

    def role_env(self, role, extra=None):
        return {**self.env, "CONVEYOR_ROLE": role, "CONVEYOR_WORKTREE": self.paths.worktree(role),
                "CONVEYOR_ROOT": self.root, **(extra or {})}

    def loop_crash(self, role, label):
        """Run the loop once and kill it at <label>, leaving its item in in_process."""
        r = self.loop(role, {"CONVEYOR_CRASH_AT": f"{label}:{os.path.join(self.tmp, 'crash-' + label)}"})
        assert r.returncode == -9, r
        return r

    def loop(self, role, extra=None):
        """Run role-loop.sh --once synchronously. Returns CompletedProcess (rc -9 = crashed)."""
        return subprocess.run([os.path.join(BIN, "role-loop.sh"), "--once"], cwd=self.root,
                              env=self.role_env(role, extra), capture_output=True, text=True)

    def handoff(self, role, draft="./tmp/handoff.txt", cwd=None, extra=None):
        return subprocess.run([os.path.join(BIN, "handoff.sh"), draft], cwd=cwd or self.paths.worktree(role),
                              env=self.role_env(role, extra), capture_output=True, text=True)

    # --- state helpers -------------------------------------------------------
    def board(self):
        return {r["name"]: r for r in board.read(self.paths)}

    def settled(self):
        rows = self.board()
        if not rows or any(r["lane"] not in FINAL_LANES for r in rows.values()):
            return False
        for role in ("operator", "coder", "reviewer"):
            rp = self.paths.role(role)
            if layout.handoffs(rp.outbox) or layout.handoffs(rp.new) or layout.handoffs(rp.in_process):
                return False
        return True

    def drive(self, rounds=20, extra=None):
        """Alternate coder/reviewer --once until settled. Returns list of return codes."""
        rcs = []
        for _ in range(rounds):
            if self.settled():
                break
            for role in ("coder", "reviewer"):
                rcs.append(self.loop(role, extra).returncode)
        return rcs

    def wait_settled(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.settled():
                return True
            time.sleep(0.2)
        return False

    def state(self):
        """End state per invariant 11: files modulo timestamps, lanes, parked tasks."""
        def norm(names):
            return sorted(n.split("_", 1)[1] for n in names)
        s = {}
        for role in ("operator", "coder", "reviewer"):
            rp = self.paths.role(role)
            s[f"{role}/sent"] = norm(layout.handoffs(rp.sent))
            if role != "operator":
                s[f"{role}/completed"] = norm(layout.handoffs(rp.completed))
        s["lanes"] = {k: v["lane"] for k, v in self.board().items()}
        s["parked"] = sorted(os.listdir(self.paths.needs_human)) if os.path.isdir(self.paths.needs_human) else []
        return s

    def parked_reason(self, task):
        return read(os.path.join(self.paths.needs_human, task, "reason")).split("\n")

    def logs(self, role):
        d = os.path.join(self.paths.logs, role)
        return "".join(read(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith(".jsonl"))

    def read_handoff(self, path):
        return handoff.read(path)


class ConveyorTest(unittest.TestCase):
    coder_conf = "max_retries=3 max_minutes=120 max_attempts=3"
    reviewer_conf = "max_minutes=60 max_attempts=2"

    def setUp(self):
        self.fx = Fixture(self.coder_conf, self.reviewer_conf)
        self.addCleanup(self.fx.cleanup)

    def run_pipeline(self, task="demo", coder=CODER_OK, reviewer=REVIEWER_PASS):
        """Start (no loops left running), create a task, drive to settled."""
        self.fx.script("coder", coder)
        self.fx.script("reviewer", reviewer)
        self.fx.start()
        self.fx.conveyor("stop")
        self.fx.task(task)
        self.fx.drive()
        return self.fx
