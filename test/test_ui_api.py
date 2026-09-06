"""API tests for the Conveyor Angular UI server."""
import json
import os
import shutil
import sys
import threading
import unittest
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "test"))

from harness import Fixture  # noqa: E402
from ui.server.httpd import Handler, ThreadingHTTPServer  # noqa: E402
from conveyor import config, inbox  # noqa: E402


def get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def get_code(url):
    """GET that returns (status, body) so non-2xx responses are assertable."""
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class UiApiTest(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self._env_saved = {}
        for k, v in self.fx.env.items():
            if k.startswith(("CONVEYOR_", "GIT_")):
                self._env_saved[k] = os.environ.get(k)
                os.environ[k] = v
        self.fx.start("--no-smoke")
        self.fx.task("demo", "# Demo\n\n1. Do thing.\n")
        Handler.repo_root = self.fx.root
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        for k, v in self._env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.fx.cleanup()

    def _clear_loop_locks(self):
        for name in ("coder", "reviewer", "specifier"):
            lock = self.fx.paths.role(name).loop_lock
            if os.path.isdir(lock):
                shutil.rmtree(lock, ignore_errors=True)

    def test_health_and_state(self):
        health = get(f"{self.base}/api/health")
        self.assertTrue(health["ok"])
        state = get(f"{self.base}/api/state")
        self.assertEqual(state["title"], "repo")
        self.assertIn("coder", state["lanes"])
        self.assertTrue(any(t["name"] == "demo" for t in state["tasks"]))
        self.assertEqual(len(state["work"]), 2)
        self.assertIn("inbox", state)
        self.assertIn("approvals", state)
        # every lane the board renders has an avatar, parked lane included
        self.assertEqual(sorted(state["avatars"]), sorted(state["lanes"]))
        self.assertEqual(state["avatars"]["needs-human"]["icon"], "back_hand")
        self.assertTrue(all(a["icon"] and a["color"] for a in state["avatars"].values()))
        wf = state["workflow"]
        self.assertIsInstance(wf, dict)
        self.assertEqual(wf["id"], "review-belt", "the id is the preset slug")
        self.assertEqual(wf["name"], "Review belt")
        self.assertEqual(wf["status"], "active")
        self.assertEqual(wf["chain"], "coder → reviewer")
        self.assertEqual(state["intake"], {"busy": False, "task": None})

    def test_intake_busy_reflected_in_state(self):
        # /api/state is what the UI polls to disable Grade/Improve while
        # ticket-reviewer's single, shared loop lock is held by another item.
        iid = inbox.create(self.fx.paths, {
            "id": "busy-ticket", "source": "manual", "title": "busy-ticket", "status": "grading",
        }, "# Busy\n")
        rp = self.fx.paths.role(config.INTAKE_ROLE)
        os.makedirs(rp.loop_lock, exist_ok=True)
        with open(os.path.join(rp.loop_lock, "pid"), "w") as f:
            f.write(str(os.getpid()))
        try:
            state = get(f"{self.base}/api/state")
            self.assertEqual(state["intake"], {"busy": True, "task": iid})
        finally:
            shutil.rmtree(rp.loop_lock, ignore_errors=True)
        state = get(f"{self.base}/api/state")
        self.assertEqual(state["intake"], {"busy": False, "task": None})

    def test_import_list_inbox_approve(self):
        req = urllib.request.Request(
            f"{self.base}/api/import",
            data=json.dumps({
                "source": "manual",
                "title": "api-ticket",
                "body": "# API\n\n1. Imported from the UI API.\n",
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
        self.assertTrue(body["ok"])
        state = get(f"{self.base}/api/state")
        self.assertTrue(any(i["id"] == "api-ticket" for i in state["inbox"]))
        item = get(f"{self.base}/api/inbox/api-ticket")
        self.assertIn("Imported from the UI API", item["source_md"])
        req = urllib.request.Request(
            f"{self.base}/api/inbox/approve",
            data=json.dumps({"id": "api-ticket", "name": "api-ticket"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
        self.assertTrue(body["ok"])
        state = get(f"{self.base}/api/state")
        row = next(i for i in state["inbox"] if i["id"] == "api-ticket")
        self.assertEqual(row["status"], "ready")
        self.assertFalse(any(t["name"] == "api-ticket" for t in state["tasks"]))

    def test_task_and_handoffs(self):
        task = get(f"{self.base}/api/tasks/demo")
        self.assertIn("Demo", task["text"])
        handoffs = get(f"{self.base}/api/handoffs/coder/new")
        self.assertIsInstance(handoffs, list)

    def test_create_task_via_api(self):
        req = urllib.request.Request(
            f"{self.base}/api/tasks",
            data=json.dumps({"name": "ui-task", "text": "# UI\n\n1. From API.\n"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
        self.assertTrue(body["ok"])
        state = get(f"{self.base}/api/state")
        self.assertTrue(any(t["name"] == "ui-task" for t in state["tasks"]))

    def test_workflow_payload(self):
        wf = get(f"{self.base}/api/workflow")
        self.assertEqual(wf["workflow"]["name"], "Review belt")
        self.assertIsNone(wf["gate"])
        self.assertEqual([r["name"] for r in wf["roles"]], ["coder", "reviewer"])
        self.assertIn("specifier", [r["name"] for r in wf["library"]])
        self.assertNotIn("sidecar", wf)
        self.assertNotIn("ticket-reviewer", [r["name"] for r in wf["roles"] + wf["library"]])
        self.assertIn("constitution.md", wf["constitution"])
        self.assertIn("## Owns", wf["roles"][0]["text"])
        self.assertTrue(wf["project"])
        self.assertIn("icon", wf["roles"][0]["avatar"])
        self.assertTrue(any(r["verdict"] == "ready" for r in wf["routes"]))

    def test_workflow_payload_has_no_starters(self):
        wf = get(f"{self.base}/api/workflow")
        self.assertNotIn("starters", wf)
        self.assertNotIn("holds_first_ready", wf)

    # --- preset CRUD ----------------------------------------------------

    def test_workflows_list(self):
        r = get(f"{self.base}/api/workflows")
        rows = {w["slug"]: w for w in r["workflows"]}
        self.assertEqual(sorted(rows),
                         ["review-belt", "solo-coder", "spec-no-gate", "spec-then-build"])
        self.assertTrue(rows["review-belt"]["active"])
        self.assertFalse(rows["review-belt"]["modified"])
        self.assertEqual(rows["review-belt"]["file"],
                         ".conveyor/workflows/review-belt.json")
        self.assertEqual(r["active"], "review-belt")
        self.assertEqual(r["status"], "active")
        self.assertEqual(r["chain"], "coder → reviewer")

    def test_workflows_list_marks_modified(self):
        # "modified" needs a marker, and only activate writes one. Without it a
        # non-matching conveyor.conf is genuinely "custom", not "modified".
        self.fx.conveyor("stop")
        self._clear_loop_locks()
        code, body = post(f"{self.base}/api/active", {"slug": "review-belt"})
        self.assertEqual(code, 200, body)
        conf = os.path.join(self.fx.root, "conveyor.conf")
        with open(conf, "w") as f:
            f.write("role coder composer-2.5\nrole tester composer-2.5\n"
                    "role reviewer gpt-5\ngate none\n")
        with open(os.path.join(self.fx.root, "roles", "tester.md"), "w") as f:
            f.write("## Owns\nx\n## Does not own\ny\n## Handoff contract\nz\n")
        r = get(f"{self.base}/api/workflows")
        self.assertEqual(r["status"], "modified")
        self.assertEqual(r["chain"], "coder → tester → reviewer",
                         "the real chain from conveyor.conf, not the preset's")

    def test_workflows_list_marks_custom_with_no_marker(self):
        conf = os.path.join(self.fx.root, "conveyor.conf")
        with open(conf, "w") as f:
            f.write("role coder composer-2.5\nrole reviewer gpt-5\n"
                    "role specifier composer-2.5\ngate none\n")
        r = get(f"{self.base}/api/workflows")
        self.assertEqual(r["status"], "custom")
        self.assertIsNone(r["active"])

    def test_workflow_detail_and_404(self):
        d = get(f"{self.base}/api/workflows/review-belt")
        self.assertEqual(d["roles_detail"][0]["model"], "composer-2.5")
        self.assertEqual(d["roles_detail"][0]["handoff"], "ready → reviewer")
        self.assertEqual(d["roles_detail"][1]["handoff"], "pass → done · findings → coder")
        self.assertTrue(d["routes"])
        self.assertFalse(d["deletable"], "the active workflow cannot be deleted")
        code, body = get_code(f"{self.base}/api/workflows/nope")
        self.assertEqual(code, 404, body)

    def test_workflow_detail_model_is_null_for_an_offbelt_role(self):
        d = get(f"{self.base}/api/workflows/spec-then-build")
        spec = [r for r in d["roles_detail"] if r["name"] == "specifier"][0]
        self.assertIsNone(spec["model"], "models live in conveyor.conf, not the preset")
        self.assertEqual(spec["handoff"], "(held for approval)")

    def test_create_workflow(self):
        code, body = post(f"{self.base}/api/workflows",
                          {"name": "QA belt", "roles": ["coder", "reviewer"]})
        self.assertEqual(code, 200, body)
        self.assertEqual(body["slug"], "qa-belt")
        slugs = [w["slug"] for w in get(f"{self.base}/api/workflows")["workflows"]]
        self.assertIn("qa-belt", slugs)

    def test_create_workflow_400_on_bad_gate(self):
        code, body = post(f"{self.base}/api/workflows",
                          {"name": "Bad", "roles": ["coder", "reviewer"],
                           "gate": "reviewer"})
        self.assertEqual(code, 409, body)  # CLI nonzero -> RuntimeError
        self.assertIn("the last role", body["error"])

    def test_create_workflow_rejects_an_unknown_role(self):
        code, body = post(f"{self.base}/api/workflows",
                          {"name": "Ghosts", "roles": ["coder", "ghost"]})
        self.assertNotEqual(code, 200)
        self.assertIn("create roles/ghost.md first", body["error"])

    def test_save_workflow(self):
        code, body = post(f"{self.base}/api/workflows/save",
                          {"slug": "solo-coder", "name": "Just the coder"})
        self.assertEqual(code, 200, body)
        d = get(f"{self.base}/api/workflows/solo-coder")
        self.assertEqual(d["name"], "Just the coder")

    def test_save_workflow_unknown_slug(self):
        code, body = post(f"{self.base}/api/workflows/save",
                          {"slug": "nope", "name": "x"})
        self.assertNotEqual(code, 200)
        self.assertIn("nope", body["error"])

    def test_delete_workflow(self):
        code, body = post(f"{self.base}/api/workflows/delete", {"slug": "solo-coder"})
        self.assertEqual(code, 200, body)
        slugs = [w["slug"] for w in get(f"{self.base}/api/workflows")["workflows"]]
        self.assertNotIn("solo-coder", slugs)

    def test_delete_workflow_409_when_active(self):
        code, body = post(f"{self.base}/api/workflows/delete", {"slug": "review-belt"})
        self.assertEqual(code, 409, body)
        self.assertIn("is active", body["error"])

    def test_activate_switches_the_pipeline(self):
        self.fx.conveyor("stop")
        self._clear_loop_locks()
        code, body = post(f"{self.base}/api/active", {"slug": "spec-then-build"})
        self.assertEqual(code, 200, body)
        wf = get(f"{self.base}/api/workflow")
        self.assertEqual([r["name"] for r in wf["roles"]],
                         ["specifier", "coder", "reviewer"])
        self.assertEqual(wf["gate"], "specifier")
        self.assertEqual(get(f"{self.base}/api/state")["workflow"]["chain"],
                         "specifier → coder → reviewer")

    def test_activate_a_gateless_three_role_workflow(self):
        self.fx.conveyor("stop")
        self._clear_loop_locks()
        code, body = post(f"{self.base}/api/active", {"slug": "spec-no-gate"})
        self.assertEqual(code, 200, body)
        wf = get(f"{self.base}/api/workflow")
        self.assertEqual(len(wf["roles"]), 3)
        self.assertIsNone(wf["gate"], "the preset says no gate; nothing may infer one")

    def test_workflow_409_while_running(self):
        code, body = post(f"{self.base}/api/active", {"slug": "spec-then-build"})
        self.assertEqual(code, 409, body)
        self.assertIn("running", body["error"])
        code, body = post(f"{self.base}/api/roles/runtime", {
            "name": "coder", "model": "gpt-5",
            "max_retries": 1, "max_minutes": 10, "max_attempts": 1,
        })
        self.assertEqual(code, 409, body)

    def test_role_write_requires_headings(self):
        coder = os.path.join(self.fx.root, "roles", "coder.md")
        with open(coder, encoding="utf-8") as f:
            original = f.read()
        code, body = post(f"{self.base}/api/roles", {"name": "coder", "text": "no headings here\n"})
        self.assertEqual(code, 400, body)
        self.assertIn("Owns", body["error"])
        with open(coder, encoding="utf-8") as f:
            self.assertEqual(f.read(), original)
        code, body = post(f"{self.base}/api/roles", {"name": "operator", "text": original})
        self.assertEqual(code, 400, body)
        patched = original.replace("## Owns", "## Owns\n\n- extra ownership line.")
        code, body = post(f"{self.base}/api/roles", {"name": "coder", "text": patched})
        self.assertEqual(code, 200, body)
        with open(coder, encoding="utf-8") as f:
            self.assertIn("extra ownership line", f.read())

    def test_runtime_and_project_write(self):
        code, body = post(f"{self.base}/api/project", {"text": "# Project\n\nfrom-api\n"})
        self.assertEqual(code, 200, body)
        with open(os.path.join(self.fx.root, "project.md"), encoding="utf-8") as f:
            self.assertIn("from-api", f.read())
        self.fx.conveyor("stop")
        self._clear_loop_locks()
        code, body = post(f"{self.base}/api/roles/runtime", {
            "name": "coder", "model": "composer-2.5",
            "max_retries": 9, "max_minutes": 15, "max_attempts": 2,
        })
        self.assertEqual(code, 200, body)
        with open(os.path.join(self.fx.root, "conveyor.conf"), encoding="utf-8") as f:
            cfg_text = f.read()
        self.assertIn("max_retries=9", cfg_text)
        self.assertIn("max_minutes=15", cfg_text)
        wf = get(f"{self.base}/api/workflow")
        coder = next(r for r in wf["roles"] if r["name"] == "coder")
        self.assertEqual(coder["max_retries"], 9)
        code, body = post(f"{self.base}/api/roles/runtime", {
            "name": "specifier", "model": "x",
            "max_retries": 1, "max_minutes": 1, "max_attempts": 1,
        })
        self.assertEqual(code, 400, body)

    def test_models_list(self):
        body = get(f"{self.base}/api/models")
        ids = [m["id"] for m in body["models"]]
        self.assertEqual(ids, ["composer-2.5", "gpt-5"])
        self.assertEqual(body["models"][0]["label"], "composer-2.5")
        self.assertIsNone(body["error"])

    def test_models_error_is_200(self):
        old = os.environ.get("CONVEYOR_AGENT_BIN")
        os.environ["CONVEYOR_AGENT_BIN"] = "/no/such/agent-bin"
        try:
            body = get(f"{self.base}/api/models")
        finally:
            if old is None:
                os.environ.pop("CONVEYOR_AGENT_BIN", None)
            else:
                os.environ["CONVEYOR_AGENT_BIN"] = old
        self.assertEqual(body["models"], [])
        self.assertTrue(body["error"])

    def test_intake_config_saves_while_loops_run(self):
        state = get(f"{self.base}/api/state")
        self.assertTrue(state["running"], "loops must be up — that is the point")
        code, body = post(f"{self.base}/api/intake/config", {
            "model": "gpt-5", "max_minutes": 10, "max_attempts": 1,
        })
        self.assertEqual(code, 200, body)
        self.assertNotEqual(code, 409)
        intake = get(f"{self.base}/api/intake")
        self.assertEqual(intake["config"]["model"], "gpt-5")
        self.assertEqual(intake["config"]["max_minutes"], 10)
        self.assertEqual(intake["config"]["max_attempts"], 1)

    def test_intake_jira_write_hides_the_token(self):
        code, body = post(f"{self.base}/api/intake/jira", {
            "site": "https://ex.atlassian.net",
            "email": "dev@ex.com",
            "token": "super-secret-token",
        })
        self.assertEqual(code, 200, body)
        blob = json.dumps(body)
        self.assertNotIn("super-secret-token", blob)
        self.assertNotIn('"token"', blob)
        self.assertTrue(body["token_set"])
        got = get(f"{self.base}/api/intake")
        self.assertNotIn("super-secret-token", json.dumps(got))
        self.assertNotIn("token", got["jira"])
        self.assertTrue(got["jira"]["token_set"])

    def test_intake_prompt_and_rubric(self):
        got = get(f"{self.base}/api/intake")
        self.assertIn("## Owns", got["prompt"])
        self.assertIn("Ready", got["rubric"])
        self.assertEqual(got["avatar"]["icon"], "inbox")
        code, body = post(f"{self.base}/api/intake/rubric", {"text": "Ready means done.\n"})
        self.assertEqual(code, 200, body)
        self.assertEqual(body["path"], "intake/rubric.md")
        code, body = post(f"{self.base}/api/intake/prompt", {"text": "no headings\n"})
        self.assertEqual(code, 400, body)


if __name__ == "__main__":
    unittest.main()
