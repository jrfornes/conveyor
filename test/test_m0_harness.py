"""M0: conveyor start creates worktrees with rules and the hook; refuses unknown models."""
import os
import unittest

from harness import ConveyorTest, read


class M0(ConveyorTest):
    def test_start_creates_harness(self):
        fx = self.fx
        fx.start()
        fx.conveyor("stop")
        for role in ("coder", "reviewer"):
            wt = fx.paths.worktree(role)
            self.assertTrue(os.path.isfile(os.path.join(wt, ".cursor", "rules", "conveyor-role.mdc")))
            self.assertEqual(fx.git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt), f"conveyor-{role}")
            rules = read(os.path.join(wt, ".cursor", "rules", "conveyor-role.mdc"))
            self.assertIn(f"# Role: {role}", rules)
            self.assertIn("# Handoffs", rules)
            self.assertTrue(os.path.isdir(os.path.join(wt, "tmp")))
        hook = os.path.join(fx.root, ".git", "hooks", "commit-msg")
        self.assertTrue(os.access(hook, os.X_OK))
        # byline hook signs a human commit as operator
        with open(os.path.join(fx.root, "note.txt"), "w") as f:
            f.write("x")
        fx.git("add", "note.txt")
        fx.git("commit", "-q", "-m", "Human commit")
        self.assertTrue(fx.git("log", "-1", "--format=%B").endswith("By operator."))
        self.assertTrue(os.path.isfile(fx.paths.board))
        self.assertTrue(os.path.isdir(fx.paths.role("operator").outbox_tmp))

    def test_start_is_idempotent_and_keeps_worktree_state(self):
        fx = self.fx
        fx.start()
        fx.conveyor("stop")
        wt = fx.paths.worktree("coder")
        with open(os.path.join(wt, "work.txt"), "w") as f:
            f.write("agent work")
        fx.git("add", "work.txt", cwd=wt)
        fx.git("commit", "-q", "-m", "Agent commit", cwd=wt)
        head = fx.git("rev-parse", "HEAD", cwd=wt)
        fx.start()
        fx.conveyor("stop")
        self.assertEqual(fx.git("rev-parse", "HEAD", cwd=wt), head)

    def test_refuses_unknown_model(self):
        r = self.fx.conveyor("start", check=False, env={"CONVEYOR_FAKE_MODELS": "other-model"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown model 'composer-2.5' for role coder", r.stderr)
        self.assertFalse(os.path.exists(self.fx.paths.worktree("coder")))


if __name__ == "__main__":
    unittest.main()
