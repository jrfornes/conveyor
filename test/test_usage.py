"""Token accounting: usage.scan classifies what it found, and never guesses.

Pure unit tests — no agent, no worktree. The rules under test are the plan's
locked decisions 3, 4 and 9: a result event wins outright, per-message events
are summed only in its absence, and an absent number stays absent.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from conveyor import layout, usage, util  # noqa: E402


def log(*events):
    return "".join(json.dumps(e) + "\n" for e in events)


RESULT = {"type": "result", "subtype": "success",
          "usage": {"input_tokens": 88100, "output_tokens": 9200}}
MSG1 = {"type": "assistant", "message": {"usage": {"input_tokens": 40000, "output_tokens": 4000}}}
MSG2 = {"type": "assistant", "message": {"usage": {"input_tokens": 48100, "output_tokens": 5200}}}


class Scan(unittest.TestCase):
    def test_result_event_wins_and_per_message_ignored(self):
        s = usage.scan(log(MSG1, RESULT))
        self.assertEqual(s["source"], "result")
        self.assertEqual((s["input"], s["output"]), (88100, 9200))

    def test_per_message_only_is_summed(self):
        s = usage.scan(log(MSG1, MSG2))
        self.assertEqual(s["source"], "messages")
        self.assertEqual((s["input"], s["output"]), (88100, 9200))

    def test_both_present_does_not_double_bill(self):
        """The guard: a cumulative result total must never be added to the deltas."""
        s = usage.scan(log(MSG1, MSG2, RESULT))
        self.assertEqual(s["source"], "result")
        self.assertEqual(s["input"], 88100)
        self.assertNotEqual(s["input"], 88100 + 40000 + 48100)

    def test_no_usage_anywhere_is_none_not_zero(self):
        s = usage.scan(log({"type": "system", "session_id": "x"},
                           {"type": "result", "text": "done"}))
        self.assertEqual(s["source"], "none")
        for f in usage.FIELDS:
            self.assertIsNone(s[f])

    def test_tolerates_wrapper_lines_and_a_truncated_tail(self):
        text = (log({"type": "output", "text": '{"usage": {"input_tokens": 999}}'})
                + log(MSG1) + '{"type":"result","usage":{"input_to')
        s = usage.scan(text)
        # The wrapped line is a string, not an event: its numbers are not billed.
        self.assertEqual(s["source"], "messages")
        self.assertEqual(s["input"], 40000)

    def test_every_alias_maps_to_its_field(self):
        for field, keys in usage.ALIASES.items():
            for k in keys:
                s = usage.scan(log({"type": "result", "usage": {k: 7}}))
                self.assertEqual(s[field], 7, f"{k} → {field}")
                for other in usage.FIELDS:
                    if other != field:
                        self.assertIsNone(s[other], f"{k} leaked into {other}")

    def test_unknown_keys_are_ignored_never_summed(self):
        s = usage.scan(log({"type": "result", "usage": {"thinking_tokens": 500}}))
        self.assertEqual(s["source"], "result")
        self.assertIsNone(s["input"])


class Total(unittest.TestCase):
    def runs(self):
        return [{"source": "result", "input": 10, "output": 1, "duration_s": 60.0},
                {"source": "messages", "input": 20, "output": 2, "duration_s": 30.0},
                {"source": "none", "input": None, "output": None, "duration_s": 15.0}]

    def test_unknown_runs_are_counted_not_zeroed(self):
        t = usage.total(self.runs())
        self.assertEqual(t["runs"], 3)
        self.assertEqual(t["unknown"], 1)
        self.assertEqual(t["known"], 2)
        self.assertEqual((t["input"], t["output"], t["total"]), (30, 3, 33))
        self.assertEqual(t["wall_s"], 105.0)

    def test_all_unknown_sums_to_none_not_zero(self):
        t = usage.total([{"source": "none", "duration_s": 1}])
        self.assertEqual(t["known"], 0)
        self.assertIsNone(t["total"])
        self.assertIsNone(t["input"])
        self.assertEqual(t["wall_s"], 1.0)  # wall time is always known


class Sidecars(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="conveyor-usage-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.paths = layout.Paths(self.tmp)

    def test_record_then_read_task_across_roles(self):
        usage.record(self.paths, "coder", "add-login", "operator-000001", 1,
                     usage.scan(log(RESULT)), 372.4, 0)
        usage.record(self.paths, "reviewer", "add-login", "coder-000001", 1,
                     usage.scan(log(MSG1)), 60.0, 0)
        usage.record(self.paths, "coder", "other", "operator-000002", 1,
                     usage.scan(""), 1.0, 0)
        runs = usage.read_task(self.paths, "add-login")
        self.assertEqual([r["role"] for r in runs], ["coder", "reviewer"])
        self.assertEqual(usage.total(runs)["total"], 88100 + 9200 + 40000 + 4000)
        self.assertEqual(usage.task_total(self.paths, "other"), None)

    def test_a_run_with_no_usage_still_writes_a_file(self):
        run = usage.record(self.paths, "coder", "demo", "operator-000001", 2,
                           usage.scan(""), 12.0, 1)
        p = usage.path(self.paths, "coder", "demo", "operator-000001", 2)
        self.assertTrue(os.path.isfile(p))
        self.assertEqual(run["source"], "none")
        self.assertEqual(run["exit"], 1)
        self.assertEqual(run["duration_s"], 12.0)
        self.assertIsNone(json.loads(util.read_text(p))["input"])


if __name__ == "__main__":
    unittest.main()
