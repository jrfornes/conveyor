"""M1: operator task → coder ready → reviewer pass → merged on main; crash-safe."""
import os
import unittest

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, Fixture, layout

LOOP_CRASHES = ["after-dequeue", "after-merge", "after-agent", "after-complete-stamp",
                "after-complete", "after-inbox-tmp", "after-deliver", "before-sent"]
AGENT_CRASHES = {
    "coder-after-commit": ('commit "Implement $TASK"\nonce crash\ndraft reviewer $TASK ready\nhandoff\nhandoff\n', REVIEWER_PASS),
    "coder-after-draft": ('commit "Implement $TASK"\ndraft reviewer $TASK ready\nonce crash\nhandoff\nhandoff\n', REVIEWER_PASS),
    "coder-after-audit": ('commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nonce crash\nhandoff\n', REVIEWER_PASS),
    "coder-after-ok": ('commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nhandoff\nonce crash\n', REVIEWER_PASS),
    "reviewer-after-audit": (CODER_OK, 'commit --empty "Verified $TASK"\ndraft done $TASK pass\nhandoff\nonce crash\nhandoff\n'),
    "reviewer-after-ok": (CODER_OK, 'commit --empty "Verified $TASK"\ndraft done $TASK pass\nhandoff\nhandoff\nonce crash\n'),
}


class M1(ConveyorTest):
    def test_round_trip(self):
        fx = self.run_pipeline("demo")
        self.assertEqual(fx.board()["demo"]["lane"], "done")
        log = fx.git("log", "--format=%B", "main")
        self.assertIn("By coder.", log)
        self.assertIn("By reviewer.", log)
        self.assertTrue(os.path.isfile(os.path.join(fx.root, "work.txt")))
        self.assertEqual(len(layout.handoffs(fx.paths.role("coder").completed)), 1)
        self.assertEqual(len(layout.handoffs(fx.paths.role("reviewer").completed)), 1)
        self.assertEqual(len(layout.handoffs(fx.paths.role("reviewer").sent)), 1)
        h = fx.read_handoff(os.path.join(fx.paths.role("reviewer").sent,
                                         layout.handoffs(fx.paths.role("reviewer").sent)[0]))[0]
        self.assertEqual((h["from"], h["to"], h["verdict"]), ("reviewer", "done", "pass"))
        done = fx.read_handoff(os.path.join(fx.paths.role("reviewer").completed,
                                            layout.handoffs(fx.paths.role("reviewer").completed)[0]))[0]
        self.assertEqual(done["outcome"], "merged")
        self.assertIn("completed_at", done)

    def test_prompt_contains_task_and_inbound(self):
        fx = self.run_pipeline("demo")
        log = fx.logs("coder")
        self.assertIn("session_id", log)
        self.assertIn('"exit": 0', log)

    def test_status_after_run(self):
        fx = self.run_pipeline("demo")
        out = fx.conveyor("status").stdout
        self.assertIn("coder      idle", out)
        self.assertIn("  demo        done         audit 2  retry 0", out)  # one audit per role


class M1Crash(unittest.TestCase):
    """Invariant 11: a crash at any step boundary, then `conveyor start`, ends identically."""

    @classmethod
    def setUpClass(cls):
        cls.base = Fixture()
        cls.base.script("coder", CODER_OK)
        cls.base.script("reviewer", REVIEWER_PASS)
        cls.base.start()
        cls.base.conveyor("stop")
        cls.base.task("demo")
        cls.base.drive()
        cls.expected = cls.base.state()
        assert cls.expected["lanes"] == {"demo": "done"}, cls.expected

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def recover_and_compare(self, fx, label):
        fx.start()
        self.assertTrue(fx.wait_settled(), f"{label}: did not settle; state {fx.state()}")
        fx.conveyor("stop")
        self.assertEqual(fx.state(), self.expected, label)
        self.assertTrue(os.path.isfile(os.path.join(fx.root, "work.txt")), label)

    def test_loop_crash_at_every_boundary(self):
        for label in LOOP_CRASHES:
            fx = Fixture()
            try:
                fx.script("coder", CODER_OK)
                fx.script("reviewer", REVIEWER_PASS)
                fx.start()
                fx.conveyor("stop")
                marker = os.path.join(fx.tmp, "crashed")
                fx.task("demo")
                rcs = fx.drive(extra={"CONVEYOR_CRASH_AT": f"{label}:{marker}"})
                self.assertIn(-9, rcs, f"{label}: loop never crashed")
                self.recover_and_compare(fx, label)
            finally:
                fx.cleanup()

    def test_agent_crash_at_every_boundary(self):
        for label, (coder, reviewer) in AGENT_CRASHES.items():
            fx = Fixture()
            try:
                fx.script("coder", coder)
                fx.script("reviewer", reviewer)
                fx.start()
                fx.conveyor("stop")
                fx.task("demo")
                fx.drive(rounds=1)
                self.recover_and_compare(fx, label)
            finally:
                fx.cleanup()


if __name__ == "__main__":
    unittest.main()
