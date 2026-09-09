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

    def test_setup_stamp_is_replaced_by_rename_never_appended(self):
        """setup.stamp is per-role queue state: written like seq, never in place."""
        import test_worktree_setup as ws

        fx = self.fx
        recorder = os.path.join(fx.tmp, "recorder.py")
        out = os.path.join(fx.tmp, "setup-runs.txt")
        with open(recorder, "w") as f:
            f.write(ws.RECORDER)
        with open(os.path.join(fx.root, "lock.txt"), "w") as f:
            f.write("v1\n")
        fx.git("add", "-A")
        fx.git("commit", "-q", "-m", "Add lock.txt")
        fx.set_global(f"worktree_setup = python3 {recorder} {out}\n"
                      "worktree_setup_paths = lock.txt")
        fx.start()
        fx.conveyor("stop")
        stamp = os.path.join(fx.paths.role("coder").base, "setup.stamp")
        first = read(stamp)
        self.assertRegex(first, r"^[0-9a-f]{64}\n$")
        with open(os.path.join(fx.paths.worktree("coder"), "lock.txt"), "w") as f:
            f.write("v2\n")
        fx.git("add", "-A", cwd=fx.paths.worktree("coder"))
        fx.git("commit", "-q", "-m", "Bump the lockfile", cwd=fx.paths.worktree("coder"))
        fx.start()
        fx.conveyor("stop")
        # Replaced wholesale, not appended to: still exactly one line, a new one.
        self.assertRegex(read(stamp), r"^[0-9a-f]{64}\n$")
        self.assertNotEqual(read(stamp), first)
        self.assertFalse(os.path.exists(stamp + ".tmp"))

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
                   "lf", "open(marker",  # crash_point: test-only marker file, not a queue file
                   'open(gi, "a")')  # conveyor init: appends to the target repo's .gitignore, not a queue file
        stray = [o for o in opens if not any(a in o for a in allowed)]
        self.assertEqual(stray, [])


if __name__ == "__main__":
    unittest.main()
