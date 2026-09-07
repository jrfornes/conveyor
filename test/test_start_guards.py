"""conveyor start refuses a tracked role rules file, and judges .gitignore by what
is committed -- the role worktrees never see the integration tree's working copy."""
import os
import unittest

from harness import ConveyorTest, read


class StartGuards(ConveyorTest):
    def rules_rel(self):
        return os.path.join(".cursor", "rules", "conveyor-role.mdc")

    def test_refuses_when_the_rules_file_is_tracked(self):
        fx = self.fx
        path = os.path.join(fx.root, self.rules_rel())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("stale rules\n")
        fx.git("add", "-f", "--", ".cursor/rules/conveyor-role.mdc")
        fx.git("commit", "-q", "-m", "Track the rules file by mistake")
        r = fx.conveyor("start", check=False)
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(".cursor/rules/conveyor-role.mdc is tracked in git on HEAD", out)
        self.assertIn("git rm --cached .cursor/rules/conveyor-role.mdc", out)
        self.assertFalse(os.path.isdir(fx.paths.worktrees))

    def test_warns_on_the_committed_gitignore_not_the_working_copy(self):
        fx = self.fx
        gi = os.path.join(fx.root, ".gitignore")
        kept = [l for l in read(gi).splitlines() if l != ".cursor/rules/conveyor-role.mdc"]
        with open(gi, "w") as f:
            f.write("\n".join(kept) + "\n")
        fx.git("commit", "-q", "-a", "-m", "Drop the rules entry from .gitignore")
        with open(gi, "a") as f:  # back in the working copy only -- what init leaves behind
            f.write(".cursor/rules/conveyor-role.mdc\n")
        r = fx.conveyor("start", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("committed .gitignore lacks .cursor/rules/conveyor-role.mdc", r.stdout)

    def test_quiet_when_the_committed_gitignore_is_complete(self):
        r = self.fx.conveyor("start", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("committed .gitignore lacks", r.stdout)


if __name__ == "__main__":
    unittest.main()
