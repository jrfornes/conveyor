"""The agent runs in its own process group, and the loop takes that group with it.

Terminating only the agent leaves children holding the stdout pipe the stamper is
blocked on, which trades one hang for another (protocol §6.7, §6.9).
"""
import os
import signal
import time
import unittest

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, gone, layout, read, wait_for

FAST = {"CONVEYOR_DRAIN_GRACE": "1", "CONVEYOR_KILL_GRACE": "1"}
CHILD = "601"  # distinctive, so a stray `sleep` from another test is never mistaken for ours


class ProcessGroups(ConveyorTest):
    def child_pid(self, role="coder"):
        path = os.path.join(self.fx.paths.worktree(role), "tmp", "child.pid")
        got = wait_for(lambda: os.path.exists(path) and read(path).strip())
        self.assertTrue(got, "fake-agent never recorded its child pid")
        return int(got)

    def test_orphan_holding_the_pipe_does_not_hang_the_loop(self):
        """The agent exits, but a child it spawned still holds stdout. The stamper
        would wait for an EOF that never comes; the group kill releases it."""
        fx = self.fx
        fx.script("coder", CODER_OK + f"spawn-child {CHILD}\n")
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        r = fx.loop("coder", FAST)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("demo: forwarded", r.stdout)
        self.assertEqual(fx.board()["demo"]["lane"], "reviewer")
        self.assertTrue(gone(self.child_pid()), "the orphan survived the loop")

    def test_stop_now_kills_the_agents_children(self):
        fx = self.fx
        fx.script("coder", f'commit "Implement $TASK"\nspawn-child {CHILD}\nsleep 600\n')
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.task("demo")
        pid = self.child_pid()
        fx.conveyor("stop", "--now")
        self.assertTrue(gone(pid), "stop --now left the agent's child running")
        rp = fx.paths.role("coder")
        self.assertEqual(len(layout.handoffs(rp.in_process)), 1)  # left for recovery (§6.7)

    def test_kill_9_of_the_loop_still_leaves_the_agent_running(self):
        """Invariant 11 is unchanged by start_new_session: the agent and the stamper
        outlive a killed loop, and the run still lands dated in the log."""
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nonce sleep 2\n'
                           'draft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.task("demo")
        time.sleep(1.0)  # the coder loop is inside the agent's sleep
        os.kill(int(read(os.path.join(fx.paths.role("coder").loop_lock, "pid"))), signal.SIGKILL)
        rp = fx.paths.role("coder")
        self.assertTrue(wait_for(lambda: layout.handoffs(rp.outbox)),
                        "the orphaned agent did not finish its handoff")
        text = fx.logs("coder")
        self.assertIn('"event": "run"', text)
        self.assertRegex(text, r'\{"at": "\d{4}-\d\d-\d\dT')


if __name__ == "__main__":
    unittest.main()
