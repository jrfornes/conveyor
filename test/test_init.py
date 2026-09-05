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
                    "roles/specifier.md", "intake/ticket-reviewer.md", "intake/rubric.md",
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

    def test_intake_files_are_not_clobbered_on_repeat_init(self):
        self.git("init", "-q")
        self.init()
        prompt = os.path.join(self.tmp, "intake", "ticket-reviewer.md")
        with open(prompt, "a") as f:
            f.write("\n## Operator edit\n")
        rubric = os.path.join(self.tmp, "intake", "rubric.md")
        with open(rubric, "a") as f:
            f.write("\noperator rubric note\n")
        self.init()
        self.assertIn("## Operator edit", read(prompt))
        self.assertIn("operator rubric note", read(rubric))

    def test_migration_refuses_when_the_old_file_is_dirty(self):
        self.git("init", "-q")
        self.init()
        dest = os.path.join(self.tmp, "roles")
        os.makedirs(dest, exist_ok=True)
        old = os.path.join(dest, "ticket-reviewer.md")
        with open(old, "w") as f:
            f.write("# dirty old prompt\n")
        # untracked and different from intake/ — refuse rather than delete
        r = self.init(check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uncommitted", (r.stdout + r.stderr).lower())
        self.assertTrue(os.path.isfile(old))
        self.assertEqual(read(old), "# dirty old prompt\n")

    def test_migration_moves_the_old_file(self):
        self.git("init", "-q")
        os.makedirs(os.path.join(self.tmp, "roles"), exist_ok=True)
        old = os.path.join(self.tmp, "roles", "ticket-reviewer.md")
        with open(old, "w") as f:
            f.write("# Role: ticket-reviewer\n\noperator kept this\n")
        r = self.init()
        self.assertIn("moved roles/ticket-reviewer.md", r.stdout)
        self.assertFalse(os.path.isfile(old))
        self.assertIn("operator kept this",
                      read(os.path.join(self.tmp, "intake", "ticket-reviewer.md")))


if __name__ == "__main__":
    unittest.main()
