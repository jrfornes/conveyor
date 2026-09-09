"""Parser and helpers for project.md gate catalog (no worktree)."""
import os
import shutil
import tempfile
import unittest

from harness import gone
from conveyor import gates, layout, util

IMPLICIT = """# Project

## Test command

```
exit 0
```
"""

GATES = """# Project

## Gates

test:
```
exit 0
```

lint:check:
```
exit 0
```

## Required on

coder ready: test, lint:check
reviewer pass: test
"""

ONE_LINE = """# Project

## Gates

test: echo hello
lint:check: exit 0

## Required on

coder ready: test, lint:check
"""


TIMEOUTS = GATES + "\n## Gate timeouts\n\ntest: 30\n"


class ParseGates(unittest.TestCase):
    def test_implicit_test_command(self):
        c = gates.parse(IMPLICIT)
        self.assertEqual(c.source, "test-command")
        self.assertEqual(c.commands, {"test": "exit 0"})
        self.assertEqual(c.required, {})

    def test_implicit_empty_skips(self):
        text = "# Project\n\n## Test command\n\n```\n<!-- skip -->\n```\n"
        c = gates.parse(text)
        self.assertEqual(c.commands["test"], "")
        self.assertEqual(gates.required(c, "coder", "ready", ["coder", "reviewer"]), [])

    def test_implicit_required_on_belt(self):
        c = gates.parse(IMPLICIT)
        self.assertEqual(gates.required(c, "coder", "ready", ["coder", "reviewer"]), ["test"])
        self.assertEqual(gates.required(c, "reviewer", "pass", ["coder", "reviewer"]), ["test"])
        self.assertEqual(gates.required(c, "coder", "findings", ["coder", "reviewer"]), [])

    def test_both_sections_error(self):
        text = IMPLICIT + "\n## Gates\n\ntest:\n```\nexit 0\n```\n\n## Required on\n\ncoder ready: test\n"
        with self.assertRaises(gates.GateParseError):
            gates.parse(text)

    def test_comment_example_does_not_trigger_both(self):
        text = """# Project

## Test command

```
exit 0
```

<!-- Or replace with:

## Gates

test:
```
make test
```

## Required on

coder ready: test
-->
"""
        gates.parse(text)  # must not raise

    def test_gates_without_required(self):
        with self.assertRaises(gates.GateParseError):
            gates.parse("# Project\n\n## Gates\n\ntest:\n```\nexit 0\n```\n")

    def test_required_without_gates(self):
        with self.assertRaises(gates.GateParseError):
            gates.parse("# Project\n\n## Required on\n\ncoder ready: test\n")

    def test_named_catalog(self):
        c = gates.parse(GATES)
        self.assertEqual(c.source, "gates")
        self.assertEqual(set(c.commands), {"test", "lint:check"})
        self.assertEqual(c.required[("coder", "ready")], ["test", "lint:check"])
        self.assertEqual(gates.required(c, "coder", "ready", ["coder", "reviewer"]),
                         ["test", "lint:check"])

    def test_one_line_argv(self):
        c = gates.parse(ONE_LINE)
        self.assertEqual(c.commands["test"], "echo hello")
        self.assertEqual(c.commands["lint:check"], "exit 0")

    def test_off_belt_role_ignored_at_validate(self):
        c = gates.parse(GATES + "\nspecifier ready: missing\n")
        missing = gates.validate_for_belt(c, ["coder", "reviewer"])
        self.assertEqual(missing, [])

    def test_missing_gate_on_belt(self):
        c = gates.parse(GATES.replace("lint:check:", "lint:check:").replace(
            "lint:check:\n```\nexit 0\n```", ""))
        # remove lint:check command but keep it in required
        text = """# Project

## Gates

test:
```
exit 0
```

## Required on

coder ready: test, lint:check
"""
        c = gates.parse(text)
        missing = gates.validate_for_belt(c, ["coder", "reviewer"])
        self.assertEqual(missing, [("coder", "ready", "lint:check")])

    def test_expand_substitutions(self):
        self.assertEqual(gates.expand("base {inbound} head {head}", "abc", "def"),
                         "base abc head def")

    def test_expand_unknown(self):
        with self.assertRaises(gates.GateSubstError) as ctx:
            gates.expand("echo {foo}", "a", "b")
        self.assertEqual(ctx.exception.token, "{foo}")


class ParseGateTimeouts(unittest.TestCase):
    def test_section_parses_and_overrides_the_default(self):
        c = gates.parse(TIMEOUTS)
        self.assertEqual(c.timeouts, {"test": 30})
        self.assertEqual(gates.timeout_for(c, "test", 900), 30)
        self.assertEqual(gates.timeout_for(c, "lint:check", 900), 900)

    def test_absent_section_takes_the_global_default(self):
        c = gates.parse(GATES)
        self.assertEqual(c.timeouts, {})
        self.assertEqual(gates.timeout_for(c, "test", 900), 900)

    def test_zero_is_unbounded(self):
        c = gates.parse(GATES + "\n## Gate timeouts\n\ntest: 0\n")
        self.assertEqual(gates.timeout_for(c, "test", 900), 0)

    def test_works_with_the_legacy_test_command_form(self):
        c = gates.parse(IMPLICIT + "\n## Gate timeouts\n\ntest: 5\n")
        self.assertEqual(gates.timeout_for(c, "test", 900), 5)

    def test_unknown_gate_name(self):
        with self.assertRaises(gates.GateParseError):
            gates.parse(GATES + "\n## Gate timeouts\n\nbuild: 30\n")

    def test_non_integer(self):
        with self.assertRaises(gates.GateParseError):
            gates.parse(GATES + "\n## Gate timeouts\n\ntest: soon\n")

    def test_negative(self):
        with self.assertRaises(gates.GateParseError):
            gates.parse(GATES + "\n## Gate timeouts\n\ntest: -1\n")

    def test_missing_value(self):
        with self.assertRaises(gates.GateParseError):
            gates.parse(GATES + "\n## Gate timeouts\n\ntest\n")


class RunGateTimeout(unittest.TestCase):
    """The exec half: a gate that never returns is killed, group and all."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="conveyor-gate-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = layout.Paths(self.tmp)

    def run_gate(self, argv, timeout=1):
        return gates.run(self.paths, self.tmp, "coder", "demo", "a1b2c3d4e5", "test",
                         argv, timeout=timeout)

    def test_slow_gate_raises_and_logs_what_it_had(self):
        with self.assertRaises(gates.GateTimeoutError) as ctx:
            self.run_gate("echo started; sleep 600")
        self.assertEqual(ctx.exception.seconds, 1)
        self.assertTrue(ctx.exception.log_path.endswith("coder-demo-a1b2c3d4e5-test.txt"),
                        ctx.exception.log_path)
        log = util.read_text(ctx.exception.log_path)
        self.assertTrue(log.startswith("exit: timeout\n"), log)
        self.assertIn("argv: echo started; sleep 600", log)
        self.assertIn("started", log)

    def test_zero_timeout_is_unbounded(self):
        self.run_gate("exit 0", timeout=0)  # must return, not raise

    def test_the_shells_child_dies_too(self):
        """The reason gates need their own group: with shell=True a plain
        `communicate(timeout=…)` kills the shell and orphans the real command."""
        marker = os.path.join(self.tmp, "child.pid")
        with self.assertRaises(gates.GateTimeoutError):
            self.run_gate(f"sh -c 'sleep 601 & echo $! > {marker}; wait'")
        pid = int(util.read_text(marker).strip())
        self.assertTrue(gone(pid), "the gate's grandchild survived the timeout")


if __name__ == "__main__":
    unittest.main()
