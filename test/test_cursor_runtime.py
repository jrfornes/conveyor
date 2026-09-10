"""Cursor CLI runtime (docs/plans/cursor-cli-runtime.md): the fixed argument
list the loop and the smoke test pass, and what `conveyor start` proves before a
task is ever dequeued."""
import os
import tempfile
import unittest

from harness import FAKE, ConveyorTest, read
from conveyor import agent, config


class Compose(unittest.TestCase):
    """agent.compose — the single source of the argument list (decisions 1, 2)."""

    def test_fixed_list_in_order_then_model_and_format(self):
        cmd = agent.compose("cursor-agent", "composer-2.5", [], output_format="stream-json")
        self.assertEqual(cmd, ["cursor-agent", "-p", "--force", "--trust", "--sandbox",
                               "disabled", "--model", "composer-2.5",
                               "--output-format", "stream-json"])

    def test_resume_sits_between_the_fixed_list_and_the_prompt(self):
        # run_agent composes, then appends --resume / prompt exactly as the loop does.
        cmd = agent.compose("cursor-agent", "composer-2.5", [], output_format="stream-json")
        cmd += ["--resume", "sess-1"]
        cmd.append("do the task")
        self.assertEqual(cmd[:6], ["cursor-agent", "-p", "--force", "--trust", "--sandbox", "disabled"])
        self.assertEqual(cmd[-1], "do the task")
        self.assertEqual(cmd[-3:-1], ["--resume", "sess-1"])

    def test_trust_in_agent_args_is_deduped_to_one(self):
        cmd = agent.compose("cursor-agent", "m", ["--trust"], output_format="stream-json")
        self.assertEqual(cmd.count("--trust"), 1)

    def test_a_role_sandbox_override_survives_after_the_fixed_one(self):
        cmd = agent.compose("cursor-agent", "m", ["--sandbox", "enabled"],
                            output_format="stream-json")
        # both present, the operator's after Conveyor's, so Cursor takes the later one
        self.assertEqual(cmd.count("--sandbox"), 2)
        first = cmd.index("--sandbox")
        self.assertEqual(cmd[first + 1], "disabled")
        self.assertEqual(cmd[cmd.index("--sandbox", first + 1) + 1], "enabled")

    def test_no_output_format_when_none(self):
        cmd = agent.compose("cursor-agent", "m", [])
        self.assertNotIn("--output-format", cmd)

    def test_extra_is_otherwise_untouched(self):
        cmd = agent.compose("cursor-agent", "m", ["--foo", "bar"], output_format="stream-json")
        self.assertEqual(cmd[-2:], ["--foo", "bar"])


class SaveDropsTrust(unittest.TestCase):
    def test_save_with_no_global_writes_no_agent_args(self):
        with tempfile.TemporaryDirectory() as d:
            config.save(d, config.Config([config.Role("coder", "m")]))
            text = read(os.path.join(d, "conveyor.conf"))
            self.assertIn("[global]", text)
            self.assertIn("agent_bin = cursor-agent", text)
            self.assertNotIn("agent_args", text)


class RunAgentArgv(ConveyorTest):
    """The loop's launch really uses the fixed list (recorded via CONVEYOR_FAKE_ARGV)."""

    def test_run_agent_begins_with_the_fixed_list(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\ndraft reviewer $TASK ready\nhandoff\nhandoff\n')
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.task("demo")
        argv = os.path.join(fx.tmp, "argv.txt")
        fx.loop("coder", {"CONVEYOR_FAKE_ARGV": argv})
        tokens = read(argv).splitlines()
        self.assertEqual(tokens[:9], ["-p", "--force", "--trust", "--sandbox", "disabled",
                                      "--model", "composer-2.5", "--output-format", "stream-json"])


class Smoke(ConveyorTest):
    """`conveyor start` proves the handoff path per role before any loop (decision 4)."""

    def smoke_script(self, role, text):
        with open(os.path.join(self.fx.scripts, role + ".smoke"), "w") as f:
            f.write(text)

    def coder_branch_subjects(self):
        return self.fx.git("log", "conveyor-coder", "--format=%s").splitlines()

    def loop_running(self, role="coder"):
        from conveyor import layout
        return layout.loop_pid(self.fx.paths, role)

    def test_smoke_pass_leaves_no_commit_and_no_probe(self):
        fx = self.fx
        self.smoke_script("coder", 'probe-write $ROOT/tmp/smoke-$ROLE.txt ok\n'
                                   'commit --empty "conveyor smoke"\nexit 0\n')
        r = fx.conveyor("start", check=False)
        fx.conveyor("stop", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("coder: smoke ok", r.stdout)
        self.assertNotIn("conveyor smoke", self.coder_branch_subjects())
        self.assertFalse(os.path.exists(os.path.join(fx.root, "tmp", "smoke-coder.txt")))

    def test_missing_probe_reports_the_sandbox(self):
        fx = self.fx
        self.smoke_script("coder", 'commit --empty "conveyor smoke"\nexit 0\n')
        r = fx.conveyor("start", check=False)
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("coder could not write outside its worktree; the Cursor sandbox is on", out)
        self.assertIn("check ~/.cursor/cli-config.json sandbox.mode and any --sandbox in cli-args", out)
        self.assertFalse(self.loop_running())

    def test_no_commit_reports_approval_mode(self):
        fx = self.fx
        self.smoke_script("coder", 'probe-write $ROOT/tmp/smoke-$ROLE.txt ok\nexit 0\n')
        r = fx.conveyor("start", check=False)
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("coder did not commit; check ~/.cursor/cli-config.json approvalMode "
                      "and permissions.deny for Shell(git)", out)

    def test_byline_not_last_reports_attribution(self):
        fx = self.fx
        self.smoke_script("coder", 'probe-write $ROOT/tmp/smoke-$ROLE.txt ok\n'
                                   'commit-amend-trailer "Made with Cursor"\nexit 0\n')
        r = fx.conveyor("start", check=False)
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('coder\'s commit does not end with "By coder."; last line is Made with Cursor', out)
        self.assertIn("Set attribution.attributeCommitsToAgent to false", out)

    def test_two_commits_refuse_without_reset(self):
        fx = self.fx
        self.smoke_script("coder", 'probe-write $ROOT/tmp/smoke-$ROLE.txt ok\n'
                                   'commit --empty "conveyor smoke"\n'
                                   'commit --empty "conveyor smoke two"\nexit 0\n')
        r = fx.conveyor("start", check=False)
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("conveyor-coder moved from", out)
        self.assertIn("expected exactly one commit", out)
        head = fx.git("rev-parse", "--short=10", "conveyor-coder")
        self.assertIn(head, out)
        # not reset: both commits are still on the branch
        subjects = self.coder_branch_subjects()
        self.assertIn("conveyor smoke", subjects)
        self.assertIn("conveyor smoke two", subjects)

    def test_no_smoke_skips_everything(self):
        fx = self.fx
        self.smoke_script("coder", 'exit 1\n')  # would fail if it ran
        r = fx.conveyor("start", "--no-smoke", check=False)
        fx.conveyor("stop", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("smoke ok", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(fx.root, "tmp", "smoke-coder.txt")))

    def test_prints_the_resolved_agent_and_version(self):
        fx = self.fx
        r = fx.conveyor("start", "--no-smoke", check=False)
        fx.conveyor("stop", check=False)
        self.assertIn(f"agent: {FAKE} (fake-agent 0.0)", r.stdout)

    def smoke_jsonl(self, role="coder"):
        return os.path.join(self.fx.paths.logs, role, "smoke.jsonl")

    def test_smoke_tees_stdout_and_replaces_it_on_the_next_start(self):
        """token-cost-on-cursor.md decision 1 / test 4: smoke.jsonl exists after a
        start and is overwritten, never appended, on the next one."""
        fx = self.fx
        fx.conveyor("start", check=False)
        fx.conveyor("stop", check=False)
        self.assertTrue(os.path.isfile(self.smoke_jsonl()))
        first = [l for l in read(self.smoke_jsonl()).splitlines() if l.strip()]
        self.assertTrue(first)  # the default smoke emits system/fake/result events
        fx.conveyor("start", check=False)
        fx.conveyor("stop", check=False)
        second = [l for l in read(self.smoke_jsonl()).splitlines() if l.strip()]
        self.assertEqual(len(second), len(first))  # replaced, not doubled


class SmokeUsageWarning(ConveyorTest):
    """token-cost-on-cursor.md decision 3 / test 1: a max_tokens ceiling against an
    agent that reports no usage in its smoke run warns, but does not refuse."""

    coder_conf = "max_minutes=120 max_attempts=3 max_tokens=1000"

    WARNING = ("warning: coder sets max_tokens but the agent reported no usage in "
               "its smoke run; the ceiling will not fire")

    def test_warns_when_max_tokens_set_and_smoke_reports_no_usage(self):
        r = self.fx.conveyor("start", check=False)
        self.fx.conveyor("stop", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("coder: smoke ok", r.stdout)
        self.assertIn(self.WARNING, r.stdout)

    def test_no_warning_when_the_role_sets_no_ceiling(self):
        # reviewer carries no max_tokens, so only coder's line may appear.
        r = self.fx.conveyor("start", check=False)
        self.fx.conveyor("stop", check=False)
        self.assertNotIn("reviewer sets max_tokens", r.stdout)


if __name__ == "__main__":
    unittest.main()
