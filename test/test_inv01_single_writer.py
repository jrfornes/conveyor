"""Invariant 1: single writer per directory (protocol §2.3 ownership table)."""
import os
import unittest

from harness import ConveyorTest, layout, read


class SingleWriter(ConveyorTest):
    def test_files_land_only_where_their_creator_may_write(self):
        fx = self.run_pipeline("demo")
        op = fx.paths.role("operator")
        self.assertEqual(sorted(os.listdir(op.base)), ["outbox", "sent", "seq"])
        for role in ("coder", "reviewer"):
            rp = fx.paths.role(role)
            for f in layout.handoffs(rp.sent):
                self.assertEqual(fx.read_handoff(os.path.join(rp.sent, f))[0]["from"], role)
            for d in (rp.new, rp.in_process, rp.completed):
                for f in layout.handoffs(d):
                    self.assertEqual(fx.read_handoff(os.path.join(d, f))[0]["to"], role)
            self.assertEqual(os.listdir(rp.failed), [])
            self.assertEqual(os.listdir(rp.outbox_tmp), [])
            self.assertEqual(os.listdir(rp.inbox_tmp), [])

    def test_agent_written_outbox_file_is_rejected(self):
        """A handoff not produced by handoff.sh lacks id/from: the loop moves it to failed/."""
        fx = self.fx
        fx.script("coder", 'write ../../.conveyor/roles/coder/outbox/x.handoff "to: reviewer\\ntask: demo\\nverdict: ready\\n"\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        rp = fx.paths.role("coder")
        self.assertEqual(layout.handoffs(rp.outbox), [])
        self.assertIn("x.handoff", os.listdir(rp.failed))
        self.assertIn("missing header", read(os.path.join(rp.failed, "x.handoff.reason")))


if __name__ == "__main__":
    unittest.main()
