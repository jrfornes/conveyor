"""Invariant 9: audit_count and retry_count never decrease."""
import unittest

from harness import CODER_OK, REVIEWER_FINDINGS, ConveyorTest


class Monotonic(ConveyorTest):
    coder_conf = "max_retries=2"

    def test_counters_only_grow_through_parking_and_resume(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_FINDINGS)
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        last = (0, 0)
        for _ in range(12):
            for role in ("coder", "reviewer"):
                fx.loop(role)
                row = fx.board()["demo"]
                cur = (int(row["audit_count"]), int(row["retry_count"]))
                self.assertGreaterEqual(cur, last)
                last = cur
        self.assertEqual(fx.board()["demo"]["lane"], "needs-human")
        fx.conveyor("resume", "demo")
        row = fx.board()["demo"]
        self.assertGreaterEqual((int(row["audit_count"]), int(row["retry_count"])), last)
        self.assertEqual(int(row["retry_count"]), 3)


if __name__ == "__main__":
    unittest.main()
