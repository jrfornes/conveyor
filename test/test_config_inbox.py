"""Surgical [inbox] writer: never a save() rewrite."""
import os
import tempfile
import unittest

from harness import REPO, read
from conveyor import config


def _write(tmp, text):
    path = os.path.join(tmp, "conveyor.conf")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


ROLES = (
    "role coder    composer-2.5  max_retries=3 max_minutes=120 max_attempts=3\n"
    "role reviewer composer-2.5  max_minutes=60 max_attempts=2\n"
)


class WriteInbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="conveyor-inbox-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_appends_section_when_missing(self):
        _write(self.tmp, ROLES + "\n[global]\npoll_seconds = 2\n")
        config.write_inbox(self.tmp, {"ticket_reviewer_model": "gpt-5"})
        text = read(os.path.join(self.tmp, "conveyor.conf"))
        self.assertTrue(text.endswith("[inbox]\nticket_reviewer_model = gpt-5\n"))
        self.assertIn("role coder    composer-2.5", text)
        self.assertIn("[global]\npoll_seconds = 2\n", text)

    def test_replaces_key_in_place(self):
        original = (
            ROLES + "\n# keep me\n[inbox]\n"
            "jira_base = https://ex.atlassian.net\n"
            "ticket_reviewer_model = composer-2.5\n"
        )
        _write(self.tmp, original)
        config.write_inbox(self.tmp, {"ticket_reviewer_model": "gpt-5"})
        text = read(os.path.join(self.tmp, "conveyor.conf"))
        self.assertIn("ticket_reviewer_model = gpt-5\n", text)
        self.assertNotIn("ticket_reviewer_model = composer-2.5\n", text)
        self.assertIn("# keep me\n", text)
        self.assertIn("role coder    composer-2.5  max_retries=3 max_minutes=120 max_attempts=3\n", text)
        self.assertIn("jira_base = https://ex.atlassian.net\n", text)

    def test_promotes_the_commented_out_example_section(self):
        example = read(os.path.join(REPO, "conveyor.conf.example"))
        _write(self.tmp, example)
        before_roles = [ln for ln in example.splitlines(True) if ln.startswith("role ")]
        config.write_inbox(self.tmp, {"ticket_reviewer_model": "gpt-5"})
        text = read(os.path.join(self.tmp, "conveyor.conf"))
        after_roles = [ln for ln in text.splitlines(True) if ln.startswith("role ")]
        self.assertEqual(before_roles, after_roles)
        self.assertIn("# Optional inbox adapter", text)
        self.assertIn("[inbox]\n", text)
        self.assertNotIn("# [inbox]", text)
        self.assertIn("ticket_reviewer_model = gpt-5\n", text)
        # commented examples under the promoted header stay comments
        self.assertIn("# jira_base = https://example.atlassian.net\n", text)
        cfg = config.load(self.tmp)
        self.assertEqual(cfg.inbox.ticket_reviewer_model, "gpt-5")
        self.assertEqual(cfg.chain_label(), "coder → reviewer")

    def test_does_not_promote_when_live_config_follows(self):
        _write(self.tmp, (
            ROLES + "\n[global]\nagent_bin = cursor-agent\n"
            "# [inbox]\n# jira_base = https://example.atlassian.net\n"
            "poll_seconds = 2\n"
        ))
        config.write_inbox(self.tmp, {"ticket_reviewer_model": "gpt-5"})
        text = read(os.path.join(self.tmp, "conveyor.conf"))
        self.assertIn("# [inbox]\n", text, "must not steal the live keys below")
        self.assertIn("poll_seconds = 2\n", text)
        cfg = config.load(self.tmp)
        self.assertEqual(cfg.poll_seconds, 2.0)
        self.assertEqual(cfg.inbox.ticket_reviewer_model, "gpt-5")
        self.assertNotIn("poll_seconds", vars(cfg.inbox))

    def test_rejects_unknown_keys_and_hashes(self):
        _write(self.tmp, ROLES)
        with self.assertRaises(config.ConfigError):
            config.write_inbox(self.tmp, {"max_retries": "1"})
        with self.assertRaises(config.ConfigError):
            config.write_inbox(self.tmp, {"ticket_reviewer_model": "gpt#5"})

    def test_intake_ceilings_defaults_and_explicit_zero(self):
        _write(self.tmp, ROLES)
        cfg = config.load(self.tmp)
        tr = cfg.role(config.INTAKE_ROLE)
        self.assertEqual(tr.max_minutes, 30)
        self.assertEqual(tr.max_attempts, 2)
        self.assertEqual(tr.max_retries, 1)
        _write(self.tmp, ROLES + "\n[inbox]\nticket_reviewer_max_minutes = 0\n"
               "ticket_reviewer_max_attempts = 0\n")
        cfg = config.load(self.tmp)
        tr = cfg.role(config.INTAKE_ROLE)
        self.assertEqual(tr.max_minutes, 0)
        self.assertEqual(tr.max_attempts, 0)

    def test_bad_inbox_int_is_config_error(self):
        _write(self.tmp, ROLES + "\n[inbox]\nticket_reviewer_max_minutes = -1\n")
        with self.assertRaises(config.ConfigError) as ctx:
            config.load(self.tmp)
        self.assertIn("non-negative integer", str(ctx.exception))
        self.assertIn("repair:", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
