"""conveyor.conf parsing and pipeline routes (protocol §1, §3.2; PRD CFG-*)."""
import os
import re
import shlex
from dataclasses import dataclass, field

ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
RESERVED = {"operator", "done"}
VERDICTS = ("ready", "pass", "findings")


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
class Config:
    roles: list
    agent_bin: str = "cursor-agent"
    agent_args: list = field(default_factory=list)
    poll_seconds: float = 2.0
    agent_version: str = ""

    def role(self, name):
        for r in self.roles:
            if r.name == name:
                return r
        raise ConfigError(f"unknown role: {name}")

    def names(self):
        return [r.name for r in self.roles]

    def routes(self):
        """Permitted (from, to, verdict) triples derived from pipeline order."""
        n = self.names()
        r = {("operator", n[0], "ready")}
        for a, b in zip(n, n[1:]):
            r.add((a, b, "ready"))
        r.add((n[-1], "done", "pass"))
        r.add((n[-1], n[0], "findings"))
        return r

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
    roles, glob, in_global = [], {}, False
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line == "[global]":
                in_global = True
                continue
            if in_global:
                if "=" not in line:
                    raise ConfigError(f"line {lineno}: expected key = value")
                k, v = (s.strip() for s in line.split("=", 1))
                glob[k] = v
                continue
            parts = shlex.split(line)
            if parts[0] != "role":
                raise ConfigError(f"line {lineno}: expected 'role ...' or '[global]'")
            roles.append(_parse_role(parts, lineno))
    names = [r.name for r in roles]
    if len(names) != len(set(names)):
        raise ConfigError("duplicate role names")
    if len(roles) != 2:
        raise ConfigError("exactly two roles are required (PRD CFG-1)")
    cfg = Config(roles)
    if "agent_bin" in glob:
        cfg.agent_bin = glob["agent_bin"]
    if "agent_args" in glob:
        cfg.agent_args = shlex.split(glob["agent_args"])
    if "poll_seconds" in glob:
        cfg.poll_seconds = float(glob["poll_seconds"])
    cfg.agent_version = glob.get("agent_version", "")
    return cfg
