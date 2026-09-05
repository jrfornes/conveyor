"""Saved workflow presets: `.conveyor/workflows/<slug>.json` + `.conveyor/active`.

`conveyor.conf` stays the single source of truth for the ACTIVE pipeline — it is
what the role loops and `bin/handoff.sh` read, and what `config.routes()` derives
the permitted handoff triples from. A preset is a saved *shape* layered on top;
`activate()` regenerates `conveyor.conf` from one.

JSON convention (this module is the repo's first persisted JSON; follow it):
`json.dumps(obj, indent=2)` with an explicit key order, plus a trailing newline,
written through `util.atomic_write`. Read with `json.loads(util.read_text(path))`.

Identity: the slug is the filename and nothing else. It is allocated once at
create time and never changes, so renaming a workflow cannot orphan
`.conveyor/active` (same reasoning as the stable item id in `inbox.py`).
"""
import json
import os
import re

from . import config, layout, util

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")
KEYS = ("name", "description", "roles", "gate")

# Ceilings for the shipped roles, so activating a seed reproduces exactly what
# `conveyor pack two|three` used to write. Anything else takes Role's defaults.
ROLE_DEFAULTS = {
    "specifier": (3, 60, 2),
    "coder": (3, 120, 3),
    "reviewer": (3, 60, 2),
}

SEEDS = (
    {
        "slug": "review-belt",
        "name": "Review belt",
        "description": "coder → reviewer. No spec hold — the operator already "
                       "approved the task file.",
        "roles": ["coder", "reviewer"],
        "gate": None,
    },
    {
        "slug": "spec-then-build",
        "name": "Spec then build",
        "description": "specifier → coder → reviewer. The first handoff after the "
                       "specifier is held for you to approve.",
        "roles": ["specifier", "coder", "reviewer"],
        "gate": "specifier",
    },
    {
        "slug": "spec-no-gate",
        "name": "Spec, no gate",
        "description": "specifier → coder → reviewer with no human gate. Every "
                       "handoff goes straight to the next role.",
        "roles": ["specifier", "coder", "reviewer"],
        "gate": None,
    },
    {
        "slug": "solo-coder",
        "name": "Solo coder",
        "description": "coder alone. No second look; pass goes straight to done.",
        "roles": ["coder"],
        "gate": None,
    },
)


class PresetError(ValueError):
    """Bad preset shape. Subclasses ValueError so httpd maps it to 400."""


def slug(name):
    """`inbox.slug` shape: lowercase, punctuation collapsed to '-'. '' if unusable."""
    s = _NON_SLUG.sub("-", (name or "").lower()).strip("-")[:48]
    return s if s and SLUG_RE.match(s) else ""


def path(paths, s):
    return os.path.join(paths.workflows, f"{s}.json")


def rel_path(s):
    """Display path, as the UI and CLI print it."""
    return f".conveyor/workflows/{s}.json"


def exists(paths, s):
    return os.path.isfile(path(paths, s))


# --- validation ---------------------------------------------------------


def validate(root, data):
    """Return a normalized preset dict. Raises PresetError (-> HTTP 400)."""
    if not isinstance(data, dict):
        raise PresetError("workflow must be an object")
    name = (data.get("name") or "").strip()
    if not name:
        raise PresetError("name is required")
    if not slug(name):
        raise PresetError("name must contain at least one letter or digit; "
                          'repair: use a name like "Review belt"')

    roles = data.get("roles")
    if not isinstance(roles, (list, tuple)) or not roles:
        raise PresetError("roles must list at least one role")
    roles = [str(r).strip() for r in roles]
    seen = set()
    for r in roles:
        if not config.ROLE_RE.match(r) or r in config.RESERVED:
            raise PresetError(f"invalid role name {r!r}")
        if r in seen:
            raise PresetError(f"role {r!r} appears twice; a role may be on the "
                              f"belt at most once")
        seen.add(r)
        if not os.path.isfile(os.path.join(root, "roles", f"{r}.md")):
            raise PresetError(f"unknown role {r!r}; create roles/{r}.md first")

    gate = data.get("gate") or None
    if gate is not None:
        gate = str(gate).strip() or None
    if gate is not None:
        # Same sentences as config.py, so the operator reads one message
        # whichever layer refuses.
        if gate not in roles:
            raise PresetError(f"gate names a role that is not on this belt: {gate!r}; "
                              f"repair: gate one of {', '.join(roles)}")
        if gate == roles[-1]:
            raise PresetError(f"cannot gate {gate!r}, the last role — its handoff goes "
                              f"to done, not to another role; repair: gate a role "
                              f"before it, or set gate to null")

    return {
        "name": name,
        "description": (data.get("description") or "").strip(),
        "roles": roles,
        "gate": gate,
    }


def routes(preset):
    """Belt edges for a preset, by config.routes()'s rule minus the intake edge.

    Deliberately not shared with `config.routes()`: that function's extra
    `ticket-reviewer -> operator` edge is load-bearing for bin/handoff.sh.
    """
    n = list(preset["roles"])
    out = [{"from": "operator", "to": n[0], "verdict": "ready"}]
    for a, b in zip(n, n[1:]):
        out.append({"from": a, "to": b, "verdict": "ready"})
    out.append({"from": n[-1], "to": "done", "verdict": "pass"})
    if len(n) > 1:
        out.append({"from": n[-1], "to": n[-2], "verdict": "findings"})
    return out


# --- read / write -------------------------------------------------------


def _render(data):
    return json.dumps({k: data[k] for k in KEYS}, indent=2, ensure_ascii=False) + "\n"


def _write(paths, s, data):
    os.makedirs(paths.workflows, exist_ok=True)
    util.atomic_write(path(paths, s), _render(data))
    return {**data, "slug": s}


def load(paths, s):
    """Raises FileNotFoundError (-> HTTP 404) when the slug is unknown."""
    p = path(paths, s)
    try:
        raw = json.loads(util.read_text(p))
    except FileNotFoundError:
        raise FileNotFoundError(f"no workflow {s!r}")
    except ValueError as e:
        raise PresetError(f"{rel_path(s)} is not valid JSON: {e}")
    if not isinstance(raw, dict):
        raise PresetError(f"{rel_path(s)} must contain an object")
    return {
        "slug": s,
        "name": raw.get("name") or s,
        "description": raw.get("description") or "",
        "roles": list(raw.get("roles") or []),
        "gate": raw.get("gate") or None,
    }


def load_all(paths):
    """Every readable preset, by display name. Unparseable files are skipped."""
    out = []
    try:
        names = sorted(os.listdir(paths.workflows))
    except FileNotFoundError:
        return out
    for f in names:
        if not f.endswith(".json"):
            continue
        try:
            out.append(load(paths, f[:-5]))
        except (PresetError, OSError):
            continue
    return sorted(out, key=lambda p: p["name"].lower())


def allocate_slug(paths, name):
    """`inbox.allocate_id` shape: base, base-2, base-3 …"""
    base = slug(name)
    if not base:
        raise PresetError("name must contain at least one letter or digit")
    if not exists(paths, base):
        return base
    n = 2
    while exists(paths, f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"


def create(root, paths, data):
    clean = validate(root, data)
    return _write(paths, allocate_slug(paths, clean["name"]), clean)


def save(root, paths, s, data):
    """Overwrite an existing preset. The slug never moves (see module docstring)."""
    current = load(paths, s)
    merged = {**current, **{k: v for k, v in data.items() if k in KEYS}}
    return _write(paths, s, validate(root, merged))


def delete(paths, cfg, s):
    with util.lock(paths.workflows_lock):
        preset = load(paths, s)
        all_slugs = [p["slug"] for p in load_all(paths)]
        active_slug, _ = resolve(paths, cfg)
        if active_slug == s:
            raise RuntimeError(
                f"{preset['name']} is active; make another workflow active first")
        if len(all_slugs) <= 1:
            raise RuntimeError(
                f"{preset['name']} is the only workflow; Conveyor keeps at least one")
        os.remove(path(paths, s))


def ensure_seeded(paths):
    """One-shot seed. Directory-exists is the marker, so a deleted seed stays deleted."""
    if os.path.isdir(paths.workflows):
        return
    for seed in SEEDS:
        _write(paths, seed["slug"], seed)


# --- active marker ------------------------------------------------------


def read_active(paths):
    try:
        return util.read_text(paths.active).strip()
    except OSError:
        return ""


def matches(preset, cfg):
    return preset["roles"] == cfg.names() and preset["gate"] == cfg.gate_role()


def resolve(paths, cfg):
    """(slug, status) where status is 'active' | 'modified' | 'custom'.

    Never trusts `.conveyor/active` blindly: a preset that actually matches
    conveyor.conf wins, which self-heals a marker left stale by a crash between
    activate()'s two writes. The comparison is (roles, gate) only — a model or
    ceiling edit is not "modified", because presets do not carry models.
    """
    marker = read_active(paths)
    presets = load_all(paths)
    hits = [p["slug"] for p in presets if matches(p, cfg)]
    if hits:
        return (marker if marker in hits else hits[0]), "active"
    if marker and any(p["slug"] == marker for p in presets):
        return marker, "modified"
    return None, "custom"


def activate(root, paths, cfg, s):
    """Rewrite conveyor.conf from a preset. Returns {"preset", "dropped"}."""
    preset = load(paths, s)
    validate(root, preset)  # roles must still exist on disk
    with util.lock(paths.workflows_lock):
        # The lock does not cover `conveyor start`, so a loop started between
        # this check and the save would be stranded. Negligible for one operator.
        live = layout.running_roles(paths, cfg)
        if live:
            raise RuntimeError(
                f"loops are running ({', '.join(live)}); run `conveyor stop` first — "
                f"switching now would strand them on roles this workflow no longer "
                f"configures")
        existing = {r.name: r for r in cfg.roles}
        fallback = cfg.roles[0]
        new_roles = []
        for name in preset["roles"]:
            role = existing.get(name)
            if role is None:
                mr, mm, ma = ROLE_DEFAULTS.get(name, (3, 120, 3))
                role = config.Role(name, fallback.model, mr, mm, ma)
            new_roles.append(role)  # reused object keeps model, ceilings and args
        dropped = [n for n in cfg.names() if n not in preset["roles"]]
        cfg.roles = new_roles
        cfg.gate = preset["gate"] or config.NO_GATE
        # conveyor.conf first: a crash before the marker leaves the pipeline
        # correct and only the cosmetic marker stale. The reverse is worse.
        config.save(root, cfg)
        util.atomic_write(paths.active, s + "\n")
    return {"preset": preset, "dropped": dropped}
