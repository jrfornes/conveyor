"""Vendor-agnostic inbox adapters. fetch(kind, raw) → list of ticket dicts.

A later GitHub/Linear adapter is one function with the same return shape.
"""
import json
import os
import re
import urllib.error
import urllib.request

JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
# Locked allowlist for customfield_* display names (expand=names). See bin/README.md.
JIRA_CUSTOM_RE = re.compile(r"acceptance|criteri|repro|expected|user story", re.I)


def fetch(source_kind, raw, cfg=None, title="", http_get=None, paths=None):
    """Return a list of {title, body, url, external_id, source}."""
    kind = (source_kind or "manual").lower()
    if kind == "manual":
        return [fetch_manual(title, raw)]
    if kind == "jira":
        return fetch_jira(raw, cfg, http_get=http_get, paths=paths)
    raise ValueError(f"unknown source {source_kind!r}")


def fetch_manual(title, raw):
    body = (raw or "").strip()
    title = (title or "").strip()
    if not title:
        for line in body.splitlines():
            t = line.strip().lstrip("#").strip()
            if t:
                title = t
                break
    if not title:
        title = "untitled"
    return {"title": title, "body": body, "url": "", "external_id": "", "source": "manual"}


def _http_get(url, headers):
    from . import jira as jiralib
    with jiralib.urlopen(url, headers) as resp:
        return resp.read().decode()


def _jira_keys(raw):
    seen, keys = set(), []
    for m in JIRA_KEY.finditer(raw or ""):
        k = m.group(1)
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def _adf_join(nodes, joiner):
    return joiner.join(p for p in (_adf_text(n) for n in nodes) if p)


def _adf_list_items(node, ordered=False):
    attrs = node.get("attrs") or {}
    start = 1
    if ordered:
        try:
            start = int(attrs.get("order", 1))
        except (TypeError, ValueError):
            start = 1
    lines, n = [], start
    for item in node.get("content") or []:
        text = _adf_text(item).strip()
        if not text:
            continue
        if ordered and isinstance(item, dict):
            idx = (item.get("attrs") or {}).get("index")
            if idx is not None:
                try:
                    n = int(idx)
                except (TypeError, ValueError):
                    pass
        if ordered:
            prefix = f"{n}. "
            n += 1
        else:
            prefix = "- "
        lines.append(prefix + text.replace("\n", "\n" + (" " * len(prefix))))
    return "\n".join(lines)


def _adf_text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return _adf_join(node, "\n")
    if not isinstance(node, dict):
        return ""
    ntype = node.get("type") or ""
    attrs = node.get("attrs") or {}
    content = node.get("content") or []
    if ntype == "text":
        text = node.get("text") or ""
        for mark in node.get("marks") or []:
            if isinstance(mark, dict) and mark.get("type") == "link":
                href = (mark.get("attrs") or {}).get("href") or ""
                if href:
                    return f"{text} ({href})"
        return text
    if ntype == "hardBreak":
        return "\n"
    if ntype == "mention":
        return attrs.get("text") or (f"@{attrs['id']}" if attrs.get("id") else "")
    if ntype == "emoji":
        return attrs.get("shortName") or node.get("text") or attrs.get("text") or ""
    if ntype == "status":
        return attrs.get("text") or ""
    if ntype in ("inlineCard", "blockCard", "media", "mediaSingle"):
        return attrs.get("url") or _adf_join(content, "")
    if ntype == "rule":
        return "---"
    if ntype == "heading":
        try:
            level = max(1, min(6, int(attrs.get("level") or 1)))
        except (TypeError, ValueError):
            level = 1
        return f"{'#' * level} {_adf_join(content, '')}".rstrip()
    if ntype == "paragraph":
        return _adf_join(content, "")
    if ntype == "bulletList":
        return _adf_list_items(node, ordered=False)
    if ntype == "orderedList":
        return _adf_list_items(node, ordered=True)
    if ntype == "listItem":
        return _adf_join(content, "\n")
    if ntype == "codeBlock":
        lang = attrs.get("language") or ""
        inner = "".join(_adf_text(c) for c in content)
        return f"```{lang}\n{inner}\n```"
    if ntype == "blockquote":
        inner = _adf_join(content, "\n")
        if not inner:
            return ""
        return "\n".join(("> " + line) if line else ">" for line in inner.splitlines())
    if ntype == "table":
        rows = []
        for row in content:
            cells = []
            for cell in (row.get("content") if isinstance(row, dict) else None) or []:
                cells.append(_adf_text(cell).replace("\n", " ").strip())
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows)
    if content:
        return _adf_join(content, "\n")
    return ""


def _jira_field_text(value):
    """Flatten a Jira string or ADF doc. Other shapes (Sprint, points) are empty."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict) and (value.get("type") or "content" in value):
        return _adf_text(value).strip()
    return ""


def _jira_description(fields):
    desc = fields.get("description") or ""
    if isinstance(desc, dict):
        return _adf_text(desc).strip()
    return str(desc)


def _jira_name(obj):
    if isinstance(obj, dict):
        return (obj.get("name") or "").strip()
    return ""


def _jira_custom_sections(fields, names):
    """Allowlisted customfield_* → (heading, text). Regex is locked in bin/README.md."""
    out = []
    for fid, value in fields.items():
        if not str(fid).startswith("customfield_"):
            continue
        label = (names or {}).get(fid) or ""
        if not JIRA_CUSTOM_RE.search(label):
            continue
        text = _jira_field_text(value)
        if text:
            out.append((label, text))
    return out


def _jira_comment_sections(fields):
    blob = fields.get("comment") or {}
    comments = blob.get("comments") if isinstance(blob, dict) else None
    if not comments:
        return []
    out = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        text = _jira_field_text(c.get("body"))
        if not text:
            continue
        author = ((c.get("author") or {}).get("displayName") or "").strip() or "unknown"
        created = str(c.get("created") or "")
        date = created[:10] if created else ""
        out.append((author, date, text))
    return out


def _jira_spec_text(fields, names=None):
    """Flattened description + allowlisted custom + comments. Blank ⇒ no spec."""
    desc = _jira_description(fields)
    parts = [desc.strip()] if desc.strip() else []
    parts.extend(text for _heading, text in _jira_custom_sections(fields, names))
    parts.extend(text for _a, _d, text in _jira_comment_sections(fields))
    return "\n".join(parts).strip()


def _jira_metadata(key, fields):
    extras = [_jira_name(fields.get(k)) for k in ("issuetype", "status", "priority")]
    extras = [n for n in extras if n]
    lines = [f"{key}  " + "  ·  ".join(extras) if extras else key]
    labels = fields.get("labels")
    if isinstance(labels, list) and labels:
        joined = ", ".join(str(x) for x in labels if x is not None and x != "")
        if joined:
            lines.append(f"Labels: {joined}")
    parent = fields.get("parent")
    if isinstance(parent, dict) and parent.get("key"):
        summary = ((parent.get("fields") or {}).get("summary") or "").strip()
        lines.append(f"Parent: {parent['key']}" + (f" {summary}" if summary else ""))
    return "\n".join(lines)


def _jira_body(key, fields, names=None):
    desc = _jira_description(fields)
    custom = _jira_custom_sections(fields, names)
    comments = _jira_comment_sections(fields)
    if not ((desc or "").strip() or custom or comments):
        return ""
    chunks = [_jira_metadata(key, fields)]
    if desc.strip():
        chunks.append("## Description\n\n" + desc.rstrip())
    for heading, text in custom:
        chunks.append(f"## {heading}\n\n{text.rstrip()}")
    if comments:
        blocks = []
        for author, date, text in comments:
            head = f"**{author}** ({date}):" if date else f"**{author}**:"
            blocks.append(f"{head}\n{text.rstrip()}")
        chunks.append("## Comments\n\n" + "\n\n".join(blocks))
    return "\n\n".join(chunks)


def fetch_jira(raw, cfg=None, http_get=None, paths=None):
    keys = _jira_keys(raw)
    if not keys:
        raise ValueError("no Jira issue keys found in input")
    from . import jira as jiralib
    if paths is not None:
        creds = jiralib.resolve(paths, cfg)
        base = creds["site"]
        auth = jiralib.auth_header(creds)
    else:
        inbox = getattr(cfg, "inbox", None)
        base = (inbox.jira_base if inbox else "") or ""
        token = ""
        if inbox and getattr(inbox, "jira_token_env", ""):
            token = os.environ.get(inbox.jira_token_env, "")
        auth = jiralib.auth_header({"email": "", "token": token})
    if not base or not auth:
        raise ValueError(
            "Jira credentials missing or incomplete; set site, email, and token "
            "via `conveyor intake jira` or Intake settings → Jira"
        )
    base = jiralib.origin(base)
    getter = http_get or _http_get
    items = []
    for key in keys:
        url = f"{base}/browse/{key}"
        api = f"{base}/rest/api/3/issue/{key}?expand=names"
        try:
            data = json.loads(getter(api, {
                "Authorization": auth,
                "Accept": "application/json",
            }))
            fields = data.get("fields") or {}
            items.append({
                "title": fields.get("summary") or key,
                "body": _jira_body(key, fields, data.get("names") or {}),
                "url": url,
                "external_id": key,
                "source": "jira",
            })
        except urllib.error.HTTPError as e:
            items.append({
                "external_id": key,
                "source": "jira",
                "error": {"status": e.code, "message": str(e.reason) or str(e)},
            })
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError,
                OSError, ValueError) as e:
            items.append({
                "external_id": key,
                "source": "jira",
                "error": {"status": 0, "message": str(e)},
            })
    return items
