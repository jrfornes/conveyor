"""The generated `## Handoff contract` block (docs/plans/generated-handoff-contract.md).

`render_contract` is a pure rendering of `Config.routes()`; the wired tests check
that `conveyor start`, `conveyor role show`, and the cockpit API carry it.
"""
import json
import os
import re
import sys
import threading
import unittest
import urllib.request

from harness import Fixture, read
from conveyor import config, roles
from conveyor.config import Config, Role


def mkcfg(names, gate=""):
    return Config([Role(n, "composer-2.5") for n in names], gate=gate)


def table_rows(block):
    """The (from, to, verdict) triples parsed out of the rendered markdown table."""
    rows = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("You are", "---"):
            continue
        rows.append((cells[0], cells[1], cells[2]))
    return rows


class RenderContract(unittest.TestCase):
    def test_rows_agree_with_routes(self):
        for n in (1, 2, 3, 4):
            cfg = mkcfg([f"r{i}" for i in range(n)])
            for name in cfg.names():
                block = roles.render_contract(cfg, name)
                got = set(table_rows(block))
                want = {(a, b, v) for (a, b, v) in cfg.routes() if a == name}
                self.assertEqual(got, want, f"belt {n}, role {name}")
                # Intake's own route is never rendered into a coding role's block.
                self.assertNotIn((config.INTAKE_ROLE, "operator", "ready"), got)

    def test_one_role_belt_has_no_findings(self):
        # The fixed draft template lists every verdict; the invariant is that a
        # one-role belt carries no findings *edge* — no row, receive clause, or
        # empty-commit rule.
        block = roles.render_contract(mkcfg(["solo"]), "solo")
        prose = block.split("Write exactly this", 1)[0]
        self.assertNotIn("findings", prose)
        self.assertEqual([v for _, _, v in table_rows(block)], ["pass"])

    def test_receive_sentence_two_and_three_pack(self):
        two = roles.render_contract(mkcfg(["coder", "reviewer"]), "coder")
        self.assertIn(
            "You receive `ready` from operator (new task) and "
            "`findings` from reviewer (rework).", two)
        three = roles.render_contract(
            mkcfg(["specifier", "coder", "reviewer"]), "coder")
        self.assertIn(
            "You receive `ready` from specifier and `findings` from reviewer.", three)

    def test_empty_commit_rule_last_role_only(self):
        cfg = mkcfg(["specifier", "coder", "reviewer"])
        self.assertIn("git commit --allow-empty", roles.render_contract(cfg, "reviewer"))
        self.assertNotIn("git commit --allow-empty", roles.render_contract(cfg, "coder"))
        self.assertNotIn("git commit --allow-empty", roles.render_contract(cfg, "specifier"))

    def test_gate_line_present_only_when_gated(self):
        gated = roles.render_contract(mkcfg(["specifier", "coder", "reviewer"], gate="specifier"), "specifier")
        self.assertIn(".conveyor/approvals/pending/", gated)
        ungated = mkcfg(["coder", "reviewer"], gate=config.NO_GATE)
        for name in ungated.names():
            self.assertNotIn(".conveyor/approvals/pending/", roles.render_contract(ungated, name))

    def test_off_belt_role_raises(self):
        with self.assertRaises(roles.RoleError):
            roles.render_contract(mkcfg(["coder", "reviewer"]), "ghost")


class ValidateAndStub(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def test_handwritten_contract_still_validates(self):
        text = "## Owns\nx\n## Does not own\ny\n## Handoff contract\nz\n"
        roles.validate_role_text(text)  # accepted, not refused
        self.assertTrue(roles.has_handwritten_contract(text))

    def test_two_headings_pass_missing_fails(self):
        roles.validate_role_text("## Owns\nx\n## Does not own\ny\n")
        with self.assertRaises(roles.RoleError) as ctx:
            roles.validate_role_text("## Owns\nx\n")
        self.assertIn("Does not own", str(ctx.exception))

    def test_stub_has_no_contract_and_passes(self):
        self.assertNotIn("Handoff contract", roles._ROLE_STUB)
        self.fx.conveyor("role", "new", "tester")
        roles.validate_role_text(read(roles.md_path(self.fx.root, "tester")))


class StartWiring(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def _skill(self, name):
        d = os.path.join(self.fx.root, ".cursor", "skills", name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("# skill\n")

    def _mdc(self, role):
        return read(os.path.join(self.fx.paths.worktree(role),
                                 ".cursor", "rules", "conveyor-role.mdc"))

    def test_section_order_role_contract_skills(self):
        self._skill("alpha")
        self.fx.conveyor("role", "skills", "coder", "--set", "alpha")
        self.fx.conveyor("start", "--no-smoke")
        mdc = self._mdc("coder")
        role_at = mdc.index("# Role: coder")
        contract_at = mdc.index("## Handoff contract")
        skills_at = mdc.index("## Assigned skills")
        self.assertLess(role_at, contract_at)
        self.assertLess(contract_at, skills_at)
        # Generated table row for the two-pack coder.
        self.assertIn("| coder | reviewer | ready |", mdc)

    def test_start_warns_once_on_handwritten_contract(self):
        path = roles.md_path(self.fx.root, "coder")
        text = read(path)
        with open(path, "w") as f:
            f.write(text + "\n## Handoff contract\n\n- hand written\n")
        self.fx.git("commit", "-q", "-am", "test: hand-written contract")
        r = self.fx.conveyor("start", "--no-smoke")
        warning = ("warning: roles/coder.md carries a hand-written Handoff contract; "
                   "the generated one overrides it — delete the section")
        self.assertEqual(r.stdout.count(warning), 1, r.stdout)

    def test_role_new_passes_validation(self):
        self.fx.conveyor("role", "new", "fresh")
        roles.validate_role_text(read(roles.md_path(self.fx.root, "fresh")))


class RoleShow(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)

    def test_show_ends_with_rendered_block(self):
        out = self.fx.conveyor("role", "show", "coder").stdout
        cfg = config.load(self.fx.root)
        block = roles.render_contract(cfg, "coder")
        self.assertIn("Handoff contract (generated from conveyor.conf", out)
        self.assertTrue(out.endswith(block), out[-400:])

    def test_show_library_role_says_off_workflow(self):
        self.fx.conveyor("role", "new", "ghost")
        out = self.fx.conveyor("role", "show", "ghost").stdout
        self.assertIn("not on the active workflow", out)


class RolesApi(unittest.TestCase):
    def setUp(self):
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

    def _workflow(self):
        with urllib.request.urlopen(f"{self.base}/api/workflow") as r:
            return json.loads(r.read())

    def test_belt_role_carries_contract_library_null(self):
        payload = self._workflow()
        cfg = config.load(self.fx.root)
        coder = next(r for r in payload["roles"] if r["name"] == "coder")
        self.assertEqual(coder["contract"], roles.render_contract(cfg, "coder"))
        self.assertFalse(coder["handwritten_contract"])
        spec = next(r for r in payload["library"] if r["name"] == "specifier")
        self.assertIsNone(spec["contract"])


if __name__ == "__main__":
    unittest.main()
