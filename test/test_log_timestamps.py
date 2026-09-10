"""Run logs and loop.log are dated: every line carries the time the loop saw it,
and `conveyor log` prints the run's date plus a UTC clock column."""
import datetime
import json
import os
import re
import unittest

from harness import ConveyorTest, read

CLOCK = re.compile(r"^\d{2}:\d{2}:\d{2} ")
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class LogTimestamps(ConveyorTest):
    def run_log(self, role="coder"):
        d = os.path.join(self.fx.paths.logs, role)
        f = sorted(n for n in os.listdir(d) if n.endswith(".jsonl") and n != "smoke.jsonl")[-1]
        return [json.loads(line) for line in read(os.path.join(d, f)).splitlines()]

    def test_every_run_log_line_is_dated_jsonl(self):
        self.run_pipeline("demo")
        events = self.run_log()
        self.assertTrue(events)
        for ev in events:
            self.assertTrue(TS.match(ev.get("at", "")), ev)
            datetime.datetime.strptime(ev["at"], "%Y-%m-%dT%H:%M:%SZ")

    def test_run_and_exit_records_frame_the_agent(self):
        self.run_pipeline("demo")
        events = self.run_log()
        first, last = events[0], events[-1]
        self.assertEqual(first["type"], "conveyor")
        self.assertEqual((first["event"], first["attempt"], first["role"]), ("run", 1, "coder"))
        self.assertEqual(first["model"], "composer-2.5")
        self.assertEqual((last["type"], last["event"], last["exit"]), ("conveyor", "exit", 0))
        self.assertLessEqual(first["at"], last["at"])
        self.assertIn("session_id", json.dumps(events[1]))  # agent output, dated by the stamper

    def test_agent_keys_survive_stamping(self):
        """`at` goes first; the agent's own object is passed through unchanged."""
        self.run_pipeline("demo")
        fake = [ev for ev in self.run_log() if ev.get("type") == "fake"][0]
        self.assertEqual(list(fake)[0], "at")
        self.assertIn("prompt", fake)
        self.assertIn("Task: demo", fake["prompt"])

    def test_conveyor_log_prints_date_and_clock(self):
        self.run_pipeline("demo")
        out = self.fx.conveyor("log", "coder").stdout.splitlines()
        header, body = out[0], out[1:]
        self.assertTrue(header.startswith("== demo_operator-000001_a1.jsonl "), header)
        self.assertTrue(TS.match(header.split()[-1]), header)
        self.assertTrue(body)
        for line in body:  # a wrapped detail continues in the clock's own column
            self.assertTrue(CLOCK.match(line) or line.startswith(" " * 9), line)
        self.assertTrue(any("[conveyor] run attempt 1, model composer-2.5" in l for l in body), body)
        self.assertTrue(any("[conveyor] exit 0" in l for l in body), body)

    def test_conveyor_log_pads_undated_lines(self):
        """Logs written before dating still render, with an empty clock column."""
        self.run_pipeline("demo")
        d = os.path.join(self.fx.paths.logs, "coder")
        f = sorted(n for n in os.listdir(d) if n.endswith(".jsonl") and n != "smoke.jsonl")[-1]
        with open(os.path.join(d, f), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "assistant", "text": "undated"}) + "\n")
        line = [l for l in self.fx.conveyor("log", "coder").stdout.splitlines() if "undated" in l][0]
        self.assertEqual(line, " " * 9 + "[assistant] undated")

    def test_loop_log_lines_are_dated(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.script("reviewer", 'commit --empty "Verified $TASK"\ndraft done $TASK pass\nhandoff\nhandoff\n')
        fx.start()
        fx.task("demo")
        self.assertTrue(fx.wait_settled(), fx.state())
        fx.conveyor("stop")
        lines = read(os.path.join(fx.paths.logs, "coder", "loop.log")).splitlines()
        self.assertTrue(lines)
        for line in lines:
            stamp, sep, rest = line.partition("  ")
            self.assertTrue(TS.match(stamp), line)
            self.assertTrue(rest.startswith("demo: "), line)
        self.assertTrue(any("attempt 1 running composer-2.5" in l for l in lines), lines)
        self.assertTrue(any(l.endswith("demo: forwarded") for l in lines), lines)


if __name__ == "__main__":
    unittest.main()
