"""Inbox attachment manifests (Jira files for ticket-reviewer only).

List on import; bytes on Grade/Improve. Never downloads video/audio/archives.
"""
import json
import os
import re
import shutil
import urllib.error

from . import inbox, jira as jiralib, util

MAX_BYTES = 10 * 1024 * 1024
MANIFEST = "attachments.json"
BLOBS = "attachments"
FOOTER_HEADING = "## Conveyor attachments"
DEFAULT_IMAGE_MIMES = frozenset({
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
})
VIDEO_EXTS = frozenset({".mp4", ".mov", ".webm", ".m4v"})
AUDIO_EXTS = frozenset({".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"})
ARCHIVE_EXTS = frozenset({".zip", ".tar", ".gz", ".tgz", ".7z"})
ARCHIVE_MIMES = frozenset({
    "application/zip", "application/x-zip-compressed", "application/x-tar",
    "application/gzip", "application/x-gzip", "application/x-7z-compressed",
    "application/x-compressed-tar",
})
ROW_KEYS = ("id", "filename", "mime", "size", "kind", "selected",
            "downloadable", "skip_reason", "content_url")
FOOTER_RE = re.compile(r"(?:\n|\A)## Conveyor attachments\n.*\Z", re.DOTALL)
UNSAFE_NAME = re.compile(r"[^\w.\-]+")


class AttachmentsError(Exception):
    pass


def item_dir(paths, iid):
    return os.path.join(paths.inbox, iid)


def manifest_path(paths, iid):
    return os.path.join(item_dir(paths, iid), MANIFEST)


def blobs_dir(paths, iid):
    return os.path.join(item_dir(paths, iid), BLOBS)


def _mime(raw):
    return (raw or "").split(";", 1)[0].strip().lower()


def _ext(filename):
    return os.path.splitext(filename or "")[1].lower()


def classify(filename, mime, size):
    """Return (kind, downloadable, skip_reason, selected)."""
    mime = _mime(mime)
    ext = _ext(filename)
    try:
        size = int(size or 0)
    except (TypeError, ValueError):
        size = 0
    if mime.startswith("video/") or ext in VIDEO_EXTS:
        return "video", False, "video", False
    if mime.startswith("audio/") or ext in AUDIO_EXTS:
        return "audio", False, "audio", False
    if mime in ARCHIVE_MIMES or ext in ARCHIVE_EXTS:
        return "archive", False, "archive", False
    kind = "image" if mime.startswith("image/") else "other"
    if size > MAX_BYTES:
        return kind, False, "oversize", False
    selected = kind == "image" and mime in DEFAULT_IMAGE_MIMES and 0 < size <= MAX_BYTES
    return kind, True, "", selected


def row_from_raw(raw):
    aid = str(raw.get("id") or "")
    filename = raw.get("filename") or aid or "file"
    mime = _mime(raw.get("mime"))
    try:
        size = int(raw.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    kind, downloadable, skip_reason, selected = classify(filename, mime, size)
    return {
        "id": aid,
        "filename": filename,
        "mime": mime,
        "size": size,
        "kind": kind,
        "selected": bool(selected),
        "downloadable": bool(downloadable),
        "skip_reason": skip_reason,
        "content_url": raw.get("content_url") or "",
    }


def rows_from(raw_list):
    out, seen = [], set()
    for raw in raw_list or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        row = row_from_raw(raw)
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
    return out


def read(paths, iid):
    path = manifest_path(paths, iid)
    try:
        data = json.loads(util.read_text(path))
    except (OSError, ValueError):
        return []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("attachments") or []
    else:
        return []
    out = []
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            out.append({k: row.get(k) for k in ROW_KEYS})
    return out


def write(paths, iid, rows):
    if not inbox.exists(paths, iid):
        raise AttachmentsError(f"no inbox item {iid}")
    payload = json.dumps({"attachments": rows}, indent=2) + "\n"
    with util.lock(paths.inbox_lock):
        util.atomic_write(manifest_path(paths, iid), payload)


def counts(rows):
    rows = rows or []
    return {
        "attachment_count": len(rows),
        "video_count": sum(1 for r in rows if r.get("kind") == "video"),
        "selected_count": sum(1 for r in rows if r.get("selected")),
    }


def video_audio_count(rows):
    return sum(1 for r in (rows or []) if r.get("kind") in ("video", "audio"))


def strip_footer(text):
    return FOOTER_RE.sub("", text or "").rstrip()


def render_footer(rows, browse_url):
    if not rows:
        return ""
    lines = [FOOTER_HEADING, ""]
    url = (browse_url or "").strip()
    for r in rows:
        name = r.get("filename") or r.get("id") or "file"
        kind = r.get("kind") or "other"
        if r.get("kind") in ("video", "audio"):
            watch = f" — watch in Jira: {url}" if url else " — watch in Jira"
            lines.append(f"- `{name}` ({kind}, not downloaded{watch})")
        elif r.get("selected"):
            lines.append(f"- `{name}` ({kind}, selected)")
        elif r.get("skip_reason") == "oversize":
            lines.append(f"- `{name}` ({kind}, not selected — oversize)")
        elif not r.get("downloadable"):
            lines.append(f"- `{name}` ({kind}, not downloaded)")
        else:
            lines.append(f"- `{name}` ({kind}, not selected)")
    return "\n".join(lines) + "\n"


def apply_footer(spec_text, rows, browse_url):
    body = strip_footer(spec_text)
    footer = render_footer(rows, browse_url)
    if not footer:
        return (body + "\n") if body else ""
    if body:
        return body + "\n\n" + footer
    return footer


def rewrite_footer(paths, iid, browse_url=None):
    rows = read(paths, iid)
    if browse_url is None:
        try:
            browse_url = inbox.read_meta(paths, iid).get("url") or ""
        except inbox.InboxError:
            browse_url = ""
        if browse_url in ("", "-"):
            browse_url = ""
    spec = inbox.read_file(paths, iid, "source.md")
    inbox.write_file(paths, iid, "source.md", apply_footer(spec, rows, browse_url))


def merge_selection(old_rows, new_rows):
    """Keep selected for ids that still exist and are still downloadable."""
    prev = {r["id"]: r for r in (old_rows or []) if r.get("id")}
    out = []
    for row in new_rows:
        if row["id"] in prev:
            keep = bool(prev[row["id"]].get("selected")) and bool(row.get("downloadable"))
            row = {**row, "selected": keep}
        out.append(row)
    return out


def install(paths, iid, raw_list, spec_text, browse_url, keep_selection=False):
    """Write manifest + source.md (spec + Conveyor footer)."""
    rows = rows_from(raw_list)
    if keep_selection:
        rows = merge_selection(read(paths, iid), rows)
    write(paths, iid, rows)
    inbox.write_file(paths, iid, "source.md", apply_footer(spec_text, rows, browse_url))
    return rows


def list_status(row):
    if row.get("selected"):
        return "selected"
    reason = row.get("skip_reason") or ""
    if reason:
        return f"skip-{reason}"
    return "off"


def format_list_line(row):
    return (f"{row.get('id') or '-'}  {list_status(row)}  {row.get('kind') or 'other'}  "
            f"{int(row.get('size') or 0)}  {row.get('filename') or '-'}")


def select(paths, iid, ids):
    """Set selected to exactly `ids` (empty = none). Refuses undownloadable ids."""
    rows = read(paths, iid)
    wanted = []
    for raw in ids or []:
        s = str(raw).strip()
        if s:
            wanted.append(s)
    known = {r["id"] for r in rows}
    unknown = [i for i in wanted if i not in known]
    if unknown:
        raise AttachmentsError(f"unknown attachment id {', '.join(unknown)}")
    want = set(wanted)
    for row in rows:
        if row["id"] in want:
            if not row.get("downloadable"):
                why = row.get("skip_reason") or row.get("kind") or "blocked"
                raise AttachmentsError(f"cannot select {row['id']} ({why})")
            row["selected"] = True
        else:
            row["selected"] = False
    write(paths, iid, rows)
    rewrite_footer(paths, iid)
    return rows


def safe_filename(name):
    base = os.path.basename(name or "file").replace("\x00", "")
    base = UNSAFE_NAME.sub("_", base).strip("._") or "file"
    return base[:120]


def blob_name(row):
    return f"{row['id']}-{safe_filename(row.get('filename') or row['id'])}"


def download_selected(paths, cfg, iid, dest_dir):
    """Download each selected file into the item dir, copy into dest_dir.

    Overwrites existing blobs. Raises AttachmentsError on any failure.
    """
    rows = [r for r in read(paths, iid) if r.get("selected")]
    if not rows:
        return []
    creds = jiralib.resolve(paths, cfg)
    auth = jiralib.auth_header(creds)
    if not auth:
        raise AttachmentsError("Jira credentials missing or incomplete; cannot download attachments")
    headers = {"Authorization": auth, "Accept": "*/*"}
    os.makedirs(blobs_dir(paths, iid), exist_ok=True)
    copied = []
    for row in rows:
        if not row.get("downloadable"):
            raise AttachmentsError(f"cannot download {row['id']} ({row.get('skip_reason') or row.get('kind')})")
        url = row.get("content_url") or ""
        if not url:
            raise AttachmentsError(f"no content_url for attachment {row['id']}")
        dest = os.path.join(blobs_dir(paths, iid), blob_name(row))
        try:
            jiralib.download_content(url, dest, headers, MAX_BYTES)
        except urllib.error.HTTPError as e:
            raise AttachmentsError(
                f"download {row['id']} failed: {e.code} {e.reason}") from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise AttachmentsError(f"download {row['id']} failed: {e}") from e
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(dest, os.path.join(dest_dir, blob_name(row)))
        copied.append(blob_name(row))
    return copied
