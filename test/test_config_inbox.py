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
        self.assertIn("# Optional intake ceilings", text)
        self.assertIn("[inbox]\n", text)
        self.assertNotIn("# [inbox]", text)
        self.assertIn("ticket_reviewer_model = gpt-5\n", text)
        # commented examples under the promoted header stay comments
        self.assertIn("# ticket_reviewer_max_minutes = 30\n", text)
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

    def test_gate_timeout_round_trips_and_save_leaves_the_file_alone(self):
        original = ROLES + "\ngate none\n\n[global]\npoll_seconds = 2\ngate_timeout = 300\n"
        _write(self.tmp, original)
        cfg = config.load(self.tmp)
        self.assertEqual(cfg.gate_timeout, 300)
        config.save(self.tmp, cfg)
        # [global] is kept verbatim, so a config carrying gate_timeout survives a save.
        self.assertIn("gate_timeout = 300\n", read(os.path.join(self.tmp, "conveyor.conf")))
        self.assertEqual(config.load(self.tmp).gate_timeout, 300)

    def test_gate_timeout_defaults_and_is_not_written_unasked(self):
        _write(self.tmp, ROLES + "\ngate none\n\n[global]\npoll_seconds = 2\n")
        cfg = config.load(self.tmp)
        self.assertEqual(cfg.gate_timeout, 900)
        config.save(self.tmp, cfg)
        self.assertNotIn("gate_timeout", read(os.path.join(self.tmp, "conveyor.conf")))

    def test_gate_timeout_rejects_a_non_integer(self):
        _write(self.tmp, ROLES + "\n[global]\ngate_timeout = soon\n")
        with self.assertRaises(config.ConfigError) as ctx:
            config.load(self.tmp)
        self.assertIn("gate_timeout = 900", str(ctx.exception))

    def test_gate_timeout_zero_is_unbounded(self):
        _write(self.tmp, ROLES + "\n[global]\ngate_timeout = 0\n")
        self.assertEqual(config.load(self.tmp).gate_timeout, 0)

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


    def test_worktree_setup_keys_round_trip_and_save_stays_byte_identical(self):
        """The three keys parse; a config without them survives save() unchanged,
        so presets.resolve() does not flip an untouched belt to `custom`."""
        _write(self.tmp, ROLES + "\ngate none\n\n[global]\npoll_seconds = 2\n"
               "worktree_setup = pnpm install --frozen-lockfile\n"
               "worktree_setup_paths = pnpm-lock.yaml package.json\n"
               "worktree_setup_timeout = 60\n")
        cfg = config.load(self.tmp)
        self.assertEqual(cfg.worktree_setup, "pnpm install --frozen-lockfile")
        self.assertEqual(cfg.worktree_setup_paths, ["pnpm-lock.yaml", "package.json"])
        self.assertEqual(cfg.worktree_setup_timeout, 60)
        before = read(os.path.join(self.tmp, "conveyor.conf"))
        config.save(self.tmp, cfg)
        after = read(os.path.join(self.tmp, "conveyor.conf"))
        self.assertIn("worktree_setup = pnpm install --frozen-lockfile", after)
        self.assertEqual(before.split("[global]")[1], after.split("[global]")[1])

    def test_defaults_when_the_keys_are_absent(self):
        _write(self.tmp, ROLES)
        cfg = config.load(self.tmp)
        self.assertEqual(cfg.worktree_setup, "")
        self.assertEqual(cfg.worktree_setup_paths, [])
        self.assertEqual(cfg.worktree_setup_timeout, 1800)
        before = read(os.path.join(self.tmp, "conveyor.conf"))
        config.save(self.tmp, cfg)
        self.assertNotIn("worktree_setup", read(os.path.join(self.tmp, "conveyor.conf")))
        self.assertIn("role coder", before)


if __name__ == "__main__":
    unittest.main()
