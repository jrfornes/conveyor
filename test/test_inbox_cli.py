"""CLI read surface for the inbox: list, show, status block, comments lifecycle."""
import os
import unittest

from harness import ConveyorTest
from conveyor import inbox

GRADE_READY = ('write grade.md "Grade: Ready\\n\\n1. none\\n"\n'
               'commit "Grade $TASK"\ndraft operator $TASK ready\nhandoff\nhandoff\n')


class InboxRead(ConveyorTest):
    def _seed(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_READY)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "cave-setup",
                    input="# Cave\n\n1. Lights work.\n")
        return fx

    def test_list_is_empty_before_any_import(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        self.assertIn("(no inbox items)", fx.conveyor("inbox", "list").stdout)

    def test_list_shows_id_source_status_grade_title(self):
        fx = self._seed()
        out = fx.conveyor("inbox", "list").stdout
        self.assertRegex(out, r"cave-setup\s+manual\s+imported\s+-\s+cave-setup")
        fx.conveyor("intake", "cave-setup")
        out = fx.conveyor("inbox", "list").stdout
        self.assertRegex(out, r"cave-setup\s+manual\s+graded\s+Ready\s+cave-setup")

    def test_list_and_show_are_pure_reads(self):
        """Neither creates or renames anything under .conveyor/ (protocol §10)."""
        fx = self.fx
        fx.conveyor("import", "--source", "manual", "--title", "untouched",
                    input="# Untouched\n")

        def tree():
            out = []
            for base, dirs, files in os.walk(fx.paths.conveyor):
                dirs.sort()
                for n in sorted(dirs) + sorted(files):
                    out.append(os.path.relpath(os.path.join(base, n), fx.paths.conveyor))
            return sorted(out)

        before = tree()
        fx.conveyor("inbox", "list")
        fx.conveyor("inbox", "show", "untouched")
        self.assertEqual(before, tree())

    def test_show_prints_meta_and_documents(self):
        fx = self._seed()
        fx.conveyor("intake", "cave-setup")
        out = fx.conveyor("inbox", "show", "cave-setup").stdout
        self.assertIn("id: cave-setup", out)
        self.assertIn("status: graded", out)
        self.assertIn("grade: Ready", out)
        self.assertIn("--- source.md ---", out)
        self.assertIn("Lights work.", out)
        self.assertIn("--- grade.md ---", out)
        self.assertIn("Grade: Ready", out)
        # absent documents get no heading
        self.assertNotIn("--- proposed-task.md ---", out)

    def test_show_unknown_id_errors(self):
        fx = self.fx
        r = fx.conveyor("inbox", "show", "nope", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no inbox item nope", r.stdout + r.stderr)

    def test_usage_lists_every_verb(self):
        r = self.fx.conveyor("inbox", check=False)
        self.assertNotEqual(r.returncode, 0)
        for verb in ("inbox list", "inbox show", "inbox approve", "inbox skip",
                     "inbox attachments"):
            self.assertIn(verb, r.stdout + r.stderr)


class StatusInboxBlock(ConveyorTest):
    def test_status_omits_inbox_when_there_are_no_items(self):
        """Runbook §6 format is unchanged for a repo that never ran import."""
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        self.assertNotIn("inbox:", fx.conveyor("status").stdout)

    def test_status_lists_open_items_and_counts_terminal_ones(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_READY)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "open-one",
                    input="# Open\n\n1. Thing.\n")
        fx.conveyor("import", "--source", "manual", "--title", "gone",
                    input="# Gone\n\n1. Thing.\n")
        fx.conveyor("inbox", "skip", "gone")
        out = fx.conveyor("status").stdout
        self.assertIn("inbox:", out)
        self.assertRegex(out, r"open-one\s+imported\s+-")
        self.assertIn("(1 skipped)", out)
        self.assertNotRegex(out, r"^\s+gone\s", )


class Comments(ConveyorTest):
    def _seed(self, notes="Please tighten requirement 2.\n"):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_READY)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "with-notes",
                    input="# Cave\n\n1. Lights work.\n")
        notes_path = os.path.join(fx.tmp, "notes.txt")
        with open(notes_path, "w") as f:
            f.write(notes)
        return fx, notes_path

    def test_comments_flag_is_accepted_and_reaches_the_item(self):
        """Regression: --comments used to be counted as a second positional."""
        fx, notes = self._seed()
        r = fx.conveyor("intake", "with-notes", "--comments", notes, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("usage: conveyor intake", r.stdout + r.stderr)

    def test_comments_are_consumed_exactly_once(self):
        fx, notes = self._seed()
        fx.conveyor("intake", "with-notes", "--comments", notes)
        d = os.path.join(fx.paths.inbox, "with-notes")
        self.assertFalse(os.path.exists(os.path.join(d, "comments.txt")))
        applied = os.path.join(d, "comments-applied.txt")
        self.assertTrue(os.path.isfile(applied))
        with open(applied) as f:
            self.assertIn("tighten requirement 2", f.read())
        self.assertIn("tighten requirement 2",
                      inbox.item(fx.paths, "with-notes")["comments_applied"])

        # A second grade must not re-send feedback the reviewer already saw.
        fx.conveyor("intake", "with-notes")
        prompts = [e for e in fx.logs("ticket-reviewer").splitlines() if '"event": "prompt"' in e]
        self.assertEqual(len(prompts), 2)
        self.assertIn("Operator comments", prompts[0])
        self.assertNotIn("Operator comments", prompts[1])
        self.assertEqual(inbox.item(fx.paths, "with-notes")["comments"], "")

    def test_comments_accepts_literal_text(self):
        fx, _ = self._seed()
        fx.conveyor("intake", "with-notes", "--comments", "inline note")
        self.assertIn("inline note",
                      inbox.item(fx.paths, "with-notes")["comments_applied"])


if __name__ == "__main__":
    unittest.main()
