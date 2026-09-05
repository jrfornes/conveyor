"""Header chrome from saved presets, plus config.save round trips."""
import os
import unittest

from harness import Fixture
from conveyor import config, presets, workflows


class Describe(unittest.TestCase):
    """Header chrome comes from the saved presets, not a hardcoded catalog."""

    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)
        presets.ensure_seeded(self.fx.paths)

    def describe(self):
        return workflows.describe(self.fx.paths, config.load(self.fx.root))

    def test_matching_shape_names_its_preset(self):
        d = self.describe()
        self.assertEqual((d["id"], d["name"], d["chain"], d["status"]),
                         ("review-belt", "Review belt", "coder → reviewer", "active"))
        cfg = config.load(self.fx.root)
        self.assertIn("specifier", workflows.library_roles(self.fx.root, cfg))

    def test_activate_moves_the_chrome(self):
        self.fx.conveyor("workflow", "activate", "spec-then-build")
        d = self.describe()
        self.assertEqual((d["id"], d["name"]), ("spec-then-build", "Spec then build"))
        cfg = config.load(self.fx.root)
        self.assertEqual(cfg.names(), ["specifier", "coder", "reviewer"])
        self.assertEqual(workflows.library_roles(self.fx.root, cfg), [])

    def test_unknown_shape_reads_as_custom(self):
        with open(os.path.join(self.fx.root, "conveyor.conf"), "w") as f:
            f.write("role coder composer-2.5\nrole specifier composer-2.5\ngate none\n")
        d = self.describe()
        self.assertEqual((d["id"], d["name"], d["status"]), ("custom", "Custom", "custom"))


class ConfigSave(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def test_config_save_keeps_global_and_inbox(self):
        path = os.path.join(self.fx.root, "conveyor.conf")
        with open(path, "w") as f:
            f.write(
                "role coder composer-2.5 max_retries=3 max_minutes=120 max_attempts=3\n"
                "role reviewer gpt-5 max_retries=3 max_minutes=60 max_attempts=2\n"
                "[global]\npoll_seconds = 0.2\nagent_bin = cursor-agent\n"
                "[inbox]\njira_base = https://example.atlassian.net\n"
            )
        cfg = config.load(self.fx.root)
        cfg.role("coder").model = "gpt-5"
        cfg.role("coder").max_minutes = 30
        config.save(self.fx.root, cfg)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("poll_seconds = 0.2", text)
        self.assertIn("jira_base = https://example.atlassian.net", text)
        cfg2 = config.load(self.fx.root)
        self.assertEqual(cfg2.role("coder").model, "gpt-5")
        self.assertEqual(cfg2.role("coder").max_minutes, 30)
        self.assertEqual(cfg2.role("reviewer").model, "gpt-5")
        self.assertEqual(cfg2.inbox.jira_base, "https://example.atlassian.net")


if __name__ == "__main__":
    unittest.main()
