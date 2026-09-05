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

BIN = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(BIN, "..", "lib"))
from conveyor import board, config, handoff, inbox, layout, queue, util  # noqa: E402

SESSION_RE = re.compile(r'"session_?[iI]d"\s*:\s*"([^"]+)"')
VALIDATOR_RE = re.compile(r'(?:E_[A-Z_]+|AUDIT_REQUIRED): [^"\\\n]*')


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
        if self.agent and self.agent.poll() is None:
            self.agent.terminate()
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
        park = lambda reason, detail: queue.park(self.paths, path, task, reason, detail)  # noqa: E731
        if not queue.merge(h["commit"], self.wt, self.role):
            return park("merge-conflict", f"merging {h['commit']} into conveyor-{self.role} conflicted")
        util.crash_point("after-merge")
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
        attempt, session, last_err, ran = int(h.get("attempt", 1)), h.get("session"), None, False
        while True:
            n = self.valid_outbox_count()
            if n == 1:
                outcome = "merged" if handoff.read(os.path.join(
                    self.rp.outbox, layout.handoffs(self.rp.outbox)[0]))[0]["to"] == "done" else "forwarded"
                handoff.stamp(path, completed_at=util.now(), outcome=outcome)
                util.crash_point("after-complete-stamp")
                handoff.move(path, self.rp.completed)
                util.crash_point("after-complete")
                return
            if n > 1:
                for i, f in enumerate(layout.handoffs(self.rp.outbox), 1):  # never deliver either
                    os.makedirs(os.path.join(self.paths.needs_human, task), exist_ok=True)
                    handoff.move(os.path.join(self.rp.outbox, f), os.path.join(self.paths.needs_human, task),
                                 f"outbox-{i}.handoff")
                return park("multiple-handoffs", f"{n} handoffs in outbox, kept as outbox-N.handoff; never guessing")
            if ran:
                attempt += 1
                handoff.stamp(path, attempt=attempt, **({"session": session} if session else {}))
                if attempt > self.me.max_attempts:
                    return park("max-attempts", f"{attempt - 1} agent runs ended without a valid handoff")
                if self.stop_requested():
                    sys.exit(0)
            if not os.path.exists(os.path.join(self.wt, ".cursor", "rules", "conveyor-role.mdc")):
                print("E_NO_RULES: .cursor/rules/conveyor-role.mdc missing", flush=True)
                return park("no-rules", "worktree has no .cursor/rules/conveyor-role.mdc; run conveyor start")
            prompt = self.build_prompt(path, task, attempt, last_err)
            if prompt is None:
                return park("no-task-file", f"tasks/{task}.md is not at HEAD after merge")
            session, last_err = self.run_agent(task, h["id"], attempt, prompt, session)
            util.crash_point("after-agent")
            ran = True

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

    def run_agent(self, task, hid, attempt, prompt, session):
        log = os.path.join(self.paths.logs, self.role, f"{task}_{hid}_a{attempt}.jsonl")
        cmd = [os.environ["CONVEYOR_AGENT_BIN"], "-p", "--force", "--model", self.me.model,
               "--output-format", "stream-json", *self.cfg.agent_args, *self.me.args]
        if session:
            cmd += ["--resume", session]
        cmd.append(prompt)
        with open(log, "a", encoding="utf-8") as lf:
            self.agent = subprocess.Popen(cmd, cwd=self.wt, stdout=lf, stderr=subprocess.STDOUT)
            rc = self.agent.wait()
            self.agent = None
            lf.write(json.dumps({"type": "conveyor", "exit": rc}) + "\n")
        text = util.read_text(log)
        m = SESSION_RE.search(text)
        errs = VALIDATOR_RE.findall(text)
        return (m.group(1) if m else session), (errs[-1] if errs else None)


def main():
    loop = Loop("--once" in sys.argv)
    loop.acquire()
    signal.signal(signal.SIGTERM, loop.on_term)
    try:
        loop.run()
    finally:
        loop.release()


if __name__ == "__main__":
    main()
