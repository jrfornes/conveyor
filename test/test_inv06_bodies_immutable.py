"""Invariant 6: a handoff body is byte-identical to its commit's message."""
import os
import subprocess
import unittest

from harness import REVIEWER_FINDINGS, ConveyorTest, layout


class BodiesImmutable(ConveyorTest):
    coder_conf = "max_retries=1"

    def test_every_stored_handoff(self):
        fx = self.run_pipeline("demo", reviewer=REVIEWER_FINDINGS)
        seen = 0
        for role in ("operator", "coder", "reviewer"):
            rp = fx.paths.role(role)
            dirs = [rp.sent] + ([] if role == "operator" else [rp.new, rp.in_process, rp.completed])
            for d in dirs:
                for f in layout.handoffs(d):
                    h, body = fx.read_handoff(os.path.join(d, f))
                    msg = subprocess.run(["git", "log", "-1", "--format=%B", h["commit"]], cwd=fx.root,
                                         capture_output=True, text=True, check=True).stdout
                    self.assertEqual(body, msg.rstrip("\n") + "\n", os.path.join(d, f))
                    self.assertTrue(body.rstrip().endswith(f"By {h['from']}."))
                    seen += 1
        parked = os.path.join(fx.paths.needs_human, "demo", "item.handoff")
        self.assertTrue(os.path.exists(parked))
        h, body = fx.read_handoff(parked)
        self.assertIn("1. requirement 1 - not proven", body)
        self.assertGreater(seen, 4)


if __name__ == "__main__":
    unittest.main()
