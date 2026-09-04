"""Handoff file format (protocol §3)."""
import os
import re

from . import util

AGENT = ("to", "task", "verdict")
VALIDATOR = ("type", "id", "from", "commit", "task_id", "created_at")
LOOP = ("enqueued_at", "dequeued_at", "attempt", "session", "completed_at", "outcome")
ORDER = AGENT + VALIDATOR + LOOP
TASK_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
HEADER_RE = re.compile(r"^([a-z][a-z_-]*): (\S(?:.*\S)?)$")


class ParseError(Exception):
    def __init__(self, lineno, msg):
        super().__init__(f"line {lineno}: {msg}")
        self.lineno = lineno


def parse(text):
    """Return (headers, body). Grammar only; key policy is the caller's job."""
    headers = {}
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line == "":
            body = "\n".join(lines[i + 1:])
            return headers, body
        m = HEADER_RE.match(line)
        if not m:
            raise ParseError(i + 1, "not `key: value`")
        if m.group(1) in headers:
            raise ParseError(i + 1, f"duplicate header {m.group(1)}")
        headers[m.group(1)] = m.group(2)
    return headers, ""


def render(headers, body):
    out = "".join(f"{k}: {headers[k]}\n" for k in ORDER if k in headers)
    out += "\n" + body
    if not out.endswith("\n"):
        out += "\n"
    return out


def filename(h):
    seq = h["id"].rsplit("-", 1)[1]
    return f"{util.compact(h['created_at'])}_{seq}_from_{h['from']}_to_{h['to']}.handoff"


def read(path):
    return parse(util.read_text(path))


def write(path, headers, body):
    """Write via <path>.tmp + rename (same directory)."""
    util.atomic_write(path, render(headers, body))


def stamp(path, **new):
    """Rewrite a handoff in place-by-rename with extra/replaced headers."""
    h, body = read(path)
    h.update({k: str(v) for k, v in new.items()})
    write(path, h, body)
    return h


def move(src, dst_dir, name=None):
    dst = os.path.join(dst_dir, name or os.path.basename(src))
    os.rename(src, dst)
    return dst


def find_id(hid, *dirs):
    """First path under dirs whose headers carry id == hid, else None."""
    for d in dirs:
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            p = os.path.join(d, f)
            if f.endswith(".handoff"):
                try:
                    if read(p)[0].get("id") == hid:
                        return p
                except (ParseError, OSError):
                    pass
    return None
