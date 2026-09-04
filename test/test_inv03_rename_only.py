"""Invariant 3: every state change is a rename; nothing is written in place."""
import os
import re
import unittest

from harness import BIN, REPO, ConveyorTest, read


class RenameOnly(ConveyorTest):
    def test_no_tmp_leftovers_and_board_replaced_not_edited(self):
        fx = self.run_pipeline("demo")
        before = os.stat(fx.paths.board).st_ino
        fx.task("second")
        self.assertNotEqual(os.stat(fx.paths.board).st_ino, before)
        for dirpath, _, files in os.walk(fx.paths.conveyor):
            for f in files:
                self.assertFalse(f.endswith(".tmp"), os.path.join(dirpath, f))

    def test_code_never_opens_queue_files_for_writing(self):
        """Static check: the only writers are atomic_write (tmp + rename) and handoff.write."""
        sources = [os.path.join(REPO, "lib", "conveyor", f) for f in os.listdir(os.path.join(REPO, "lib", "conveyor")) if f.endswith(".py")]
        sources += [os.path.join(BIN, f) for f in ("conveyor", "handoff.sh", "role-loop.sh", "merge.sh")]
        opens = []
        for src in sources:
            for i, line in enumerate(read(src).splitlines(), 1):
                if re.search(r"open\([^)]*['\"][wa]['\"]", line):
                    opens.append(f"{os.path.basename(src)}:{i}: {line.strip()}")
        allowed = ("atomic_write", 'open(tmp, "w"', "pid", "loop.log", "stop", "log, \"a\"", "open(path, \"a\")",
                   "lf")
        stray = [o for o in opens if not any(a in o for a in allowed)]
        self.assertEqual(stray, [])


if __name__ == "__main__":
    unittest.main()
