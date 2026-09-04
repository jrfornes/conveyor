"""M2: audit gate and byline enforcement."""
import os
import unittest

from harness import REVIEWER_PASS, ConveyorTest, layout


def coder_log(fx):
    return fx.logs("coder")


class M2(ConveyorTest):
    def test_first_handoff_challenged_identical_second_accepted(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        log = coder_log(fx)
        self.assertIn("AUDIT_REQUIRED: handoff for demo not queued (audit 1)", log)
        self.assertIn("run exactly the same command again to queue this handoff", log)
        self.assertIn("OK: coder-000001 queued for reviewer", log)
        self.assertLess(log.index("AUDIT_REQUIRED"), log.index("OK: coder-000001"))
        self.assertEqual(fx.board()["demo"]["audit_count"], "1")
        self.assertEqual(os.listdir(fx.paths.role("coder").audit_pending), [])
        self.assertEqual(len(layout.handoffs(fx.paths.role("reviewer").new)), 1)

    def test_changed_candidate_is_challenged_again(self):
        fx = self.fx
        fx.script("coder", 'commit "First"\ndraft reviewer $TASK ready\nhandoff\n'
                           'commit "Second"\nhandoff\nhandoff\n')
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        log = coder_log(fx)
        self.assertIn("(audit 1)", log)
        self.assertIn("(audit 2)", log)
        self.assertIn("OK: coder-000001", log)
        self.assertEqual(fx.board()["demo"]["audit_count"], "2")

    def test_only_one_handoff_call_means_nothing_queued(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop_crash("coder", "after-agent")
        self.assertEqual(layout.handoffs(fx.paths.role("coder").outbox), [])
        self.assertEqual(os.listdir(fx.paths.role("coder").audit_pending), ["demo.fp"])
        self.assertEqual(fx.board()["demo"]["lane"], "coder")
        fx.loop("coder")  # attempts 2..3 re-run the script, each challenged anew, then park
        self.assertEqual(fx.parked_reason("demo")[0], "max-attempts")
        self.assertEqual(layout.handoffs(fx.paths.role("reviewer").new), [])

    def test_no_verify_commit_rejected(self):
        fx = self.fx
        fx.script("coder", 'commit --no-verify "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        log = coder_log(fx)
        self.assertIn("E_NO_BYLINE: HEAD commit lacks `By coder.`", log)
        self.assertIn("Amend the commit without --no-verify: git commit --amend --no-edit", log)
        self.assertEqual(layout.handoffs(fx.paths.role("coder").outbox), [])


if __name__ == "__main__":
    unittest.main()
