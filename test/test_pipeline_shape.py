"""Stage 2: pipelines of any length, with the gate declared instead of inferred.

Covers the shapes `conveyor.conf` could not express before: one role, four roles,
and a gate that sits somewhere other than the first role.
"""
import os
import unittest

from harness import Fixture, layout, read
from conveyor import config, handoff, queue

SPEC_OK = 'commit "Localize $TASK"\ndraft coder $TASK ready\nhandoff\nhandoff\n'

TR = ("ticket-reviewer", "operator", "ready")


def write_conf(root, body):
    with open(os.path.join(root, "conveyor.conf"), "w") as f:
        f.write(body + "\n[global]\npoll_seconds = 0.2\n")


def load(root, body):
    write_conf(root, body)
    return config.load(root)


class Shapes(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    # --- one role -------------------------------------------------------

    def test_one_role_loads_and_has_no_findings_edge(self):
        cfg = load(self.fx.root, "role coder composer-2.5")
        self.assertEqual(cfg.names(), ["coder"])
        self.assertEqual(cfg.routes(), {
            ("operator", "coder", "ready"),
            ("coder", "done", "pass"),
            TR,
        })
        self.assertIsNone(cfg.gate_role())
        self.assertEqual(cfg.next_of("coder"), "done")

    def test_one_role_cannot_be_gated(self):
        with self.assertRaises(config.ConfigError) as e:
            load(self.fx.root, "role coder composer-2.5\ngate coder")
        self.assertIn("the last role", str(e.exception))

    # --- four roles -----------------------------------------------------

    def test_four_roles_chain_and_bounce(self):
        cfg = load(self.fx.root,
                   "role specifier composer-2.5\nrole coder composer-2.5\n"
                   "role tester composer-2.5\nrole reviewer gpt-5")
        self.assertEqual(cfg.routes(), {
            ("operator", "specifier", "ready"),
            ("specifier", "coder", "ready"),
            ("coder", "tester", "ready"),
            ("tester", "reviewer", "ready"),
            ("reviewer", "done", "pass"),
            ("reviewer", "tester", "findings"),
            TR,
        })
        self.assertIsNone(cfg.gate_role(), "four roles must not inherit the 3-role gate")

    def test_gate_after_a_middle_role(self):
        cfg = load(self.fx.root,
                   "role specifier composer-2.5\nrole coder composer-2.5\n"
                   "role tester composer-2.5\nrole reviewer gpt-5\ngate coder")
        self.assertEqual(cfg.gate_role(), "coder")

    # --- backward compatibility ----------------------------------------

    def test_three_roles_without_gate_line_still_gate_the_first(self):
        cfg = load(self.fx.root,
                   "role specifier composer-2.5\nrole coder composer-2.5\nrole reviewer gpt-5")
        self.assertEqual(cfg.gate_role(), "specifier")

    def test_two_roles_without_gate_line_have_no_gate(self):
        cfg = load(self.fx.root, "role coder composer-2.5\nrole reviewer gpt-5")
        self.assertIsNone(cfg.gate_role())

    def test_explicit_gate_overrides_the_three_role_default(self):
        cfg = load(self.fx.root,
                   "role specifier composer-2.5\nrole coder composer-2.5\n"
                   "role reviewer gpt-5\ngate coder")
        self.assertEqual(cfg.gate_role(), "coder")

    # --- parse errors ---------------------------------------------------

    def test_gate_on_last_role_refused(self):
        with self.assertRaises(config.ConfigError) as e:
            load(self.fx.root, "role coder composer-2.5\nrole reviewer gpt-5\ngate reviewer")
        msg = str(e.exception)
        self.assertIn("cannot gate 'reviewer', the last role", msg)
        self.assertIn("repair:", msg)

    def test_gate_on_unconfigured_role_refused(self):
        with self.assertRaises(config.ConfigError) as e:
            load(self.fx.root, "role coder composer-2.5\nrole reviewer gpt-5\ngate nobody")
        msg = str(e.exception)
        self.assertIn("unconfigured role 'nobody'", msg)
        self.assertIn("gate one of coder, reviewer", msg)

    def test_duplicate_gate_refused(self):
        with self.assertRaises(config.ConfigError) as e:
            load(self.fx.root,
                 "role specifier composer-2.5\nrole coder composer-2.5\n"
                 "role reviewer gpt-5\ngate specifier\ngate coder")
        self.assertIn("duplicate gate directive", str(e.exception))

    def test_gate_without_a_role_refused(self):
        with self.assertRaises(config.ConfigError) as e:
            load(self.fx.root, "role coder composer-2.5\nrole reviewer gpt-5\ngate")
        self.assertIn("gate needs exactly one role", str(e.exception))

    def test_no_roles_refused(self):
        with self.assertRaises(config.ConfigError) as e:
            load(self.fx.root, "# nothing here")
        self.assertIn("at least one role is required", str(e.exception))

    # --- round trip -----------------------------------------------------

    def test_save_writes_the_gate_resolved(self):
        cfg = load(self.fx.root,
                   "role specifier composer-2.5\nrole coder composer-2.5\nrole reviewer gpt-5")
        config.save(self.fx.root, cfg)
        text = read(os.path.join(self.fx.root, "conveyor.conf"))
        self.assertIn("gate specifier", text,
                      "a legacy three-pack must be saved with its gate stated")
        self.assertEqual(config.load(self.fx.root).gate_role(), "specifier")

    def test_save_writes_gate_none_when_there_is_no_gate(self):
        cfg = load(self.fx.root, "role coder composer-2.5\nrole reviewer gpt-5")
        config.save(self.fx.root, cfg)
        self.assertIn("gate none", read(os.path.join(self.fx.root, "conveyor.conf")))
        self.assertIsNone(config.load(self.fx.root).gate_role())

    # --- `gate none`: an explicitly ungated belt -------------------------

    def test_gate_none_beats_the_three_role_inference(self):
        """The whole point of the sentinel: three roles, deliberately no gate."""
        cfg = load(self.fx.root,
                   "role specifier composer-2.5\nrole coder composer-2.5\n"
                   "role reviewer gpt-5\ngate none")
        self.assertIsNone(cfg.gate_role())

    def test_gate_none_round_trips_through_save(self):
        cfg = load(self.fx.root,
                   "role specifier composer-2.5\nrole coder composer-2.5\n"
                   "role reviewer gpt-5\ngate none")
        config.save(self.fx.root, cfg)
        self.assertIn("gate none", read(os.path.join(self.fx.root, "conveyor.conf")))
        self.assertIsNone(config.load(self.fx.root).gate_role())

    def test_gate_none_is_allowed_on_a_one_role_belt(self):
        cfg = load(self.fx.root, "role coder composer-2.5\ngate none")
        self.assertIsNone(cfg.gate_role())

    def test_none_is_not_a_usable_role_name(self):
        with self.assertRaises(config.ConfigError) as e:
            load(self.fx.root, "role none composer-2.5\nrole reviewer gpt-5")
        self.assertIn("invalid role name 'none'", str(e.exception))


class GateRouting(unittest.TestCase):
    """The hold and the reject follow the gated role, not names()[0]."""

    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)
        write_conf(self.fx.root,
                   "role specifier composer-2.5 max_retries=3 max_minutes=60 max_attempts=2\n"
                   "role coder composer-2.5 max_retries=3 max_minutes=120 max_attempts=3\n"
                   "role reviewer gpt-5 max_minutes=60 max_attempts=2\n"
                   "gate specifier")

    def test_declared_gate_holds_exactly_like_the_inferred_one(self):
        fx = self.fx
        fx.script("specifier", SPEC_OK)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.task("demo")
        self.assertEqual(fx.loop("specifier").returncode, 0, "specifier loop")
        pending = layout.handoffs(fx.paths.approvals_pending)
        self.assertEqual(len(pending), 1, pending)
        self.assertEqual(layout.handoffs(fx.paths.role("coder").new), [])

    def test_reject_returns_to_the_gated_role(self):
        fx = self.fx
        fx.script("specifier", SPEC_OK)
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.task("demo")
        fx.loop("specifier")
        cfg = config.load(fx.root)
        pending = layout.handoffs(fx.paths.approvals_pending)
        hid = handoff.read(os.path.join(fx.paths.approvals_pending, pending[0]))[0]["id"]
        h = queue.reject_pending(fx.paths, cfg, hid, "not localized enough")
        self.assertEqual(h["to"], cfg.gate_role())
        self.assertEqual(h["to"], "specifier")
        self.assertEqual(len(layout.handoffs(fx.paths.role("specifier").new)), 1)
        self.assertEqual(layout.handoffs(fx.paths.approvals_pending), [])


if __name__ == "__main__":
    unittest.main()
