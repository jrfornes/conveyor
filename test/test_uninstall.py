"""conveyor uninstall — runtime teardown and optional bundle removal."""
import os
import subprocess
import unittest

from harness import BIN, Fixture, REPO, read


class Uninstall(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def uninstall(self, *args, check=True):
        return self.fx.conveyor("uninstall", *args, check=check)

    def hook_path(self):
        return os.path.join(self.fx.git("rev-parse", "--path-format=absolute", "--git-common-dir"),
                            "hooks", "commit-msg")

    def branches(self):
        out = self.fx.git("branch", "--list", "conveyor-*")
        return [b.strip().lstrip("* ") for b in out.splitlines() if b.strip()]

    def test_dry_run_without_yes_removes_nothing(self):
        self.fx.start("--no-smoke")
        self.assertTrue(os.path.isdir(self.fx.paths.conveyor))
        r = self.uninstall(check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dry run", r.stdout)
        self.assertIn("would remove", r.stdout)
        self.assertTrue(os.path.isdir(self.fx.paths.conveyor))
        self.assertTrue(os.path.isdir(self.fx.paths.worktrees))

    def test_runtime_removes_state_but_keeps_bundle(self):
        self.fx.start("--no-smoke")
        self.assertTrue(os.path.isfile(self.hook_path()))
        r = self.uninstall("--yes")
        self.assertEqual(r.returncode, 0)
        self.assertIn("uninstalled", r.stdout)
        self.assertFalse(os.path.isdir(self.fx.paths.conveyor))
        self.assertFalse(os.path.isdir(self.fx.paths.worktrees))
        self.assertFalse(os.path.isfile(self.hook_path()))
        self.assertEqual(self.branches(), [])
        self.assertTrue(os.path.isfile(os.path.join(self.fx.root, "constitution.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.fx.root, "conveyor.conf")))
        self.assertTrue(os.path.isdir(os.path.join(self.fx.root, "roles")))

    def test_bundle_removes_init_files(self):
        self.fx.start("--no-smoke")
        gi_before = read(os.path.join(self.fx.root, ".gitignore")).splitlines()
        for e in (".worktrees/", ".conveyor/", ".cursor/rules/conveyor-role.mdc", "tmp/"):
            self.assertIn(e, gi_before)
        r = self.uninstall("--yes", "--bundle")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.isfile(os.path.join(self.fx.root, "constitution.md")))
        self.assertFalse(os.path.isdir(os.path.join(self.fx.root, "roles")))
        self.assertFalse(os.path.isfile(os.path.join(self.fx.root, "conveyor.conf")))
        self.assertFalse(os.path.isdir(os.path.join(self.fx.root, "tasks")))
        gi_after = read(os.path.join(self.fx.root, ".gitignore")).splitlines()
        for e in (".worktrees/", ".conveyor/", ".cursor/rules/conveyor-role.mdc", "tmp/"):
            self.assertNotIn(e, gi_after)

    def test_custom_hook_is_left_with_warning(self):
        self.fx.start("--no-smoke")
        with open(self.hook_path(), "w") as f:
            f.write("# custom hook\n")
        r = self.uninstall("--yes")
        self.assertEqual(r.returncode, 0)
        self.assertIn("warning:", r.stdout)
        self.assertTrue(os.path.isfile(self.hook_path()))
        self.assertIn("custom hook", read(self.hook_path()))

    def test_refuses_conveyor_source_checkout(self):
        r = subprocess.run([os.path.join(BIN, "conveyor"), "uninstall", "--yes"],
                           cwd=REPO, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("source checkout", r.stdout + r.stderr)

    def test_custom_role_kept_on_runtime_removed_on_bundle(self):
        extra = os.path.join(self.fx.root, "roles", "extra.md")
        with open(extra, "w") as f:
            f.write("# Role: extra\n")
        self.fx.start("--no-smoke")
        self.uninstall("--yes")
        self.assertTrue(os.path.isfile(extra))
        # re-init runtime for second pass
        self.fx.start("--no-smoke")
        self.uninstall("--yes", "--bundle")
        self.assertFalse(os.path.isfile(extra))
        self.assertFalse(os.path.isdir(os.path.join(self.fx.root, "roles")))


if __name__ == "__main__":
    unittest.main()
