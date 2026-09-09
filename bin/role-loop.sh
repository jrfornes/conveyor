#!/usr/bin/env python3
"""Per-role loop (protocol §6). Identity from CONVEYOR_ROLE / CONVEYOR_WORKTREE.
`--once`: recover or process at most one item, then exit."""
import json
import os
import re
import signal
import subprocess
import sys
import time

if sys.version_info < (3, 10):
    print(f"conveyor requires Python 3.10+ (found {sys.version.split()[0]} at {sys.executable})",
          file=sys.stderr)
    sys.exit(1)

BIN = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(BIN, "..", "lib"))
from conveyor import (agent as agentlib, board, config, handoff, inbox,  # noqa: E402
                      layout, queue, setup as setuplib, usage, util)

SESSION_RE = re.compile(r'"session_?[iI]d"\s*:\s*"([^"]+)"')
VALIDATOR_RE = re.compile(r'(?:E_[A-Z_]+|AUDIT_REQUIRED): [^"\\\n]*')


def stamped(line):
    """One run-log line with the time it was read as its first key (protocol §6.9).

    A JSON object gains `at` (never overwriting one the agent supplied); anything
    else -- agent stderr, a stray traceback -- is wrapped so the file stays JSONL.
    `at` goes first so the rest of the object keeps the agent's key order."""
    raw = line.rstrip("\n")
    try:
        ev = json.loads(raw)
        if not isinstance(ev, dict):
            raise ValueError
    except ValueError:
        return json.dumps({"at": util.now(), "type": "output", "text": raw}) + "\n"
    if "at" in ev:
        return raw + "\n"
    return json.dumps({"at": util.now(), **ev}) + "\n"


def usage_text(scanned, elapsed):
    """One line of spend for the run log. `-` where the agent reported nothing:
    an absent number is never printed as 0 (plan decisions 3 and 4)."""
    return (f"in {usage.human(scanned['input'])}, out {usage.human(scanned['output'])}, "
            f"{int(elapsed) // 60}m{int(elapsed) % 60:02d}s ({scanned['source']})")


def stamp_stream(src, dst):
    """`--stamp`: copy stdin to stdout, dating each line. Own process so the agent's
    output survives the loop; readline (not iteration) so `tail -f` stays live."""
    for line in iter(src.readline, ""):
        if line.strip():
            dst.write(stamped(line))
            dst.flush()


class DatedStdout:
    """stdout wrapper prefixing every line with a UTC timestamp, so
    .conveyor/logs/<role>/loop.log reads as a timeline (protocol §6.11)."""

    def __init__(self, stream):
        self.stream = stream
        self.fresh = True

    def write(self, s):
        for part in s.splitlines(keepends=True):
            if self.fresh:
                self.stream.write(f"{util.now()}  ")
            self.stream.write(part)
            self.fresh = part.endswith("\n")
        self.stream.flush()
        return len(s)

    def flush(self):
        self.stream.flush()


class Loop:
    def __init__(self, once):
        self.once = once
        self.role = os.environ["CONVEYOR_ROLE"]
        self.wt = os.environ["CONVEYOR_WORKTREE"]
        self.paths = layout.Paths(layout.find_root())
        self.cfg = config.load(self.paths.root)
        self.me = self.cfg.role(self.role)
        self.rp = self.paths.role(self.role)
        self.agent = None
        self.agent_pgid = None
        os.environ["CONVEYOR_ROOT"] = self.paths.root
        os.environ.setdefault("CONVEYOR_AGENT_BIN", self.cfg.agent_bin)
        os.environ["PATH"] = BIN + os.pathsep + os.environ.get("PATH", "")

    # --- lifecycle -------------------------------------------------------
    def acquire(self):
        for _ in range(2):
            try:
                os.mkdir(self.rp.loop_lock)
                with open(os.path.join(self.rp.loop_lock, "pid"), "w") as f:
                    f.write(str(os.getpid()))
                return
            except FileExistsError:
                try:
                    pid = int(util.read_text(os.path.join(self.rp.loop_lock, "pid")))
                except (OSError, ValueError):
                    pid = 0
                if pid and util._pid_alive(pid):
                    util.die(f"loop already running, pid {pid}")
                subprocess.run(["rm", "-rf", self.rp.loop_lock])
        util.die("could not acquire loop lock")

    def release(self):
        subprocess.run(["rm", "-rf", self.rp.loop_lock])

    def stop_requested(self):
        if os.path.exists(self.rp.stop):
            os.remove(self.rp.stop)
            return True
        return False

    def on_term(self, *_):
        # No agent.wait() here: the handler may run inside Popen.wait(), which holds a lock.
        # TERM goes to the agent's process group, not just the leader: `stop --now` must
        # stop the tree, or children it spawned outlive the loop (protocol §6.7).
        if self.agent_pgid:
            try:
                os.killpg(self.agent_pgid, signal.SIGTERM)
            except OSError:
                pass  # the group is already gone; that is the success case
        raise SystemExit(4)

    def run(self):
        items = layout.handoffs(self.rp.in_process)
        if len(items) > 1:
            print(f"ambiguous: {len(items)} items in process", flush=True)
            sys.exit(3)
        if items:
            self.process(items[0])
        queue.sweep(self.paths, self.cfg, self.role)
        if self.once and items:
            return
        while True:
            if self.stop_requested():
                return
            queue.sweep(self.paths, self.cfg, self.role)  # picks up resumed done-items
            new = layout.handoffs(self.rp.new)
            if not new:
                if self.once:
                    return
                time.sleep(self.cfg.poll_seconds)
                continue
            queue.dequeue(self.paths, self.role, new[0])
            util.crash_point("after-dequeue")
            self.process(new[0])
            queue.sweep(self.paths, self.cfg, self.role)
            if self.once:
                return

    # --- one item ----------------------------------------------------------
    def process(self, f):
        path = os.path.join(self.rp.in_process, f)
        try:
            h, _ = handoff.read(path)
        except handoff.ParseError as e:
            return queue.fail(self.rp, path, f"parse-error: {e}")
        if "dequeued_at" not in h:
            h = handoff.stamp(path, dequeued_at=util.now(), attempt=1)
        task = h["task"]
        print(f"{task}: processing {h['id']} from {h['from']} ({h['verdict']}, {h['commit']})", flush=True)
        park = lambda reason, detail: queue.park(self.paths, path, task, reason, detail)  # noqa: E731
        before = setuplib.blobs(self.wt, self.cfg) if setuplib.enabled(self.cfg) else {}
        fail = queue.merge(h["commit"], self.wt, self.role)
        if fail:
            reason, detail = fail
            repair = "" if reason == "merge-conflict" else (
                f"; delete them from .worktrees/{self.role} or untrack them in the commit "
                f"(git rm --cached), then run: conveyor resume {task}")
            return park(reason, f"merging {h['commit']} into conveyor-{self.role} {detail}{repair}")
        util.crash_point("after-merge")
        if not self.worktree_setup(task, park, before, h["commit"]):
            return
        intake = self.role == config.INTAKE_ROLE
        row = None if intake else board.get(self.paths, task)
        if not intake and row is None:
            return queue.fail(self.rp, path, "no-board-row")
        if intake:
            started = h.get("dequeued_at")
        else:
            started = queue.started_at(self.paths, row, h)
            if int(row["retry_count"]) > self.me.max_retries:
                return park("max-retries", f"reviewer sent findings {row['retry_count']} times")
        # Intake is one-shot: `>=` so max_minutes=0 parks on the same pass.
        # Belt roles keep `>` so a just-started task still gets one attempt (M4).
        if started:
            age = util.age_seconds(started)
            over = age >= self.me.max_minutes * 60 if intake else age > self.me.max_minutes * 60
            if over:
                return park("max-minutes", f"task started {started}, exceeds max_minutes {self.me.max_minutes}")
        spent = self.over_tokens(task)
        if spent is not None:
            return park("max-tokens", f"{usage.human(spent)} tokens over max_tokens {self.me.max_tokens}")
        attempt, session, last_err, ran = int(h.get("attempt", 1)), h.get("session"), None, False
        killed = None
        while True:
            n = self.valid_outbox_count()
            if n == 1:
                outcome = "merged" if handoff.read(os.path.join(
                    self.rp.outbox, layout.handoffs(self.rp.outbox)[0]))[0]["to"] == "done" else "forwarded"
                handoff.stamp(path, completed_at=util.now(), outcome=outcome)
                util.crash_point("after-complete-stamp")
                print(f"{task}: {outcome}", flush=True)
                handoff.move(path, self.rp.completed)
                util.crash_point("after-complete")
                return
            if n > 1:
                for i, f in enumerate(layout.handoffs(self.rp.outbox), 1):  # never deliver either
                    os.makedirs(os.path.join(self.paths.needs_human, task), exist_ok=True)
                    handoff.move(os.path.join(self.rp.outbox, f), os.path.join(self.paths.needs_human, task),
                                 f"outbox-{i}.handoff")
                return park("multiple-handoffs", f"{n} handoffs in outbox, kept as outbox-N.handoff; never guessing")
            if killed:
                # The outbox is checked first on purpose: an agent that queued a valid
                # handoff and then wedged has done the work, and the kill must not
                # discard it. An empty outbox means the task's budget is spent, so this
                # is a park, never another attempt -- a retry would spend it twice.
                return park("max-minutes", killed)
            if ran:
                attempt += 1
                handoff.stamp(path, attempt=attempt, **({"session": session} if session else {}))
                if attempt > self.me.max_attempts:
                    return park("max-attempts", f"{attempt - 1} agent runs ended without a valid handoff")
                # Amends §6.6: the budget is also checked between attempts. A task can
                # spend all of it inside one item, and a ceiling that only fires on the
                # next dequeue bounds nothing. No running agent is ever killed for cost.
                spent = self.over_tokens(task)
                if spent is not None:
                    return park("max-tokens", f"{usage.human(spent)} tokens over max_tokens {self.me.max_tokens}")
                if self.stop_requested():
                    sys.exit(0)
            if not os.path.exists(os.path.join(self.wt, ".cursor", "rules", "conveyor-role.mdc")):
                print("E_NO_RULES: .cursor/rules/conveyor-role.mdc missing", flush=True)
                return park("no-rules", "worktree has no .cursor/rules/conveyor-role.mdc; run conveyor start")
            if self.agent_binary() is None:
                b = os.environ["CONVEYOR_AGENT_BIN"]
                print(f"E_NO_AGENT: agent binary {b!r} not found or not executable", flush=True)
                return park("no-agent", f"CONVEYOR_AGENT_BIN {b!r} is not an executable; "
                            "install the agent or fix agent_bin in conveyor.conf, then run conveyor resume")
            prompt = self.build_prompt(path, task, attempt, last_err)
            if prompt is None:
                return park("no-task-file", f"tasks/{task}.md is not at HEAD after merge")
            # Recomputed per attempt: the deadline is what is left of the task's
            # budget, so three attempts cannot each spend the whole of it.
            session, last_err, kill_detail = self.run_agent(
                task, h["id"], attempt, prompt, session, self.deadline_seconds(started))
            util.crash_point("after-agent")
            killed = kill_detail
            ran = True

    def over_tokens(self, task):
        """Tokens billed to this task so far when they exceed this role's ceiling.

        `max_tokens=0` is unbounded, and a total no agent reported (every sidecar
        `source: none`) is unknown, not zero: Conveyor refuses rather than parks a
        task on a number it invented (PRD §5.5). Task-wide across every role and
        attempt, read from the current role's config -- the `max_minutes` rule."""
        if not self.me.max_tokens:
            return None
        spent = usage.task_total(self.paths, task)
        return spent if spent is not None and spent > self.me.max_tokens else None

    def deadline_seconds(self, started):
        """One run's wall-clock budget: what is left of `max_minutes` for this task.

        Floored at 60 s. Without the floor `max_minutes = 0` -- legal, and what the
        M4 ceiling test configures -- would kill every run the instant it started,
        and a just-started task is promised one attempt (§6.6). The floor is the only
        place a run may outlive the task budget.
        """
        forced = os.environ.get("CONVEYOR_DEADLINE_SECONDS")
        if forced:  # test hook, same family as CONVEYOR_CRASH_AT
            return float(forced)
        budget = self.me.max_minutes * 60
        remaining = budget - util.age_seconds(started) if started else budget
        return max(60, remaining)

    def worktree_setup(self, task, park, before, commit):
        """Protocol §6.3: make the merged tree runnable again before the agent sees it.

        The merge that just landed can carry a lockfile the tree's installed
        dependencies predate. Left alone, the role's own gate then fails on a
        missing module rather than on the task -- and for a reviewer that
        becomes a finding against the coder's correct work. Runs before the
        ceiling checks, so a stale tree never reaches an agent, and inside the
        item's max_minutes budget, so an install that eats the whole budget is
        visible as max-minutes rather than exempt from it. False = parked."""
        need, reason = setuplib.needs_run(self.paths, self.wt, self.cfg, self.role)
        if not need:
            return True
        label = setuplib.label(reason, setuplib.diff_names(before, setuplib.blobs(self.wt, self.cfg)))
        print(f"{task}: setup ({label}) …", flush=True)
        r = setuplib.run(self.paths, self.paths.root, self.wt, self.cfg, self.role,
                         reason, commit=commit)
        if not r.ok:
            detail = (f"timed out after {self.cfg.worktree_setup_timeout}s" if r.timed_out
                      else f"exited {r.code}")
            print(f"{task}: setup {detail}", flush=True)
            park("setup-failed", f"worktree setup {detail} after merging {commit}; "
                 f"see logs/{self.role}/setup.log, then run: conveyor resume {task}")
            return False
        print(f"{task}: setup ok, {util.duration(r.seconds)}", flush=True)
        names, total = setuplib.dirty_paths(self.wt)
        if total:
            print(setuplib.format_dirty(self.wt, names, total), flush=True)
        return True

    def valid_outbox_count(self):
        n = 0
        for f in layout.handoffs(self.rp.outbox):
            p = os.path.join(self.rp.outbox, f)
            try:
                hh = handoff.read(p)[0]
                if any(k not in hh for k in queue.REQUIRED):
                    raise handoff.ParseError(0, "missing header")
                n += 1
            except handoff.ParseError as e:
                queue.fail(self.rp, p, f"parse-error: {e}")
        return n

    def build_prompt(self, path, task, attempt, last_err):
        if self.role == config.INTAKE_ROLE:
            return self.build_intake_prompt(path, task, attempt, last_err)
        text = util.git(["show", f"HEAD:tasks/{task}.md"], self.wt, check=False)
        if not text:
            return None
        parts = ["Re-read your role and constitution.",
                 f"Task: {task}\n{text}",
                 "Inbound handoff:\n" + util.read_text(path).rstrip("\n")]
        if attempt > 1:
            parts.append("Your previous attempt ended without a valid handoff. Last validator output:\n"
                         + (last_err or "No handoff.sh call was observed."))
        parts.append("When finished, write ./tmp/handoff.txt and run handoff.sh ./tmp/handoff.txt. "
                     "Do not end your run until it prints OK.")
        return "\n\n".join(parts)

    def build_intake_prompt(self, path, task, attempt, last_err):
        source = inbox.read_file(self.paths, task, "source.md")
        comments = inbox.read_file(self.paths, task, "comments.txt")
        inbound = util.read_text(path)
        improve = "mode: improve" in inbound
        parts = ["Re-read your role and constitution.",
                 f"Task: {task}",
                 f"Mode: {'improve' if improve else 'grade'}",
                 "Original ticket:\n" + (source or "(empty)")]
        if comments.strip():
            parts.append("Operator comments:\n" + comments)
        parts.append("Inbound handoff:\n" + inbound.rstrip("\n"))
        if improve:
            parts.append("Write grade.md (Ready, Gaps, or Unusable plus the gap list) and "
                         "proposed-task.md (numbered task markdown; mark invented vs quoted). "
                         "Commit both. Hand off `to: operator`, `verdict: ready`.")
        else:
            parts.append("Write grade.md with Ready, Gaps, or Unusable against the rubric. "
                         "Commit it. Hand off `to: operator`, `verdict: ready`. Do not write tasks/.")
        if attempt > 1:
            parts.append("Your previous attempt ended without a valid handoff. Last validator output:\n"
                         + (last_err or "No handoff.sh call was observed."))
        parts.append("When finished, write ./tmp/handoff.txt and run handoff.sh ./tmp/handoff.txt. "
                     "Do not end your run until it prints OK.")
        return "\n\n".join(parts)

    def agent_binary(self):
        """Resolve CONVEYOR_AGENT_BIN the way Popen(cwd=worktree) will, or None.
        A bare name is looked up on PATH; a path with a separator is taken as-is
        (relative paths resolve against the worktree, the agent's cwd)."""
        return agentlib.resolve(os.environ["CONVEYOR_AGENT_BIN"], self.wt)

    def run_agent(self, task, hid, attempt, prompt, session, deadline_s):
        log = os.path.join(self.paths.logs, self.role, f"{task}_{hid}_a{attempt}.jsonl")
        cmd = agentlib.compose(os.environ["CONVEYOR_AGENT_BIN"], self.me.model,
                               [*self.cfg.agent_args, *self.me.args], output_format="stream-json")
        if session:
            cmd += ["--resume", session]
        cmd.append(prompt)
        print(f"{task}: attempt {attempt} running {self.me.model}"
              f"{' (resume)' if session else ''}", flush=True)
        with open(log, "a", encoding="utf-8") as lf:
            lf.write(stamped(json.dumps(
                {"type": "conveyor", "event": "run", "role": self.role, "task": task,
                 "attempt": attempt, "model": self.me.model, "resumed": bool(session),
                 "text": f"attempt {attempt}, model {self.me.model}"
                         f"{', resumed session' if session else ''}"})))
            lf.flush()
            started = time.monotonic()
            try:
                # start_new_session: the agent leads its own process group, so the
                # deadline (and `stop --now`) can take its children with it. Without
                # it the agent shares the loop's group and a killpg would kill the loop.
                self.agent = subprocess.Popen(cmd, cwd=self.wt, stdout=subprocess.PIPE,
                                              stderr=subprocess.STDOUT, start_new_session=True)
            except OSError as e:
                # Binary vanished or lost +x since the pre-flight check: degrade to a
                # failed attempt (max-attempts will park) rather than crash the loop.
                self.agent = None
                msg = f"E_NO_AGENT: cannot launch {cmd[0]!r}: {e}"
                lf.write(stamped(json.dumps({"type": "conveyor", "error": msg})))
                return session, msg, None
            self.agent_pgid = self.agent.pid  # start_new_session makes pid == pgid
            # The stamper, not the loop, sits between the agent and the log: kill -9 of
            # the loop leaves agent and stamper running and the run still lands dated
            # in the file, exactly as the plain redirect used to (invariant 11).
            stamper = subprocess.Popen([sys.executable, os.path.join(BIN, "role-loop.sh"), "--stamp"],
                                       stdin=self.agent.stdout, stdout=lf, stderr=subprocess.DEVNULL)
            self.agent.stdout.close()  # the stamper owns the read end; it needs the EOF
            started = time.monotonic()
            killed = escalated = False
            try:
                rc = self.agent.wait(timeout=deadline_s)
            except subprocess.TimeoutExpired:
                killed = True
                escalated = util.kill_group(self.agent_pgid, self.agent)
                rc = self.agent.wait()
            elapsed = time.monotonic() - started
            self.agent = None
            # The stamper sees EOF only when every writer closes, so a child that
            # inherited the agent's stdout outlives the agent and would block this
            # wait forever. Bound it, then take the whole group with it.
            if not self.drain(stamper):
                util.kill_group(self.agent_pgid)
                if not self.drain(stamper):
                    stamper.kill()
                    stamper.wait()
            self.agent_pgid = None
            detail = None
            if killed:
                span = util.duration(elapsed)
                # `text` reads as the predicate of `event`, the way the run record does:
                # `conveyor log` prints them in that order (LOG_DETAIL_KEYS).
                said = f"after {span} (max-minutes deadline)"
                lf.write(stamped(json.dumps(
                    {"type": "conveyor", "event": "killed", "reason": "max-minutes",
                     "after_s": int(elapsed), "signal": "TERM", "escalated": escalated,
                     "text": said})))
                print(f"{task}: attempt {attempt} killed {said}", flush=True)
                detail = (f"killed attempt {attempt} after {span}, "
                          f"exceeds max_minutes {self.me.max_minutes}")
            # Every agent line is on disk now, so one read serves the usage scan and
            # both regexes below. The usage record goes in before `exit`, which stays
            # the last line of a run (§6.9). A run killed on its deadline is billed
            # too: the tokens it spent before the kill were still spent.
            text = util.read_text(log)
            scanned = usage.scan(text)
            lf.write(stamped(json.dumps({"type": "conveyor", "event": "usage",
                                         "text": usage_text(scanned, elapsed),
                                         "input_tokens": scanned["input"],
                                         "output_tokens": scanned["output"],
                                         "source": scanned["source"]})))
            lf.write(stamped(json.dumps({"type": "conveyor", "event": "exit", "exit": rc})))
        print(f"{task}: attempt {attempt} agent exited {rc}", flush=True)
        usage.record(self.paths, self.role, task, hid, attempt, scanned, elapsed, rc)
        m = SESSION_RE.search(text)
        errs = VALIDATOR_RE.findall(text)
        return (m.group(1) if m else session), (errs[-1] if errs else None), detail

    @staticmethod
    def drain(stamper):
        """Wait a bounded time for the stamper to finish. False when it is still stuck."""
        try:
            stamper.wait(timeout=util.drain_grace())
            return True
        except subprocess.TimeoutExpired:
            return False


def main():
    if "--stamp" in sys.argv:
        # Agent output is not always clean UTF-8, and the log must not die over a byte.
        sys.stdin.reconfigure(errors="replace")
        sys.stdout.reconfigure(errors="replace")
        return stamp_stream(sys.stdin, sys.stdout)
    sys.stdout = DatedStdout(sys.stdout)
    loop = Loop("--once" in sys.argv)
    loop.acquire()
    signal.signal(signal.SIGTERM, loop.on_term)
    try:
        loop.run()
    finally:
        loop.release()


if __name__ == "__main__":
    main()
