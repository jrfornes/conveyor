"""Invariant 12: ambiguity parks, never guesses."""
import os
import unittest

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, layout, read


class AmbiguityParks(ConveyorTest):
    def start_task(self, coder=CODER_OK, reviewer=REVIEWER_PASS, task="demo"):
        fx = self.fx
        fx.script("coder", coder)
        fx.script("reviewer", reviewer)
        fx.start()
        fx.conveyor("stop")
        fx.task(task)
        return fx

    def test_two_outbox_files_park(self):
        fx = self.start_task(coder=CODER_OK + 'commit "Again"\nhandoff\nhandoff\n')
        fx.loop("coder")
        self.assertEqual(fx.parked_reason("demo")[0], "multiple-handoffs")
        self.assertEqual(layout.handoffs(fx.paths.role("coder").outbox), [])
        self.assertEqual(sorted(os.listdir(os.path.join(fx.paths.needs_human, "demo"))),
                         ["item.handoff", "outbox-1.handoff", "outbox-2.handoff", "reason"])
        self.assertEqual(layout.handoffs(fx.paths.role("reviewer").new), [])

    def test_missing_rules_file_parks(self):
        fx = self.start_task()
        os.remove(os.path.join(fx.paths.worktree("coder"), ".cursor", "rules", "conveyor-role.mdc"))
        r = fx.loop("coder")
        self.assertIn("E_NO_RULES", r.stdout)
        self.assertEqual(fx.parked_reason("demo")[0], "no-rules")
        self.assertEqual([f for f in os.listdir(os.path.join(fx.paths.logs, "coder")) if f.endswith(".jsonl")], [])

    def test_merge_conflict_on_pass_parks_and_resume_recovers(self):
        fx = self.start_task(coder='write work.txt "coder version"\ncommit "Implement $TASK"\n'
                                   'draft reviewer $TASK ready\nhandoff\nhandoff\n')
        with open(os.path.join(fx.root, "work.txt"), "w") as f:
            f.write("main version")
        fx.git("add", "work.txt")
        fx.git("commit", "-q", "-m", "Conflicting change on main")
        fx.drive()
        self.assertEqual(fx.parked_reason("demo")[0], "merge-conflict")
        self.assertEqual(fx.git("status", "--porcelain"), "")
        self.assertEqual(layout.handoffs(fx.paths.role("reviewer").outbox), [])
        # operator resolves by merging by hand, then resumes
        fx.git("merge", "-q", "-s", "ours", "--no-edit", "conveyor-reviewer")
        fx.conveyor("resume", "demo")
        self.assertEqual(len(layout.handoffs(fx.paths.role("reviewer").outbox)), 1)
        fx.loop("reviewer")
        self.assertEqual(fx.board()["demo"]["lane"], "done")
        self.assertEqual(len(layout.handoffs(fx.paths.role("reviewer").sent)), 1)

    def test_merge_conflict_into_role_worktree_parks(self):
        fx = self.start_task()
        wt = fx.paths.worktree("coder")
        for cwd, text in ((fx.root, "main"), (wt, "coder")):
            with open(os.path.join(cwd, "clash.txt"), "w") as f:
                f.write(text)
            fx.git("add", "clash.txt", cwd=cwd)
            fx.git("commit", "-q", "-m", f"clash {text}", cwd=cwd)
        fx.task("later")
        fx.loop("coder")  # demo: fine
        fx.loop("coder")  # later: operator commit conflicts with the coder branch
        self.assertEqual(fx.parked_reason("later")[0], "merge-conflict")

    def test_untracked_file_in_the_way_parks_apart_from_a_conflict(self):
        """git refusing to clobber an untracked file is not a conflict: nothing merged,
        and the repair is to remove the file, not to reconcile two edits."""
        fx = self.start_task(coder='write note.txt "from coder"\ncommit "Implement $TASK"\n'
                                   'draft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.loop("coder")
        stray = os.path.join(fx.paths.worktree("reviewer"), "note.txt")
        with open(stray, "w") as f:
            f.write("left lying around")
        fx.loop("reviewer")
        reason = fx.parked_reason("demo")
        self.assertEqual(reason[0], "untracked-collision")
        self.assertIn("would overwrite untracked note.txt", reason[1])
        self.assertIn("conveyor resume demo", reason[1])
        self.assertEqual(read(stray), "left lying around")  # nothing was merged over it
        self.assertEqual(fx.board()["demo"]["lane"], "needs-human")
        self.assertEqual(layout.handoffs(fx.paths.role("reviewer").outbox), [])



if __name__ == "__main__":
    unittest.main()
