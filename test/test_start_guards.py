"""conveyor start refuses a tracked role rules file, and commits missing
.gitignore entries so role worktrees actually ignore runtime paths."""
import os
import unittest

from harness import ConveyorTest, read


GITIGNORE = [".worktrees/", ".conveyor/", ".cursor/rules/conveyor-role.mdc", "tmp/"]


class StartGuards(ConveyorTest):
    def rules_rel(self):
        return os.path.join(".cursor", "rules", "conveyor-role.mdc")

    def drop_gitignore(self, *entries, commit=True):
        gi = os.path.join(self.fx.root, ".gitignore")
        kept = [l for l in read(gi).splitlines() if l not in entries]
        with open(gi, "w") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
        if commit:
            self.fx.git("commit", "-q", "-a", "-m", "Drop gitignore entries")

    def show_gi(self, rev="HEAD"):
        return self.fx.git("show", f"{rev}:.gitignore")

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

    def test_commits_gitignore_when_only_the_working_copy_has_the_entries(self):
        """Init appends; operators forget to commit. Start must make HEAD match."""
        fx = self.fx
        self.drop_gitignore(".cursor/rules/conveyor-role.mdc")
        with open(os.path.join(fx.root, ".gitignore"), "a") as f:
            f.write(".cursor/rules/conveyor-role.mdc\n")
        before = fx.git("rev-parse", "HEAD")
        r = fx.conveyor("start", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("committed .gitignore lacks", r.stdout)
        self.assertIn("committed .gitignore (.cursor/rules/conveyor-role.mdc)", r.stdout)
        self.assertNotEqual(before, fx.git("rev-parse", "HEAD"))
        self.assertIn(".cursor/rules/conveyor-role.mdc", self.show_gi())
        self.assertIn(".cursor/rules/conveyor-role.mdc", self.show_gi("conveyor-coder"))
        self.assertIn("Ignore Conveyor runtime paths", fx.git("log", "-1", "--format=%s"))
        self.assertIn("By operator.", fx.git("log", "-1", "--format=%B"))

    def test_appends_and_commits_when_head_lacks_the_entries(self):
        fx = self.fx
        self.drop_gitignore(*GITIGNORE)
        r = fx.conveyor("start", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("committed .gitignore (", r.stdout)
        gi = self.show_gi()
        for entry in GITIGNORE:
            self.assertIn(entry, gi.splitlines(), entry)
        for entry in GITIGNORE:
            self.assertIn(entry, self.show_gi("conveyor-coder").splitlines(), entry)

    def test_quiet_when_the_committed_gitignore_is_complete(self):
        before = self.fx.git("rev-parse", "HEAD")
        r = self.fx.conveyor("start", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("committed .gitignore", r.stdout)
        self.assertEqual(before, self.fx.git("rev-parse", "HEAD"))

    def test_commits_gitignore_on_an_existing_idle_role_branch(self):
        fx = self.fx
        fx.conveyor("start")
        fx.conveyor("stop")
        wt = fx.paths.worktree("coder")
        gi = os.path.join(wt, ".gitignore")
        kept = [l for l in read(gi).splitlines() if l != ".cursor/rules/conveyor-role.mdc"]
        with open(gi, "w") as f:
            f.write("\n".join(kept) + "\n")
        fx.git("commit", "-q", "-a", "-m", "Drop the rules entry on the role branch", cwd=wt)
        r = fx.conveyor("start", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("committed .gitignore on conveyor-coder", r.stdout)
        self.assertIn(".cursor/rules/conveyor-role.mdc", self.show_gi("conveyor-coder").splitlines())


if __name__ == "__main__":
    unittest.main()
