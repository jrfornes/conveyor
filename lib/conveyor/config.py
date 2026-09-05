"""conveyor.conf parsing and pipeline routes (protocol §1, §3.2; PRD CFG-*)."""
import os
import re
import shlex
from dataclasses import dataclass, field

from . import util

ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
# "none" is reserved so `gate none` can never be confused with a role of that name.
RESERVED = {"operator", "done", "ticket-reviewer", "none"}
VERDICTS = ("ready", "pass", "findings")
INTAKE_ROLE = "ticket-reviewer"
NO_GATE = "none"
INTAKE_DEFAULT_MINUTES = 30
INTAKE_DEFAULT_ATTEMPTS = 2
INBOX_KEYS = ("jira_base", "jira_token_env", "ticket_reviewer_model",
              "ticket_reviewer_max_minutes", "ticket_reviewer_max_attempts")


class ConfigError(Exception):
    pass


@dataclass
class Role:
    name: str
    model: str
    max_retries: int = 3
    max_minutes: int = 120
    max_attempts: int = 3
    args: list = field(default_factory=list)


@dataclass
class InboxConf:
    jira_base: str = ""
    jira_token_env: str = ""
    ticket_reviewer_model: str = ""
    ticket_reviewer_max_minutes: int | None = None  # None = default; 0 is a legal ceiling
    ticket_reviewer_max_attempts: int | None = None


@dataclass
class Config:
    roles: list
    gate: str = ""          # declared `gate <role>`; "" means undeclared
    agent_bin: str = "cursor-agent"
    agent_args: list = field(default_factory=list)
    poll_seconds: float = 2.0
    agent_version: str = ""
    inbox: InboxConf = field(default_factory=InboxConf)

    def role(self, name):
        for r in self.roles:
            if r.name == name:
                return r
        if name == INTAKE_ROLE:
            model = self.inbox.ticket_reviewer_model or (self.roles[-1].model if self.roles else "composer-2.5")
            minutes = (INTAKE_DEFAULT_MINUTES if self.inbox.ticket_reviewer_max_minutes is None
                       else self.inbox.ticket_reviewer_max_minutes)
            attempts = (INTAKE_DEFAULT_ATTEMPTS if self.inbox.ticket_reviewer_max_attempts is None
                        else self.inbox.ticket_reviewer_max_attempts)
            return Role(INTAKE_ROLE, model, max_retries=1, max_minutes=minutes, max_attempts=attempts)
        raise ConfigError(f"unknown role: {name}")

    def names(self):
        return [r.name for r in self.roles]

    def chain_label(self):
        return " → ".join(self.names())

    def routes(self):
        """Permitted (from, to, verdict) triples derived from pipeline order."""
        n = self.names()
        r = {("operator", n[0], "ready")}
        for a, b in zip(n, n[1:]):
            r.add((a, b, "ready"))
        r.add((n[-1], "done", "pass"))
        if len(n) > 1:
            # Findings bounce to the penultimate role. A one-role belt has no
            # previous role, so it has no findings edge at all.
            r.add((n[-1], n[-2], "findings"))
        r.add((INTAKE_ROLE, "operator", "ready"))
        return r

    def gate_role(self):
        """Role whose outbound `ready` is held for the operator, or None.

        `gate <role>` gates that role; `gate none` is explicitly ungated. With
        no gate line at all a three-role pipeline gates its first role, which
        reproduces the three-pack hold that protocol §3.2 mandates for configs
        written before `gate` existed. `save()` always writes one of the two
        forms, so only hand-written legacy files rely on that inference.
        """
        if self.gate == NO_GATE:
            return None
        if self.gate:
            return self.gate
        return self.names()[0] if len(self.roles) == 3 else None

    def next_of(self, role):
        n = self.names()
        i = n.index(role)
        return n[i + 1] if i + 1 < len(n) else "done"


def _parse_role(parts, lineno):
    if len(parts) < 3:
        raise ConfigError(f"line {lineno}: role needs <name> <model>")
    name, model = parts[1], parts[2]
    if not ROLE_RE.match(name) or name in RESERVED:
        raise ConfigError(f"line {lineno}: invalid role name {name!r}")
    role = Role(name, model)
    for tok in parts[3:]:
        m = re.match(r"^(max_retries|max_minutes|max_attempts)=(\d+)$", tok)
        if m:
            setattr(role, m.group(1), int(m.group(2)))
        else:
            role.args.append(tok)
    return role


def load(root):
    path = os.path.join(root, "conveyor.conf")
    if not os.path.exists(path):
        raise ConfigError(f"missing {path}")
    roles, glob, inbox, section = [], {}, {}, None
    gate, gate_line = "", 0
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                if section not in ("global", "inbox"):
                    raise ConfigError(f"line {lineno}: unknown section [{section}]")
                continue
            if section in ("global", "inbox"):
                if "=" not in line:
                    raise ConfigError(f"line {lineno}: expected key = value")
                k, v = (s.strip() for s in line.split("=", 1))
                (glob if section == "global" else inbox)[k] = v
                continue
            parts = shlex.split(line)
            if parts[0] == "gate":
                if gate:
                    raise ConfigError(
                        f"line {lineno}: duplicate gate directive (already set on line "
                        f"{gate_line}); repair: keep one `gate <role>` line")
                if len(parts) != 2:
                    raise ConfigError(
                        f"line {lineno}: gate needs exactly one role; "
                        f"repair: write `gate <role>`")
                gate, gate_line = parts[1], lineno
                continue
            if parts[0] != "role":
                raise ConfigError(
                    f"line {lineno}: expected 'role ...', 'gate ...' or '[global]'")
            roles.append(_parse_role(parts, lineno))
    if not roles:
        raise ConfigError(
            "at least one role is required; repair: add a `role <name> <model>` line")
    names = [r.name for r in roles]
    if len(names) != len(set(names)):
        raise ConfigError("duplicate role names")
    if gate and gate != NO_GATE:
        if gate not in names:
            raise ConfigError(
                f"line {gate_line}: gate names unconfigured role {gate!r}; "
                f"repair: gate one of {', '.join(names)}, or `gate none`")
        if gate == names[-1]:
            raise ConfigError(
                f"line {gate_line}: cannot gate {gate!r}, the last role — its handoff "
                f"goes to done, not to another role; repair: gate a role before it, "
                f"or write `gate none`")
    cfg = Config(roles, gate=gate)
    if "agent_bin" in glob:
        cfg.agent_bin = glob["agent_bin"]
    if "agent_args" in glob:
        cfg.agent_args = shlex.split(glob["agent_args"])
    if "poll_seconds" in glob:
        cfg.poll_seconds = float(glob["poll_seconds"])
    cfg.agent_version = glob.get("agent_version", "")
    cfg.inbox = InboxConf(
        jira_base=inbox.get("jira_base", ""),
        jira_token_env=inbox.get("jira_token_env", ""),
        ticket_reviewer_model=inbox.get("ticket_reviewer_model", ""),
        ticket_reviewer_max_minutes=_inbox_int(inbox, "ticket_reviewer_max_minutes"),
        ticket_reviewer_max_attempts=_inbox_int(inbox, "ticket_reviewer_max_attempts"),
    )
    return cfg


def _inbox_int(inbox, key):
    """Parse a non-negative int, or None when the key is absent. 0 is legal."""
    if key not in inbox:
        return None
    raw = inbox[key]
    if not re.fullmatch(r"\d+", raw):
        raise ConfigError(
            f"{key} must be a non-negative integer; repair: set {key} = N")
    return int(raw)


def _kept_sections(text):
    """Preserve [global] and [inbox] blocks (including headers) from conveyor.conf."""
    glob_lines = []
    keep = False
    for line in text.splitlines(True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            keep = stripped[1:-1] in ("global", "inbox")
            if keep:
                glob_lines.append(line if line.endswith("\n") else line + "\n")
            continue
        if keep:
            glob_lines.append(line if line.endswith("\n") else line + "\n")
    return glob_lines


def save(root, cfg):
    """Rewrite role lines; keep existing [global] / [inbox] verbatim."""
    path = os.path.join(root, "conveyor.conf")
    text = util.read_text(path) if os.path.isfile(path) else ""
    glob_lines = _kept_sections(text)
    lines = ["# Conveyor pipeline configuration. Written by `conveyor workflow activate`.\n\n"]
    for r in cfg.roles:
        extra = (" " + " ".join(r.args)) if r.args else ""
        lines.append(
            f"role {r.name:<9} {r.model} max_retries={r.max_retries} "
            f"max_minutes={r.max_minutes} max_attempts={r.max_attempts}{extra}\n"
        )
    # Always written, resolved: `gate <role>` or `gate none`. A file Conveyor
    # wrote never relies on the legacy three-role inference in gate_role().
    lines.append(f"\ngate {cfg.gate_role() or NO_GATE}\n")
    lines.append("\n")
    if glob_lines:
        lines.extend(glob_lines)
    else:
        lines.append("[global]\nagent_bin = cursor-agent\nagent_args = --trust\npoll_seconds = 2\n")
    util.atomic_write(path, "".join(lines))


def write_inbox(root, updates):
    """Surgical [inbox] edit. Role lines, comments, and other sections stay byte-identical.

    Does not go through save() — that renormalizes every role line and always
    emits a resolved gate, which would flip presets.resolve() to custom.
    """
    unknown = [k for k in updates if k not in INBOX_KEYS]
    if unknown:
        raise ConfigError(f"unknown inbox key {unknown[0]!r}")
    for k, v in updates.items():
        s = "" if v is None else str(v)
        if "#" in s or "\n" in s:
            raise ConfigError(f"inbox value for {k} must not contain # or newline")
    if not updates:
        return
    path = os.path.join(root, "conveyor.conf")
    text = util.read_text(path) if os.path.isfile(path) else ""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    live = _find_header(lines, "[inbox]")
    if live is not None:
        _upsert_inbox_keys(lines, live, updates)
    else:
        commented = _find_header(lines, "# [inbox]")
        if commented is not None and _safe_to_promote(lines, commented):
            lines[commented] = lines[commented].replace("# [inbox]", "[inbox]", 1)
            _upsert_inbox_keys(lines, commented, updates)
        else:
            if lines:
                lines.append("\n")
            lines.append("[inbox]\n")
            for k, v in updates.items():
                lines.append(f"{k} = {v}\n")
    util.atomic_write(path, "".join(lines))


def _find_header(lines, header):
    for i, line in enumerate(lines):
        if line.strip() == header:
            return i
    return None


def _safe_to_promote(lines, comment_idx):
    """True when only comments/blanks follow `# [inbox]` before EOF or a live section."""
    for line in lines[comment_idx + 1:]:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("[") and s.endswith("]"):
            return True
        return False
    return True


def _inbox_section_end(lines, header_idx):
    for i in range(header_idx + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith("[") and s.endswith("]"):
            return i
    return len(lines)


def _upsert_inbox_keys(lines, header_idx, updates):
    end = _inbox_section_end(lines, header_idx)
    pending = dict(updates)
    for i in range(header_idx + 1, end):
        raw = lines[i]
        body = raw.split("#", 1)[0]
        if "=" not in body:
            continue
        key = body.split("=", 1)[0].strip()
        if key not in pending:
            continue
        m = re.match(r"^(\s*" + re.escape(key) + r"\s*=\s*)(.*?)(\s*)$", raw.rstrip("\n"))
        nl = "\n" if raw.endswith("\n") else ""
        if m:
            lines[i] = m.group(1) + str(pending[key]) + nl
        else:
            lines[i] = f"{key} = {pending[key]}{nl}"
        del pending[key]
    if pending:
        insert = [f"{k} = {v}\n" for k, v in pending.items()]
        lines[end:end] = insert
