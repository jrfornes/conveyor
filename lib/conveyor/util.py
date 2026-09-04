"""Timestamps, atomic writes, mkdir locks, git helper."""
import contextlib
import datetime
import os
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


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


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
