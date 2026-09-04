"""Invariant 4: exactly-once delivery, even when the sender crashes mid-sweep."""
import os
import unittest
from collections import Counter

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, layout


def id_counts(fx):
    c = Counter()
    for role in ("coder", "reviewer"):
        rp = fx.paths.role(role)
        for d in (rp.new, rp.in_process, rp.completed):
            for f in layout.handoffs(d):
                c[fx.read_handoff(os.path.join(d, f))[0]["id"]] += 1
    nh = fx.paths.needs_human
    for t in os.listdir(nh):
        p = os.path.join(nh, t, "item.handoff")
        if os.path.exists(p):
            c[fx.read_handoff(p)[0]["id"]] += 1
    return c


class ExactlyOnce(ConveyorTest):
    def check(self, fx):
        counts = id_counts(fx)
        self.assertTrue(all(n == 1 for n in counts.values()), counts)
        for role in ("operator", "coder", "reviewer"):
            rp = fx.paths.role(role)
            for f in layout.handoffs(rp.sent):
                h = fx.read_handoff(os.path.join(rp.sent, f))[0]
                if h["to"] != "done":
                    self.assertEqual(counts[h["id"]], 1, h["id"])

    def test_clean_run(self):
        self.check(self.run_pipeline("demo"))

    def test_crash_between_deliver_and_sent_does_not_duplicate(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_PASS)
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        marker = os.path.join(fx.tmp, "crashed")
        rcs = fx.drive(extra={"CONVEYOR_CRASH_AT": f"after-deliver:{marker}"})
        self.assertIn(-9, rcs)
        fx.drive()
        self.assertEqual(fx.board()["demo"]["lane"], "done")
        self.check(fx)
        self.assertEqual(len(layout.handoffs(fx.paths.role("coder").sent)), 1)


if __name__ == "__main__":
    unittest.main()
