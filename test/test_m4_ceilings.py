"""M4: ceilings park tasks in needs-human; conveyor status matches runbook §6."""
import json
import os
import re
import time
import unittest

from harness import CODER_OK, REVIEWER_FINDINGS, ConveyorTest, layout

# A one-second deadline and a one-second TERM->KILL grace, so the kill paths are
# exercised without the suite paying the real 60 s floor.
FAST = {"CONVEYOR_DEADLINE_SECONDS": "1", "CONVEYOR_KILL_GRACE": "1",
        "CONVEYOR_DRAIN_GRACE": "1"}


class M4Retries(ConveyorTest):
    coder_conf = "max_retries=3 max_attempts=3"

    def test_impossible_task_parks_on_max_retries(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_FINDINGS)
        fx.start()
        fx.conveyor("stop")
        fx.task("fix-cache", "# fix-cache\n\n1. Make the test suite fail.\n")
        fx.drive(rounds=20)
        row = fx.board()["fix-cache"]
        self.assertEqual(row["lane"], "needs-human")
        self.assertEqual(row["retry_count"], "4")
        reason = fx.parked_reason("fix-cache")
        self.assertEqual(reason[0], "max-retries")
        self.assertEqual(reason[1], "reviewer sent findings 4 times")
        out = fx.conveyor("status").stdout
        self.assertRegex(out, r"(?m)^coder      idle\s+new: 0")
        self.assertRegex(out, r"(?m)^reviewer   idle\s+new: 0")
        self.assertIn("needs-human:\n  fix-cache   max-retries   reviewer sent findings 4 times\n", out)
        # `tok -`: the fake agent reports no usage, and unknown is never printed as 0.
        self.assertIn("board:\n  fix-cache   needs-human  audit 8  retry 4  tok -\n", out)

    def test_resume_moves_item_back_and_keeps_counters(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_FINDINGS)
        fx.start()
        fx.conveyor("stop")
        fx.task("fix-cache")
        fx.drive(rounds=20)
        before = fx.board()["fix-cache"]
        fx.conveyor("resume", "fix-cache")
        self.assertFalse(os.path.exists(os.path.join(fx.paths.needs_human, "fix-cache")))
        new = layout.handoffs(fx.paths.role("coder").new)
        self.assertEqual(len(new), 1)
        h = fx.read_handoff(os.path.join(fx.paths.role("coder").new, new[0]))[0]
        self.assertEqual(h["attempt"], "1")
        after = fx.board()["fix-cache"]
        self.assertEqual(after["lane"], "coder")
        for k in ("task_id", "audit_count", "retry_count"):
            self.assertEqual(after[k], before[k])


class M4Attempts(ConveyorTest):
    coder_conf = "max_attempts=2"

    def test_no_handoff_parks_on_max_attempts(self):
        fx = self.fx
        fx.script("coder", 'commit "Partial"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        self.assertEqual(fx.parked_reason("demo")[0], "max-attempts")
        logs = sorted(os.listdir(os.path.join(fx.paths.logs, "coder")))
        self.assertEqual([l for l in logs if l.endswith(".jsonl")],
                         ["demo_operator-000001_a1.jsonl", "demo_operator-000001_a2.jsonl"])
        h = fx.read_handoff(os.path.join(fx.paths.needs_human, "demo", "item.handoff"))[0]
        self.assertEqual(h["attempt"], "3")
        self.assertTrue(h["session"].startswith("fake-"))

    def test_second_attempt_resumes_session_and_quotes_validator(self):
        fx = self.fx
        fx.script("coder", 'commit "Partial"\ndraft reviewer $TASK ready\nhandoff\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        prompts = re.findall(r'"prompt": "(.*?)"\}', fx.logs("coder"))
        self.assertEqual(len(prompts), 2)
        self.assertIn("Last validator output:\\nAUDIT_REQUIRED: handoff for demo not queued (audit 1)", prompts[1])
        self.assertIn("--resume", fx.logs("coder"))


class M4Minutes(ConveyorTest):
    coder_conf = "max_minutes=0"

    def test_wall_clock_ceiling(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_FINDINGS)
        fx.start()
        fx.conveyor("stop")
        fx.task("slow")
        fx.loop("coder")
        fx.loop("reviewer")
        time.sleep(1.1)
        fx.loop("coder")
        self.assertEqual(fx.parked_reason("slow")[0], "max-minutes")
        self.assertNotEqual(fx.board()["slow"]["started_at"], "-")

    def test_zero_minutes_still_parks_on_the_pre_flight_check(self):
        """Regression guard for the 60 s floor: max_minutes=0 must keep parking the
        way it always did -- before the run, with the pre-flight detail text -- not
        by killing a run that has only just started."""
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", REVIEWER_FINDINGS)
        fx.start()
        fx.conveyor("stop")
        fx.task("slow")
        fx.loop("coder")
        fx.loop("reviewer")
        time.sleep(1.1)
        fx.loop("coder")
        reason = fx.parked_reason("slow")
        self.assertEqual(reason[0], "max-minutes")
        self.assertTrue(reason[1].startswith("task started "), reason[1])
        self.assertIn("exceeds max_minutes 0", reason[1])


class M4Deadline(ConveyorTest):
    """The deadline half of max_minutes: a wedged run is killed, not waited on."""

    coder_conf = "max_minutes=120 max_attempts=3"

    def wedge(self, script, extra=None):
        fx = self.fx
        fx.script("coder", script)
        fx.start()
        fx.conveyor("stop")
        fx.task("slow")
        return fx.loop("coder", {**FAST, **(extra or {})})

    def records(self):
        return [json.loads(l) for l in self.fx.logs("coder").splitlines() if l.strip()]

    def jsonl(self):
        return sorted(f for f in os.listdir(os.path.join(self.fx.paths.logs, "coder"))
                      if f.endswith(".jsonl"))

    def test_wedged_run_is_killed_and_parks(self):
        r = self.wedge('commit "Partial"\nsleep 600\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        reason = self.fx.parked_reason("slow")
        self.assertEqual(reason[0], "max-minutes")
        self.assertTrue(reason[1].startswith("killed attempt 1 after "), reason[1])
        self.assertIn("exceeds max_minutes 120", reason[1])
        self.assertRegex(r.stdout, r"slow: attempt 1 killed after \d+m\d+s \(max-minutes deadline\)")
        self.assertEqual(self.fx.board()["slow"]["lane"], "needs-human")

    def test_kill_is_not_a_failed_attempt(self):
        self.wedge('commit "Partial"\nsleep 600\n')
        # One run log, not two: the budget is spent, so there is no retry to log.
        self.assertEqual(self.jsonl(), ["slow_operator-000001_a1.jsonl"])
        h = self.fx.read_handoff(
            os.path.join(self.fx.paths.needs_human, "slow", "item.handoff"))[0]
        self.assertEqual(h["attempt"], "1")

    def test_run_log_ends_killed_then_exit(self):
        self.wedge('commit "Partial"\nsleep 600\n')
        records = self.records()
        # `usage` sits between them: the kill is recorded, then what the run spent
        # before it, then the exit code -- which stays the last line of a run (§6.9).
        self.assertEqual([r.get("event") for r in records[-3:]], ["killed", "usage", "exit"])
        killed = records[-3]
        self.assertEqual(killed["reason"], "max-minutes")
        self.assertEqual(killed["signal"], "TERM")
        self.assertFalse(killed["escalated"])
        self.assertGreaterEqual(killed["after_s"], 1)
        self.assertEqual(killed["text"], f"after {killed['after_s'] // 60}m{killed['after_s'] % 60}s"
                                        " (max-minutes deadline)")

    def test_handoff_wins_over_the_kill(self):
        """An agent that queued a valid handoff and then wedged has done the work.
        The kill must not discard it: the outbox is the only signal."""
        fx = self.fx
        r = self.wedge(CODER_OK + "sleep 600\n", {"CONVEYOR_DEADLINE_SECONDS": "5"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("slow: forwarded", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(fx.paths.needs_human, "slow")))
        self.assertEqual(fx.board()["slow"]["lane"], "reviewer")
        self.assertEqual(len(layout.handoffs(fx.paths.role("reviewer").new)), 1)

    def test_term_ignored_escalates_to_kill(self):
        self.wedge('commit "Partial"\nignore-term\nsleep 600\n')
        killed = [r for r in self.records() if r.get("event") == "killed"]
        self.assertEqual(len(killed), 1, self.records())
        self.assertTrue(killed[0]["escalated"], killed[0])
        self.assertEqual(self.fx.parked_reason("slow")[0], "max-minutes")


class M4Tokens(ConveyorTest):
    """max_tokens: the cost ceiling. Task-wide, checked between attempts, and
    never fired on a number no agent reported (plan decisions 7, 8, 9)."""

    coder_conf = "max_tokens=1000 max_attempts=3"
    SPENDS = 'commit "Partial"\nusage 4000 1000\nexit 0\n'

    def test_over_budget_parks_max_tokens(self):
        fx = self.fx
        fx.script("coder", self.SPENDS)
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        reason = fx.parked_reason("demo")
        self.assertEqual(reason[0], "max-tokens")
        self.assertEqual(reason[1], "5.0k tokens over max_tokens 1000")
        self.assertEqual(fx.board()["demo"]["lane"], "needs-human")

    def test_park_happens_between_attempts_not_on_the_next_dequeue(self):
        """One item, one agent run: attempt 1 blows the budget and there is no
        attempt 2. A ceiling that only fired on the next dequeue would bound nothing."""
        fx = self.fx
        fx.script("coder", self.SPENDS)
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        runs = [f for f in sorted(os.listdir(os.path.join(fx.paths.logs, "coder")))
                if f.endswith(".jsonl")]
        self.assertEqual(runs, ["demo_operator-000001_a1.jsonl"])
        self.assertEqual(fx.parked_reason("demo")[0], "max-tokens")

    def test_the_budget_is_task_wide_across_roles(self):
        """A coder-reviewer bounce is one budget: the reviewer's spend is counted
        against the coder's ceiling on the way back (decision 7)."""
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nusage 400 100\n'
                           'draft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.script("reviewer", 'commit --empty "Review: $TASK\\n\\n1. requirement 1 - not proven"\n'
                              'usage 400 200\ndraft coder $TASK findings\nhandoff\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.drive(rounds=6)
        # 500 (coder) + 600 (reviewer) = 1100 > 1000, though neither role spent it alone.
        self.assertEqual(fx.parked_reason("demo")[0], "max-tokens")
        self.assertEqual(fx.parked_reason("demo")[1], "1.1k tokens over max_tokens 1000")

    def test_usage_the_agent_never_reported_does_not_park(self):
        """Every sidecar `source: none`: the total is unknown, so the ceiling cannot
        fire. Conveyor refuses rather than parks on a number it invented."""
        fx = self.fx
        fx.script("coder", 'commit "Partial"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        self.assertEqual(fx.parked_reason("demo")[0], "max-attempts")


class M4TokensUnset(ConveyorTest):
    def test_no_max_tokens_never_parks_however_much_is_spent(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nusage 9000000 9000000\n'
                           'draft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.script("reviewer", 'commit --empty "Verified $TASK"\nusage 9000000 9000000\n'
                              'draft done $TASK pass\nhandoff\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.drive()
        self.assertEqual(fx.board()["demo"]["lane"], "done")
        self.assertEqual(os.listdir(fx.paths.needs_human), [])


class M4NoAgent(ConveyorTest):
    def test_missing_agent_binary_parks(self):
        fx = self.fx
        fx.script("coder", CODER_OK)  # never runs; the binary is unreachable
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        r = fx.loop("coder", {"CONVEYOR_AGENT_BIN": "/nonexistent/conveyor-agent"})
        self.assertEqual(r.returncode, 0, r.stderr)  # parked, not crashed
        self.assertIn("E_NO_AGENT", r.stdout)
        self.assertEqual(fx.parked_reason("demo")[0], "no-agent")
        self.assertEqual(fx.board()["demo"]["lane"], "needs-human")
        self.assertTrue(os.path.exists(os.path.join(fx.paths.needs_human, "demo", "item.handoff")))
        # No agent log was written: the loop never got as far as launching.
        self.assertEqual([f for f in os.listdir(os.path.join(fx.paths.logs, "coder"))
                          if f.endswith(".jsonl")], [])


class IntakeCeilingsDoNotChangeBelt(ConveyorTest):
    def test_inbox_zero_does_not_rewrite_coder_minutes(self):
        from conveyor import config
        config.write_inbox(self.fx.root, {"ticket_reviewer_max_minutes": "0"})
        cfg = config.load(self.fx.root)
        self.assertEqual(cfg.role("coder").max_minutes, 120)
        self.assertEqual(cfg.role(config.INTAKE_ROLE).max_minutes, 0)


if __name__ == "__main__":
    unittest.main()
