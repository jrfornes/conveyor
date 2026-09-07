"""Jira site URL validation and redirect-safe HTTP."""
import base64
import json
import os
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

from harness import ConveyorTest
from conveyor import adapters, config, jira as jiralib


class JiraOrigin(unittest.TestCase):
    def test_rejects_invalid(self):
        bad = [
            "",
            "file:///etc/passwd",
            "ex.atlassian.net",
            "http://evil.example",
            "ftp://jira.example",
        ]
        for site in bad:
            with self.subTest(site=site):
                with self.assertRaises(ValueError):
                    jiralib.origin(site)

    def test_accepts_valid(self):
        cases = [
            ("https://ex.atlassian.net/", "https://ex.atlassian.net"),
            ("https://ex.atlassian.net/browse/PROJ-9", "https://ex.atlassian.net"),
            ("https://jira.example/jira", "https://jira.example/jira"),
            ("http://127.0.0.1:9", "http://127.0.0.1:9"),
            ("http://localhost:8080/jira", "http://localhost:8080/jira"),
        ]
        for raw, want in cases:
            with self.subTest(raw=raw):
                self.assertEqual(jiralib.origin(raw), want)


class JiraWrite(ConveyorTest):
    def test_bad_site_raises_and_does_not_overwrite(self):
        fx = self.fx
        jiralib.write(fx.paths, "https://good.example", "a@b.com", "tok")
        with self.assertRaises(ValueError):
            jiralib.write(fx.paths, "http://evil.example", "a@b.com", "tok2")
        stored = jiralib.read(fx.paths)
        self.assertEqual(stored["site"], "https://good.example")
        self.assertEqual(stored["token"], "tok")

    def test_bad_site_on_fresh_path_no_file(self):
        fx = self.fx
        with self.assertRaises(ValueError):
            jiralib.write(fx.paths, "file:///etc/passwd", "a@b.com", "tok")
        self.assertFalse(os.path.isfile(fx.paths.jira))

    def test_stores_canonical_site(self):
        fx = self.fx
        jiralib.write(fx.paths, "https://ex.atlassian.net/browse/PROJ-9", "a@b.com", "tok")
        stored = jiralib.read(fx.paths)
        self.assertEqual(stored["site"], "https://ex.atlassian.net")


class JiraCli(ConveyorTest):
    def test_intake_jira_bad_site_dies_unchanged(self):
        fx = self.fx
        jiralib.write(fx.paths, "https://good.example", "a@b.com", "tok")
        r = fx.conveyor("intake", "jira", "--site", "http://example.com",
                        "--email", "a@b.com", "--token-stdin", input="tok\n", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("site must be https", r.stderr)
        stored = jiralib.read(fx.paths)
        self.assertEqual(stored["site"], "https://good.example")

    def test_check_invalid_site_no_500(self):
        fx = self.fx
        os.makedirs(fx.paths.local, exist_ok=True)
        with open(fx.paths.jira, "w", encoding="utf-8") as f:
            json.dump({"site": "http://corp.example", "email": "a@b.com", "token": "tok"}, f)
        result = jiralib.check(fx.paths, config.load(fx.root))
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 0)
        self.assertIn("site must be https", result["message"])


class _RedirectHandler(BaseHTTPRequestHandler):
    redirect_to = ""
    dest_hits = 0

    def do_GET(self):
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        if self.path.startswith("/dest"):
            type(self).dest_hits += 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args):
        pass


class JiraRedirect(unittest.TestCase):
    def _server(self, redirect_to):
        handler = type("H", (_RedirectHandler,), {"redirect_to": redirect_to, "dest_hits": 0})
        server = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        return server, handler, port

    def test_refuses_cross_port_redirect(self):
        server_a, handler_a, port_a = self._server("")
        server_b, handler_b, port_b = self._server("")
        try:
            handler_a.redirect_to = f"http://127.0.0.1:{port_b}/dest"
            url = f"http://127.0.0.1:{port_a}/redirect"
            auth = "Basic " + base64.b64encode(b"a@b.com:tok").decode("ascii")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                with jiralib.urlopen(url, {"Authorization": auth}):
                    pass
            self.assertIn("refusing cross-host redirect", str(ctx.exception.reason))
            self.assertEqual(handler_b.dest_hits, 0)
        finally:
            server_a.shutdown()
            server_b.shutdown()

    def test_refuses_cross_host_redirect(self):
        server, handler, port = self._server("https://evil.example/dest")
        try:
            url = f"http://127.0.0.1:{port}/redirect"
            auth = "Basic " + base64.b64encode(b"a@b.com:tok").decode("ascii")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                with jiralib.urlopen(url, {"Authorization": auth}):
                    pass
            self.assertIn("refusing cross-host redirect", str(ctx.exception.reason))
        finally:
            server.shutdown()

    def test_same_origin_redirect_follows(self):
        server, handler, port = self._server("")
        try:
            handler.redirect_to = f"http://127.0.0.1:{port}/dest"
            url = f"http://127.0.0.1:{port}/redirect"
            with jiralib.urlopen(url, {}) as resp:
                self.assertEqual(resp.status, 200)
            self.assertEqual(handler.dest_hits, 1)
        finally:
            server.shutdown()


class JiraFetchFallback(ConveyorTest):
    def test_stale_jira_base_fails_closed(self):
        fx = self.fx
        conf = os.path.join(fx.root, "conveyor.conf")
        with open(conf, encoding="utf-8") as f:
            text = f.read()
        text += "\n[inbox]\njira_base = http://corp.example\n"
        with open(conf, "w", encoding="utf-8") as f:
            f.write(text)
        os.makedirs(fx.paths.local, exist_ok=True)
        with open(fx.paths.jira, "w", encoding="utf-8") as f:
            json.dump({"site": "", "email": "a@b.com", "token": "tok"}, f)
        with self.assertRaises(ValueError) as ctx:
            adapters.fetch("jira", "PROJ-9", cfg=config.load(fx.root), paths=fx.paths)
        self.assertIn("site must be https", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
