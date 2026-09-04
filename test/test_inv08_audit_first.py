"""Invariant 8: no handoff reaches outbox/ without an accepted fingerprint."""
import os
import unittest

from harness import ConveyorTest, layout, read


class AuditFirst(ConveyorTest):
    def test_audit_count_at_least_one_per_sent_handoff(self):
        fx = self.run_pipeline("demo")
        self.assertGreaterEqual(int(fx.board()["demo"]["audit_count"]), 1)
        self.assertEqual(int(fx.board()["demo"]["audit_count"]), 2)

    def test_fingerprint_file_lifecycle(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop_crash("coder", "after-agent")
        rp = fx.paths.role("coder")
        self.assertEqual(layout.handoffs(rp.outbox), [])
        fp = read(os.path.join(rp.audit_pending, "demo.fp")).split("\n")
        self.assertTrue(fp[0].startswith("fp: "))
        self.assertTrue(fp[1].startswith("commit: "))
        self.assertTrue(fp[2].startswith("challenged_at: "))
        self.assertFalse(os.path.exists(rp.seq), "a challenged submission must not consume a sequence number")
        # identical resubmission from the same worktree is accepted without a new challenge
        r = fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(len(layout.handoffs(rp.outbox)), 1)
        self.assertFalse(os.path.exists(os.path.join(rp.audit_pending, "demo.fp")))
        self.assertEqual(fx.board()["demo"]["audit_count"], "1")


if __name__ == "__main__":
    unittest.main()
