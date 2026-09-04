"""conveyor init: automates runbook §3 step 1 (copy the bundle into a target repo)."""
import os
import tempfile
import unittest

from harness import BIN, REPO, read
import subprocess


class Init(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="conveyor-init-")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", self.tmp]))

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.tmp, capture_output=True,
                              text=True, check=True).stdout.strip()

    def init(self, *args, check=True):
        r = subprocess.run([os.path.join(BIN, "conveyor"), "init", *args], cwd=self.tmp,
                           capture_output=True, text=True)
        if check and r.returncode != 0:
            raise AssertionError(r.stdout + r.stderr)
        return r

    def test_refuses_outside_a_git_checkout(self):
        r = self.init(check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is not a git checkout", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "constitution.md")))

    def test_installs_bundle(self):
        self.git("init", "-q")
        self.init()
        for rel in ("constitution.md", "constitution/engineering.md", "constitution/workflow.md",
                    "constitution/handoffs.md", "roles/coder.md", "roles/reviewer.md",
                    "conveyor.conf.example", "project.md", "conveyor.conf"):
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, rel)), rel)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "tasks")))
        gi = read(os.path.join(self.tmp, ".gitignore")).splitlines()
        for e in (".worktrees/", ".conveyor/", ".cursor/rules/conveyor-role.mdc", "tmp/"):
            self.assertIn(e, gi)
        self.assertEqual(read(os.path.join(self.tmp, "constitution.md")),
                         read(os.path.join(REPO, "constitution.md")))

    def test_idempotent_and_never_clobbers_operator_files(self):
        self.git("init", "-q")
        self.init()
        proj = os.path.join(self.tmp, "project.md")
        with open(proj, "a") as f:
            f.write("\n## Test command\n\nmake test\n")
        conf = os.path.join(self.tmp, "conveyor.conf")
        with open(conf, "a") as f:
            f.write("\n# operator edit\n")
        with open(os.path.join(self.tmp, "tasks", "keep-me.md"), "w") as f:
            f.write("existing task\n")
        self.init()  # second run
        self.assertIn("make test", read(proj))
        self.assertIn("# operator edit", read(conf))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "tasks", "keep-me.md")))

    def test_gitignore_append_is_idempotent(self):
        self.git("init", "-q")
        self.init()
        first = read(os.path.join(self.tmp, ".gitignore"))
        self.init()
        self.assertEqual(read(os.path.join(self.tmp, ".gitignore")), first)

    def test_refreshes_shipped_files_on_repeat_init(self):
        """Shipped-as-is files track the conveyor repo; only the operator's own files persist."""
        self.git("init", "-q")
        self.init()
        rules = os.path.join(self.tmp, "roles", "coder.md")
        with open(rules, "a") as f:
            f.write("\nlocal edit\n")
        self.init()
        self.assertNotIn("local edit", read(rules))


if __name__ == "__main__":
    unittest.main()
