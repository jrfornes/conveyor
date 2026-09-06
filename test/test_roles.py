"""Unit and CLI tests for role library CRUD and skills sidecars."""
import os
import shutil
import unittest

from harness import Fixture, read
from conveyor import config, presets, roles


def _headings(text):
    return all(h in text for h in roles.REQUIRED_ROLE_HEADINGS)


class RolesLib(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root

    def _skill(self, name, body="# Skill\n\nDoes things.\n", catalog=".cursor/skills"):
        d = os.path.join(self.root, catalog, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write(body)

    def _agents_skill(self, name, body="# Skill\n\nFrom agents.\n"):
        self._skill(name, body, catalog=".agents/skills")

    def test_create_stub_has_three_headings(self):
        roles.create(self.root, "tester")
        text = read(roles.md_path(self.root, "tester"))
        self.assertTrue(_headings(text))
        self.assertIn("# Role: tester", text)

    def test_create_from_copies_md_and_skills(self):
        self._skill("alpha")
        roles.write_skills(self.root, "coder", ["alpha"])
        roles.create(self.root, "clone", from_name="coder")
        self.assertEqual(read(roles.md_path(self.root, "clone")),
                         read(roles.md_path(self.root, "coder")))
        self.assertEqual(roles.read_skills(self.root, "clone"), ["alpha"])

    def test_create_refuses_reserved_exists_bad_name(self):
        with self.assertRaises(roles.RoleError):
            roles.create(self.root, "operator")
        roles.create(self.root, "tester")
        with self.assertRaises(roles.RoleError) as ctx:
            roles.create(self.root, "tester")
        self.assertIn("already exists", str(ctx.exception))
        with self.assertRaises(roles.RoleError):
            roles.create(self.root, "Bad_Name")

    def test_delete_refuses_on_belt_and_preset(self):
        cfg = config.load(self.root)
        with self.assertRaises(roles.RoleError) as ctx:
            roles.delete(self.root, self.fx.paths, cfg, "coder")
        self.assertIn("on the active belt", str(ctx.exception))
        roles.create(self.root, "ghost")
        self.fx.conveyor("workflow", "edit", "solo-coder", "--roles", "coder,ghost,reviewer")
        with self.assertRaises(roles.RoleError) as ctx:
            roles.delete(self.root, self.fx.paths, cfg, "ghost")
        self.assertIn("used by workflow", str(ctx.exception))

    def test_delete_library_role_removes_file_not_queues(self):
        roles.create(self.root, "ghost")
        qdir = self.fx.paths.role("coder").base
        os.makedirs(qdir, exist_ok=True)
        marker = os.path.join(qdir, "keep")
        with open(marker, "w") as f:
            f.write("1\n")
        cfg = config.load(self.root)
        roles.delete(self.root, self.fx.paths, cfg, "ghost")
        self.assertFalse(os.path.isfile(roles.md_path(self.root, "ghost")))
        self.assertTrue(os.path.isfile(marker))

    def test_write_skills_sidecar_and_unknown(self):
        roles.create(self.root, "tester")
        self._skill("alpha")
        roles.write_skills(self.root, "tester", ["alpha"])
        self.assertEqual(roles.read_skills(self.root, "tester"), ["alpha"])
        sidecar = read(roles.skills_path(self.root, "tester"))
        self.assertIn("alpha", sidecar)
        with self.assertRaises(roles.RoleError) as ctx:
            roles.write_skills(self.root, "tester", ["nope"])
        self.assertIn("unknown skill", str(ctx.exception))

    def test_available_skills_discovers_skill_md(self):
        self._skill("beta", "---\ndescription: Beta skill\n---\n\nBody.\n")
        avail = roles.available_skills(self.root)
        self.assertEqual(avail, [{
            "name": "beta",
            "description": "Beta skill",
            "source": ".cursor/skills",
        }])

    def test_available_skills_discovers_agents_only(self):
        self._agents_skill("gamma", "---\ndescription: Agents skill\n---\n\nBody.\n")
        avail = roles.available_skills(self.root)
        self.assertEqual(avail, [{
            "name": "gamma",
            "description": "Agents skill",
            "source": ".agents/skills",
        }])

    def test_available_skills_agents_wins_on_collision(self):
        self._skill("dup", "---\ndescription: Cursor copy\n---\n\nBody.\n")
        self._agents_skill("dup", "---\ndescription: Agents copy\n---\n\nBody.\n")
        avail = roles.available_skills(self.root)
        self.assertEqual(avail, [{
            "name": "dup",
            "description": "Agents copy",
            "source": ".agents/skills",
        }])

    def test_write_skills_accepts_agents_only(self):
        roles.create(self.root, "tester")
        self._agents_skill("agents-only")
        roles.write_skills(self.root, "tester", ["agents-only"])
        self.assertEqual(roles.read_skills(self.root, "tester"), ["agents-only"])


class CliRoles(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def role(self, *args, **kw):
        return self.fx.conveyor("role", *args, **kw)

    def _skill(self, name, catalog=".cursor/skills"):
        d = os.path.join(self.fx.root, catalog, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write(f"# {name}\n\nSkill text.\n")

    def _agents_skill(self, name):
        self._skill(name, catalog=".agents/skills")

    def test_role_new_and_list(self):
        out = self.role("new", "tester").stdout
        self.assertIn("roles/tester.md created", out)
        self.assertIn("tester", self.role("list").stdout)

    def test_role_show(self):
        self.role("new", "tester")
        out = self.role("show", "tester").stdout
        self.assertIn("roles/tester.md", out)
        self.assertIn("library", out)
        self.assertIn("## Owns", out)

    def test_role_skills_set_and_list(self):
        self.role("new", "tester")
        self._skill("alpha")
        self.role("skills", "tester", "--set", "alpha")
        out = self.role("skills", "tester").stdout
        self.assertIn("assigned: alpha", out)
        self.assertIn("alpha", out)

    def test_role_delete_library(self):
        self.role("new", "ghost")
        self.role("delete", "ghost")
        self.assertFalse(os.path.isfile(os.path.join(self.fx.root, "roles", "ghost.md")))

    def test_start_fails_on_missing_assigned_skill(self):
        self.role("new", "tester")
        roles.write_skills(self.fx.root, "tester", [])
        with open(roles.skills_path(self.fx.root, "tester"), "w") as f:
            f.write("ghost\n")
        self.fx.conveyor("workflow", "edit", "solo-coder", "--roles", "tester")
        self.fx.conveyor("workflow", "activate", "solo-coder")
        r = self.fx.conveyor("start", "--no-smoke", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("assigned skill 'ghost' is missing", r.stderr)

    def test_ensure_worktree_copies_assigned_skill(self):
        self.role("new", "tester")
        self._skill("alpha")
        self.role("skills", "tester", "--set", "alpha")
        self.fx.conveyor("workflow", "edit", "solo-coder", "--roles", "tester")
        self.fx.conveyor("workflow", "activate", "solo-coder")
        self.fx.conveyor("start", "--no-smoke")
        wt_skill = os.path.join(self.fx.paths.worktree("tester"),
                                ".cursor", "skills", "alpha", "SKILL.md")
        self.assertTrue(os.path.isfile(wt_skill))
        mdc = read(os.path.join(self.fx.paths.worktree("tester"),
                                ".cursor", "rules", "conveyor-role.mdc"))
        self.assertIn("Assigned skills", mdc)
        self.assertIn("`alpha`", mdc)
        self.assertIn("`.cursor/skills/alpha/`", mdc)

    def test_start_injects_agents_skill_to_agents_path(self):
        self.role("new", "tester")
        self._agents_skill("beta")
        self.role("skills", "tester", "--set", "beta")
        self.fx.conveyor("workflow", "edit", "solo-coder", "--roles", "tester")
        self.fx.conveyor("workflow", "activate", "solo-coder")
        self.fx.conveyor("start", "--no-smoke")
        wt = self.fx.paths.worktree("tester")
        agents_skill = os.path.join(wt, ".agents", "skills", "beta", "SKILL.md")
        cursor_skill = os.path.join(wt, ".cursor", "skills", "beta", "SKILL.md")
        self.assertTrue(os.path.isfile(agents_skill))
        self.assertFalse(os.path.isfile(cursor_skill))
        mdc = read(os.path.join(wt, ".cursor", "rules", "conveyor-role.mdc"))
        self.assertIn("`.agents/skills/beta/`", mdc)

    def test_start_collision_injects_agents_only(self):
        self.role("new", "tester")
        self._skill("shared")
        self._agents_skill("shared")
        self.role("skills", "tester", "--set", "shared")
        self.fx.conveyor("workflow", "edit", "solo-coder", "--roles", "tester")
        self.fx.conveyor("workflow", "activate", "solo-coder")
        self.fx.conveyor("start", "--no-smoke")
        wt = self.fx.paths.worktree("tester")
        self.assertTrue(os.path.isfile(
            os.path.join(wt, ".agents", "skills", "shared", "SKILL.md")))
        self.assertFalse(os.path.isfile(
            os.path.join(wt, ".cursor", "skills", "shared", "SKILL.md")))

    def test_start_removes_stale_cursor_copy_after_agents_collision(self):
        self.role("new", "tester")
        self._skill("shared")
        self.role("skills", "tester", "--set", "shared")
        self.fx.conveyor("workflow", "edit", "solo-coder", "--roles", "tester")
        self.fx.conveyor("workflow", "activate", "solo-coder")
        self.fx.conveyor("start", "--no-smoke")
        wt = self.fx.paths.worktree("tester")
        self.assertTrue(os.path.isfile(
            os.path.join(wt, ".cursor", "skills", "shared", "SKILL.md")))
        self._agents_skill("shared")
        self.fx.conveyor("start", "--no-smoke")
        self.assertTrue(os.path.isfile(
            os.path.join(wt, ".agents", "skills", "shared", "SKILL.md")))
        self.assertFalse(os.path.isfile(
            os.path.join(wt, ".cursor", "skills", "shared", "SKILL.md")))

    def test_role_skills_set_agents_only(self):
        self.role("new", "tester")
        self._agents_skill("agents-only")
        self.role("skills", "tester", "--set", "agents-only")
        out = self.role("skills", "tester").stdout
        self.assertIn("assigned: agents-only", out)
        self.assertIn("agents-only", out)


class RolesApi(unittest.TestCase):
    def setUp(self):
        import json
        import sys
        import threading
        import urllib.error
        import urllib.request

        self._json = json
        self._urllib = urllib
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)
        REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, REPO)
        from ui.server.httpd import Handler, ThreadingHTTPServer
        Handler.repo_root = self.fx.root
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()

    def post(self, path, data):
        req = self._urllib.request.Request(
            f"{self.base}{path}",
            data=self._json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._urllib.request.urlopen(req) as r:
                return r.status, self._json.loads(r.read())
        except self._urllib.error.HTTPError as e:
            return e.code, self._json.loads(e.read())

    def _skill(self, name, catalog=".cursor/skills"):
        d = os.path.join(self.fx.root, catalog, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("# skill\n")

    def _agents_skill(self, name):
        self._skill(name, catalog=".agents/skills")

    def test_http_create_delete_skills(self):
        code, body = self.post("/api/roles/create", {"name": "tester"})
        self.assertEqual(code, 200, body)
        self._skill("alpha")
        code, body = self.post("/api/roles/skills", {"name": "tester", "skills": ["nope"]})
        self.assertEqual(code, 400, body)
        self.assertIn("unknown skill", body["error"])
        code, body = self.post("/api/roles/skills", {"name": "tester", "skills": ["alpha"]})
        self.assertEqual(code, 200, body)
        wf = self._urllib.request.urlopen(f"{self.base}/api/workflow")
        payload = self._json.loads(wf.read())
        lib = next(r for r in payload["library"] if r["name"] == "tester")
        self.assertEqual(lib["skills"], ["alpha"])
        self.assertTrue(any(s["name"] == "alpha" for s in payload["available_skills"]))
        code, body = self.post("/api/roles/delete", {"name": "coder"})
        self.assertEqual(code, 400, body)
        self.assertIn("on the active belt", body["error"])
        code, body = self.post("/api/roles/delete", {"name": "tester"})
        self.assertEqual(code, 200, body)

    def test_http_skills_accepts_agents_only(self):
        code, body = self.post("/api/roles/create", {"name": "tester"})
        self.assertEqual(code, 200, body)
        self._agents_skill("agents-only")
        code, body = self.post("/api/roles/skills",
                                {"name": "tester", "skills": ["agents-only"]})
        self.assertEqual(code, 200, body)
        wf = self._urllib.request.urlopen(f"{self.base}/api/workflow")
        payload = self._json.loads(wf.read())
        lib = next(r for r in payload["library"] if r["name"] == "tester")
        self.assertEqual(lib["skills"], ["agents-only"])
        avail = next(s for s in payload["available_skills"] if s["name"] == "agents-only")
        self.assertEqual(avail["source"], ".agents/skills")


if __name__ == "__main__":
    unittest.main()
