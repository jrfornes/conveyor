"""Role avatars and header chrome for the active pipeline.

Workflow identity lives in `presets`; nothing here is a protocol object.
"""
import os

AVATARS = {
    "specifier": {
        "icon": "edit_note",
        "color": "#5c6bc0",
        "owns": "Localize the task to this repository",
    },
    "coder": {
        "icon": "code",
        "color": "#00897b",
        "owns": "Implement and prove the task",
    },
    "reviewer": {
        "icon": "fact_check",
        "color": "#ef6c00",
        "owns": "Verify the coder's commit",
    },
    "ticket-reviewer": {
        "icon": "inbox",
        "color": "#7b1fa2",
        "owns": "Grade and rewrite incoming tickets",
    },
    "operator": {
        "icon": "person",
        "color": "#546e7a",
        "owns": "You. Tasks, intake, approve.",
    },
    "needs-human": {
        "icon": "back_hand",
        "color": "#c62828",
        "owns": "Parked; only the operator moves it",
    },
    "done": {
        "icon": "check_circle",
        "color": "#2e7d32",
        "owns": "Merged to main",
    },
}

_FALLBACK_AVATAR = {"icon": "person_outline", "color": "#78909c", "owns": ""}


def avatar(name):
    a = AVATARS.get(name, _FALLBACK_AVATAR)
    return {"icon": a["icon"], "color": a["color"], "owns": a["owns"]}


def describe(paths, cfg):
    """Header chrome for the active pipeline: {id, name, chain, status}.

    Identity comes from the saved presets (`presets.resolve`), never from a
    hardcoded catalog: `id` is the matching slug, or "custom" when
    conveyor.conf is a shape no preset describes.
    """
    from . import presets
    slug, status = presets.resolve(paths, cfg)
    chain = cfg.chain_label()
    if slug is None:
        return {"id": "custom", "name": "Custom", "chain": chain, "status": status}
    return {"id": slug, "name": presets.load(paths, slug)["name"],
            "chain": chain, "status": status}


def library_roles(root, cfg):
    """roles/*.md names not in the active belt.

    ticket-reviewer is excluded so an un-migrated repo's stale
    roles/ticket-reviewer.md cannot appear as a library role.
    """
    belt = set(cfg.names())
    names = []
    roles_dir = os.path.join(root, "roles")
    if not os.path.isdir(roles_dir):
        return names
    for f in sorted(os.listdir(roles_dir)):
        if not f.endswith(".md"):
            continue
        name = f[:-3]
        if name in belt or name == "ticket-reviewer":
            continue
        names.append(name)
    return names
