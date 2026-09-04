"""Every validator error code in protocol §4.5, with its exact repair text."""
import os
import shutil
import stat
import unittest

from harness import BIN, ConveyorTest, board, layout

REPAIR = {
    "E_ENV": "You are not running inside a Conveyor role loop. Stop and report this.",
    "E_DRAFT_PATH": "Write the draft to ./tmp/handoff.txt inside your worktree and run handoff.sh ./tmp/handoff.txt",
    "E_DIRTY": "Commit or discard all changes, then retry. Handoffs carry commits, not working trees.",
    "E_WRONG_BRANCH": "Run: git checkout conveyor-coder. Do not create or switch branches.",
    "E_NO_INBOUND": "You have no task in process. Do not hand off. Finish your run.",
    "E_TASK_MISMATCH": "Your in-process task is demo. Set `task: demo`.",
    "E_PARSE": "Each line must be `key: value` with lowercase key and a single space after the colon.",
    "E_DRAFT_HAS_BODY": "Remove everything after the three header lines. Prose belongs in your commit message.",
    "E_RESERVED_HEADER": "Delete the `commit` line. Never write from, commit, id, type, task_id or timestamps yourself.",
    "E_UNKNOWN_HEADER": "Only `to`, `task` and `verdict` are allowed.",
    "E_MISSING_HEADER": "Add `verdict: <value>`.",
    "E_BAD_RECIPIENT": "Valid recipients: coder, reviewer, done.",
    "E_BAD_VERDICT": "Valid verdicts: ready, pass, findings.",
    "E_BAD_ROUTE": "As coder you may send: to: reviewer, verdict: ready.",
    "E_TASK_FILE": "The task file must be committed. Do not create task files; report this.",
    "E_NOT_MY_TASK": "This task is not in your lane. Do not hand off. Finish your run and report this.",
    "E_NO_BYLINE": "Amend the commit without --no-verify: git commit --amend --no-edit",
    "E_NO_CHANGE": "You have not committed anything. Commit your work (or, as reviewer, an empty commit carrying findings) and retry.",
    "E_AMBIGUOUS_SHA": "Report this to the operator; it requires a longer abbreviation.",
    "E_LOCK": "Retry once. If it fails again, report it.",
}
PROBLEM = {
    "E_ENV": "CONVEYOR_ROLE or CONVEYOR_WORKTREE not set",
    "E_DRAFT_PATH": "draft is outside ./tmp/",
    "E_DIRTY": "worktree has uncommitted changes",
    "E_WRONG_BRANCH": "HEAD is not conveyor-coder",
    "E_NO_INBOUND": "nothing in inbox/in_process",
    "E_TASK_MISMATCH": "draft task ≠ in-process task",
    "E_PARSE": "line 1 is not `key: value`",
    "E_DRAFT_HAS_BODY": "draft has content after a blank line",
    "E_RESERVED_HEADER": "header `commit` is filled by the system",
    "E_UNKNOWN_HEADER": "header `foo` is not recognised",
    "E_MISSING_HEADER": "`verdict` is required",
    "E_BAD_RECIPIENT": "`nobody` is not a role",
    "E_BAD_VERDICT": "`maybe` is not valid",
    "E_BAD_ROUTE": "coder may not send `pass` to `done`",
    "E_TASK_FILE": "tasks/demo.md not at HEAD",
    "E_NOT_MY_TASK": "board lane for demo is reviewer, not coder",
    "E_NO_BYLINE": "HEAD commit lacks `By coder.`",
    "E_NO_CHANGE": "HEAD equals the inbound commit",
    "E_AMBIGUOUS_SHA": "10-char abbreviation is ambiguous",
    "E_LOCK": "could not acquire a lock within 30 s",
}
GOOD = "to: reviewer\ntask: demo\nverdict: ready\n"


class Errors(ConveyorTest):
    """Coder worktree left with one in-process item and one committed change."""

    def setUp(self):
        super().setUp()
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop_crash("coder", "after-agent")
        self.wt = fx.paths.worktree("coder")
        self.assertEqual(len(layout.handoffs(fx.paths.role("coder").in_process)), 1)

    def draft(self, text=GOOD, name="handoff.txt"):
        path = os.path.join(self.wt, "tmp", name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def expect(self, code, r, **fmt):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout, f"{code}: {PROBLEM[code]}\n  {REPAIR[code]}\n")

    def test_E_ENV(self):
        self.draft()
        env = {**self.fx.role_env("coder")}
        del env["CONVEYOR_ROLE"]
        import subprocess
        r = subprocess.run([os.path.join(BIN, "handoff.sh"), "./tmp/handoff.txt"], cwd=self.wt,
                           env=env, capture_output=True, text=True)
        self.expect("E_ENV", r)
        self.expect("E_ENV", self.fx.handoff("coder", draft=os.path.join(self.wt, "tmp", "handoff.txt"),
                                             cwd=self.fx.root))

    def test_E_DRAFT_PATH(self):
        with open(os.path.join(self.wt, "handoff.txt"), "w") as f:
            f.write(GOOD)
        r = self.fx.handoff("coder", draft="./handoff.txt")
        os.remove(os.path.join(self.wt, "handoff.txt"))
        self.expect("E_DRAFT_PATH", r)

    def test_E_DIRTY(self):
        self.draft()
        with open(os.path.join(self.wt, "scratch.txt"), "w") as f:
            f.write("x")
        self.expect("E_DIRTY", self.fx.handoff("coder"))

    def test_E_WRONG_BRANCH(self):
        self.draft()
        self.fx.git("checkout", "-q", "-b", "other", cwd=self.wt)
        self.expect("E_WRONG_BRANCH", self.fx.handoff("coder"))

    def test_E_NO_INBOUND(self):
        rp = self.fx.paths.role("coder")
        item = layout.handoffs(rp.in_process)[0]
        os.rename(os.path.join(rp.in_process, item), os.path.join(rp.completed, item))
        self.draft()
        self.expect("E_NO_INBOUND", self.fx.handoff("coder"))

    def test_E_TASK_MISMATCH(self):
        self.draft("to: reviewer\ntask: other\nverdict: ready\n")
        self.expect("E_TASK_MISMATCH", self.fx.handoff("coder"))

    def test_E_PARSE(self):
        self.draft("to reviewer\ntask: demo\nverdict: ready\n")
        self.expect("E_PARSE", self.fx.handoff("coder"))

    def test_E_DRAFT_HAS_BODY(self):
        self.draft(GOOD + "\nI did the thing.\n")
        self.expect("E_DRAFT_HAS_BODY", self.fx.handoff("coder"))

    def test_trailing_blank_lines_tolerated(self):
        self.draft(GOOD + "\n\n")
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_E_RESERVED_HEADER(self):
        self.draft(GOOD + "commit: 0123456789\n")
        self.expect("E_RESERVED_HEADER", self.fx.handoff("coder"))

    def test_E_UNKNOWN_HEADER(self):
        self.draft(GOOD + "foo: bar\n")
        self.expect("E_UNKNOWN_HEADER", self.fx.handoff("coder"))

    def test_E_MISSING_HEADER(self):
        self.draft("to: reviewer\ntask: demo\n")
        self.expect("E_MISSING_HEADER", self.fx.handoff("coder"))

    def test_E_BAD_RECIPIENT(self):
        self.draft("to: nobody\ntask: demo\nverdict: ready\n")
        self.expect("E_BAD_RECIPIENT", self.fx.handoff("coder"))

    def test_E_BAD_VERDICT(self):
        self.draft("to: reviewer\ntask: demo\nverdict: maybe\n")
        self.expect("E_BAD_VERDICT", self.fx.handoff("coder"))

    def test_E_BAD_ROUTE(self):
        self.draft("to: done\ntask: demo\nverdict: pass\n")
        self.expect("E_BAD_ROUTE", self.fx.handoff("coder"))

    def test_E_TASK_FILE(self):
        self.fx.git("rm", "-q", "tasks/demo.md", cwd=self.wt)
        self.fx.git("commit", "-q", "-m", "Drop task file", cwd=self.wt)
        self.draft()
        self.expect("E_TASK_FILE", self.fx.handoff("coder"))

    def test_E_NOT_MY_TASK(self):
        board.update(self.fx.paths, "demo", lane="reviewer")
        self.draft()
        self.expect("E_NOT_MY_TASK", self.fx.handoff("coder"))

    def test_E_NO_BYLINE(self):
        with open(os.path.join(self.wt, "work.txt"), "a") as f:
            f.write("more\n")
        self.fx.git("commit", "-q", "-a", "--no-verify", "-m", "Sneaky", cwd=self.wt)
        self.draft()
        self.expect("E_NO_BYLINE", self.fx.handoff("coder"))

    def test_E_NO_CHANGE(self):
        self.fx.git("reset", "-q", "--hard", "HEAD~1", cwd=self.wt)
        self.draft()
        self.expect("E_NO_CHANGE", self.fx.handoff("coder"))

    def test_E_AMBIGUOUS_SHA(self):
        shim = os.path.join(self.fx.tmp, "shim")
        os.makedirs(shim)
        real = shutil.which("git")
        with open(os.path.join(shim, "git"), "w") as f:
            f.write("#!/usr/bin/env python3\nimport os, sys\na = sys.argv[1:]\n"
                    "if a[:2] == ['rev-parse', '--short=10']:\n    a[1] = '--short=11'\n"
                    f"os.execv({real!r}, ['git', *a])\n")
        os.chmod(os.path.join(shim, "git"), stat.S_IRWXU)
        self.draft()
        r = self.fx.handoff("coder", extra={"PATH": shim + os.pathsep + os.environ["PATH"]})
        self.expect("E_AMBIGUOUS_SHA", r)

    def test_E_LOCK(self):
        os.mkdir(self.fx.paths.board_lock)
        with open(os.path.join(self.fx.paths.board_lock, "pid"), "w") as f:
            f.write(str(os.getpid()))
        self.draft()
        r = self.fx.handoff("coder", extra={"CONVEYOR_LOCK_TIMEOUT": "0.3"})
        shutil.rmtree(self.fx.paths.board_lock)
        self.expect("E_LOCK", r)

    def test_success_then_ok_exit_codes(self):
        self.draft()
        self.assertEqual(self.fx.handoff("coder").returncode, 2)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.stdout, "OK: coder-000001 queued for reviewer\n")


if __name__ == "__main__":
    unittest.main()
