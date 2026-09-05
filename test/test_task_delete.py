"""task --delete removes audit_pending fingerprints so a recreated name is challenged,
and takes the needs-human entry with the board row so no ghost park survives."""
import os
import unittest

from harness import CODER_OK, ConveyorTest, board, layout, read


def audit_fps(fx):
    fps = []
    for role in os.listdir(fx.paths.roles):
        d = fx.paths.role(role).audit_pending
        if os.path.isdir(d):
            fps.extend(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".fp"))
    return fps


class TaskDelete(ConveyorTest):
    def test_delete_clears_fp_and_recreate_is_challenged(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop_crash("coder", "after-agent")
        self.assertEqual(os.listdir(fx.paths.role("coder").audit_pending), ["demo.fp"])
        fx.loop("coder")  # exhaust attempts → needs-human
        self.assertEqual(fx.parked_reason("demo")[0], "max-attempts")
        self.assertIn("demo.fp", os.listdir(fx.paths.role("coder").audit_pending))

        fx.conveyor("task", "demo", "--delete")
        self.assertEqual(audit_fps(fx), [])
        self.assertIsNone(fx.board().get("demo"))

        fx.script("coder", CODER_OK)
        fx.task("demo")
        fx.loop("coder")
        log = fx.logs("coder")
        self.assertIn("AUDIT_REQUIRED: handoff for demo not queued (audit 1)", log)
        self.assertEqual(fx.board()["demo"]["audit_count"], "1")

    def test_delete_after_done_clears_fps(self):
        fx = self.run_pipeline("demo")
        self.assertEqual(fx.board()["demo"]["lane"], "done")
        self.assertEqual(audit_fps(fx), [])

        fx.conveyor("task", "demo", "--delete")
        self.assertEqual(audit_fps(fx), [])

        fx.task("demo")
        fx.loop("coder")
        self.assertIn("AUDIT_REQUIRED", fx.logs("coder"))

    def park(self, task="demo"):
        """Drive a task into needs-human/ with reason max-attempts."""
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task(task)
        fx.loop_crash("coder", "after-agent")
        fx.loop("coder")
        self.assertEqual(fx.parked_reason(task)[0], "max-attempts")
        return fx

    def test_delete_parked_removes_the_park_directory(self):
        fx = self.park("demo")
        d = os.path.join(fx.paths.needs_human, "demo")
        self.assertTrue(os.path.isdir(d))

        out = fx.conveyor("task", "demo", "--delete").stdout
        self.assertIn("needs-human", out)
        self.assertFalse(os.path.exists(d))
        self.assertEqual(os.listdir(fx.paths.needs_human), [])
        self.assertIsNone(fx.board().get("demo"))

    def test_resume_refuses_when_the_board_row_is_gone(self):
        """Defensive: a row deleted out from under a park must not half-resume it."""
        fx = self.park("demo")
        d = os.path.join(fx.paths.needs_human, "demo")
        board.delete(fx.paths, "demo")  # the pre-fix state, reproduced directly

        r = fx.conveyor("resume", "demo", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("has no board row", r.stderr)
        # nothing moved: the handoff is still parked, not sitting in a live queue
        self.assertTrue(os.path.isfile(os.path.join(d, "item.handoff")))
        self.assertEqual(layout.handoffs(fx.paths.role("coder").new), [])


if __name__ == "__main__":
    unittest.main()
