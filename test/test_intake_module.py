"""Intake module: prompt stack, rubric injection, stale roles/ file ignored."""
import os
import unittest

from harness import ConveyorTest, read
from conveyor import config, inbox, intake as intakelib


GRADE = (
    'write grade.md "Grade: Ready\\n\\n1. none\\n"\n'
    'commit "Grade $TASK"\n'
    "draft operator $TASK ready\n"
    "handoff\n"
    "handoff\n"
)


class IntakeModule(ConveyorTest):
    def _mdc(self, role):
        return os.path.join(self.fx.paths.worktree(role), ".cursor", "rules", "conveyor-role.mdc")

    def test_rubric_lands_between_project_and_prompt(self):
        fx = self.fx
        fx.script("ticket-reviewer", GRADE)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "stack-check",
                    input="# Stack\n\n1. Check order.\n")
        fx.conveyor("intake", "stack-check")
        text = read(self._mdc("ticket-reviewer"))
        proj = text.index("# Project")
        rubric = text.index("# Grading rubric (intake/rubric.md)")
        prompt = text.index("# Role: ticket-reviewer")
        self.assertLess(proj, rubric)
        self.assertLess(rubric, prompt)
        self.assertIn("Ready / Gaps / Unusable", text)

    def test_belt_role_mdc_has_no_rubric(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        text = read(self._mdc("coder"))
        self.assertNotIn("Grading rubric", text)
        self.assertNotIn("intake/rubric.md", text)
        self.assertIn("# Role: coder", text)

    def test_missing_rubric_is_tolerated(self):
        fx = self.fx
        os.remove(intakelib.rubric_path(fx.root))
        fx.script("ticket-reviewer", GRADE)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "no-rubric",
                    input="# Ticket\n\n1. Still grades.\n")
        r = fx.conveyor("intake", "no-rubric")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = read(self._mdc("ticket-reviewer"))
        self.assertNotIn("# Grading rubric", text)
        self.assertIn("## Grades", text)
        self.assertIn("Grade: Ready", text)
        self.assertIn("Ready / Gaps / Unusable", text)
        self.assertIn("# Role: ticket-reviewer", text)
        self.assertEqual(inbox.item(fx.paths, "no-rubric")["status"], "graded")

    def test_stale_roles_ticket_reviewer_is_ignored(self):
        fx = self.fx
        stale = os.path.join(fx.root, "roles", "ticket-reviewer.md")
        with open(stale, "w", encoding="utf-8") as f:
            f.write("# STALE PROMPT — must not appear in the .mdc\n")
        fx.script("ticket-reviewer", GRADE)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "stale-check",
                    input="# T\n\n1. x.\n")
        fx.conveyor("intake", "stale-check")
        text = read(self._mdc("ticket-reviewer"))
        self.assertNotIn("STALE PROMPT", text)
        self.assertIn("# Role: ticket-reviewer", text)

    def test_intake_honours_max_minutes(self):
        fx = self.fx
        config.write_inbox(fx.root, {"ticket_reviewer_max_minutes": "0"})
        fx.script("ticket-reviewer", GRADE)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "time-up",
                    input="# Slow\n\n1. Too late.\n")
        r = fx.conveyor("intake", "time-up", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("max-minutes", r.stdout + r.stderr)
        self.assertEqual(inbox.read_meta(fx.paths, "time-up")["status"], "imported")
        self.assertFalse(os.path.isdir(os.path.join(fx.paths.needs_human, "time-up")))


if __name__ == "__main__":
    unittest.main()
