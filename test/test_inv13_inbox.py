"""Invariant 13: inbox items appear whole, carry legal fields, and match tasks/."""
import os
import unittest

from harness import ConveyorTest
from conveyor import inbox

GRADE_READY = ('write grade.md "Grade: Ready\\n\\n1. none\\n"\n'
               'commit "Grade $TASK"\ndraft operator $TASK ready\nhandoff\nhandoff\n')
GRADE_GAPS_IMPROVE = ('write grade.md "Grade: Gaps\\n\\n1. no acceptance\\n"\n'
                      'write proposed-task.md "# Task\\n\\n1. Numbered requirement.\\n"\n'
                      'commit "Improve $TASK"\ndraft operator $TASK ready\nhandoff\nhandoff\n')


class InboxInvariant(ConveyorTest):
    def _run(self):
        """Drive an inbox through import → grade → improve → approve → start."""
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_READY)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        for title in ("cave-setup", "left-imported", "skipped-one"):
            fx.conveyor("import", "--source", "manual", "--title", title,
                        input=f"# {title}\n\n1. Thing.\n")
        fx.conveyor("inbox", "skip", "skipped-one")
        fx.conveyor("intake", "cave-setup")
        fx.conveyor("inbox", "approve", "cave-setup")
        fx.conveyor("start-task", "cave-setup")
        fx.script("ticket-reviewer", GRADE_GAPS_IMPROVE)
        fx.conveyor("intake", "left-imported", "--improve")
        return fx

    def test_items_arrive_whole(self):
        """create() renames .tmp-<id>/ into place: no partial item is ever visible."""
        fx = self._run()
        leftovers = [n for n in os.listdir(fx.paths.inbox) if n.startswith(".tmp-")]
        self.assertEqual(leftovers, [])
        for iid in inbox.list_ids(fx.paths):
            d = os.path.join(fx.paths.inbox, iid)
            self.assertTrue(os.path.isfile(os.path.join(d, "meta.txt")), iid)
            self.assertTrue(os.path.isfile(os.path.join(d, "source.md")), iid)
            self.assertFalse([f for f in os.listdir(d) if f.endswith(".tmp")], iid)

    def test_status_and_grade_are_always_legal(self):
        fx = self._run()
        for iid in inbox.list_ids(fx.paths):
            meta = inbox.read_meta(fx.paths, iid)
            self.assertIn(meta["status"], inbox.STATUSES, iid)
            self.assertIn(meta["grade"], inbox.GRADE_VALUES, iid)

    def test_ready_or_started_item_has_a_committed_task_file(self):
        fx = self._run()
        tracked = fx.git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
        seen = 0
        for iid in inbox.list_ids(fx.paths):
            meta = inbox.read_meta(fx.paths, iid)
            if meta["status"] not in ("ready", "started"):
                continue
            seen += 1
            self.assertNotEqual(meta["task_name"], "-", iid)
            self.assertIn(f"tasks/{meta['task_name']}.md", tracked, iid)
        self.assertEqual(seen, 1)

    def test_id_is_stable_across_every_status_change(self):
        """Status is a meta field; the item directory is never renamed."""
        fx = self._run()
        self.assertEqual(inbox.read_meta(fx.paths, "cave-setup")["status"], "started")
        self.assertEqual(inbox.read_meta(fx.paths, "skipped-one")["status"], "skipped")
        self.assertEqual(inbox.read_meta(fx.paths, "left-imported")["status"], "awaiting-approval")
        self.assertEqual(sorted(inbox.list_ids(fx.paths)),
                         ["cave-setup", "left-imported", "skipped-one"])


if __name__ == "__main__":
    unittest.main()
