"""Jira credentials in .conveyor/local/jira.json (gitignored, mode 600).

Auth is Basic base64(email:token). Bearer never worked against Atlassian Cloud.
"""
import base64
import json
import os
import urllib.error
import urllib.request

from . import util


def read(paths):
    """{site, email, token}; missing or corrupt file reads as empty strings."""
    empty = {"site": "", "email": "", "token": ""}
    try:
        data = json.loads(util.read_text(paths.jira))
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    return {
        "site": str(data.get("site") or ""),
        "email": str(data.get("email") or ""),
        "token": str(data.get("token") or ""),
    }


def write(paths, site, email, token):
    os.makedirs(paths.local, exist_ok=True)
    payload = json.dumps({"site": site, "email": email, "token": token}, indent=2) + "\n"
    util.atomic_write(paths.jira, payload)
    os.chmod(paths.jira, 0o600)


def clear(paths):
    if os.path.isfile(paths.jira):
        os.remove(paths.jira)


def resolve(paths, cfg):
    """Merge jira.json over [inbox] fallbacks. Email can only come from the file."""
    stored = read(paths)
    inbox = getattr(cfg, "inbox", None) if cfg is not None else None
    site = stored["site"] or ((inbox.jira_base if inbox else "") or "")
    token = stored["token"]
    if not token:
        env = (inbox.jira_token_env if inbox else "") or ""
        token = os.environ.get(env, "") if env else ""
    return {"site": site, "email": stored["email"], "token": token}


def auth_header(creds):
    """Basic base64(email:token), or "" when either is missing."""
    email = (creds.get("email") or "").strip()
    token = (creds.get("token") or "").strip()
    if not email or not token:
        return ""
    raw = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
    return "Basic " + raw


def redact(creds):
    """{site, email, token_set} — the token never enters an HTTP response."""
    return {
        "site": creds.get("site") or "",
        "email": creds.get("email") or "",
        "token_set": bool(creds.get("token")),
    }


def check(paths, cfg):
    """GET /rest/api/3/myself. Strictly out of the import path."""
    creds = resolve(paths, cfg)
    auth = auth_header(creds)
    site = (creds.get("site") or "").rstrip("/")
    if not site or not auth:
        return {"ok": False, "status": 0, "message": "missing site, email, or token"}
    url = f"{site}/rest/api/3/myself"
    req = urllib.request.Request(url, headers={
        "Authorization": auth,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "status": resp.status, "message": "ok"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "message": str(e.reason) or str(e)}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "status": 0, "message": str(e)}
