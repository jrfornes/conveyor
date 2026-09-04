"""Invariant 5: merge.sh twice == merge.sh once; conflicts leave the tree clean."""
import os
import subprocess
import unittest

from harness import BIN, ConveyorTest


class IdempotentMerge(ConveyorTest):
    def merge(self, commit, cwd, role="coder"):
        return subprocess.run([os.path.join(BIN, "merge.sh"), commit], cwd=cwd,
                              env=self.fx.role_env(role), capture_output=True, text=True).returncode

    def test_twice_is_once(self):
        fx = self.fx
        fx.start()
        fx.conveyor("stop")
        with open(os.path.join(fx.root, "new.txt"), "w") as f:
            f.write("x")
        fx.git("add", "new.txt")
        fx.git("commit", "-q", "-m", "On main")
        c = fx.git("rev-parse", "--short=10", "HEAD")
        wt = fx.paths.worktree("coder")
        self.assertEqual(self.merge(c, wt), 0)
        head = fx.git("rev-parse", "HEAD", cwd=wt)
        self.assertEqual(self.merge(c, wt), 0)
        self.assertEqual(fx.git("rev-parse", "HEAD", cwd=wt), head)
        self.assertEqual(fx.git("status", "--porcelain", cwd=wt), "")

    def test_conflict_exits_1_and_aborts(self):
        fx = self.fx
        fx.start()
        fx.conveyor("stop")
        wt = fx.paths.worktree("coder")
        for cwd, text in ((fx.root, "main"), (wt, "coder")):
            with open(os.path.join(cwd, "work.txt"), "w") as f:
                f.write(text)
            fx.git("add", "work.txt", cwd=cwd)
            fx.git("commit", "-q", "-m", f"Add work.txt ({text})", cwd=cwd)
        c = fx.git("rev-parse", "--short=10", "HEAD")
        head = fx.git("rev-parse", "HEAD", cwd=wt)
        self.assertEqual(self.merge(c, wt), 1)
        self.assertEqual(fx.git("rev-parse", "HEAD", cwd=wt), head)
        self.assertEqual(fx.git("status", "--porcelain", cwd=wt), "")
        self.assertFalse(os.path.exists(os.path.join(wt, ".git", "MERGE_HEAD")))

    def test_merge_commit_carries_byline(self):
        fx = self.fx
        fx.start()
        fx.conveyor("stop")
        wt = fx.paths.worktree("coder")
        for cwd, name in ((fx.root, "a.txt"), (wt, "b.txt")):
            with open(os.path.join(cwd, name), "w") as f:
                f.write(name)
            fx.git("add", name, cwd=cwd)
            fx.git("commit", "-q", "-m", f"Add {name}", cwd=cwd)
        self.assertEqual(self.merge(fx.git("rev-parse", "HEAD"), wt), 0)
        self.assertTrue(fx.git("log", "-1", "--format=%B", cwd=wt).endswith("By coder."))


if __name__ == "__main__":
    unittest.main()
