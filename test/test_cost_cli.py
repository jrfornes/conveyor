"""`conveyor cost` and the `tok` column in `conveyor status` (runbook §6, §6.2).

The operator surface for token spend. `-` means the agent reported nothing and is
never printed as `0`; a task with no runs at all still reads as a task.
"""
import os
import unittest

from harness import ConveyorTest, read

CODER_USAGE = ('commit "Implement $TASK"\nusage 88100 9200\n'
               'draft reviewer $TASK ready\nhandoff\nhandoff\n')
REVIEWER_USAGE = ('commit --empty "Verified $TASK"\nusage 63000 4100\n'
                  'draft done $TASK pass\nhandoff\nhandoff\n')
# Same belt, but the agent never says what it spent.
CODER_SILENT = ('commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nhandoff\n')
REVIEWER_SILENT = ('commit --empty "Verified $TASK"\ndraft done $TASK pass\nhandoff\nhandoff\n')


class CostCLI(ConveyorTest):
    def run_task(self, task, coder=CODER_USAGE, reviewer=REVIEWER_USAGE):
        fx = self.fx
        fx.script("coder", coder)
        fx.script("reviewer", reviewer)
        fx.start()
        fx.conveyor("stop")
        fx.task(task)
        fx.drive()
        return fx

    def test_no_usage_files_at_all_is_an_empty_state_not_an_error(self):
        r = self.fx.conveyor("cost")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "no agent runs recorded yet.\n")

    def test_cost_task_lists_one_row_per_run_with_correct_totals(self):
        fx = self.run_task("add-login")
        out = fx.conveyor("cost", "add-login").stdout
        self.assertIn("ROLE      ATTEMPT  IN        OUT      TOTAL     WALL   SOURCE\n", out)
        self.assertRegex(out, r"(?m)^coder           1  88\.1k     9\.2k     97\.3k     \d+m\s+result$")
        self.assertRegex(out, r"(?m)^reviewer        1  63\.0k     4\.1k     67\.1k     \d+m\s+result$")
        # 88100+9200+63000+4100 = 164400 tokens, billed across both roles.
        self.assertRegex(out, r"(?m)^ +151\.1k    13\.3k    164\.4k")

    def test_cost_summary_totals_every_task(self):
        fx = self.run_task("add-login")
        fx.task("fix-cache")
        fx.drive()
        out = fx.conveyor("cost").stdout
        self.assertIn("TASK          RUNS  IN        OUT      TOTAL     WALL\n", out)
        self.assertRegex(out, r"(?m)^add-login        2  151\.1k    13\.3k    164\.4k")
        self.assertRegex(out, r"(?m)^ +4  302\.2k    26\.6k    328\.8k")
        self.assertIn("2 tasks, 4 runs.", out)
        self.assertNotIn("reported no usage", out)

    def test_silent_agent_reads_as_unknown_not_zero(self):
        fx = self.run_task("add-login", CODER_SILENT, REVIEWER_SILENT)
        out = fx.conveyor("cost").stdout
        self.assertRegex(out, r"(?m)^add-login        2  -         -        -")
        self.assertIn("2 runs reported no usage.", out)
        detail = fx.conveyor("cost", "add-login").stdout
        self.assertRegex(detail, r"(?m)^coder           1  -         -        -         \d+m\s+none$")

    def test_all_silent_points_at_the_runbook(self):
        """Decision 3: when every run in view reported nothing (the Cursor case),
        one trailing line says where to read why."""
        fx = self.run_task("add-login", CODER_SILENT, REVIEWER_SILENT)
        out = fx.conveyor("cost").stdout
        self.assertIn("no run reported usage; see runbook §6.2", out)

    def test_one_reported_run_suppresses_the_runbook_line(self):
        fx = self.run_task("add-login")  # CODER_USAGE / REVIEWER_USAGE both report
        out = fx.conveyor("cost").stdout
        self.assertNotIn("no run reported usage; see runbook", out)

    def test_unknown_task_dies(self):
        r = self.fx.conveyor("cost", "nope", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("conveyor cost: unknown task nope", r.stderr)

    def test_a_run_that_reported_nothing_still_wrote_a_sidecar(self):
        """`source: none` and no file mean different things and must stay distinct."""
        fx = self.run_task("add-login", CODER_SILENT, REVIEWER_SILENT)
        p = os.path.join(fx.paths.logs, "coder", "add-login_operator-000001_a1.usage.json")
        self.assertTrue(os.path.isfile(p))
        self.assertIn('"source": "none"', read(p))

    def test_status_board_prints_the_tok_column(self):
        fx = self.run_task("add-login")
        fx.script("coder", CODER_SILENT)
        fx.script("reviewer", REVIEWER_SILENT)
        fx.task("fix-cache")
        fx.drive()
        out = fx.conveyor("status").stdout
        self.assertIn("  add-login   done         audit 2  retry 0  tok 164.4k\n", out)
        self.assertIn("  fix-cache   done         audit 2  retry 0  tok -\n", out)

    def test_usage_record_reaches_conveyor_log_unchanged(self):
        fx = self.run_task("add-login")
        out = fx.conveyor("log", "coder").stdout
        self.assertRegex(out, r"\[conveyor\] usage in 88\.1k, out 9\.2k, \d+m\d\ds \(result\)")
        self.assertIn("[conveyor] exit 0", out)


class CostBudgetLine(ConveyorTest):
    coder_conf = "max_tokens=500000"

    def test_budget_line_shows_percent_used(self):
        fx = self.fx
        fx.script("coder", CODER_USAGE)
        fx.start()
        fx.conveyor("stop")
        fx.task("add-login")
        fx.loop("coder")           # leaves the task in the reviewer's lane
        fx.conveyor("stop")
        out = fx.conveyor("cost", "add-login").stdout
        self.assertNotIn("max_tokens", out)  # the reviewer lane sets no ceiling

    def test_budget_line_refuses_a_percentage_it_cannot_measure(self):
        fx = self.fx
        fx.script("coder", 'commit "Partial"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")           # parks on max-attempts with no usage reported
        fx.conveyor("resume", "demo")
        out = fx.conveyor("cost", "demo").stdout
        self.assertIn("max_tokens 500000 (coder) — no run reported usage, "
                      "so nothing is counted against it.", out)


if __name__ == "__main__":
    unittest.main()
