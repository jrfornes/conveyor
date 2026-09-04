"""Invariant 11: kill -9 of running loops mid-agent, then conveyor start, same end state."""
import os
import signal
import time
import unittest

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, read


class Restart(ConveyorTest):
    def test_kill_running_loops_and_restart(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nonce sleep 2\ndraft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.task("demo")
        time.sleep(1.0)  # coder loop is inside the agent's sleep
        pid = int(read(os.path.join(fx.paths.role("coder").loop_lock, "pid")))
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
        self.assertEqual(fx.board()["demo"]["lane"], "coder")
        fx.start()
        self.assertTrue(fx.wait_settled(), fx.state())
        fx.conveyor("stop")
        self.assertEqual(fx.state(), {
            "operator/sent": ["000001_from_operator_to_coder.handoff"],
            "coder/sent": ["000001_from_coder_to_reviewer.handoff"],
            "coder/completed": ["000001_from_operator_to_coder.handoff"],
            "reviewer/sent": ["000001_from_reviewer_to_done.handoff"],
            "reviewer/completed": ["000001_from_coder_to_reviewer.handoff"],
            "lanes": {"demo": "done"}, "parked": []})

    def test_stop_now_leaves_item_for_recovery(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nonce sleep 5\ndraft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.task("demo")
        time.sleep(1.0)
        fx.conveyor("stop", "--now")
        rp = fx.paths.role("coder")
        self.assertEqual(len(os.listdir(rp.in_process)), 1)
        self.assertFalse(os.path.exists(rp.loop_lock))
        fx.start()
        self.assertTrue(fx.wait_settled(), fx.state())
        fx.conveyor("stop")
        self.assertEqual(fx.board()["demo"]["lane"], "done")


if __name__ == "__main__":
    unittest.main()
