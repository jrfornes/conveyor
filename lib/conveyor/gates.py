"""Project gate catalog in project.md (protocol §4.4)."""
import os
import re
import subprocess

from . import util

GATE_NAME = re.compile(r"^[a-z][a-z0-9:-]*$")
ROLE_VERDICT = re.compile(r"^([a-z][a-z0-9-]*)\s+(ready|pass):\s*(.+)$")
PLACEHOLDER = re.compile(r"\{[^}]+\}")
KNOWN = frozenset({"{inbound}", "{head}"})
IMPLICIT_GATE = "test"


class GateError(Exception):
    """Base for gate failures mapped to E_* in handoff.sh."""


class GateParseError(GateError):
    pass


class GateUnknownError(GateError):
    def __init__(self, name):
        self.name = name
        super().__init__(name)


class GateSubstError(GateError):
    def __init__(self, token):
        self.token = token
        super().__init__(token)


class GateFailedError(GateError):
    def __init__(self, exit_code, log_path):
        self.exit_code = exit_code
        self.log_path = log_path
        super().__init__(exit_code)


class GateTimeoutError(GateError):
    def __init__(self, seconds, log_path):
        self.seconds = seconds
        self.log_path = log_path
        super().__init__(seconds)


class Catalog:
    __slots__ = ("commands", "required", "source", "timeouts")

    def __init__(self, commands, required, source, timeouts=None):
        self.commands = commands
        self.required = required
        self.source = source
        self.timeouts = timeouts or {}


def _section_lines(text, heading):
    collecting, lines = False, []
    for line in _strip_comments(text).splitlines():
        if not collecting:
            if line.startswith(heading):
                collecting = True
            continue
        if line.startswith("## "):
            break
        lines.append(line)
    return lines


def _fence_command(lines, start=0):
    body = "\n".join(lines[start:])
    start = body.find("```")
    if start < 0:
        return ""
    nl = body.find("\n", start)
    if nl < 0:
        return ""
    end = body.find("```", nl + 1)
    if end < 0:
        return ""
    fence = re.sub(r"<!--.*?-->", "", body[nl + 1:end], flags=re.DOTALL)
    for line in fence.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def _parse_gates_section(lines):
    commands = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([a-z][a-z0-9:-]*):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        name, rest = m.group(1), m.group(2).strip()
        if not GATE_NAME.match(name):
            raise GateParseError(f"invalid gate name {name!r}")
        if name in commands:
            raise GateParseError(f"duplicate gate name {name!r}")
        if rest:
            commands[name] = rest
            i += 1
            continue
        cmd = _fence_command(lines, i + 1)
        commands[name] = cmd
        i += 1
        while i < len(lines) and not re.match(r"^[a-z][a-z0-9:-]*:\s*", lines[i]):
            i += 1
    return commands


def _parse_required_section(lines):
    required = {}
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = ROLE_VERDICT.match(s)
        if not m:
            raise GateParseError(f"required-on line is not `<role> ready|pass: name, ...`: {s!r}")
        role, verdict, tail = m.group(1), m.group(2), m.group(3)
        names = [n.strip() for n in tail.split(",") if n.strip()]
        if not names:
            raise GateParseError(f"required-on line lists no gates: {s!r}")
        for name in names:
            if not GATE_NAME.match(name):
                raise GateParseError(f"invalid gate name {name!r}")
        required[(role, verdict)] = names
    return required


def _parse_timeouts_section(lines, commands):
    """`## Gate timeouts`: `<name>: <seconds>`, one per line. Shaped like ## Required on.

    A separate section rather than a token on the gate line, so `_parse_gates_section`
    and its fence handling stay untouched. 0 means unbounded, as it does in config.
    """
    timeouts = {}
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([a-z][a-z0-9:-]*):\s*(.+)$", s)
        if not m:
            raise GateParseError(f"gate-timeout line is not `<name>: <seconds>`: {s!r}")
        name, value = m.group(1), m.group(2).strip()
        if name in timeouts:
            raise GateParseError(f"duplicate gate timeout for {name!r}")
        if name not in commands:
            raise GateParseError(f"gate timeout names unknown gate {name!r}")
        if not re.fullmatch(r"\d+", value):
            raise GateParseError(
                f"gate timeout for {name!r} must be a non-negative integer: {value!r}")
        timeouts[name] = int(value)
    return timeouts


def _parse_test_command(text):
    lines = _section_lines(text, "## Test command")
    cmd = _fence_command(lines)
    commands = {IMPLICIT_GATE: cmd}
    required = {}
    return Catalog(commands, required, "test-command", _timeouts(text, commands))


def _timeouts(text, commands):
    if not _has_heading(text, "## Gate timeouts"):
        return {}
    return _parse_timeouts_section(_section_lines(text, "## Gate timeouts"), commands)


def _strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _has_heading(text, title):
    for line in text.splitlines():
        if line.startswith(title):
            return True
    return False


def parse(text):
    """Parse project.md gate catalog. Missing file content is empty."""
    text = _strip_comments(text)
    has_gates = _has_heading(text, "## Gates")
    has_required = _has_heading(text, "## Required on")
    has_test = _has_heading(text, "## Test command")
    if has_gates and has_test:
        raise GateParseError("project.md has both ## Gates and ## Test command; keep one")
    if has_gates and not has_required:
        raise GateParseError("project.md has ## Gates but no ## Required on")
    if has_required and not has_gates:
        raise GateParseError("project.md has ## Required on but no ## Gates")
    if has_gates:
        commands = _parse_gates_section(_section_lines(text, "## Gates"))
        required = _parse_required_section(_section_lines(text, "## Required on"))
        return Catalog(commands, required, "gates", _timeouts(text, commands))
    if has_test or text.strip():
        return _parse_test_command(text)
    return Catalog({}, {}, "test-command")


def required(catalog, role, verdict, belt):
    """Gate names to run for (role, verdict). belt is an iterable of role names on the workflow."""
    belt_set = set(belt)
    if catalog.source == "test-command":
        cmd = catalog.commands.get(IMPLICIT_GATE, "")
        if not cmd.strip():
            return []
        if role in belt_set and verdict in ("ready", "pass"):
            return [IMPLICIT_GATE]
        return []
    names = catalog.required.get((role, verdict), [])
    return list(names)


def expand(argv, inbound, head):
    """Substitute {inbound} and {head}; refuse unknown placeholders."""
    for m in PLACEHOLDER.finditer(argv):
        if m.group(0) not in KNOWN:
            raise GateSubstError(m.group(0))
    return argv.replace("{inbound}", inbound).replace("{head}", head)


def log_path(paths, role, task, commit, name):
    return os.path.join(paths.gates, f"{role}-{task}-{commit}-{name}.txt")


def timeout_for(catalog, name, default):
    """The gate's budget in seconds: `## Gate timeouts` beats `[global] gate_timeout`."""
    return catalog.timeouts.get(name, default)


_RUNNING_PGID = None  # process group of the gate in flight, for kill_running()


def kill_running():
    """Stop the gate currently in flight, if any.

    `handoff.sh` calls this from its SIGTERM handler. A gate runs in its own
    session, so the agent's process-group kill does not reach it: without this a
    killed run leaves an `nx build` running forever.
    """
    util.kill_group(_RUNNING_PGID)


def run(paths, wt, role, task, commit, name, argv, timeout=0):
    """Run one gate command; write log and raise on nonzero exit or timeout.

    `timeout` is seconds, 0 = unbounded. The command gets its own process group:
    with shell=True a plain `communicate(timeout=…)` kills the shell and orphans
    the command that is actually stuck, so the deadline kills the whole group.
    """
    global _RUNNING_PGID
    os.makedirs(paths.gates, exist_ok=True)
    p = subprocess.Popen(argv, shell=True, cwd=wt, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    _RUNNING_PGID = p.pid
    try:
        try:
            out, err = p.communicate(timeout=timeout or None)
        except subprocess.TimeoutExpired:
            util.kill_group(p.pid, p)
            out, err = p.communicate()
            path = _write_log(paths, role, task, commit, name, "timeout", argv, out, err)
            raise GateTimeoutError(timeout, path)
    finally:
        _RUNNING_PGID = None
    if p.returncode == 0:
        return
    path = _write_log(paths, role, task, commit, name, p.returncode, argv, out, err)
    raise GateFailedError(p.returncode, path)


def _write_log(paths, role, task, commit, name, status, argv, out, err):
    """A timed-out gate writes the same log shape as a failed one, with `exit: timeout`
    and whatever output it had produced so far."""
    path = log_path(paths, role, task, commit, name)
    util.atomic_write(
        path,
        f"exit: {status}\nargv: {argv}\n--- stdout ---\n{out}--- stderr ---\n{err}",
    )
    return path


def validate_for_belt(catalog, belt):
    """Return list of (role, verdict, name) for required names missing from the catalog."""
    belt_set = set(belt)
    missing = []
    for (role, verdict), names in catalog.required.items():
        if role not in belt_set:
            continue
        for name in names:
            if name not in catalog.commands:
                missing.append((role, verdict, name))
    return missing


def read_catalog(root, wt=None):
    base = wt or root
    path = os.path.join(base, "project.md")
    text = util.read_text(path) if os.path.isfile(path) else ""
    return parse(text)
