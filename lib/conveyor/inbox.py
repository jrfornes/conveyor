"""Inbox items under .conveyor/inbox/<id>/ (protocol §2.4).

Every meta write: lock, rewrite whole file, rename. Status is a field, not a
directory — the id is stable so the item dir is not renamed on status change.
"""
import os
import re

from . import util

STATUSES = ("imported", "grading", "graded", "improving", "awaiting-approval",
            "ready", "started", "skipped")
META_KEYS = ("source", "title", "url", "external_id", "status", "grade",
             "created_at", "task_name")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
SLUG_RE = re.compile(r"[^a-z0-9]+")
RESERVED_IDS = {"config", "jira"}  # collide with `conveyor intake config|jira`


class InboxError(Exception):
    pass


def _dir(paths, iid):
    return os.path.join(paths.inbox, iid)


def _meta_path(paths, iid):
    return os.path.join(_dir(paths, iid), "meta.txt")


def parse_meta(text):
    meta = {k: "-" for k in META_KEYS}
    for line in text.split("\n"):
        if not line or ": " not in line:
            continue
        k, v = line.split(": ", 1)
        if k in META_KEYS:
            meta[k] = v
    return meta


def render_meta(meta):
    return "".join(f"{k}: {meta.get(k) or '-'}\n" for k in META_KEYS)


def slug(title):
    s = SLUG_RE.sub("-", (title or "").lower()).strip("-")[:48]
    if s and ID_RE.match(s):
        return s
    return ""


def exists(paths, iid):
    return os.path.isfile(_meta_path(paths, iid))


def allocate_id(paths, preferred):
    """Return a free id: preferred, preferred-2, …, or manual-NNNN."""
    os.makedirs(paths.inbox, exist_ok=True)
    base = preferred if preferred and ID_RE.match(preferred) else ""
    if base and base not in RESERVED_IDS and not exists(paths, base):
        return base
    if base:
        n = 2
        while exists(paths, f"{base}-{n}"):
            n += 1
        return f"{base}-{n}"
    seq_path = os.path.join(paths.inbox, "seq")
    try:
        n = int(util.read_text(seq_path).strip() or 0)
    except FileNotFoundError:
        n = 0
    n += 1
    util.atomic_write(seq_path, f"{n}\n")
    return f"manual-{n:04d}"


def create(paths, meta, source_md=""):
    """Create an item via tmp dir + rename. Returns id."""
    os.makedirs(paths.inbox, exist_ok=True)
    with util.lock(paths.inbox_lock):
        iid = allocate_id(paths, meta.get("id") or slug(meta.get("title", "")))
        tmp = os.path.join(paths.inbox, f".tmp-{iid}")
        os.makedirs(tmp, exist_ok=True)
        row = {k: meta.get(k) or "-" for k in META_KEYS}
        row["created_at"] = meta.get("created_at") or util.now()
        row["status"] = meta.get("status") or "imported"
        util.atomic_write(os.path.join(tmp, "meta.txt"), render_meta(row))
        util.atomic_write(os.path.join(tmp, "source.md"), source_md if source_md.endswith("\n") or not source_md else source_md + "\n")
        os.rename(tmp, _dir(paths, iid))
    return iid


def list_ids(paths):
    if not os.path.isdir(paths.inbox):
        return []
    return sorted(n for n in os.listdir(paths.inbox)
                  if n != "seq" and not n.startswith(".") and os.path.isdir(os.path.join(paths.inbox, n)))


def read_meta(paths, iid):
    try:
        return parse_meta(util.read_text(_meta_path(paths, iid)))
    except FileNotFoundError:
        raise InboxError(f"no inbox item {iid}") from None


def update_meta(paths, iid, **changes):
    with util.lock(paths.inbox_lock):
        meta = read_meta(paths, iid)
        for k, v in changes.items():
            if k not in META_KEYS:
                raise InboxError(f"unknown meta key {k}")
            meta[k] = v if v not in ("", None) else "-"
        if meta["status"] not in STATUSES:
            raise InboxError(f"invalid status {meta['status']}")
        util.atomic_write(_meta_path(paths, iid), render_meta(meta))
        return meta


def read_file(paths, iid, name):
    path = os.path.join(_dir(paths, iid), name)
    try:
        return util.read_text(path)
    except FileNotFoundError:
        return ""


def write_file(paths, iid, name, text):
    if not exists(paths, iid):
        raise InboxError(f"no inbox item {iid}")
    if not text.endswith("\n") and text:
        text += "\n"
    util.atomic_write(os.path.join(_dir(paths, iid), name), text)


def item(paths, iid):
    """Full item dict for API/CLI."""
    meta = read_meta(paths, iid)
    meta["id"] = iid
    meta["source_md"] = read_file(paths, iid, "source.md")
    meta["grade_md"] = read_file(paths, iid, "grade.md")
    meta["proposed_md"] = read_file(paths, iid, "proposed-task.md")
    meta["comments"] = read_file(paths, iid, "comments.txt")
    return meta


def list_items(paths):
    out = []
    for iid in list_ids(paths):
        try:
            meta = read_meta(paths, iid)
        except InboxError:
            continue
        meta["id"] = iid
        meta["has_grade"] = bool(read_file(paths, iid, "grade.md").strip())
        meta["has_proposed"] = bool(read_file(paths, iid, "proposed-task.md").strip())
        out.append(meta)
    return out


def parse_grade(text):
    """Ready / Gaps / Unusable from the grade file, else -."""
    for line in text.splitlines()[:30]:
        low = line.strip().lower()
        for g in ("ready", "gaps", "unusable"):
            if re.search(rf"\b{g}\b", low):
                return g.capitalize() if g != "gaps" else "Gaps"
    return "-"
