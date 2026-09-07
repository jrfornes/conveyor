"""Throwaway fixture used by `conveyor-ui --demo`."""
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "lib"))

from conveyor import board, inbox, layout, presets  # noqa: E402
from ui.server import demo, state  # noqa: E402


class UiDemo(unittest.TestCase):
    def setUp(self):
        self.fx = demo.make_demo()
        self.addCleanup(self.fx.cleanup)

    def test_fixture_is_a_target_repo(self):
        root = self.fx.root
        self.assertTrue(os.path.isfile(os.path.join(root, "conveyor.conf")))
        self.assertTrue(os.path.isdir(os.path.join(root, ".git")))
        self.assertEqual(state.resolve_root(root), os.path.realpath(root))

    def test_seeds_board_inbox_and_workflows(self):
        root = self.fx.root
        paths = layout.Paths(root)
        rows = {r["name"]: r for r in board.read(paths)}
        self.assertEqual(rows["demo"]["lane"], "coder")
        self.assertEqual(rows["stuck"]["lane"], "needs-human")
        self.assertTrue(os.path.isfile(os.path.join(paths.needs_human, "stuck", "reason")))
        self.assertIn("sample-ticket", inbox.list_ids(paths))
        self.assertEqual(inbox.read_meta(paths, "proj-9")["source"], "jira")
        slugs = {p["slug"] for p in presets.load_all(paths)}
        self.assertIn("review-belt", slugs)

    def test_state_payload_is_browsable(self):
        snap = state.build_state(self.fx.root)
        self.assertTrue(any(t["name"] == "demo" for t in snap["tasks"]))
        self.assertTrue(any(t["name"] == "stuck" for t in snap["tasks"]))
        self.assertTrue(any(i["id"] == "sample-ticket" for i in snap["inbox"]))
        self.assertTrue(any(i["id"] == "proj-9" and i["source"] == "jira" for i in snap["inbox"]))
        row = next(i for i in snap["inbox"] if i["id"] == "proj-9")
        self.assertEqual(row["attachment_count"], 2)
        self.assertEqual(row["video_count"], 1)
        self.assertEqual(row["selected_count"], 1)
        self.assertTrue(snap["needs_human"])
        self.assertEqual(snap["workflow"]["id"], "review-belt")


class UiDemoCli(unittest.TestCase):
    def test_demo_and_root_conflict(self):
        r = subprocess.run(
            [sys.executable, "-m", "ui.server", "--demo", "--root", "/tmp"],
            cwd=REPO, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": REPO},
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("--demo and --root cannot be combined", r.stderr)

    def test_help_lists_demo(self):
        r = subprocess.run(
            [os.path.join(REPO, "bin", "conveyor-ui"), "--help"],
            cwd="/", capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--demo", r.stdout)


if __name__ == "__main__":
    unittest.main()
