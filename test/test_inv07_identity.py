"""Invariant 7: identity headers are never agent-supplied, always validator-filled."""
import os
import re
import unittest

from harness import ConveyorTest, handoff, layout, read


class Identity(ConveyorTest):
    def test_drafts_bare_installed_complete(self):
        fx = self.run_pipeline("demo")
        for role in ("coder", "reviewer"):
            draft = read(os.path.join(fx.paths.worktree(role), "tmp", "handoff.txt"))
            self.assertEqual(sorted(handoff.parse(draft)[0]), ["task", "to", "verdict"])
            rp = fx.paths.role(role)
            for d in (rp.sent, rp.completed):
                for f in layout.handoffs(d):
                    h = fx.read_handoff(os.path.join(d, f))[0]
                    for k in handoff.VALIDATOR:
                        self.assertIn(k, h, f)
                    self.assertEqual(h["type"], "git_handoff")
                    self.assertRegex(h["commit"], r"^[0-9a-f]{10}$")
                    self.assertRegex(h["id"], r"^(operator|coder|reviewer)-\d{6}$")
                    self.assertRegex(h["created_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
                    self.assertEqual(h["task_id"], fx.board()["demo"]["task_id"])
                    self.assertEqual(f, handoff.filename(h))
                    keys = list(h)
                    self.assertEqual(keys, [k for k in handoff.ORDER if k in h], "header order")

    def test_operator_handoff_matches_validator_rules(self):
        fx = self.fx
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        rp = fx.paths.role("operator")
        f = layout.handoffs(rp.sent)[0]
        h, body = fx.read_handoff(os.path.join(rp.sent, f))
        self.assertEqual((h["from"], h["to"], h["verdict"], h["id"]), ("operator", "coder", "ready", "operator-000001"))
        self.assertTrue(body.rstrip().endswith("By operator."))
        self.assertTrue(fx.git("rev-parse", "HEAD").startswith(h["commit"]))
        self.assertTrue(re.match(r"^\d{8}T\d{6}Z_000001_from_operator_to_coder\.handoff$", f))


if __name__ == "__main__":
    unittest.main()
