"""Inbox CRUD, adapters, intake one-shot, approve writes tasks/ without enqueue."""
import json
import os
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

from harness import ConveyorTest, layout
from conveyor import adapters, config, inbox


class _JiraMockHandler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        for key, spec in self.routes.items():
            if f"/issue/{key}" in self.path:
                status, body = spec
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if body is not None:
                    self.wfile.write(body.encode() if isinstance(body, str) else body)
                return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args):
        pass


def _jira_mock_server(routes):
    handler = type("Handler", (_JiraMockHandler,), {"routes": routes})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    return server, base


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

    def test_jira_adapter_fake_http(self):
        from conveyor import jira as jiralib

        def http_get(url, headers):
            self.assertIn("/rest/api/3/issue/PROJ-9", url)
            self.assertIn("expand=names", url)
            self.assertTrue(headers["Authorization"].startswith("Basic "))
            self.assertNotIn("Bearer", headers["Authorization"])
            return json.dumps({"fields": {"summary": "Broken login", "description": "Repro: click login"}})

        jiralib.write(self.fx.paths, "https://ex.atlassian.net", "dev@ex.com", "tok")
        items = adapters.fetch("jira", "see PROJ-9 please", cfg=type("C", (), {
            "inbox": type("I", (), {"jira_base": "", "jira_token_env": ""})()
        })(), http_get=http_get, paths=self.fx.paths)
        self.assertEqual(items[0]["title"], "Broken login")
        self.assertIn("click login", items[0]["body"])

    def test_jira_keys_from_urls(self):
        keys = adapters._jira_keys("https://ex.atlassian.net/browse/PROJ-9\nPROJ-9")
        self.assertEqual(keys, ["PROJ-9"])

    def test_jira_cli_without_creds_refuses(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        r = fx.conveyor("import", "--source", "jira", input="ABC-42\n", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Jira credentials missing or incomplete", r.stderr + r.stdout)
        self.assertFalse(os.path.isdir(os.path.join(fx.paths.inbox, "abc-42")))

    def test_jira_adapter_http_error(self):
        from conveyor import jira as jiralib

        def http_get(url, headers):
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

        jiralib.write(self.fx.paths, "https://ex.atlassian.net", "dev@ex.com", "tok")
        items = adapters.fetch("jira", "PROJ-9", cfg=config.load(self.fx.root),
                               http_get=http_get, paths=self.fx.paths)
        self.assertIn("error", items[0])
        self.assertEqual(items[0]["error"]["status"], 404)

    def test_jira_cli_http_404_no_row(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        server, base = _jira_mock_server({"PROJ-9": (404, None)})
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            r = fx.conveyor("import", "--source", "jira", input="PROJ-9\n", check=False)
        finally:
            server.shutdown()
            server.server_close()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("failed PROJ-9  404", r.stdout)
        self.assertFalse(os.path.isdir(os.path.join(fx.paths.inbox, "proj-9")))

    def test_jira_cli_http_401_no_row(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        server, base = _jira_mock_server({"PROJ-9": (401, None)})
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            r = fx.conveyor("import", "--source", "jira", input="PROJ-9\n", check=False)
        finally:
            server.shutdown()
            server.server_close()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("failed PROJ-9  401", r.stdout)

    def test_jira_cli_mixed_success_and_failure(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        good = json.dumps({"fields": {"summary": "Good ticket", "description": "Body text"}})
        server, base = _jira_mock_server({
            "PROJ-9": (200, good),
            "PROJ-10": (404, None),
        })
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            r = fx.conveyor("import", "--source", "jira", input="PROJ-9\nPROJ-10\n", check=False)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(r.returncode, 0)
        self.assertIn("imported proj-9", r.stdout)
        self.assertIn("failed PROJ-10  404", r.stdout)
        self.assertTrue(os.path.isdir(os.path.join(fx.paths.inbox, "proj-9")))
        self.assertFalse(os.path.isdir(os.path.join(fx.paths.inbox, "proj-10")))

    def test_adf_text_flattens_lists_links_mentions(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Steps"}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "See "},
                        {
                            "type": "text",
                            "text": "the docs",
                            "marks": [{"type": "link",
                                       "attrs": {"href": "https://ex.com/login"}}],
                        },
                        {"type": "hardBreak"},
                        {"type": "mention", "attrs": {"id": "abc", "text": "@Ada"}},
                    ],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {"type": "listItem", "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "one"}],
                        }]},
                        {"type": "listItem", "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "two"}],
                        }]},
                    ],
                },
            ],
        }
        text = adapters._adf_text(adf)
        self.assertIn("## Steps", text)
        self.assertIn("the docs (https://ex.com/login)", text)
        self.assertIn("@Ada", text)
        self.assertIn("- one", text)
        self.assertIn("- two", text)
        self.assertNotIn("onetwo", text)
        self.assertRegex(text, r"login\)\n@Ada")
        self.assertEqual(adapters._adf_text({
            "type": "mention", "attrs": {"id": "abc-1"},
        }), "@abc-1")

    def test_jira_allowlisted_custom_fields(self):
        from conveyor import jira as jiralib

        def http_get(url, headers):
            self.assertIn("expand=names", url)
            return json.dumps({
                "names": {
                    "customfield_10010": "Acceptance Criteria",
                    "customfield_10020": "Sprint",
                    "customfield_10016": "Story point estimate",
                    "customfield_10030": "Steps to Reproduce",
                },
                "fields": {
                    "summary": "Login bug",
                    "description": "Click login",
                    "issuetype": {"name": "Bug"},
                    "status": {"name": "In Progress"},
                    "priority": {"name": "High"},
                    "labels": ["api", "login"],
                    "parent": {"key": "PROJ-1",
                               "fields": {"summary": "Parent summary"}},
                    "customfield_10010": "Given I am on login",
                    "customfield_10020": {"name": "Sprint 12"},
                    "customfield_10016": 5,
                    "customfield_10030": {
                        "type": "doc",
                        "content": [{"type": "paragraph", "content": [
                            {"type": "text", "text": "Open the app"},
                        ]}],
                    },
                },
            })

        jiralib.write(self.fx.paths, "https://ex.atlassian.net", "dev@ex.com", "tok")
        items = adapters.fetch("jira", "PROJ-9", cfg=config.load(self.fx.root),
                               http_get=http_get, paths=self.fx.paths)
        body = items[0]["body"]
        self.assertIn("PROJ-9  Bug  ·  In Progress  ·  High", body)
        self.assertIn("Labels: api, login", body)
        self.assertIn("Parent: PROJ-1 Parent summary", body)
        self.assertIn("## Description", body)
        self.assertIn("Click login", body)
        self.assertIn("## Acceptance Criteria", body)
        self.assertIn("Given I am on login", body)
        self.assertIn("## Steps to Reproduce", body)
        self.assertIn("Open the app", body)
        self.assertNotIn("## Sprint", body)
        self.assertNotIn("Sprint 12", body)
        self.assertNotIn("## Story point estimate", body)

    def test_jira_metadata_only_is_empty_body(self):
        from conveyor import jira as jiralib

        def http_get(url, headers):
            return json.dumps({
                "names": {},
                "fields": {
                    "summary": "No spec",
                    "description": "",
                    "issuetype": {"name": "Bug"},
                    "status": {"name": "To Do"},
                    "priority": {"name": "High"},
                },
            })

        jiralib.write(self.fx.paths, "https://ex.atlassian.net", "dev@ex.com", "tok")
        items = adapters.fetch("jira", "PROJ-9", cfg=config.load(self.fx.root),
                               http_get=http_get, paths=self.fx.paths)
        self.assertEqual(items[0]["title"], "No spec")
        self.assertEqual(items[0]["body"], "")

    def test_jira_cli_empty_description_notice(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        body = json.dumps({"fields": {"summary": "Blank desc", "description": ""}})
        server, base = _jira_mock_server({"PROJ-9": (200, body)})
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            r = fx.conveyor("import", "--source", "jira", input="PROJ-9\n")
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("imported proj-9", r.stdout)
        self.assertIn("notice: proj-9 has an empty Jira description", r.stdout)
        self.assertNotIn("credentials", r.stdout.lower())
        self.assertTrue(os.path.isdir(os.path.join(fx.paths.inbox, "proj-9")))
        self.assertEqual(inbox.read_file(fx.paths, "proj-9", "source.md").strip(), "")

    def test_jira_cli_comment_fills_empty_description(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        body = json.dumps({
            "fields": {
                "summary": "Blank desc",
                "description": "",
                "comment": {
                    "comments": [{
                        "author": {"displayName": "Ada"},
                        "created": "2026-09-01T12:00:00.000+0000",
                        "body": "Please add acceptance criteria.",
                    }],
                },
            },
        })
        server, base = _jira_mock_server({"PROJ-9": (200, body)})
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            r = fx.conveyor("import", "--source", "jira", input="PROJ-9\n")
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("imported proj-9", r.stdout)
        self.assertNotIn("empty Jira description", r.stdout)
        src = inbox.read_file(fx.paths, "proj-9", "source.md")
        self.assertIn("## Comments", src)
        self.assertIn("**Ada** (2026-09-01):", src)
        self.assertIn("Please add acceptance criteria.", src)

    def test_refresh_updates_in_place(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        first = json.dumps({"fields": {"summary": "Old title", "description": "Old body"}})
        second = json.dumps({"fields": {"summary": "New title", "description": "New body from Jira"}})
        server, base = _jira_mock_server({"PROJ-9": (200, first)})
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            fx.conveyor("import", "--source", "jira", input="PROJ-9\n")
            server.shutdown()
            server.server_close()
            server, base = _jira_mock_server({"PROJ-9": (200, second)})
            jiralib.write(fx.paths, base, "dev@ex.com", "tok")
            r = fx.conveyor("import", "--refresh", "proj-9")
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("refreshed proj-9  New title", r.stdout)
        self.assertFalse(os.path.isdir(os.path.join(fx.paths.inbox, "proj-9-2")))
        self.assertEqual(inbox.list_ids(fx.paths), ["proj-9"])
        meta = inbox.read_meta(fx.paths, "proj-9")
        self.assertEqual(meta["title"], "New title")
        self.assertEqual(meta["status"], "imported")
        self.assertIn("New body from Jira", inbox.read_file(fx.paths, "proj-9", "source.md"))

    def test_refresh_404_leaves_row_unchanged(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        good = json.dumps({"fields": {"summary": "Keep me", "description": "Original body"}})
        server, base = _jira_mock_server({"PROJ-9": (200, good)})
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            fx.conveyor("import", "--source", "jira", input="PROJ-9\n")
            server.shutdown()
            server.server_close()
            server, base = _jira_mock_server({"PROJ-9": (404, None)})
            jiralib.write(fx.paths, base, "dev@ex.com", "tok")
            r = fx.conveyor("import", "--refresh", "proj-9", check=False)
        finally:
            server.shutdown()
            server.server_close()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("failed PROJ-9", r.stdout + r.stderr)
        meta = inbox.read_meta(fx.paths, "proj-9")
        self.assertEqual(meta["title"], "Keep me")
        self.assertIn("Original body", inbox.read_file(fx.paths, "proj-9", "source.md"))

    def test_refresh_refuses_graded_and_manual(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "hand-written",
                    input="# Manual\n\nDo not fetch.\n")
        before = inbox.read_file(fx.paths, "hand-written", "source.md")
        r = fx.conveyor("import", "--refresh", "hand-written", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Jira", r.stdout + r.stderr)
        self.assertEqual(inbox.read_file(fx.paths, "hand-written", "source.md"), before)
        inbox.update_meta(fx.paths, "hand-written", status="graded", source="jira",
                          external_id="PROJ-9")
        r = fx.conveyor("import", "--refresh", "hand-written", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("graded", r.stdout + r.stderr)
        self.assertIn("imported", r.stdout + r.stderr)
        self.assertEqual(inbox.read_file(fx.paths, "hand-written", "source.md"), before)
        self.assertEqual(inbox.read_meta(fx.paths, "hand-written")["status"], "graded")

    def test_replace_overwrites_source(self):
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "rewrite-src",
                    input="# Old\n\nReplace me.\n")
        r = fx.conveyor("import", "--replace", "rewrite-src", input="# New\n\nUpdated body.\n")
        self.assertIn("replaced rewrite-src", r.stdout)
        self.assertIn("Updated body", inbox.read_file(fx.paths, "rewrite-src", "source.md"))
        self.assertEqual(inbox.read_meta(fx.paths, "rewrite-src")["status"], "imported")
        inbox.update_meta(fx.paths, "rewrite-src", status="graded")
        r = fx.conveyor("import", "--replace", "rewrite-src",
                        input="# Nope\n", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("graded", r.stdout + r.stderr)
        self.assertIn("Updated body", inbox.read_file(fx.paths, "rewrite-src", "source.md"))

    def test_reimport_same_key_creates_suffix_and_points_at_refresh(self):
        fx = self.fx
        from conveyor import jira as jiralib
        fx.start("--no-smoke")
        fx.conveyor("stop")
        body = json.dumps({"fields": {"summary": "Once", "description": "First"}})
        server, base = _jira_mock_server({"PROJ-9": (200, body)})
        jiralib.write(fx.paths, base, "dev@ex.com", "tok")
        try:
            fx.conveyor("import", "--source", "jira", input="PROJ-9\n")
            r = fx.conveyor("import", "--source", "jira", input="PROJ-9\n")
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("imported proj-9-2", r.stdout)
        self.assertIn("notice: proj-9 exists; created proj-9-2. "
                      "To update the original: conveyor import --refresh proj-9", r.stdout)
        self.assertTrue(os.path.isdir(os.path.join(fx.paths.inbox, "proj-9")))
        self.assertTrue(os.path.isdir(os.path.join(fx.paths.inbox, "proj-9-2")))

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

    def test_intake_busy_lock_is_reported_and_leaves_item_gradable(self):
        # ticket-reviewer's loop lock is shared across every inbox item: a
        # second `conveyor intake` while one is in flight must fail with a
        # clear message and must not strand the item in "grading" forever.
        fx = self.fx
        fx.start("--no-smoke")
        fx.conveyor("stop")
        fx.conveyor("import", "--source", "manual", "--title", "locked-ticket",
                    input="# Locked\n\n1. Something.\n")
        rp = fx.paths.role(config.INTAKE_ROLE)
        os.makedirs(rp.loop_lock, exist_ok=True)
        with open(os.path.join(rp.loop_lock, "pid"), "w") as f:
            f.write(str(os.getpid()))
        r = fx.conveyor("intake", "locked-ticket", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("busy", r.stdout + r.stderr)
        self.assertIn(str(os.getpid()), r.stdout + r.stderr)
        self.assertEqual(inbox.read_meta(fx.paths, "locked-ticket")["status"], "imported")

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
