"""Timestamps, atomic writes, mkdir locks, process-group kill, bounded commands,
git helper."""
import contextlib
import datetime
import os
import signal
import subprocess
import sys
import time

UTC = datetime.timezone.utc
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def now():
    return datetime.datetime.now(UTC).strftime(TS_FMT)


def parse_ts(ts):
    return datetime.datetime.strptime(ts, TS_FMT).replace(tzinfo=UTC)


def compact(ts):
    return ts.replace("-", "").replace(":", "")


def age_seconds(ts):
    return int((datetime.datetime.now(UTC) - parse_ts(ts)).total_seconds())


def atomic_write(path, text):
    """Write text to path via <path>.tmp + rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def atomic_write_bytes(path, data):
    """Write bytes to path via <path>.tmp + rename."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


KILL_GRACE = 10.0     # seconds a process group gets between TERM and KILL
DRAIN_GRACE = 5.0     # seconds a reader gets to see EOF before its writers are killed


def kill_grace():
    """Seconds between TERM and KILL for a process group. Env knob for tests."""
    return _env_seconds("CONVEYOR_KILL_GRACE", KILL_GRACE)


def drain_grace():
    """Seconds a pipe reader gets to finish before the writers are killed."""
    return _env_seconds("CONVEYOR_DRAIN_GRACE", DRAIN_GRACE)


def _env_seconds(key, default):
    try:
        return float(os.environ.get(key, default))
    except ValueError:
        return default


def _group_gone(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def kill_group(pgid, proc=None, grace=None):
    """TERM a process group, then KILL whatever is left. True when KILL was needed.

    Every long-running child Conveyor launches gets `start_new_session=True`, so
    `pgid` is the leader's pid and the group holds everything it spawned --
    including a grandchild still holding the stdout pipe its parent's reader is
    blocked on. Signalling only the leader trades one hang for another.

    Signalling a group whose members have all exited raises ProcessLookupError;
    that is the success case, so every call is wrapped rather than checked first.
    `proc` is the leader's Popen, reaped while polling so a zombie leader does
    not keep the group looking alive for the whole grace period.
    """
    if pgid is None:
        return False
    grace = kill_grace() if grace is None else grace
    try:
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        return False
    deadline = time.monotonic() + grace
    while True:
        if proc is not None:
            proc.poll()
        if _group_gone(pgid):
            return False
        if time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        return False
    if proc is not None:
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=grace)
    return True


def duration(seconds):
    """`120m0s` -- how a killed run's elapsed time reads in the log and the park."""
    s = int(seconds)
    return f"{s // 60}m{s % 60}s"


class LockTimeout(Exception):
    pass


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextlib.contextmanager
def lock(path, timeout=None):
    """Protocol §8.2: mkdir lock with pid file; stale pid may be removed once."""
    timeout = float(os.environ.get("CONVEYOR_LOCK_TIMEOUT", 30)) if timeout is None else timeout
    deadline = time.monotonic() + timeout
    removed_stale = False
    while True:
        try:
            os.mkdir(path)
            break
        except FileExistsError:
            pass
        pidfile = os.path.join(path, "pid")
        try:
            pid = int(read_text(pidfile).strip())
            stale = not _pid_alive(pid)
        except (OSError, ValueError):
            stale = os.path.isdir(path) and time.monotonic() > deadline
        if stale and not removed_stale:
            removed_stale = True
            with contextlib.suppress(OSError):
                os.remove(pidfile)
            with contextlib.suppress(OSError):
                os.rmdir(path)
            continue
        if time.monotonic() > deadline:
            raise LockTimeout(path)
        time.sleep(0.1)
    try:
        with open(os.path.join(path, "pid"), "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(os.path.join(path, "pid"))
        with contextlib.suppress(OSError):
            os.rmdir(path)


def run_bounded(command, cwd, env, timeout, log_path):
    """Run a shell command under a deadline; write a gate-style log.

    Returns (returncode, timed_out, seconds). `timeout` of 0 (or None) is
    unbounded. The command gets its own process group (`start_new_session`)
    so the deadline reaches the whole tree through kill_group: `shell=True`
    with a plain `communicate(timeout=...)` kills the shell and orphans
    whatever it spawned, which for an install is the part that matters.

    Output that arrived before the kill is kept, so the log still shows how
    far the command got. `returncode` is the shell's exit status, negative
    when a signal ended it.
    """
    started = time.monotonic()
    p = subprocess.Popen(command, shell=True, cwd=cwd, env=env, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=True)
    timed_out = False
    try:
        out, err = p.communicate(timeout=timeout or None)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group(p.pid, p)
        out, err = p.communicate()
    seconds = time.monotonic() - started
    if log_path:
        if os.path.dirname(log_path):
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
        exit_line = "timeout" if timed_out else p.returncode
        atomic_write(log_path,
                     f"exit: {exit_line}\ncommand: {command}\n"
                     f"--- stdout ---\n{out or ''}--- stderr ---\n{err or ''}")
    return p.returncode, timed_out, seconds


def git(args, cwd, env=None, check=True):
    """Run git, return stdout stripped. Raises CalledProcessError when check."""
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run(["git", *args], cwd=cwd, env=e, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise subprocess.CalledProcessError(r.returncode, r.args, r.stdout, r.stderr)
    return r.stdout.strip()


def git_ok(args, cwd, env=None):
    return subprocess.run(["git", *args], cwd=cwd, env=env and {**os.environ, **env},
                          capture_output=True).returncode == 0


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def crash_point(label):
    """Test hook: CONVEYOR_CRASH_AT=<label>:<marker> kills this process once at <label>."""
    at, _, marker = os.environ.get("CONVEYOR_CRASH_AT", "").partition(":")
    if at != label or (marker and os.path.exists(marker)):
        return
    if marker:
        open(marker, "w").close()
    os.kill(os.getpid(), 9)


def bin_dir():
    """Directory holding the conveyor scripts (resolved through symlinks)."""
    return os.path.dirname(os.path.realpath(sys.argv[0]))
