"""Pipeline shapes via the seeded starters: routes, spec hold, approve/reject, findings.

See test_pipeline_shape.py for arbitrary lengths and a declared gate.
"""
import os
import shutil
import unittest

from harness import Fixture, layout, read
from conveyor import config, handoff, util

SPEC_OK = 'commit "Localize $TASK"\ndraft coder $TASK ready\nhandoff\nhandoff\n'
CODER_OK = 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nhandoff\n'
REVIEWER_FINDINGS = ('commit --empty "Review: $TASK\\n\\n1. requirement 1 - not proven"\n'
                     'draft coder $TASK findings\nhandoff\nhandoff\n')


class SpecThenBuild(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)
        with open(os.path.join(self.fx.root, "conveyor.conf"), "w") as f:
            f.write("role specifier composer-2.5 max_retries=3 max_minutes=60 max_attempts=2\n"
                    "role coder composer-2.5 max_retries=3 max_minutes=120 max_attempts=3\n"
                    "role reviewer gpt-5 max_minutes=60 max_attempts=2\n"
                    "[global]\npoll_seconds = 0.2\n")

    def test_review_belt_routes_unchanged(self):
        two = Fixture()
        self.addCleanup(two.cleanup)
        cfg = config.load(two.root)
        self.assertEqual(cfg.routes(), {
            ("operator", "coder", "ready"),
            ("coder", "reviewer", "ready"),
            ("reviewer", "done", "pass"),
            ("reviewer", "coder", "findings"),
            ("ticket-reviewer", "operator", "ready"),
        })
        self.assertIsNone(cfg.gate_role())

    def test_spec_then_build_findings_to_coder_not_specifier(self):
        cfg = config.load(self.fx.root)
        self.assertEqual(len(cfg.names()), 3)
        self.assertIn(("reviewer", "coder", "findings"), cfg.routes())
        self.assertNotIn(("reviewer", "specifier", "findings"), cfg.routes())
        self.assertIn(("specifier", "coder", "ready"), cfg.routes())
        self.assertIn(("operator", "specifier", "ready"), cfg.routes())
        self.assertIsNotNone(cfg.gate_role())

    def test_specifier_ready_held_then_approve(self):
        fx = self.fx
        fx.script("specifier", SPEC_OK)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.task("demo")
        self.assertTrue(layout.handoffs(fx.paths.role("specifier").new) or
                        layout.handoffs(fx.paths.role("operator").sent))
        rc = fx.loop("specifier").returncode
        self.assertEqual(rc, 0, "specifier loop")
        pending = layout.handoffs(fx.paths.approvals_pending)
        self.assertEqual(len(pending), 1, pending)
        self.assertEqual(layout.handoffs(fx.paths.role("coder").new), [])
        hid = handoff.read(os.path.join(fx.paths.approvals_pending, pending[0]))[0]["id"]
        task_id = fx.board()["demo"]["task_id"]
        audit = fx.board()["demo"]["audit_count"]
        fx.conveyor("approve", hid)
        self.assertEqual(layout.handoffs(fx.paths.approvals_pending), [])
        self.assertEqual(len(layout.handoffs(fx.paths.role("coder").new)), 1)
        self.assertEqual(fx.board()["demo"]["lane"], "coder")
        self.assertEqual(fx.board()["demo"]["task_id"], task_id)
        self.assertEqual(fx.board()["demo"]["audit_count"], audit)

    def test_reject_returns_to_specifier_preserves_task_id(self):
        fx = self.fx
        fx.script("specifier", SPEC_OK)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.task("demo")
        self.assertEqual(fx.loop("specifier").returncode, 0)
        pending = layout.handoffs(fx.paths.approvals_pending)
        hid = handoff.read(os.path.join(fx.paths.approvals_pending, pending[0]))[0]["id"]
        task_id = fx.board()["demo"]["task_id"]
        audit = fx.board()["demo"]["audit_count"]
        fx.conveyor("reject", hid, input="Need a test plan.\n")
        self.assertEqual(layout.handoffs(fx.paths.approvals_pending), [])
        new = layout.handoffs(fx.paths.role("specifier").new)
        self.assertEqual(len(new), 1)
        h, body = handoff.read(os.path.join(fx.paths.role("specifier").new, new[0]))
        self.assertEqual(h["task_id"], task_id)
        self.assertEqual(h["verdict"], "findings")
        self.assertIn("Need a test plan", body)
        self.assertEqual(fx.board()["demo"]["task_id"], task_id)
        self.assertEqual(fx.board()["demo"]["audit_count"], audit)
        self.assertEqual(fx.board()["demo"]["lane"], "specifier")

    def test_findings_land_on_coder(self):
        fx = self.fx
        fx.script("specifier", SPEC_OK)
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_FINDINGS)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.task("demo")
        self.assertEqual(fx.loop("specifier").returncode, 0)
        pending = layout.handoffs(fx.paths.approvals_pending)
        hid = handoff.read(os.path.join(fx.paths.approvals_pending, pending[0]))[0]["id"]
        fx.conveyor("approve", hid)
        self.assertEqual(fx.loop("coder").returncode, 0)
        self.assertEqual(fx.loop("reviewer").returncode, 0)
        self.assertTrue(layout.handoffs(fx.paths.role("coder").new) or
                        layout.handoffs(fx.paths.role("coder").in_process))
        self.assertEqual(layout.handoffs(fx.paths.role("specifier").new), [])

    def test_workflow_activate_seeds(self):
        fx = self.fx
        r = fx.conveyor("workflow", "activate", "review-belt")
        self.assertIn("coder → reviewer", r.stdout)
        self.assertEqual(config.load(fx.root).names(), ["coder", "reviewer"])
        r = fx.conveyor("workflow", "activate", "spec-then-build")
        self.assertIn("specifier → coder → reviewer", r.stdout)
        cfg = config.load(fx.root)
        self.assertEqual(cfg.names(), ["specifier", "coder", "reviewer"])
        self.assertEqual(cfg.gate_role(), "specifier")

    def test_activate_refuses_while_a_loop_is_running(self):
        """Switching mid-run would strand a loop on a role the new workflow drops."""
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        conf = os.path.join(fx.root, "conveyor.conf")
        before = read(conf)
        lock = fx.paths.role("coder").loop_lock
        os.makedirs(lock, exist_ok=True)
        with open(os.path.join(lock, "pid"), "w") as f:
            f.write(str(os.getpid()))  # a pid that is genuinely alive
        try:
            r = fx.conveyor("workflow", "activate", "review-belt", check=False)
        finally:
            shutil.rmtree(lock)
        self.assertEqual(r.returncode, 1)
        self.assertIn("loops are running (coder)", r.stderr)
        self.assertEqual(read(conf), before)

    def test_activate_warns_about_the_orphaned_worktree_and_keeps_it(self):
        """Activate stays a pure config write; `conveyor start` does the pruning."""
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        self.assertTrue(os.path.isdir(fx.paths.worktree("specifier")))
        r = fx.conveyor("workflow", "activate", "review-belt")
        self.assertIn("specifier left the workflow", r.stdout)
        self.assertIn(".worktrees/specifier", r.stdout)
        self.assertTrue(os.path.isdir(fx.paths.worktree("specifier")))

    def test_accepts_one_and_four_roles(self):
        """Stage 2 lifted the 2-or-3 limit; see test_pipeline_shape for the shapes."""
        path = os.path.join(self.fx.root, "conveyor.conf")
        with open(path, "w") as f:
            f.write("role coder composer-2.5\n")
        self.assertEqual(config.load(self.fx.root).names(), ["coder"])
        with open(path, "w") as f:
            f.write("role a composer-2.5\nrole b composer-2.5\nrole c composer-2.5\nrole d composer-2.5\n")
        self.assertEqual(config.load(self.fx.root).names(), ["a", "b", "c", "d"])
        with open(path, "w") as f:
            f.write("")
        with self.assertRaises(config.ConfigError):
            config.load(self.fx.root)


class PruneWorktrees(unittest.TestCase):
    """`conveyor start` reconciles .worktrees/ to the active workflow."""

    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def branches(self):
        return self.fx.git("branch", "--list", "conveyor-*")

    def test_start_prunes_a_stale_worktree_and_keeps_the_branch(self):
        fx = self.fx
        fx.conveyor("workflow", "activate", "spec-then-build")
        fx.start("--no-smoke")
        fx.conveyor("stop")
        self.assertTrue(os.path.isdir(fx.paths.worktree("specifier")))
        fx.conveyor("workflow", "activate", "review-belt")
        r = fx.start("--no-smoke")
        self.assertIn("removed stale worktree .worktrees/specifier", r.stdout)
        self.assertFalse(os.path.isdir(fx.paths.worktree("specifier")))
        self.assertIn("conveyor-specifier", self.branches(),
                      "the branch is the record of the dropped role's work")
        self.assertTrue(os.path.isdir(fx.paths.role("specifier").base),
                        "the audit trail under .conveyor/roles/ is never touched")

    def test_start_keeps_a_dirty_stale_worktree(self):
        fx = self.fx
        fx.conveyor("workflow", "activate", "spec-then-build")
        fx.start("--no-smoke")
        fx.conveyor("stop")
        with open(os.path.join(fx.paths.worktree("specifier"), "scratch.txt"), "w") as f:
            f.write("work in progress\n")
        fx.conveyor("workflow", "activate", "review-belt")
        r = fx.start("--no-smoke")
        self.assertIn("uncommitted changes", r.stdout)
        self.assertTrue(os.path.isdir(fx.paths.worktree("specifier")))

    def test_start_never_prunes_the_intake_worktree(self):
        """ticket-reviewer is never in cfg.names(); pruning it would break intake."""
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        wt = fx.paths.worktree("ticket-reviewer")
        util.git(["worktree", "add", "--force", "-B", "conveyor-ticket-reviewer",
                  wt, "HEAD"], fx.root)
        r = fx.start("--no-smoke")
        self.assertNotIn("removed stale worktree .worktrees/ticket-reviewer", r.stdout)
        self.assertTrue(os.path.isdir(wt))

    def test_start_ignores_a_stray_directory_under_worktrees(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        stray = os.path.join(fx.paths.worktrees, "notes")
        os.makedirs(stray, exist_ok=True)
        with open(os.path.join(stray, "keep.txt"), "w") as f:
            f.write("mine\n")
        fx.start("--no-smoke")
        self.assertTrue(os.path.isdir(stray), "git does not call this a worktree")


if __name__ == "__main__":
    unittest.main()
