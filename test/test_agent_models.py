"""Parser and fallback for cursor-agent --list-models / models."""
import os
import stat
import sys
import tempfile
import textwrap
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "lib"))

from conveyor.agent import AgentError, list_models, parse_models  # noqa: E402


class ParseModels(unittest.TestCase):
    def test_skips_header_and_blanks(self):
        text = """
Available models

composer-2.5 - Composer 2.5
gpt-5.3-codex-high - Codex 5.3 High
"""
        self.assertEqual(parse_models(text), [
            {"id": "composer-2.5", "label": "Composer 2.5"},
            {"id": "gpt-5.3-codex-high", "label": "Codex 5.3 High"},
        ])

    def test_id_only_lines(self):
        self.assertEqual(parse_models("composer-2.5\ngpt-5\n"), [
            {"id": "composer-2.5", "label": "composer-2.5"},
            {"id": "gpt-5", "label": "gpt-5"},
        ])

    def test_header_alone_is_empty(self):
        self.assertEqual(parse_models("Available models\n\n"), [])


class ListModels(unittest.TestCase):
    def _script(self, body):
        fd, path = tempfile.mkstemp(prefix="fake-models-")
        os.close(fd)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        self.addCleanup(lambda: os.remove(path))
        return path

    def test_prefers_list_models(self):
        path = self._script(textwrap.dedent("""\
            #!/usr/bin/env python3
            import sys
            if sys.argv[1:] == ["--list-models"]:
                print("Available models")
                print()
                print("composer-2.5 - Composer 2.5")
                raise SystemExit(0)
            raise SystemExit("should not fall back")
        """))
        self.assertEqual(list_models(path), [
            {"id": "composer-2.5", "label": "Composer 2.5"},
        ])

    def test_falls_back_to_models(self):
        path = self._script(textwrap.dedent("""\
            #!/usr/bin/env python3
            import sys
            if sys.argv[1:] == ["--list-models"]:
                raise SystemExit(2)
            if sys.argv[1:] == ["models"]:
                print("composer-2.5")
                print("gpt-5")
                raise SystemExit(0)
            raise SystemExit(1)
        """))
        self.assertEqual(list_models(path), [
            {"id": "composer-2.5", "label": "composer-2.5"},
            {"id": "gpt-5", "label": "gpt-5"},
        ])

    def test_both_fail(self):
        path = self._script(textwrap.dedent("""\
            #!/usr/bin/env python3
            raise SystemExit(1)
        """))
        with self.assertRaises(AgentError):
            list_models(path)


if __name__ == "__main__":
    unittest.main()
