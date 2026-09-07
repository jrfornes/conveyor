"""Jira credentials in .conveyor/local/jira.json (gitignored, mode 600).

Auth is Basic base64(email:token). Bearer never worked against Atlassian Cloud.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import util

_ORIGIN_ERR = "site must be https://… (http://127.0.0.1 is allowed for local Jira)"


def origin(site):
    """Canonical Jira base URL: https (http loopback only), /browse stripped."""
    site = (site or "").strip()
    if not site:
        raise ValueError("missing site")
    parts = urlsplit(site)
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(_ORIGIN_ERR)
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError(_ORIGIN_ERR)
    if scheme == "http" and host not in ("127.0.0.1", "localhost"):
        raise ValueError(_ORIGIN_ERR)
    path = parts.path or ""
    if path == "/browse" or path.startswith("/browse/"):
        path = ""
    netloc = parts.netloc
    return f"{scheme}://{netloc}{path}".rstrip("/")


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        orig = urlsplit(req.full_url)
        dest = urlsplit(newurl)
        if (orig.scheme, orig.netloc) != (dest.scheme, dest.netloc):
            raise urllib.error.HTTPError(
                req.full_url, code, "refusing cross-host redirect", headers, fp)
        return urllib.request.HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl)


def urlopen(url, headers, timeout=15):
    """urllib opener that refuses cross-host redirects (keeps Basic auth local)."""
    opener = urllib.request.build_opener(_SameOriginRedirectHandler())
    req = urllib.request.Request(url, headers=headers)
    return opener.open(req, timeout=timeout)


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
    site = origin(site)
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
    site = (creds.get("site") or "").strip()
    if not site or not auth:
        return {"ok": False, "status": 0, "message": "missing site, email, or token"}
    try:
        site = origin(site)
    except ValueError as e:
        return {"ok": False, "status": 0, "message": str(e)}
    url = f"{site}/rest/api/3/myself"
    try:
        with urlopen(url, {
            "Authorization": auth,
            "Accept": "application/json",
        }) as resp:
            return {"ok": True, "status": resp.status, "message": "ok"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "message": str(e.reason) or str(e)}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "status": 0, "message": str(e)}
