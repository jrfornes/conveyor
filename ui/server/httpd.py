"""Stdlib HTTP server for Conveyor UI API + static Angular build."""
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import cli, state

UI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(UI_ROOT, "dist", "ui", "browser")


class Handler(BaseHTTPRequestHandler):
    repo_root = None

    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Client gave up (nav away, request timeout) before the response
            # landed. The mutation already ran; there is no one left to tell.
            pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/health":
                return self._json(200, {"ok": True, "root": self.repo_root})
            if path == "/api/state":
                return self._json(200, state.build_state(self.repo_root))
            if path.startswith("/api/tasks/"):
                name = urllib.parse.unquote(path.split("/api/tasks/", 1)[1])
                text = state.read_task(self.repo_root, name)
                return self._json(200, {"name": name, "text": text})
            if path.startswith("/api/logs/"):
                role = path.split("/api/logs/", 1)[1]
                task = qs.get("task", [None])[0]
                return self._json(200, state.read_logs(self.repo_root, role, task))
            if path.startswith("/api/handoffs/"):
                rest = path.split("/api/handoffs/", 1)[1]
                parts = rest.split("/", 1)
                if len(parts) != 2:
                    raise ValueError("expected /api/handoffs/<role>/<dir>")
                return self._json(200, state.read_handoffs(self.repo_root, parts[0], parts[1]))
            if path.startswith("/api/inbox/"):
                iid = urllib.parse.unquote(path.split("/api/inbox/", 1)[1])
                return self._json(200, state.read_inbox_item(self.repo_root, iid))
            if path.startswith("/api/commits/"):
                sha = path.split("/api/commits/", 1)[1]
                stat = state.git_commit_stat(self.repo_root, sha)
                return self._json(200, {"sha": sha, "stat": stat})
            if path == "/api/workflow":
                return self._json(200, state.build_workflow(self.repo_root))
            if path == "/api/workflows":
                return self._json(200, state.build_workflows(self.repo_root))
            if path.startswith("/api/workflows/"):
                slug = urllib.parse.unquote(path.split("/api/workflows/", 1)[1])
                return self._json(200, state.build_workflow_detail(self.repo_root, slug))
            if path == "/api/models":
                return self._json(200, state.list_models(self.repo_root))
            if path == "/api/intake":
                return self._json(200, state.build_intake(self.repo_root))
            return self._static(path)
        except FileNotFoundError as e:
            return self._json(404, {"error": str(e)})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_json()
            if path == "/api/tasks":
                msg = cli.create_task(self.repo_root, body["name"], body["text"])
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/tasks/delete":
                msg = cli.delete_task(self.repo_root, body["name"])
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/resume":
                msg = cli.resume_task(self.repo_root, body["task"], body.get("to"))
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/start":
                msg = cli.start(self.repo_root)
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/stop":
                msg = cli.stop(self.repo_root, now=body.get("now", False))
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/import":
                msg = cli.import_tickets(
                    self.repo_root,
                    body.get("source", "manual"),
                    title=body.get("title", ""),
                    body=body.get("body") or body.get("text") or "",
                )
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/intake":
                msg = cli.intake(
                    self.repo_root, body["id"],
                    improve=body.get("improve", False),
                    comments=body.get("comments"),
                )
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/inbox/approve":
                msg = cli.inbox_approve(self.repo_root, body["id"], body.get("name"), body.get("text"))
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/inbox/skip":
                msg = cli.inbox_skip(self.repo_root, body["id"])
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/start-task":
                msg = cli.start_task(self.repo_root, body["name"])
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/approve":
                msg = cli.approve(self.repo_root, body["id"])
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/reject":
                msg = cli.reject(self.repo_root, body["id"], body.get("comments", ""))
                return self._json(200, {"ok": True, "message": msg})
            # Action suffixes are matched as exact literals, before any
            # slug-shaped branch, so /api/workflows/save is never read as a slug.
            if path == "/api/workflows/save":
                slug = body["slug"]
                msg = cli.save_workflow(self.repo_root, slug, body)
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/workflows/delete":
                msg = cli.delete_workflow(self.repo_root, body["slug"])
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/workflows":
                msg = cli.create_workflow(self.repo_root, body)
                # The CLI allocates the slug (it may suffix a taken one), so read
                # it back out of the message rather than re-deriving it here.
                return self._json(200, {"ok": True, "message": msg,
                                        "slug": state.slug_from_message(msg)})
            if path == "/api/active":
                state.require_stopped(self.repo_root)
                msg = cli.activate_workflow(self.repo_root, body["slug"])
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/roles":
                state.write_role(self.repo_root, body["name"], body["text"])
                return self._json(200, {"ok": True})
            if path == "/api/roles/create":
                state.create_role(self.repo_root, body["name"], body.get("from"))
                return self._json(200, {"ok": True, "message": f"roles/{body['name']}.md created"})
            if path == "/api/roles/delete":
                state.delete_role(self.repo_root, body["name"])
                return self._json(200, {"ok": True, "message": f"roles/{body['name']}.md deleted"})
            if path == "/api/roles/skills":
                state.write_role_skills(self.repo_root, body["name"], body.get("skills", []))
                return self._json(200, {"ok": True, "message": f"roles/{body['name']}.skills saved"})
            if path == "/api/roles/runtime":
                state.update_role_runtime(
                    self.repo_root,
                    body["name"],
                    body["model"],
                    body["max_retries"],
                    body["max_minutes"],
                    body["max_attempts"],
                )
                return self._json(200, {"ok": True})
            if path == "/api/project":
                state.write_project(self.repo_root, body["text"])
                return self._json(200, {"ok": True})
            if path == "/api/gates/run":
                msg = state.run_project_gate(
                    self.repo_root, body["name"], body.get("role"))
                return self._json(200, {"ok": True, "message": msg})
            if path == "/api/intake/prompt":
                state.write_intake_prompt(self.repo_root, body["text"])
                return self._json(200, {"ok": True, "path": "intake/ticket-reviewer.md"})
            if path == "/api/intake/rubric":
                state.write_intake_rubric(self.repo_root, body["text"])
                return self._json(200, {"ok": True, "path": "intake/rubric.md"})
            if path == "/api/intake/config":
                state.write_intake_config(
                    self.repo_root,
                    body.get("model"),
                    body.get("max_minutes"),
                    body.get("max_attempts"),
                )
                return self._json(200, {"ok": True, "path": "conveyor.conf"})
            if path == "/api/intake/jira/clear":
                state.clear_intake_jira(self.repo_root)
                return self._json(200, {"ok": True})
            if path == "/api/intake/jira/test":
                return self._json(200, state.test_intake_jira(self.repo_root))
            if path == "/api/intake/jira":
                redacted = state.write_intake_jira(
                    self.repo_root,
                    body.get("site", ""),
                    body.get("email", ""),
                    body.get("token"),
                )
                return self._json(200, {"ok": True, **redacted})
            return self._json(404, {"error": "not found"})
        except KeyError as e:
            return self._json(400, {"error": f"missing field: {e.args[0]}"})
        except FileNotFoundError as e:
            return self._json(404, {"error": str(e)})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except RuntimeError as e:
            return self._json(409, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _static(self, path):
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/")
        filepath = os.path.join(DIST, rel)
        if not os.path.isfile(filepath):
            filepath = os.path.join(DIST, "index.html")
        if not os.path.isfile(filepath):
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"UI not built. Run: cd ui && npm run build")
            return
        ctype = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
        with open(filepath, "rb") as f:
            data = f.read()
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


def serve(root, host="127.0.0.1", port=8765):
    state.resolve_root(root)
    Handler.repo_root = os.path.realpath(root)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Conveyor UI: http://{host}:{port}  (root: {Handler.repo_root})")
    server.serve_forever()
