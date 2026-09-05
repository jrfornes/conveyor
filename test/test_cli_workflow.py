"""`conveyor workflow` — the operator's half of workflow CRUD."""
import os
import unittest

from harness import Fixture, read
from conveyor import config, presets


class CliWorkflow(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def wf(self, *args, **kw):
        return self.fx.conveyor("workflow", *args, **kw)

    def conf(self):
        return read(os.path.join(self.fx.root, "conveyor.conf"))

    # --- read verbs -----------------------------------------------------

    def test_list_seeds_and_marks_the_active_one(self):
        out = self.wf("list").stdout
        for slug in ("review-belt", "spec-then-build", "spec-no-gate", "solo-coder"):
            self.assertIn(slug, out)
        active = [l for l in out.splitlines() if l.strip().startswith("review-belt")]
        self.assertTrue(active and active[0].rstrip().endswith("active"), out)

    def test_list_reports_a_custom_shape(self):
        with open(os.path.join(self.fx.root, "conveyor.conf"), "w") as f:
            f.write("role coder composer-2.5\nrole reviewer gpt-5\n"
                    "role specifier composer-2.5\ngate none\n")
        self.assertIn("custom shape", self.wf("list").stdout)

    def test_show_prints_chain_and_gate(self):
        out = self.wf("show", "spec-then-build").stdout
        self.assertIn("specifier → coder → reviewer", out)
        self.assertIn("gate:  specifier", out)
        self.assertIn(".conveyor/workflows/spec-then-build.json", out)

    def test_show_prints_gate_none(self):
        self.assertIn("gate:  none", self.wf("show", "spec-no-gate").stdout)

    # --- write verbs ----------------------------------------------------

    def test_new_creates_and_slugifies(self):
        out = self.wf("new", "QA belt", "--roles", "coder,reviewer").stdout
        self.assertIn(".conveyor/workflows/qa-belt.json created", out)
        p = presets.load(self.fx.paths, "qa-belt")
        self.assertEqual(p["roles"], ["coder", "reviewer"])
        self.assertEqual(p["name"], "QA belt")

    def test_new_suffixes_a_taken_slug(self):
        self.wf("new", "QA belt", "--roles", "coder,reviewer")
        out = self.wf("new", "QA belt", "--roles", "coder,reviewer").stdout
        self.assertIn("qa-belt-2.json created", out)

    def test_new_accepts_a_gate_and_a_description(self):
        self.wf("new", "Gated", "--roles", "specifier,coder,reviewer",
                "--gate", "coder", "--description", "three with a mid gate")
        p = presets.load(self.fx.paths, "gated")
        self.assertEqual(p["gate"], "coder")
        self.assertEqual(p["description"], "three with a mid gate")

    def test_new_without_roles_prints_usage(self):
        r = self.wf("new", "Nope", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage: conveyor workflow", r.stderr)

    def test_new_rejects_an_unknown_role(self):
        r = self.wf("new", "Ghosts", "--roles", "coder,ghost", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("create roles/ghost.md first", r.stderr)

    def test_edit_changes_roles_and_gate(self):
        self.wf("edit", "solo-coder", "--roles", "specifier,coder,reviewer",
                "--gate", "specifier")
        p = presets.load(self.fx.paths, "solo-coder")
        self.assertEqual(p["roles"], ["specifier", "coder", "reviewer"])
        self.assertEqual(p["gate"], "specifier")

    def test_edit_no_gate_clears_the_gate(self):
        self.wf("edit", "spec-then-build", "--no-gate")
        self.assertIsNone(presets.load(self.fx.paths, "spec-then-build")["gate"])

    def test_edit_keeps_the_slug_when_the_name_changes(self):
        self.wf("edit", "solo-coder", "--name", "Just the coder")
        self.assertTrue(presets.exists(self.fx.paths, "solo-coder"))
        self.assertEqual(presets.load(self.fx.paths, "solo-coder")["name"], "Just the coder")

    def test_edit_with_no_flags_errors(self):
        r = self.wf("edit", "solo-coder", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing to change", r.stderr)

    def test_delete_removes_the_file(self):
        self.wf("delete", "solo-coder")
        self.assertFalse(presets.exists(self.fx.paths, "solo-coder"))

    def test_delete_refuses_the_active_workflow(self):
        r = self.wf("delete", "review-belt", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is active", r.stderr)

    # --- activate -------------------------------------------------------

    def test_activate_rewrites_conveyor_conf(self):
        out = self.wf("activate", "spec-then-build").stdout
        self.assertIn("specifier → coder → reviewer", out)
        self.assertIn("gate after specifier", out)
        self.assertIn(".conveyor/active → spec-then-build", out)
        cfg = config.load(self.fx.root)
        self.assertEqual(cfg.names(), ["specifier", "coder", "reviewer"])
        self.assertEqual(cfg.gate_role(), "specifier")

    def test_activate_a_gateless_three_role_workflow(self):
        self.wf("activate", "spec-no-gate")
        self.assertIn("no gate", self.wf("show", "spec-no-gate").stdout.lower())
        self.assertIn("gate none", self.conf())
        self.assertIsNone(config.load(self.fx.root).gate_role())

    def test_activate_warns_about_a_dropped_role(self):
        self.wf("activate", "spec-then-build")
        self.fx.start("--no-smoke")
        self.fx.conveyor("stop")
        out = self.wf("activate", "review-belt").stdout
        self.assertIn("specifier left the workflow", out)

    def test_activate_refuses_while_a_loop_is_running(self):
        before = self.conf()
        lock = self.fx.paths.role("coder").loop_lock
        os.makedirs(lock, exist_ok=True)
        with open(os.path.join(lock, "pid"), "w") as f:
            f.write(f"{os.getpid()}\n")
        r = self.wf("activate", "spec-then-build", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("loops are running (coder)", r.stderr)
        self.assertEqual(self.conf(), before)

    def test_unknown_slug_exits_nonzero_with_the_slug_in_the_message(self):
        r = self.wf("show", "nope", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nope", r.stderr)

    def test_bad_verb_prints_the_usage_line(self):
        r = self.wf("frobnicate", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage: conveyor workflow", r.stderr)


if __name__ == "__main__":
    unittest.main()
