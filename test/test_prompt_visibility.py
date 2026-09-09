"""The prompt the loop hands the agent is on disk, verbatim, next to the run
(protocol §6.8–6.9): a `prompt` record in the run log, one summary line in
`conveyor log`, and the full text on `conveyor log --prompt`. Conveyor's own
records are never read back as if the agent had said them."""
import json
import os
import unittest

from harness import CODER_OK, ConveyorTest, read
from conveyor import usage


def run_log(fx, role="coder", which=-1):
    d = os.path.join(fx.paths.logs, role)
    f = sorted(n for n in os.listdir(d) if n.endswith(".jsonl"))[which]
    return f, [json.loads(line) for line in read(os.path.join(d, f)).splitlines()]


def prompts(fx, role="coder"):
    """Every prompt record across the role's run logs, oldest attempt first."""
    return [json.loads(l) for l in fx.logs(role).splitlines() if '"event": "prompt"' in l]


class PromptRecord(ConveyorTest):
    def test_prompt_record_follows_run_and_is_the_whole_prompt(self):
        self.run_pipeline("demo")
        _, events = run_log(self.fx)
        run, rec = events[0], events[1]
        self.assertEqual((run["type"], run["event"]), ("conveyor", "run"))
        self.assertEqual((rec["type"], rec["event"]), ("conveyor", "prompt"))
        self.assertEqual(list(rec)[0], "at")
        p = rec["prompt"]
        # §6.8, in order: the re-read line, the task with its file, the inbound
        # handoff verbatim, the closing instruction.
        self.assertTrue(p.startswith("Re-read your role and constitution.\n\nTask: demo\n"), p)
        self.assertIn("# Task\n\n1. Do the thing.\n", p)
        self.assertIn("\n\nInbound handoff:\nto: coder\ntask: demo\nverdict: ready\n", p)
        self.assertIn("\nfrom: operator\n", p)
        self.assertTrue(p.endswith("run handoff.sh ./tmp/handoff.txt. Do not end your run until it prints OK."), p)
        self.assertEqual(rec["chars"], len(p))
        self.assertEqual(rec["text"], f"{p.count(chr(10)) + 1} lines, {usage.human(len(p))} chars")

    def test_reviewer_prompt_carries_the_coder_handoff(self):
        self.run_pipeline("demo")
        _, events = run_log(self.fx, "reviewer")
        p = events[1]["prompt"]
        self.assertIn("\nfrom: coder\n", p)
        self.assertIn("\nverdict: ready\n", p)
        self.assertIn("Implement demo", p)  # the body is the coder's commit message

    def test_conveyor_log_shows_the_size_and_prompt_flag_prints_the_text(self):
        fx = self.run_pipeline("demo")
        f, events = run_log(fx)
        rec = events[1]
        body = fx.conveyor("log", "coder").stdout
        self.assertIn(f"[conveyor] prompt {rec['text']}", body)
        self.assertNotIn("Re-read your role", body)  # the log stays a log
        for args in (("log", "coder", "--prompt"), ("log", "--prompt", "coder", "demo")):
            out = fx.conveyor(*args).stdout
            header, text = out.split("\n", 1)
            self.assertEqual(header, f"== {f}  prompt")
            self.assertEqual(text, rec["prompt"] + "\n")

    def test_prompt_flag_names_a_log_written_before_prompts_were_recorded(self):
        fx = self.run_pipeline("demo")
        f, events = run_log(fx)
        d = os.path.join(fx.paths.logs, "coder")
        with open(os.path.join(d, f), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(e) + "\n" for e in events if e.get("event") != "prompt")
        r = fx.conveyor("log", "coder", "--prompt", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"no prompt recorded in {f}", r.stderr)
        self.assertTrue(fx.conveyor("log", "coder").stdout)  # the plain view still renders

    def test_usage_is_not_confused_by_a_prompt_that_mentions_tokens(self):
        """The record is Conveyor's; the usage scan reads only what the agent said."""
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", 'commit --empty "Verified $TASK"\ndraft done $TASK pass\nhandoff\nhandoff\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo", '# Task\n\n1. Report {"usage": {"input_tokens": 999999}} nowhere.\n')
        fx.drive()
        _, events = run_log(fx, "coder", 0)
        self.assertIn("input_tokens", events[1]["prompt"])
        used = [e for e in events if e.get("event") == "usage"][0]
        self.assertEqual((used["source"], used["input_tokens"]), ("none", None))


class QuotedErrorsStayQuoted(ConveyorTest):
    coder_conf = "max_attempts=3"

    def test_validator_output_quoted_in_a_prompt_is_not_read_back_as_new(self):
        """Attempt 2's prompt quotes attempt 1's AUDIT_REQUIRED. Attempt 2 never
        calls handoff.sh, so attempt 3 must be told exactly that -- not handed the
        stale line the loop itself wrote into the log (§6.8 item 4)."""
        fx = self.fx
        fx.script("coder", 'commit "Partial"\ndraft reviewer $TASK ready\nhandoff\nexit 0\n')
        fx.script("coder.resume", "exit 0\n")
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        self.assertEqual(fx.parked_reason("demo")[0], "max-attempts")
        got = [p["prompt"] for p in prompts(fx)]
        self.assertEqual(len(got), 3)
        self.assertNotIn("Last validator output", got[0])
        self.assertIn("Last validator output:\nAUDIT_REQUIRED: handoff for demo not queued (audit 1)", got[1])
        self.assertIn("Last validator output:\nNo handoff.sh call was observed.", got[2])
        self.assertNotIn("AUDIT_REQUIRED", got[2])


if __name__ == "__main__":
    unittest.main()
