"""Role library CRUD and skill assignment sidecars.

Coding roles live in `roles/<name>.md` with optional `roles/<name>.skills`.
Assignments are injected into each worktree at `conveyor start`; they are not
stored in `conveyor.conf` so library roles can carry skills off-belt.
"""
import os
import re
import shutil

from . import config, presets, util

REQUIRED_ROLE_HEADINGS = ("Owns", "Does not own")
INTAKE_EXCLUDED = "ticket-reviewer"
CONTRACT_HEADING = "Handoff contract"

# Repo-root catalogs only; `.agents/skills` wins on duplicate names.
SKILL_CATALOGS = (".agents/skills", ".cursor/skills")

_ROLE_STUB = """# Role: {name}

## Owns

- (describe what this role owns)

## Does not own

- (describe what this role does not own)
"""


class RoleError(ValueError):
    """Bad role name, sidecar, or delete guard. Maps to HTTP 400 / util.die."""


def md_path(root, name):
    return os.path.join(root, "roles", f"{name}.md")


def skills_path(root, name):
    return os.path.join(root, "roles", f"{name}.skills")


def resolve_skill(root, name):
    """Return `(rel_catalog, abs_dir)` when `<catalog>/<name>/SKILL.md` exists."""
    for rel in SKILL_CATALOGS:
        abs_dir = os.path.join(root, rel, name)
        if os.path.isfile(os.path.join(abs_dir, "SKILL.md")):
            return rel, abs_dir
    return None, None


def skill_dir(root, name):
    """Absolute path to the winning skill tree, or `.cursor/skills/<name>`."""
    _, abs_dir = resolve_skill(root, name)
    if abs_dir:
        return abs_dir
    return os.path.join(root, ".cursor", "skills", name)


def validate_name(name):
    if not config.ROLE_RE.match(name):
        raise RoleError(f"invalid role name {name!r}")
    if name in config.RESERVED or name == INTAKE_EXCLUDED:
        raise RoleError(f"reserved role: {name}")


def validate_role_text(text):
    for heading in REQUIRED_ROLE_HEADINGS:
        if not re.search(rf"^#+\s+{re.escape(heading)}\s*$", text, re.M):
            raise RoleError(f"role file must include heading {heading!r}")


def has_handwritten_contract(text):
    """True when a role file still carries its own `## Handoff contract` heading.

    The section is now generated from conveyor.conf (see render_contract); a
    hand-written one is accepted but overridden, and `conveyor start` warns.
    """
    return bool(re.search(rf"^#+\s+{re.escape(CONTRACT_HEADING)}\s*$", text, re.M))


# The "When" column, keyed by verdict. Matches constitution/handoffs.md's
# two-pack example so the generated block reads the same as the process layer.
_VERDICT_WHEN = {
    "ready": "Task done and verified",
    "findings": "Something is missing or wrong",
    "pass": "Every requirement is proven",
}
# Row order within the table: `ready` first, then `findings`, then `pass`.
_VERDICT_ORDER = {"ready": 0, "findings": 1, "pass": 2}

_DRAFT_BLOCK = (
    "Write exactly this to ./tmp/handoff.txt, then run "
    "handoff.sh ./tmp/handoff.txt:\n\n"
    "    to: <role or done>\n"
    "    task: <task name from your prompt>\n"
    "    verdict: <ready | pass | findings>\n"
)


def render_contract(cfg, name):
    """The generated `## Handoff contract` block for role `name`.

    Pure function of `cfg.routes()`, `cfg.names()`, `cfg.gate_role()`, and
    `name` (decision 2 of docs/plans/generated-handoff-contract.md). Raises
    RoleError for a name not on the active belt.
    """
    names = cfg.names()
    if name not in names:
        raise RoleError(f"role {name!r} is not on the active workflow")
    i = names.index(name)
    is_first = i == 0
    is_penultimate = i == len(names) - 2  # -1 when len == 1; never matches

    rows = sorted(
        ((a, to, v) for (a, to, v) in cfg.routes() if a == name),
        key=lambda r: _VERDICT_ORDER.get(r[2], 9),
    )

    table = ["| You are | to | verdict | When |", "|---|---|---|---|"]
    for _, to, v in rows:
        table.append(f"| {name} | {to} | {v} | {_VERDICT_WHEN.get(v, '')} |")

    # Each entry is one paragraph; blocks are joined by a blank line.
    blocks = [
        f"## {CONTRACT_HEADING}",
        "Generated from conveyor.conf at conveyor start. This section overrides "
        "any\nhand-written contract above it.",
        "\n".join(table),
    ]

    if cfg.gate_role() == name:
        blocks.append(
            "Your `ready` is held in `.conveyor/approvals/pending/` until the "
            "operator\napproves it; a rejection comes back as a `findings`-style "
            "body beginning\n`Rejected by operator:`.")

    if any(v == "findings" for _, _, v in rows):
        blocks.append(
            "For `findings`, HEAD must be a commit you made, not the one you "
            "received;\nan empty commit (`git commit --allow-empty`) whose "
            "message is the findings\nlist is the expected form.")

    receive = _receive_sentence(cfg, name, is_first, is_penultimate)
    if receive:
        blocks.append(receive)

    blocks.append(_DRAFT_BLOCK.rstrip("\n"))
    return "\n\n".join(blocks) + "\n"


def _receive_sentence(cfg, name, is_first, is_penultimate):
    """The "You receive ..." line for a role (every role receives a `ready`).

    Parentheticals ("(new task)", "(rework)") appear only for a first role,
    reproducing the shipped coder.md prose for the two-pack.
    """
    names = cfg.names()
    i = names.index(name)
    clauses = []
    if is_first:
        clauses.append("`ready` from operator (new task)")
    else:
        clauses.append(f"`ready` from {names[i - 1]}")
    if is_penultimate:
        last = names[-1]
        clauses.append(f"`findings` from {last} (rework)" if is_first
                       else f"`findings` from {last}")
    return "You receive " + " and ".join(clauses) + "."


def list_names(root):
    """Every `roles/*.md` except ticket-reviewer."""
    d = os.path.join(root, "roles")
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md"):
            continue
        name = f[:-3]
        if name == INTAKE_EXCLUDED:
            continue
        out.append(name)
    return out


def create(root, name, from_name=None):
    validate_name(name)
    path = md_path(root, name)
    if os.path.isfile(path):
        raise RoleError(f"role {name!r} already exists")
    if from_name:
        validate_name(from_name)
        src = md_path(root, from_name)
        if not os.path.isfile(src):
            raise RoleError(f"unknown role {from_name!r}; create roles/{from_name}.md first")
        util.atomic_write(path, util.read_text(src))
        src_sk = skills_path(root, from_name)
        if os.path.isfile(src_sk):
            util.atomic_write(skills_path(root, name), util.read_text(src_sk))
    else:
        util.atomic_write(path, _ROLE_STUB.format(name=name))
    return path


def delete(root, paths, cfg, name):
    validate_name(name)
    path = md_path(root, name)
    if not os.path.isfile(path):
        raise RoleError(f"unknown role {name!r}; create roles/{name}.md first")
    if name in cfg.names():
        raise RoleError(
            f"cannot delete {name!r}: on the active belt; "
            f"repair: take it off the workflow first")
    for p in presets.load_all(paths):
        if name in p["roles"]:
            raise RoleError(
                f"cannot delete {name!r}: used by workflow {p['slug']!r}; "
                f"repair: edit or delete that preset")
    os.remove(path)
    sk = skills_path(root, name)
    if os.path.isfile(sk):
        os.remove(sk)


def _parse_skills_sidecar(text):
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ".." in line or "/" in line:
            raise RoleError(f"invalid skill name {line!r}")
        out.append(line)
    return out


def read_skills(root, name):
    path = skills_path(root, name)
    if not os.path.isfile(path):
        return []
    return _parse_skills_sidecar(util.read_text(path))


def _skill_description(skill_md):
    text = util.read_text(skill_md)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            block = text[3:end]
            for line in block.splitlines():
                if line.strip().startswith("description:"):
                    val = line.split(":", 1)[1].strip().strip("'\"")
                    if val:
                        return val
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("---"):
            return s
    return ""


def _skill_repair_hint(name):
    return (
        f"add .agents/skills/{name}/SKILL.md or .cursor/skills/{name}/SKILL.md "
        f"or drop it from roles/<role>.skills")


def available_skills(root):
    """Discover repo-root `.agents/skills` and `.cursor/skills` trees."""
    by_name = {}
    for rel in reversed(SKILL_CATALOGS):
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for skill_name in os.listdir(base):
            skill_md = os.path.join(base, skill_name, "SKILL.md")
            if os.path.isfile(skill_md):
                by_name[skill_name] = {
                    "name": skill_name,
                    "description": _skill_description(skill_md),
                    "source": rel,
                }
    return [by_name[k] for k in sorted(by_name)]


def assigned_skills(root, name):
    return read_skills(root, name)


def write_skills(root, name, skills):
    validate_name(name)
    if not os.path.isfile(md_path(root, name)):
        raise RoleError(f"unknown role {name!r}; create roles/{name}.md first")
    avail = {s["name"] for s in available_skills(root)}
    clean = []
    seen = set()
    for raw in skills:
        s = str(raw).strip()
        if not s:
            raise RoleError(f"invalid skill name {raw!r}")
        if ".." in s or "/" in s:
            raise RoleError(f"invalid skill name {s!r}")
        if s not in avail:
            raise RoleError(f"unknown skill {s!r}; repair: {_skill_repair_hint(s)}")
        if s in seen:
            continue
        seen.add(s)
        clean.append(s)
    body = "\n".join(clean) + ("\n" if clean else "")
    util.atomic_write(skills_path(root, name), body)


def _assigned_skills_block(root, names):
    if not names:
        return ""
    lines = ["\n\n## Assigned skills\n"]
    for n in names:
        rel, _ = resolve_skill(root, n)
        path = f"{rel}/{n}/" if rel else f".cursor/skills/{n}/"
        lines.append(f"- `{n}` (`{path}`)\n")
    return "".join(lines)


def _remove_worktree_skill(wt, name):
    for rel in SKILL_CATALOGS:
        dest = os.path.join(wt, rel, name)
        if os.path.exists(dest):
            shutil.rmtree(dest)


def inject_skills(root, wt, name):
    """Copy assigned skill trees into the worktree; return mdc suffix.

    Raises RoleError when an assigned skill directory is missing on disk.
    """
    assigned = read_skills(root, name)
    if not assigned:
        return ""
    for skill in assigned:
        rel, src = resolve_skill(root, skill)
        if not rel:
            raise RoleError(
                f"assigned skill {skill!r} is missing; repair: "
                f"{_skill_repair_hint(skill)} or run conveyor role skills "
                f"{name} --set ...")
        _remove_worktree_skill(wt, skill)
        dest = os.path.join(wt, rel, skill)
        shutil.copytree(src, dest)
    return _assigned_skills_block(root, assigned)
