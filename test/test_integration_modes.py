"""`[global] integration` policy on `done`: merge (default), hold, command.

Protocol §7.3. Default `merge` is exercised throughout the M-series; here we cover
`hold` (no merge) and `command` (operator hook), including the `done-command` park."""
import os
import unittest

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, layout, read

ENV_KEYS = ("CONVEYOR_ROOT", "CONVEYOR_TASK", "CONVEYOR_TASK_ID",
            "CONVEYOR_COMMIT", "CONVEYOR_BRANCH", "CONVEYOR_BASE")

STUB = ('import os, sys\n'
        'open(sys.argv[1], "w").write('
        '"".join(f"{k}={os.environ.get(k, chr(45))}\\n" for k in %r))\n'
        'sys.exit(int(sys.argv[2]))\n' % (ENV_KEYS,))


class IntegrationModes(ConveyorTest):
    def _hook(self, exit_code):
        """Write a stub integration hook; return (script_path, env_out_path)."""
        stub = os.path.join(self.fx.tmp, "hook.py")
        out = os.path.join(self.fx.tmp, "hook-env.txt")
        with open(stub, "w") as f:
            f.write(STUB)
        return stub, out, exit_code

    def _drive_to_done(self):
        self.fx.script("coder", CODER_OK)
        self.fx.script("reviewer", REVIEWER_PASS)
        self.fx.start()
        self.fx.conveyor("stop")
        self.fx.task("demo")
        self.fx.drive()

    def test_hold_does_not_merge_into_main(self):
        self.fx.set_global("integration = hold")
        self.fx.script("coder", CODER_OK)
        self.fx.script("reviewer", REVIEWER_PASS)
        self.fx.start()
        self.fx.conveyor("stop")
        self.fx.task("demo")
        head_before = self.fx.git("rev-parse", "HEAD")
        self.fx.drive()
        self.assertEqual(self.fx.board()["demo"]["lane"], "done")
        # main never advanced: the done-commit was left on the role branch, not merged.
        self.assertEqual(self.fx.git("rev-parse", "HEAD"), head_before)

    def test_command_runs_hook_and_completes(self):
        stub, out, _ = self._hook(0)
        self.fx.set_global(f"integration = command: python3 {stub} {out} 0")
        self._drive_to_done()
        self.assertEqual(self.fx.board()["demo"]["lane"], "done")
        self.assertEqual(len(layout.handoffs(self.fx.paths.role("reviewer").sent)), 1)
        env = dict(l.split("=", 1) for l in read(out).splitlines())
        self.assertEqual(env["CONVEYOR_TASK"], "demo")
        self.assertEqual(env["CONVEYOR_BASE"], "main")
        self.assertEqual(env["CONVEYOR_BRANCH"], "conveyor-reviewer")
        self.assertRegex(env["CONVEYOR_COMMIT"], r"^[0-9a-f]{10}$")

    def test_command_base_is_configurable(self):
        stub, out, _ = self._hook(0)
        self.fx.set_global(f"integration = command: python3 {stub} {out} 0\n"
                           "integration_base = release/next")
        self._drive_to_done()
        env = dict(l.split("=", 1) for l in read(out).splitlines())
        self.assertEqual(env["CONVEYOR_BASE"], "release/next")

    def test_command_failure_parks_done_command(self):
        stub, out, _ = self._hook(1)
        self.fx.set_global(f"integration = command: python3 {stub} {out} 1")
        self._drive_to_done()
        self.assertEqual(self.fx.parked_reason("demo")[0], "done-command")
        self.assertEqual(self.fx.board()["demo"]["lane"], "needs-human")
        self.assertTrue(os.path.exists(
            os.path.join(self.fx.paths.needs_human, "demo", "item.handoff")))
        # the hook's log is captured for the operator
        log = os.path.join(self.fx.paths.logs, "integration")
        self.assertTrue(any(f.startswith("demo-") for f in os.listdir(log)))


class BadIntegrationConfig(ConveyorTest):
    def test_unknown_value_is_rejected(self):
        from conveyor import config
        self.fx.set_global("integration = publish")
        with self.assertRaises(config.ConfigError):
            config.load(self.fx.root)

    def test_command_without_a_command_is_rejected(self):
        from conveyor import config
        self.fx.set_global("integration = command:")
        with self.assertRaises(config.ConfigError):
            config.load(self.fx.root)


if __name__ == "__main__":
    unittest.main()
