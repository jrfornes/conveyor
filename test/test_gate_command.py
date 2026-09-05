"""Project test command gate: ready/pass run the fence; findings/empty skip."""
import os
import unittest

from harness import CODER_OK, ConveyorTest, layout

CODER_READY = "to: reviewer\ntask: demo\nverdict: ready\n"
REVIEWER_PASS = "to: done\ntask: demo\nverdict: pass\n"
REVIEWER_FINDINGS = "to: coder\ntask: demo\nverdict: findings\n"


class GateCommand(ConveyorTest):
    def coder_ready(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop_crash("coder", "after-agent")
        return fx.paths.worktree("coder")

    def reviewer_in_process(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", 'commit --empty "Verified $TASK"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        fx.loop_crash("reviewer", "after-agent")
        return fx.paths.worktree("reviewer")

    def commit_fence(self, role, inner):
        wt = self.fx.paths.worktree(role)
        with open(os.path.join(wt, "project.md"), "w") as f:
            f.write("# Project\n\n## Test command\n\n```\n" + inner + "\n```\n")
        self.fx.git("add", "project.md", cwd=wt)
        self.fx.git("commit", "-q", "--no-verify", "-m", f"Set test command\n\nBy {role}.", cwd=wt)
        return wt

    def draft(self, role, text):
        path = os.path.join(self.fx.paths.worktree(role), "tmp", "handoff.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def gates_names(self):
        d = self.fx.paths.gates
        if not os.path.isdir(d):
            return []
        return os.listdir(d)

    def test_empty_and_comment_only_skip(self):
        self.coder_ready()
        self.draft("coder", CODER_READY)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("OK:"), r.stdout)
        self.assertEqual(self.gates_names(), [])

        self.commit_fence("coder", "")
        self.draft("coder", CODER_READY)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.gates_names(), [])

    def test_exit_0_still_audits(self):
        self.coder_ready()
        self.commit_fence("coder", "exit 0")
        self.draft("coder", CODER_READY)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("OK:"), r.stdout)
        self.assertEqual(self.gates_names(), [])

    def test_exit_1_ready_refuses_before_audit(self):
        self.coder_ready()
        self.commit_fence("coder", "echo gate-fail; exit 1")
        self.draft("coder", CODER_READY)
        rp = self.fx.paths.role("coder")
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(r.stdout.startswith("E_GATE_FAILED:"), r.stdout)
        self.assertEqual(os.listdir(rp.audit_pending), [])
        self.assertEqual(layout.handoffs(rp.outbox), [])
        names = self.gates_names()
        self.assertEqual(len(names), 1, names)
        with open(os.path.join(self.fx.paths.gates, names[0]), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("gate-fail", log)
        self.assertIn("exit: 1", log)
        self.assertIn("echo gate-fail; exit 1", log)

    def test_exit_1_findings_skips_gate(self):
        self.reviewer_in_process()
        self.commit_fence("reviewer", "echo gate-fail; exit 1")
        self.draft("reviewer", REVIEWER_FINDINGS)
        rp = self.fx.paths.role("reviewer")
        r = self.fx.handoff("reviewer")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("reviewer")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("OK:"), r.stdout)
        self.assertEqual(len(layout.handoffs(rp.outbox)), 1)
        self.assertEqual(self.gates_names(), [])

    def test_exit_1_pass_fails(self):
        self.reviewer_in_process()
        self.commit_fence("reviewer", "echo gate-fail; exit 1")
        self.draft("reviewer", REVIEWER_PASS)
        rp = self.fx.paths.role("reviewer")
        r = self.fx.handoff("reviewer")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(r.stdout.startswith("E_GATE_FAILED:"), r.stdout)
        self.assertEqual(os.listdir(rp.audit_pending), [])
        self.assertEqual(layout.handoffs(rp.outbox), [])
        names = self.gates_names()
        self.assertEqual(len(names), 1, names)
        with open(os.path.join(self.fx.paths.gates, names[0]), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("gate-fail", log)


if __name__ == "__main__":
    unittest.main()
