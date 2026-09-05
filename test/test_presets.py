"""Saved workflow presets: schema, validation, seeding, staleness, activate."""
import json
import os
import unittest

from harness import Fixture, read
from conveyor import config, presets


def write_conf(root, body):
    with open(os.path.join(root, "conveyor.conf"), "w") as f:
        f.write(body + "\n[global]\npoll_seconds = 0.2\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.cleanup)
        self.paths = self.fx.paths
        presets.ensure_seeded(self.paths)

    def cfg(self):
        return config.load(self.fx.root)


class Seeding(Base):
    def test_seeds_four_workflows(self):
        slugs = [p["slug"] for p in presets.load_all(self.paths)]
        self.assertEqual(sorted(slugs),
                         ["review-belt", "solo-coder", "spec-no-gate", "spec-then-build"])

    def test_a_deleted_seed_is_not_resurrected(self):
        os.remove(presets.path(self.paths, "solo-coder"))
        presets.ensure_seeded(self.paths)
        self.assertFalse(presets.exists(self.paths, "solo-coder"))

    def test_seed_json_shape(self):
        text = read(presets.path(self.paths, "review-belt"))
        self.assertTrue(text.endswith("\n"))
        self.assertIn('\n  "name"', text, "indent=2")
        raw = json.loads(text)
        self.assertEqual(list(raw), ["name", "description", "roles", "gate"])
        self.assertNotIn("slug", raw, "the filename is the only source of the slug")
        self.assertIsNone(raw["gate"])

    def test_spec_no_gate_seed_is_three_roles_with_no_gate(self):
        p = presets.load(self.paths, "spec-no-gate")
        self.assertEqual(len(p["roles"]), 3)
        self.assertIsNone(p["gate"])


class Validation(Base):
    def bad(self, data):
        with self.assertRaises(presets.PresetError) as e:
            presets.validate(self.fx.root, data)
        return str(e.exception)

    def test_preset_error_is_a_value_error(self):
        self.assertTrue(issubclass(presets.PresetError, ValueError))

    def test_rejects_blank_name(self):
        self.assertIn("name is required", self.bad({"name": " ", "roles": ["coder"]}))

    def test_rejects_unsluggable_name(self):
        self.assertIn("at least one letter or digit",
                      self.bad({"name": "!!!", "roles": ["coder"]}))

    def test_rejects_empty_roles(self):
        self.assertIn("roles must list at least one role",
                      self.bad({"name": "X", "roles": []}))

    def test_rejects_duplicate_role(self):
        self.assertIn("appears twice",
                      self.bad({"name": "X", "roles": ["coder", "coder"]}))

    def test_rejects_missing_role_file(self):
        self.assertIn("unknown role 'ghost'; create roles/ghost.md first",
                      self.bad({"name": "X", "roles": ["ghost"]}))

    def test_rejects_reserved_role_name(self):
        self.assertIn("invalid role name 'done'",
                      self.bad({"name": "X", "roles": ["done"]}))

    def test_rejects_gate_off_the_belt(self):
        msg = self.bad({"name": "X", "roles": ["coder", "reviewer"], "gate": "specifier"})
        self.assertIn("not on this belt: 'specifier'", msg)
        self.assertIn("gate one of coder, reviewer", msg)

    def test_rejects_gate_on_the_last_role(self):
        msg = self.bad({"name": "X", "roles": ["coder", "reviewer"], "gate": "reviewer"})
        self.assertIn("cannot gate 'reviewer', the last role", msg)
        self.assertIn("repair:", msg)

    def test_normalizes_blank_gate_to_none(self):
        clean = presets.validate(self.fx.root, {"name": "X", "roles": ["coder"], "gate": ""})
        self.assertIsNone(clean["gate"])
        self.assertEqual(clean["description"], "")


class Routes(Base):
    def test_one_role_has_no_findings_edge(self):
        r = presets.routes({"roles": ["coder"]})
        self.assertEqual(r, [{"from": "operator", "to": "coder", "verdict": "ready"},
                             {"from": "coder", "to": "done", "verdict": "pass"}])

    def test_four_roles_bounce_to_the_penultimate(self):
        r = presets.routes({"roles": ["a", "b", "c", "d"]})
        self.assertIn({"from": "d", "to": "c", "verdict": "findings"}, r)
        self.assertIn({"from": "c", "to": "d", "verdict": "ready"}, r)

    def test_never_includes_the_intake_edge(self):
        r = presets.routes({"roles": ["coder", "reviewer"]})
        self.assertNotIn("ticket-reviewer", [h["from"] for h in r])


class CreateSaveDelete(Base):
    def test_create_allocates_a_slug(self):
        p = presets.create(self.fx.root, self.paths,
                           {"name": "QA belt", "roles": ["coder", "reviewer"]})
        self.assertEqual(p["slug"], "qa-belt")
        self.assertTrue(presets.exists(self.paths, "qa-belt"))

    def test_create_suffixes_a_taken_slug(self):
        body = {"name": "QA belt", "roles": ["coder", "reviewer"]}
        presets.create(self.fx.root, self.paths, body)
        self.assertEqual(presets.create(self.fx.root, self.paths, body)["slug"], "qa-belt-2")

    def test_save_keeps_the_slug_when_the_name_changes(self):
        presets.save(self.fx.root, self.paths, "solo-coder", {"name": "Just the coder"})
        self.assertTrue(presets.exists(self.paths, "solo-coder"))
        self.assertEqual(presets.load(self.paths, "solo-coder")["name"], "Just the coder")

    def test_save_validates(self):
        with self.assertRaises(presets.PresetError):
            presets.save(self.fx.root, self.paths, "solo-coder", {"roles": []})

    def test_load_unknown_slug_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            presets.load(self.paths, "nope")

    def test_load_all_skips_an_unparseable_file(self):
        with open(presets.path(self.paths, "broken"), "w") as f:
            f.write("{not json")
        slugs = [p["slug"] for p in presets.load_all(self.paths)]
        self.assertNotIn("broken", slugs)
        self.assertIn("review-belt", slugs)

    def test_delete_removes_the_file(self):
        presets.delete(self.paths, self.cfg(), "solo-coder")
        self.assertFalse(presets.exists(self.paths, "solo-coder"))

    def test_delete_refuses_the_active_workflow(self):
        with self.assertRaises(RuntimeError) as e:
            presets.delete(self.paths, self.cfg(), "review-belt")
        self.assertIn("is active", str(e.exception))

    def test_delete_refuses_the_last_workflow(self):
        # A shape no seed matches, so nothing is active and the active guard
        # cannot mask the last-workflow guard.
        write_conf(self.fx.root,
                   "role coder composer-2.5\nrole reviewer gpt-5\nrole specifier composer-2.5\n"
                   "gate none")
        for s in ("solo-coder", "spec-no-gate", "spec-then-build"):
            presets.delete(self.paths, self.cfg(), s)
        with self.assertRaises(RuntimeError) as e:
            presets.delete(self.paths, self.cfg(), "review-belt")
        self.assertIn("only workflow", str(e.exception))


class Resolve(Base):
    def test_matching_preset_reads_as_active(self):
        self.assertEqual(presets.resolve(self.paths, self.cfg()), ("review-belt", "active"))

    def test_hand_edited_conf_reads_as_modified(self):
        util_active = os.path.join(self.fx.root, ".conveyor", "active")
        os.makedirs(os.path.dirname(util_active), exist_ok=True)
        with open(util_active, "w") as f:
            f.write("review-belt\n")
        write_conf(self.fx.root,
                   "role coder composer-2.5\nrole tester composer-2.5\nrole reviewer gpt-5\n"
                   "gate none")
        os.makedirs(os.path.join(self.fx.root, "roles"), exist_ok=True)
        slug, status = presets.resolve(self.paths, self.cfg())
        self.assertEqual((slug, status), ("review-belt", "modified"))

    def test_unknown_shape_with_no_marker_reads_as_custom(self):
        write_conf(self.fx.root,
                   "role coder composer-2.5\nrole reviewer gpt-5\nrole specifier composer-2.5\n"
                   "gate none")
        self.assertEqual(presets.resolve(self.paths, self.cfg()), (None, "custom"))

    def test_resolve_self_heals_a_stale_marker(self):
        """Crash between activate()'s two writes: the shape wins over the marker."""
        with open(self.paths.active, "w") as f:
            f.write("spec-then-build\n")
        self.assertEqual(presets.resolve(self.paths, self.cfg()), ("review-belt", "active"))

    def test_gate_distinguishes_two_presets_with_the_same_roles(self):
        presets.activate(self.fx.root, self.paths, self.cfg(), "spec-no-gate")
        self.assertEqual(presets.resolve(self.paths, self.cfg()), ("spec-no-gate", "active"))
        presets.activate(self.fx.root, self.paths, self.cfg(), "spec-then-build")
        self.assertEqual(presets.resolve(self.paths, self.cfg()), ("spec-then-build", "active"))


class Activate(Base):
    def test_activate_rewrites_the_pipeline_and_the_marker(self):
        presets.activate(self.fx.root, self.paths, self.cfg(), "spec-then-build")
        self.assertEqual(self.cfg().names(), ["specifier", "coder", "reviewer"])
        self.assertEqual(read(self.paths.active), "spec-then-build\n")

    def test_activate_writes_the_preset_gate(self):
        presets.activate(self.fx.root, self.paths, self.cfg(), "spec-then-build")
        self.assertIn("gate specifier", read(os.path.join(self.fx.root, "conveyor.conf")))
        self.assertEqual(self.cfg().gate_role(), "specifier")

    def test_activate_of_a_three_role_preset_with_no_gate_writes_gate_none(self):
        """The Stage 2 inference must not resurrect a gate the preset says is off."""
        presets.activate(self.fx.root, self.paths, self.cfg(), "spec-no-gate")
        text = read(os.path.join(self.fx.root, "conveyor.conf"))
        self.assertIn("gate none", text)
        self.assertNotIn("gate specifier", text)
        self.assertIsNone(self.cfg().gate_role())

    def test_activate_carries_over_model_and_ceilings(self):
        write_conf(self.fx.root,
                   "role coder gpt-5 max_retries=9 max_minutes=7 max_attempts=5\n"
                   "role reviewer gpt-5")
        presets.activate(self.fx.root, self.paths, self.cfg(), "spec-then-build")
        cfg = self.cfg()
        coder = cfg.role("coder")
        self.assertEqual((coder.model, coder.max_retries, coder.max_minutes,
                          coder.max_attempts), ("gpt-5", 9, 7, 5))
        spec = cfg.role("specifier")
        self.assertEqual(spec.model, "gpt-5", "a new role takes the first role's model")
        self.assertEqual((spec.max_retries, spec.max_minutes, spec.max_attempts), (3, 60, 2))

    def test_activate_carries_over_extra_role_args(self):
        write_conf(self.fx.root, "role coder composer-2.5 --flag\nrole reviewer gpt-5")
        presets.activate(self.fx.root, self.paths, self.cfg(), "spec-then-build")
        self.assertIn("--flag", read(os.path.join(self.fx.root, "conveyor.conf")))

    def test_activate_preserves_global_and_inbox_sections(self):
        with open(os.path.join(self.fx.root, "conveyor.conf"), "w") as f:
            f.write("role coder composer-2.5\nrole reviewer gpt-5\n"
                    "[global]\npoll_seconds = 0.2\n"
                    "[inbox]\njira_base = https://example.atlassian.net\n")
        presets.activate(self.fx.root, self.paths, self.cfg(), "solo-coder")
        text = read(os.path.join(self.fx.root, "conveyor.conf"))
        self.assertIn("poll_seconds = 0.2", text)
        self.assertIn("jira_base = https://example.atlassian.net", text)

    def test_activate_reports_dropped_roles(self):
        r = presets.activate(self.fx.root, self.paths, self.cfg(), "solo-coder")
        self.assertEqual(r["dropped"], ["reviewer"])

    def test_activate_refuses_while_a_loop_is_running(self):
        before = read(os.path.join(self.fx.root, "conveyor.conf"))
        lock = self.paths.role("coder").loop_lock
        os.makedirs(lock, exist_ok=True)
        with open(os.path.join(lock, "pid"), "w") as f:
            f.write(f"{os.getpid()}\n")
        with self.assertRaises(RuntimeError) as e:
            presets.activate(self.fx.root, self.paths, self.cfg(), "spec-then-build")
        self.assertIn("loops are running (coder)", str(e.exception))
        self.assertEqual(read(os.path.join(self.fx.root, "conveyor.conf")), before)

    def test_activate_unknown_slug_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            presets.activate(self.fx.root, self.paths, self.cfg(), "nope")


if __name__ == "__main__":
    unittest.main()
