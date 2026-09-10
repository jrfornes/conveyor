"""`[global] worktree_setup`: a role's tree is usable the moment it exists.

Protocol §2.3 (setup.stamp), §6.3 (post-merge setup), §6.10 (setup-failed).
The plan filed these mid-pipeline cases under test_pipeline.py; they live here
instead, beside the recorder fixture they all need."""
import os
import time
import unittest

from harness import CODER_OK, REVIEWER_PASS, ConveyorTest, layout, read

# Appends one `role|reason|commit|root|worktree|cwd` line per invocation, then
# exits with the code in <out>.fail-<role> (default 0). One opaque command that
# branches on $CONVEYOR_ROLE -- exactly what an operator's hook does.
RECORDER = '''import os, sys
keys = ("CONVEYOR_ROLE", "CONVEYOR_REASON", "CONVEYOR_COMMIT", "CONVEYOR_ROOT",
        "CONVEYOR_WORKTREE")
role = os.environ.get("CONVEYOR_ROLE", "")
with open(sys.argv[1], "a") as f:
    f.write("|".join([os.environ.get(k, "") for k in keys] + [os.getcwd()]) + "\\n")
fail = sys.argv[1] + ".fail-" + role
sys.exit(int(read.strip()) if os.path.isfile(fail) and (read := open(fail).read()).strip() else 0)
'''

# A command whose own child outlives a naive `timeout=`: the shell gets a
# python that spawns a heartbeat writer and then sleeps. Killing only the
# shell would leave the heartbeat running -- which is the bug run_bounded exists
# to not have.
HEARTBEAT = '''import sys, time
while True:
    with open(sys.argv[1], "a") as f:
        f.write("x")
    time.sleep(0.05)
'''
SPAWNER = '''import subprocess, sys, time
subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])
time.sleep(60)
'''

CODER_TOUCHES_LOCK = ('write lock.txt "v2"\n'
                      'commit "Implement $TASK"\n'
                      'draft reviewer $TASK ready\nhandoff\nhandoff\n')


class SetupFixture(ConveyorTest):
    """A repo with a committed lock.txt and a recorder wired as worktree_setup."""

    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.fx.tmp, "setup-runs.txt")
        self.recorder = self.write_script("recorder.py", RECORDER)
        self.write_lock("v1", commit="Add lock.txt")

    # --- fixture helpers ---------------------------------------------------
    def write_script(self, name, text):
        path = os.path.join(self.fx.tmp, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def write_lock(self, text, commit=None, cwd=None):
        with open(os.path.join(cwd or self.fx.root, "lock.txt"), "w") as f:
            f.write(text + "\n")
        if commit:
            self.fx.git("add", "-A", cwd=cwd)
            self.fx.git("commit", "-q", "-m", commit, cwd=cwd)

    def enable(self, command=None, paths="lock.txt", timeout=None):
        lines = [f"worktree_setup = {command or self.record_cmd()}"]
        if paths is not None:
            lines.append(f"worktree_setup_paths = {paths}")
        if timeout is not None:
            lines.append(f"worktree_setup_timeout = {timeout}")
        self.fx.set_global("\n".join(lines))

    def record_cmd(self, extra=""):
        """The recorder reads argv[1] only; `extra` is a spare word that changes
        the command string (and so the stamp) without changing what it does."""
        return f"python3 {self.recorder} {self.out}{extra}"

    def fail_for(self, role, code=1):
        with open(f"{self.out}.fail-{role}", "w") as f:
            f.write(str(code))

    def runs(self):
        """[{role, reason, commit, root, worktree, cwd}] in invocation order."""
        if not os.path.isfile(self.out):
            return []
        keys = ("role", "reason", "commit", "root", "worktree", "cwd")
        return [dict(zip(keys, line.split("|")))
                for line in read(self.out).splitlines() if line.strip()]

    def stamp_of(self, role):
        p = os.path.join(self.fx.paths.role(role).base, "setup.stamp")
        return read(p).strip() if os.path.isfile(p) else ""

    def setup_log(self, role):
        p = os.path.join(self.fx.paths.logs, role, "setup.log")
        return read(p) if os.path.isfile(p) else ""


class NotConfigured(SetupFixture):
    def test_absent_worktree_setup_changes_nothing(self):
        """1. The feature off means the run path is what it was."""
        r = self.fx.start()
        self.fx.conveyor("stop")
        self.assertNotIn("setup", r.stdout)
        self.assertEqual(self.runs(), [])
        for role in ("coder", "reviewer"):
            self.assertEqual(self.stamp_of(role), "")
            self.assertFalse(os.path.isfile(
                os.path.join(self.fx.paths.logs, role, "setup.log")))


class StartRunsSetup(SetupFixture):
    def test_runs_once_per_role_with_the_documented_env(self):
        """2. cwd is the worktree; the hook is told who it is and why it ran."""
        self.enable()
        r = self.fx.start()
        self.fx.conveyor("stop")
        runs = self.runs()
        self.assertEqual([x["role"] for x in runs], ["coder", "reviewer"])
        for x in runs:
            self.assertEqual(x["reason"], "create")
            self.assertEqual(x["commit"], "")      # empty at conveyor start
            self.assertEqual(x["root"], self.fx.paths.root)
            self.assertEqual(os.path.realpath(x["cwd"]),
                             os.path.realpath(self.fx.paths.worktree(x["role"])))
            self.assertEqual(os.path.realpath(x["worktree"]),
                             os.path.realpath(self.fx.paths.worktree(x["role"])))
        self.assertIn("coder: setup (create) … ok,", r.stdout)
        self.assertIn("reviewer: setup (create) … ok,", r.stdout)
        for role in ("coder", "reviewer"):
            self.assertRegex(self.stamp_of(role), r"^[0-9a-f]{64}$")
            self.assertEqual(self.setup_log(role).splitlines()[0], "exit: 0")

    def test_a_matching_stamp_is_silence(self):
        """3. Second start with nothing changed: no run, and no line about it."""
        self.enable()
        self.fx.start()
        self.fx.conveyor("stop")
        stamps = {r: self.stamp_of(r) for r in ("coder", "reviewer")}
        r = self.fx.start()
        self.fx.conveyor("stop")
        self.assertEqual(len(self.runs()), 2)
        self.assertNotIn("setup", r.stdout)
        self.assertEqual(stamps, {r: self.stamp_of(r) for r in ("coder", "reviewer")})

    def test_a_watched_path_moving_on_the_branch_re_runs_it(self):
        """4. Content, not mtime: the blob at the role branch's HEAD decides."""
        self.enable()
        self.fx.start()
        self.fx.conveyor("stop")
        wt = self.fx.paths.worktree("coder")
        self.write_lock("v2", commit="Bump the lockfile", cwd=wt)
        r = self.fx.start()
        self.fx.conveyor("stop")
        runs = self.runs()
        self.assertEqual([x["role"] for x in runs], ["coder", "reviewer", "coder"])
        self.assertEqual(runs[-1]["reason"], "changed")
        self.assertIn("coder: setup (changed) … ok,", r.stdout)
        self.assertNotIn("reviewer: setup", r.stdout)   # its tree did not move

    def test_touching_a_watched_file_without_changing_it_does_not_re_run(self):
        """3/4 corollary: mtime is not evidence."""
        self.enable()
        self.fx.start()
        self.fx.conveyor("stop")
        os.utime(os.path.join(self.fx.paths.worktree("coder"), "lock.txt"), None)
        self.fx.start()
        self.fx.conveyor("stop")
        self.assertEqual(len(self.runs()), 2)

    def test_changing_the_command_re_runs_everywhere(self):
        """5. The command is in the hash on purpose."""
        self.enable()
        self.fx.start()
        self.fx.conveyor("stop")
        self.fx.set_global(f"worktree_setup = {self.record_cmd(extra=' v2')}")
        r = self.fx.start()
        self.fx.conveyor("stop")
        self.assertEqual([x["role"] for x in self.runs()],
                         ["coder", "reviewer", "coder", "reviewer"])
        self.assertIn("coder: setup (changed) … ok,", r.stdout)

    def test_a_path_absent_at_head_hashes_as_a_dash(self):
        """6. A missing watched path is not a crash; adding it is a change."""
        self.enable(paths="ghost.txt lock.txt")
        self.fx.start()
        self.fx.conveyor("stop")
        self.assertEqual(len(self.runs()), 2)
        wt = self.fx.paths.worktree("reviewer")
        with open(os.path.join(wt, "ghost.txt"), "w") as f:
            f.write("now here\n")
        self.fx.git("add", "-A", cwd=wt)
        self.fx.git("commit", "-q", "-m", "Add ghost.txt", cwd=wt)
        self.fx.start()
        self.fx.conveyor("stop")
        self.assertEqual([x["role"] for x in self.runs()],
                         ["coder", "reviewer", "reviewer"])
        self.assertEqual(self.runs()[-1]["reason"], "changed")


class StartRefuses(SetupFixture):
    def test_failure_stops_the_start_before_any_loop(self):
        """7. A half-installed tree never gets an agent."""
        self.enable()
        self.fail_for("coder", 3)
        r = self.fx.conveyor("start", check=False)
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("conveyor start: worktree setup failed for coder (exit 3)", out)
        self.assertIn(os.path.join(".conveyor", "logs", "coder", "setup.log"), out)
        self.assertEqual(self.stamp_of("coder"), "")       # a failure is not done
        self.assertEqual([x["role"] for x in self.runs()], ["coder"])  # reviewer untouched
        self.assertEqual(self.setup_log("coder").splitlines()[0], "exit: 3")
        for role in ("coder", "reviewer"):
            self.assertEqual(layout.loop_pid(self.fx.paths, role), 0)
            self.assertFalse(os.path.isdir(self.fx.paths.role(role).loop_lock))

    def test_no_setup_skips_and_leaves_the_stamp_unwritten(self):
        """8. The escape hatch does not lie about the tree's state."""
        self.enable()
        r = self.fx.conveyor("start", "--no-setup")
        self.fx.conveyor("stop")
        self.assertEqual(self.runs(), [])
        self.assertNotIn("setup", r.stdout)
        self.assertEqual(self.stamp_of("coder"), "")
        self.fx.start()
        self.fx.conveyor("stop")
        self.assertEqual([x["reason"] for x in self.runs()], ["create", "create"])

    def test_timeout_kills_the_command_and_its_children(self):
        """11. shell=True in its own process group, TERM then KILL."""
        beat = os.path.join(self.fx.tmp, "beat.txt")
        hb = self.write_script("heartbeat.py", HEARTBEAT)
        sp = self.write_script("spawner.py", SPAWNER)
        self.enable(command=f"python3 {sp} {hb} {beat}", timeout=1)
        r = self.fx.conveyor("start", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("worktree setup failed for coder (timed out after 1s)",
                      r.stdout + r.stderr)
        self.assertEqual(self.setup_log("coder").splitlines()[0], "exit: timeout")
        self.assertEqual(self.stamp_of("coder"), "")
        # The grandchild died with the group: its heartbeat file stops growing.
        size = os.path.getsize(beat)
        time.sleep(1)
        self.assertEqual(os.path.getsize(beat), size)

    def test_a_dirty_tree_warns_and_does_not_refuse(self):
        """12. handoff.sh would refuse E_DIRTY; say so rather than guess a .gitignore."""
        self.enable(command="mkdir -p junk && touch junk/a junk/b junk/c "
                            "junk/d junk/e junk/f junk/g")
        r = self.fx.start()
        self.fx.conveyor("stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("is dirty after setup", r.stdout)
        self.assertIn("(7 paths)", r.stdout)
        self.assertIn("E_DIRTY", r.stdout)
        warning = [l for l in r.stdout.splitlines() if "dirty after setup" in l][0]
        self.assertEqual(warning.count("junk/"), 5)   # at most five, then an ellipsis
        self.assertIn("…", warning)
        self.assertNotEqual(self.stamp_of("coder"), "")   # the command did exit 0


class LiveLoop(SetupFixture):
    def test_a_running_loop_is_warned_about_never_installed_into(self):
        """13. Installing into a tree an agent is working in corrupts the run."""
        self.enable()
        self.fx.start()                       # loops are up and stay up
        before = self.stamp_of("coder")
        self.fx.set_global(f"worktree_setup = {self.record_cmd(extra=' v2')}")
        r = self.fx.conveyor("start")
        self.fx.conveyor("stop")
        self.assertIn("warning: coder's loop is running (pid ", r.stdout)
        self.assertIn("Stop the loop and re-run conveyor start", r.stdout)
        self.assertEqual(self.stamp_of("coder"), before)
        self.assertEqual([x["role"] for x in self.runs()], ["coder", "reviewer"])


class SetupCommand(SetupFixture):
    def test_force_runs_despite_a_matching_stamp(self):
        """9. Convenience over documenting `rm .conveyor/roles/coder/setup.stamp`."""
        self.enable()
        self.fx.start()
        self.fx.conveyor("stop")
        r = self.fx.conveyor("setup")           # nothing changed: silence
        self.assertNotIn("setup (", r.stdout)
        self.assertEqual(len(self.runs()), 2)
        r = self.fx.conveyor("setup", "--role", "coder", "--force")
        self.assertEqual([x["role"] for x in self.runs()], ["coder", "reviewer", "coder"])
        self.assertIn("coder: setup (create) … ok,", r.stdout)
        self.assertNotEqual(self.stamp_of("coder"), "")

    def test_refuses_when_the_feature_is_off(self):
        self.fx.start()
        self.fx.conveyor("stop")
        r = self.fx.conveyor("setup", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no `worktree_setup` under [global]", r.stdout + r.stderr)


class BadConfig(SetupFixture):
    def test_paths_without_a_command_is_a_config_error(self):
        """10. It means the operator expected something to run."""
        from conveyor import config
        self.fx.set_global("worktree_setup_paths = lock.txt")
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.fx.root)
        msg = str(cm.exception)
        self.assertIn("worktree_setup_paths is set but worktree_setup is not", msg)
        self.assertIn("repair: add `worktree_setup = <shell command>`", msg)

    def test_a_non_integer_timeout_is_a_config_error(self):
        from conveyor import config
        self.enable(timeout="soon")
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.fx.root)
        self.assertIn("worktree_setup_timeout must be a non-negative number of seconds",
                      str(cm.exception))


class MidPipeline(SetupFixture):
    """The half that bites: the reviewer merges a lockfile its tree predates."""

    def start_belt(self, coder=CODER_TOUCHES_LOCK, reviewer=REVIEWER_PASS):
        self.enable()
        self.fx.script("coder", coder)
        self.fx.script("reviewer", reviewer)
        self.fx.start()
        self.fx.conveyor("stop")

    def test_the_reviewer_sets_up_after_merging_a_lockfile_change(self):
        """14. Right after merge.sh, before the ceilings, before the agent."""
        self.start_belt()
        self.fx.task("add-login")
        self.fx.loop("coder")
        self.fx.loop("reviewer")
        runs = self.runs()
        self.assertEqual([x["role"] for x in runs], ["coder", "reviewer", "reviewer"])
        last = runs[-1]
        self.assertEqual(last["reason"], "changed")
        self.assertRegex(last["commit"], r"^[0-9a-f]{10}$")
        # the commit it was handed is the one the reviewer just merged
        h = self.fx.read_handoff(os.path.join(
            self.fx.paths.role("reviewer").completed,
            layout.handoffs(self.fx.paths.role("reviewer").completed)[0]))[0]
        self.assertEqual(last["commit"], h["commit"])
        self.assertEqual(self.fx.board()["add-login"]["lane"], "done")

    def test_a_merge_that_touches_no_watched_path_does_not_re_run(self):
        """17. The stamp is the authority; an unrelated commit is not a change."""
        self.start_belt(coder=CODER_OK)
        self.fx.task("demo")
        self.fx.drive()
        self.assertEqual([x["role"] for x in self.runs()], ["coder", "reviewer"])
        self.assertEqual(self.fx.board()["demo"]["lane"], "done")

    def test_setup_failure_parks_setup_failed_without_running_an_agent(self):
        """15. A stale tree never reaches an agent: it would review the environment."""
        self.start_belt()
        self.fx.task("add-login")
        self.fx.loop("coder")
        self.fail_for("reviewer", 1)
        r = self.fx.loop("reviewer")
        self.assertEqual(r.returncode, 0, r.stderr)   # parked, not crashed
        reason = self.fx.parked_reason("add-login")
        self.assertEqual(reason[0], "setup-failed")
        self.assertIn("worktree setup exited 1 after merging", reason[1])
        self.assertIn("conveyor resume add-login", reason[1])
        self.assertEqual(self.fx.board()["add-login"]["lane"], "needs-human")
        self.assertTrue(os.path.isfile(os.path.join(
            self.fx.paths.needs_human, "add-login", "item.handoff")))
        self.assertEqual([f for f in os.listdir(os.path.join(self.fx.paths.logs, "reviewer"))
                          if f.endswith(".jsonl") and f != "smoke.jsonl"], [])
        self.assertEqual(self.setup_log("reviewer").splitlines()[0], "exit: 1")

    def test_resume_after_setup_failed_behaves_like_every_other_reason(self):
        """16. Attempt reset to 1, counters preserved."""
        self.start_belt()
        self.fx.task("add-login")
        self.fx.loop("coder")
        self.fail_for("reviewer", 1)
        self.fx.loop("reviewer")
        before = self.fx.board()["add-login"]
        os.remove(f"{self.out}.fail-reviewer")
        self.fx.conveyor("resume", "add-login")
        new = layout.handoffs(self.fx.paths.role("reviewer").new)
        self.assertEqual(len(new), 1)
        h = self.fx.read_handoff(os.path.join(self.fx.paths.role("reviewer").new, new[0]))[0]
        self.assertEqual(h["attempt"], "1")
        after = self.fx.board()["add-login"]
        self.assertEqual(after["lane"], "reviewer")
        for k in ("task_id", "audit_count", "retry_count"):
            self.assertEqual(after[k], before[k])
        self.fx.drive()
        self.assertEqual(self.fx.board()["add-login"]["lane"], "done")


if __name__ == "__main__":
    unittest.main()
