"""Parser and helpers for project.md gate catalog (no worktree)."""
import unittest

from conveyor import gates

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


if __name__ == "__main__":
    unittest.main()
