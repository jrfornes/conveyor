"""Inbox CRUD, adapters, intake one-shot, approve writes tasks/ without enqueue."""
import json
import os
import unittest

from harness import ConveyorTest, layout
from conveyor import adapters, inbox


class InboxCrud(ConveyorTest):
    def test_manual_import_and_status_meta(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        r = fx.conveyor("import", "--source", "manual", "--title", "Login timeout",
                        input="# Login\n\nTimes out after 30s.\n")
        self.assertIn("imported login-timeout", r.stdout)
        paths = fx.paths
        meta = inbox.read_meta(paths, "login-timeout")
        self.assertEqual(meta["status"], "imported")
        self.assertEqual(meta["source"], "manual")
        self.assertIn("Times out", inbox.read_file(paths, "login-timeout", "source.md"))
        fx.conveyor("inbox", "skip", "login-timeout")
        self.assertEqual(inbox.read_meta(paths, "login-timeout")["status"], "skipped")

    def test_jira_adapter_fake_http_and_missing_creds(self):
        from conveyor import jira as jiralib

        def http_get(url, headers):
            self.assertIn("/rest/api/3/issue/PROJ-9", url)
            self.assertTrue(headers["Authorization"].startswith("Basic "))
            self.assertNotIn("Bearer", headers["Authorization"])
            return json.dumps({"fields": {"summary": "Broken login", "description": "Repro: click login"}})

        jiralib.write(self.fx.paths, "https://ex.atlassian.net", "dev@ex.com", "tok")
        items = adapters.fetch("jira", "see PROJ-9 please", cfg=type("C", (), {
            "inbox": type("I", (), {"jira_base": "", "jira_token_env": ""})()
        })(), http_get=http_get, paths=self.fx.paths)
        self.assertEqual(items[0]["title"], "Broken login")
        self.assertIn("click login", items[0]["body"])
        items = adapters.fetch("jira", "https://ex.atlassian.net/browse/PROJ-9\nPROJ-9", cfg=type("C", (), {
            "inbox": type("I", (), {"jira_base": "", "jira_token_env": ""})()
        })())
        self.assertEqual(items[0]["external_id"], "PROJ-9")
        self.assertEqual(items[0]["body"], "")

    def test_jira_cli_without_creds_still_creates(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        r = fx.conveyor("import", "--source", "jira", input="ABC-42\n")
        self.assertIn("imported abc-42", r.stdout)
        self.assertEqual(inbox.read_meta(fx.paths, "abc-42")["external_id"], "ABC-42")

    def test_intake_grade_and_approve_writes_task_not_board(self):
        fx = self.fx
        fx.script("ticket-reviewer",
                  'write grade.md "Grade: Ready\\n\\n1. none\\n"\n'
                  'commit "Grade $TASK"\n'
                  "draft operator $TASK ready\n"
                  "handoff\n"
                  "handoff\n")
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "cave-setup",
                    input="# Cave\n\n1. Lights work.\n")
        r = fx.conveyor("intake", "cave-setup")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        item = inbox.item(fx.paths, "cave-setup")
        self.assertEqual(item["status"], "graded")
        self.assertEqual(item["grade"], "Ready")
        self.assertIn("Grade: Ready", item["grade_md"])
        fx.conveyor("inbox", "approve", "cave-setup", "--name", "cave-setup")
        self.assertTrue(os.path.isfile(os.path.join(fx.root, "tasks", "cave-setup.md")))
        self.assertEqual(inbox.read_meta(fx.paths, "cave-setup")["status"], "ready")
        self.assertIsNone(fx.board().get("cave-setup"))
        fx.conveyor("start-task", "cave-setup")
        self.assertEqual(fx.board()["cave-setup"]["lane"], "coder")
        self.assertEqual(inbox.read_meta(fx.paths, "cave-setup")["status"], "started")
        self.assertTrue(layout.handoffs(fx.paths.role("coder").new) or
                        layout.handoffs(fx.paths.role("operator").sent))

    def test_intake_improve_writes_proposed(self):
        fx = self.fx
        fx.script("ticket-reviewer",
                  'write grade.md "Grade: Gaps\\n\\n1. no acceptance\\n"\n'
                  'write proposed-task.md "# Task\\n\\n1. Numbered requirement.\\n"\n'
                  'commit "Improve $TASK"\n'
                  "draft operator $TASK ready\n"
                  "handoff\n"
                  "handoff\n")
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "rewrite-me",
                    input="Vague ticket.\n")
        fx.conveyor("intake", "rewrite-me", "--improve")
        item = inbox.item(fx.paths, "rewrite-me")
        self.assertEqual(item["status"], "awaiting-approval")
        self.assertIn("Numbered requirement", item["proposed_md"])


if __name__ == "__main__":
    unittest.main()
