"""Vendor-agnostic inbox adapters. fetch(kind, raw) → list of ticket dicts.

A later GitHub/Linear adapter is one function with the same return shape.
"""
import json
import re
import urllib.error
import urllib.request

JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


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
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode()


def _jira_keys(raw):
    seen, keys = set(), []
    for m in JIRA_KEY.finditer(raw or ""):
        k = m.group(1)
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def _jira_description(fields):
    desc = fields.get("description") or ""
    if isinstance(desc, dict):
        return _adf_text(desc).strip()
    return str(desc)


def _adf_text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        parts = [_adf_text(c) for c in node.get("content") or []]
        joiner = "\n" if node.get("type") in ("paragraph", "heading", "listItem") else ""
        return joiner.join(p for p in parts if p)
    if isinstance(node, list):
        return "\n".join(_adf_text(n) for n in node)
    return ""


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
        # Duck-typed tests have no email → no Basic header → skip fetch.
        auth = ""
    getter = http_get or _http_get
    items = []
    for key in keys:
        url = f"{base.rstrip('/')}/browse/{key}" if base else key
        body, title = "", key
        if base and auth:
            api = f"{base.rstrip('/')}/rest/api/3/issue/{key}"
            try:
                data = json.loads(getter(api, {
                    "Authorization": auth,
                    "Accept": "application/json",
                }))
                fields = data.get("fields") or {}
                title = fields.get("summary") or key
                body = _jira_description(fields)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                    json.JSONDecodeError, OSError, ValueError):
                body = ""
        items.append({
            "title": title,
            "body": body,
            "url": url if base else "",
            "external_id": key,
            "source": "jira",
        })
    return items
