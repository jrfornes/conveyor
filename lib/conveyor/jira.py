"""Jira credentials in .conveyor/local/jira.json (gitignored, mode 600).

Auth is Basic base64(email:token). Bearer never worked against Atlassian Cloud.
"""
import base64
import contextlib
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

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


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def _same_origin(a, b):
    pa, pb = urlsplit(a), urlsplit(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def _stream_to(resp, dest, max_bytes):
    cl = resp.headers.get("Content-Length")
    if cl is not None:
        try:
            nlen = int(cl)
        except ValueError:
            nlen = None
        if nlen is not None and nlen > max_bytes:
            raise ValueError(f"attachment exceeds {max_bytes} bytes")
    tmp = dest + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    n = 0
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                n += len(chunk)
                if n > max_bytes:
                    raise ValueError(f"attachment exceeds {max_bytes} bytes")
                f.write(chunk)
        os.replace(tmp, dest)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def download_content(url, dest, headers, max_bytes, timeout=15):
    """Stream url to dest via dest.tmp + rename.

    First hop is authenticated on the Jira origin. A single cross-host 302
    (Cloud CDN) is followed without Authorization. Any other redirect or
    off-site hop fails closed. Does not use urlopen (which never follows
    cross-host).
    """
    opener = urllib.request.build_opener(_NoRedirectHandler())
    current = url
    hdrs = dict(headers or {})
    cdn_used = False
    hops = 0
    while True:
        hops += 1
        if hops > 6:
            raise urllib.error.HTTPError(
                current, 302, "refusing redirect loop", hdrs, None)
        req = urllib.request.Request(current, headers=hdrs)
        try:
            with opener.open(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(
                        current, resp.status, f"unexpected status {resp.status}",
                        resp.headers, None)
                _stream_to(resp, dest, max_bytes)
                return
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303, 307, 308):
                raise
            loc = e.headers.get("Location") if e.headers else None
            if not loc:
                raise urllib.error.HTTPError(
                    current, e.code, "redirect with no Location", e.headers, None)
            nxt = urljoin(current, loc)
            if _same_origin(current, nxt):
                if cdn_used:
                    raise urllib.error.HTTPError(
                        current, e.code, "refusing further redirect", e.headers, None)
                current = nxt
                continue
            if e.code != 302 or cdn_used:
                raise urllib.error.HTTPError(
                    current, e.code, "refusing cross-host redirect", e.headers, None)
            cdn_used = True
            current = nxt
            hdrs = {k: v for k, v in hdrs.items() if k.lower() != "authorization"}


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
