"""Invariant 2: at most one in-process item per role; more than one refuses."""
import os
import shutil
import unittest

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, layout


class OneInProcess(ConveyorTest):
    def test_never_more_than_one_during_a_run(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.conveyor("stop")
        fx.task("a")
        fx.task("b")
        for _ in range(10):
            for role in ("coder", "reviewer"):
                fx.loop(role)
                self.assertLessEqual(len(layout.handoffs(fx.paths.role(role).in_process)), 1)
        self.assertEqual({r["lane"] for r in fx.board().values()}, {"done"})

    def test_two_in_process_refuses_to_start(self):
        fx = self.fx
        fx.script("coder", 'exit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("a")
        fx.loop_crash("coder", "after-agent")  # item stays in in_process
        rp = fx.paths.role("coder")
        item = layout.handoffs(rp.in_process)[0]
        shutil.copy(os.path.join(rp.in_process, item), os.path.join(rp.in_process, "z" + item))
        r = fx.loop("coder")
        self.assertEqual(r.returncode, 3)
        self.assertIn("ambiguous: 2 items in process", r.stdout)
        self.assertEqual(len(layout.handoffs(rp.in_process)), 2)


if __name__ == "__main__":
    unittest.main()
