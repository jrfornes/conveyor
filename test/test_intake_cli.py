"""CLI: conveyor intake config | jira; reserved inbox ids."""
import base64
import json
import os
import stat
import subprocess
import unittest

from harness import ConveyorTest
from conveyor import adapters, config, inbox, jira as jiralib


class IntakeCli(ConveyorTest):
    def test_intake_config_print_and_write(self):
        fx = self.fx
        r = fx.conveyor("intake", "config")
        self.assertIn("model ", r.stdout)
        self.assertIn("max_minutes 30", r.stdout)
        self.assertIn("max_attempts 2", r.stdout)
        fx.conveyor("intake", "config", "--model", "gpt-5", "--minutes", "10", "--attempts", "1")
        cfg = config.load(fx.root)
        self.assertEqual(cfg.inbox.ticket_reviewer_model, "gpt-5")
        self.assertEqual(cfg.inbox.ticket_reviewer_max_minutes, 10)
        self.assertEqual(cfg.role(config.INTAKE_ROLE).max_attempts, 1)
        # save() was not used: no renormalized gate line from a custom rewrite
        with open(os.path.join(fx.root, "conveyor.conf"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("gate none", text)

    def test_intake_jira_write_and_redact(self):
        fx = self.fx
        r = fx.conveyor("intake", "jira", "--site", "https://ex.atlassian.net",
                        "--email", "dev@ex.com", "--token-stdin", input="s3cret\n")
        self.assertIn("wrote .conveyor/local/jira.json", r.stdout)
        shown = fx.conveyor("intake", "jira")
        self.assertIn("site https://ex.atlassian.net", shown.stdout)
        self.assertIn("email dev@ex.com", shown.stdout)
        self.assertIn("token_set True", shown.stdout)
        self.assertNotIn("s3cret", shown.stdout)
        stored = jiralib.read(fx.paths)
        self.assertEqual(stored["token"], "s3cret")
        fx.conveyor("intake", "jira", "--clear")
        self.assertFalse(os.path.isfile(fx.paths.jira))

    def test_reserved_ids_skip_config_and_jira(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        r = fx.conveyor("import", "--source", "manual", "--title", "config",
                        input="# Config ticket\n\n1. Not the verb.\n")
        self.assertIn("imported config-2", r.stdout)
        r = fx.conveyor("import", "--source", "jira", input="JIRA-1\n")
        # slug from JIRA-1 is jira-1, not reserved; force a 'jira' preferred
        iid = inbox.create(fx.paths, {"id": "jira", "title": "jira", "source": "manual"})
        self.assertEqual(iid, "jira-2")

    def test_jira_basic_auth_from_local_json(self):
        fx = self.fx
        jiralib.write(fx.paths, "https://ex.atlassian.net", "dev@ex.com", "tok")
        seen = {}

        def http_get(url, headers):
            seen["url"] = url
            seen["headers"] = headers
            return json.dumps({"fields": {"summary": "Broken login", "description": "Repro"}})

        items = adapters.fetch("jira", "see PROJ-9 please", cfg=config.load(fx.root),
                               http_get=http_get, paths=fx.paths)
        self.assertEqual(items[0]["title"], "Broken login")
        self.assertIn("/rest/api/3/issue/PROJ-9", seen["url"])
        expected = "Basic " + base64.b64encode(b"dev@ex.com:tok").decode("ascii")
        self.assertEqual(seen["headers"]["Authorization"], expected)
        self.assertNotIn("Bearer", seen["headers"]["Authorization"])
        self.assertNotIn("Bearer", json.dumps(seen["headers"]))

    def test_jira_partial_creds_degrade_silently(self):
        fx = self.fx
        called = []

        def http_get(url, headers):
            called.append(url)
            raise AssertionError("HTTP must not run")

        items = adapters.fetch("jira", "PROJ-9", cfg=config.load(fx.root),
                               http_get=http_get, paths=fx.paths)
        self.assertEqual(called, [])
        self.assertEqual(items[0]["title"], "PROJ-9")
        self.assertEqual(items[0]["body"], "")
        # site but no email
        jiralib.write(fx.paths, "https://ex.atlassian.net", "", "tok")
        items = adapters.fetch("jira", "PROJ-9", cfg=config.load(fx.root),
                               http_get=http_get, paths=fx.paths)
        self.assertEqual(called, [])
        self.assertEqual(items[0]["body"], "")

    def test_jira_json_is_mode_600_and_gitignored(self):
        fx = self.fx
        jiralib.write(fx.paths, "https://ex.atlassian.net", "dev@ex.com", "tok")
        mode = stat.S_IMODE(os.stat(fx.paths.jira).st_mode)
        self.assertEqual(mode, 0o600)
        r = subprocess.run(["git", "check-ignore", "-q", ".conveyor/local/jira.json"],
                           cwd=fx.root)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
