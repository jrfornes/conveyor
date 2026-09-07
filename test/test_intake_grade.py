"""Grade integrity: the `Grade:` line is the only signal, and approve honours it."""
import os
import unittest

from harness import ConveyorTest
from conveyor import inbox

GRADE_READY = ('write grade.md "Grade: Ready\\n\\n1. none\\n"\n'
               'commit "Grade $TASK"\ndraft operator $TASK ready\nhandoff\nhandoff\n')
GRADE_UNUSABLE = ('write grade.md "Grade: Unusable\\n\\n1. no problem statement\\n"\n'
                  'commit "Grade $TASK"\ndraft operator $TASK ready\nhandoff\nhandoff\n')
# A gap list that mentions "ready" but carries no verdict line. The old
# parser read this as Ready; it must not.
GRADE_PROSE = ('write grade.md "The acceptance criteria are not ready.\\n\\n1. no repro\\n"\n'
               'commit "Grade $TASK"\ndraft operator $TASK ready\nhandoff\nhandoff\n')


class ParseGrade(unittest.TestCase):
    def test_verdict_line_only(self):
        for text, expected in (
            ("Grade: Ready\n\n1. none\n", "Ready"),
            ("Grade: Gaps\n\n1. no repro\n", "Gaps"),
            ("Grade: Unusable\n", "Unusable"),
            ("grade:ready\n", "Ready"),
            # markdown the agent may wrap around it
            ("**Grade:** Gaps\n", "Gaps"),
            ("## Grade: Unusable\n", "Unusable"),
            ("  Grade: Ready\n", "Ready"),
            # the first verdict line wins; prose above it is not a verdict
            ("The ticket has gaps.\nGrade: Ready\n", "Ready"),
        ):
            with self.subTest(text=text):
                self.assertEqual(inbox.parse_grade(text), expected)

    def test_prose_is_never_a_verdict(self):
        """The regression this guard exists for: a gap that says "not ready"."""
        self.assertEqual(inbox.parse_grade("1. Acceptance criteria are not ready\n"), "unparsed")
        self.assertEqual(inbox.parse_grade("The ticket has gaps and is unusable.\n"), "unparsed")
        self.assertEqual(inbox.parse_grade("Grade: Bogus\n"), "unparsed")

    def test_missing_grade_file_is_dash(self):
        self.assertEqual(inbox.parse_grade(""), "-")
        self.assertEqual(inbox.parse_grade("   \n\n"), "-")

    def test_every_result_is_a_legal_value(self):
        for text in ("Grade: Ready\n", "nothing here\n", ""):
            self.assertIn(inbox.parse_grade(text), inbox.GRADE_VALUES)


class GradeGuards(ConveyorTest):
    def _import(self, title, body="# Cave\n\n1. Lights work.\n"):
        self.fx.start("--no-smoke")
        self.fx.conveyor("stop")
        self.fx.conveyor("import", "--source", "manual", "--title", title, input=body)

    def test_grade_without_verdict_line_is_unparsed_and_blocks_approve(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_PROSE)
        self._import("prose-grade")
        r = fx.conveyor("intake", "prose-grade")
        self.assertEqual(inbox.read_meta(fx.paths, "prose-grade")["grade"], "unparsed")
        self.assertIn("unparsed", r.stdout)
        self.assertIn('has no "Grade: Ready|Gaps|Unusable" line', r.stdout)

        r = fx.conveyor("inbox", "approve", "prose-grade", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('grade.md has no "Grade:" line', r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(fx.root, "tasks", "prose-grade.md")))

        fx.conveyor("inbox", "approve", "prose-grade", "--force")
        self.assertTrue(os.path.isfile(os.path.join(fx.root, "tasks", "prose-grade.md")))
        self.assertEqual(inbox.read_meta(fx.paths, "prose-grade")["status"], "ready")

    def test_unusable_blocks_approve_until_forced(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_UNUSABLE)
        self._import("no-problem")
        r = fx.conveyor("intake", "no-problem")
        self.assertIn("graded no-problem  Unusable", r.stdout)
        r = fx.conveyor("inbox", "approve", "no-problem", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is graded Unusable", r.stdout + r.stderr)
        fx.conveyor("inbox", "approve", "no-problem", "--force")
        self.assertTrue(os.path.isfile(os.path.join(fx.root, "tasks", "no-problem.md")))

    def test_ungraded_blocks_approve_until_forced(self):
        fx = self.fx
        self._import("never-graded")
        r = fx.conveyor("inbox", "approve", "never-graded", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("has no grade", r.stdout + r.stderr)
        fx.conveyor("inbox", "approve", "never-graded", "--force")
        self.assertTrue(os.path.isfile(os.path.join(fx.root, "tasks", "never-graded.md")))

    def test_ready_approves_without_force(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_READY)
        self._import("cave-setup")
        r = fx.conveyor("intake", "cave-setup")
        self.assertIn("graded cave-setup  Ready", r.stdout)
        fx.conveyor("inbox", "approve", "cave-setup")
        self.assertEqual(inbox.read_meta(fx.paths, "cave-setup")["status"], "ready")


class RegradeGuard(ConveyorTest):
    def test_intake_refuses_ready_and_started(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_READY)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "cave-setup",
                    input="# Cave\n\n1. Lights work.\n")
        fx.conveyor("intake", "cave-setup")
        fx.conveyor("inbox", "approve", "cave-setup")

        r = fx.conveyor("intake", "cave-setup", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is ready; tasks/cave-setup.md is already committed", r.stdout + r.stderr)

        fx.conveyor("start-task", "cave-setup")
        r = fx.conveyor("intake", "cave-setup", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is started", r.stdout + r.stderr)

    def test_skipped_stays_regradable(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE_READY)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "second-thoughts",
                    input="# Cave\n\n1. Lights work.\n")
        fx.conveyor("inbox", "skip", "second-thoughts")
        fx.conveyor("intake", "second-thoughts")
        self.assertEqual(inbox.read_meta(fx.paths, "second-thoughts")["grade"], "Ready")


if __name__ == "__main__":
    unittest.main()
