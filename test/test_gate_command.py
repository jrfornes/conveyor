"""Project gate catalog: ready/pass run required gates; findings/empty skip."""
import os
import unittest

from harness import CODER_OK, ConveyorTest, layout

CODER_READY = "to: reviewer\ntask: demo\nverdict: ready\n"
REVIEWER_PASS = "to: done\ntask: demo\nverdict: pass\n"
REVIEWER_FINDINGS = "to: coder\ntask: demo\nverdict: findings\n"


class GateCommand(ConveyorTest):
    def coder_ready(self):
        fx = self.fx
        fx.script("coder", 'commit "Implement $TASK"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop_crash("coder", "after-agent")
        return fx.paths.worktree("coder")

    def reviewer_in_process(self):
        fx = self.fx
        fx.script("coder", CODER_OK)
        fx.script("reviewer", 'commit --empty "Verified $TASK"\nexit 0\n')
        fx.start()
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("coder")
        fx.loop_crash("reviewer", "after-agent")
        return fx.paths.worktree("reviewer")

    def write_project(self, role, text):
        wt = self.fx.paths.worktree(role)
        with open(os.path.join(wt, "project.md"), "w") as f:
            f.write(text)
        self.fx.git("add", "project.md", cwd=wt)
        self.fx.git("commit", "-q", "--no-verify", "-m", f"Set project gates\n\nBy {role}.", cwd=wt)
        return wt

    def commit_fence(self, role, inner):
        return self.write_project(role, "# Project\n\n## Test command\n\n```\n" + inner + "\n```\n")

    def draft(self, role, text):
        path = os.path.join(self.fx.paths.worktree(role), "tmp", "handoff.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def gates_names(self):
        d = self.fx.paths.gates
        if not os.path.isdir(d):
            return []
        return os.listdir(d)

    def test_empty_and_comment_only_skip(self):
        self.coder_ready()
        self.draft("coder", CODER_READY)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("OK:"), r.stdout)
        self.assertEqual(self.gates_names(), [])

        self.commit_fence("coder", "")
        self.draft("coder", CODER_READY)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.gates_names(), [])

    def test_exit_0_still_audits(self):
        self.coder_ready()
        self.commit_fence("coder", "exit 0")
        self.draft("coder", CODER_READY)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("OK:"), r.stdout)
        self.assertEqual(self.gates_names(), [])

    def test_exit_1_ready_refuses_before_audit(self):
        self.coder_ready()
        self.commit_fence("coder", "echo gate-fail; exit 1")
        self.draft("coder", CODER_READY)
        rp = self.fx.paths.role("coder")
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(r.stdout.startswith("E_GATE_FAILED:"), r.stdout)
        self.assertEqual(os.listdir(rp.audit_pending), [])
        self.assertEqual(layout.handoffs(rp.outbox), [])
        names = self.gates_names()
        self.assertEqual(len(names), 1, names)
        self.assertTrue(names[0].endswith("-test.txt"), names)
        with open(os.path.join(self.fx.paths.gates, names[0]), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("gate-fail", log)
        self.assertIn("exit: 1", log)
        self.assertIn("echo gate-fail; exit 1", log)

    def test_exit_1_findings_skips_gate(self):
        self.reviewer_in_process()
        self.commit_fence("reviewer", "echo gate-fail; exit 1")
        self.draft("reviewer", REVIEWER_FINDINGS)
        rp = self.fx.paths.role("reviewer")
        r = self.fx.handoff("reviewer")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)
        self.assertEqual(self.gates_names(), [])
        r = self.fx.handoff("reviewer")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("OK:"), r.stdout)
        self.assertEqual(len(layout.handoffs(rp.outbox)), 1)
        self.assertEqual(self.gates_names(), [])

    def test_exit_1_pass_fails(self):
        self.reviewer_in_process()
        self.commit_fence("reviewer", "echo gate-fail; exit 1")
        self.draft("reviewer", REVIEWER_PASS)
        rp = self.fx.paths.role("reviewer")
        r = self.fx.handoff("reviewer")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(r.stdout.startswith("E_GATE_FAILED:"), r.stdout)
        self.assertEqual(os.listdir(rp.audit_pending), [])
        self.assertEqual(layout.handoffs(rp.outbox), [])
        names = self.gates_names()
        self.assertEqual(len(names), 1, names)
        self.assertTrue(names[0].endswith("-test.txt"), names)
        with open(os.path.join(self.fx.paths.gates, names[0]), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("gate-fail", log)

    def test_named_gates_run_in_order(self):
        self.coder_ready()
        text = """# Project

## Gates

test:
```
exit 0
```

lint:
```
echo lint-ran; exit 1
```

## Required on

coder ready: test, lint
"""
        self.write_project("coder", text)
        self.draft("coder", CODER_READY)
        rp = self.fx.paths.role("coder")
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("gate lint failed", r.stdout)
        self.assertEqual(os.listdir(rp.audit_pending), [])
        names = self.gates_names()
        self.assertEqual(len(names), 1, names)
        self.assertIn("-lint.txt", names[0])

    def test_inbound_substitution(self):
        self.coder_ready()
        inbound = layout.handoffs(self.fx.paths.role("coder").in_process)[0]
        from harness import handoff as handoff_mod
        inbound_commit = handoff_mod.read(
            os.path.join(self.fx.paths.role("coder").in_process, inbound))[0]["commit"]
        text = f"""# Project

## Gates

test:
```
test "{{inbound}}" = "{inbound_commit}" || exit 1
```

## Required on

coder ready: test
"""
        self.write_project("coder", text)
        self.draft("coder", CODER_READY)
        r = self.fx.handoff("coder")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUDIT_REQUIRED", r.stdout)

    def test_start_refuses_unknown_gate(self):
        text = """# Project

## Gates

test:
```
exit 0
```

## Required on

coder ready: test, missing
"""
        with open(os.path.join(self.fx.root, "project.md"), "w") as f:
            f.write(text)
        r = self.fx.conveyor("start", "--no-smoke", check=False)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("unknown gate", r.stderr + r.stdout)
        self.assertIn("missing", r.stderr + r.stdout)

    def test_gate_run_dies_on_its_own_budget(self):
        self.coder_ready()
        self.write_project("coder", "# Project\n\n## Test command\n\n```\nsleep 600\n```\n"
                                    "\n## Gate timeouts\n\ntest: 1\n")
        r = self.fx.conveyor("gate", "run", "test", "--role", "coder", check=False)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        out = r.stdout + r.stderr
        self.assertIn("test timed out after 1s", out)
        self.assertIn(".conveyor/logs/gates/", out)
        names = self.gates_names()
        self.assertEqual(len(names), 1, names)
        with open(os.path.join(self.fx.paths.gates, names[0]), encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("exit: timeout\n"))

    def test_gate_run_matches_handoff(self):
        self.coder_ready()
        inner = "echo gate-cli; exit 0"
        self.commit_fence("coder", inner)
        r = self.fx.conveyor("gate", "run", "test", "--role", "coder")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
