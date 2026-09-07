"""Assemble /api/state from lib/conveyor (filesystem is source of truth)."""
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "lib"))

from conveyor import (  # noqa: E402
    agent, board, config, gates, handoff, intake as intakelib, jira as jiralib,
    layout, presets, queue, roles, util, workflows,
)


def resolve_root(root_arg=None):
    root = root_arg or os.environ.get("CONVEYOR_UI_ROOT")
    if root:
        root = os.path.realpath(root)
    else:
        root = layout.find_root()
    if not os.path.isfile(os.path.join(root, "conveyor.conf")):
        raise ValueError(f"no conveyor.conf in {root}")
    if not os.path.isdir(os.path.join(root, ".git")):
        raise ValueError(f"not a git checkout: {root}")
    return root


loop_pid = layout.loop_pid


def role_state(paths, cfg, role_name):
    rp = paths.role(role_name)
    role_cfg = cfg.role(role_name)
    running = bool(loop_pid(paths, role_name))
    stopped = os.path.exists(rp.stop)
    items = layout.handoffs(rp.in_process)
    done = layout.handoffs(rp.completed)
    last = None
    if done:
        try:
            last = handoff.read(os.path.join(rp.completed, done[-1]))[0].get("task")
        except handoff.ParseError:
            pass
    entry = {
        "role": role_name,
        "running": running,
        "stopped": stopped,
        "new_count": len(layout.handoffs(rp.new)),
        "last_completed": last,
    }
    if items:
        try:
            h = handoff.read(os.path.join(rp.in_process, items[0]))[0]
            age = util.age_seconds(h["dequeued_at"]) if "dequeued_at" in h else 0
            entry.update({
                "state": "busy" if running else "idle",
                "task": h.get("task"),
                "task_id": h.get("task_id"),
                "handoff_id": h.get("id"),
                "age_seconds": age,
                "attempt": int(h.get("attempt", 1)),
                "max_attempts": role_cfg.max_attempts,
            })
        except handoff.ParseError:
            entry["state"] = "busy" if running else "idle"
    else:
        entry["state"] = "idle" if running else "stopped"
    return entry


def needs_human(paths):
    out = []
    for p in sorted(queue.parked_items(paths)):
        task = os.path.basename(os.path.dirname(p))
        reason_path = os.path.join(os.path.dirname(p), "reason")
        try:
            lines = util.read_text(reason_path).split("\n")
            out.append({
                "task": task,
                "reason": lines[0] if lines else "unknown",
                "detail": lines[1] if len(lines) > 1 else "",
            })
        except OSError:
            out.append({"task": task, "reason": "unknown", "detail": ""})
    return out


def build_state(root):
    cfg = config.load(root)
    paths = layout.Paths(root)
    # board.tsv, not the .conveyor/ directory: reading workflow presets seeds
    # .conveyor/ on a repo that has never run, and that must not read as initialized.
    initialized = os.path.isfile(paths.board)
    lanes = cfg.names() + ["needs-human", "done"]
    tasks = []
    if initialized:
        for r in board.read(paths):
            tasks.append({
                "name": r["name"],
                "lane": r["lane"],
                "task_id": r["task_id"],
                "audit_count": int(r["audit_count"]),
                "retry_count": int(r["retry_count"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
    work = [role_state(paths, cfg, n) for n in cfg.names()] if initialized else []
    nh = needs_human(paths) if initialized else []
    running = any(w.get("running") for w in work) if work else False
    inbox_items = []
    approvals = []
    intake_busy_pid = loop_pid(paths, config.INTAKE_ROLE) if initialized else 0
    intake_busy_task = None
    if initialized:
        from conveyor import inbox as inbox_mod
        for it in inbox_mod.list_items(paths):
            if intake_busy_pid and it.get("status") in ("grading", "improving"):
                intake_busy_task = it["id"]
            inbox_items.append({
                "id": it["id"],
                "source": it.get("source", "-"),
                "title": it.get("title", it["id"]),
                "url": it.get("url", "-"),
                "external_id": it.get("external_id", "-"),
                "status": it.get("status", "imported"),
                "grade": it.get("grade", "-"),
                "created_at": it.get("created_at", ""),
                "task_name": it.get("task_name", "-"),
                "has_grade": it.get("has_grade", False),
                "has_proposed": it.get("has_proposed", False),
            })
        for a in queue.pending_approvals(paths):
            h = a["headers"]
            approvals.append({
                "id": h.get("id"),
                "task": h.get("task"),
                "from": h.get("from"),
                "to": h.get("to"),
                "commit": h.get("commit"),
                "file": a["file"],
            })
    return {
        "title": os.path.basename(root),
        "root": root,
        "initialized": initialized,
        "lanes": lanes,
        "avatars": {lane: workflows.avatar(lane) for lane in lanes},
        "roles": cfg.names(),
        "workflow": workflows.describe(paths, cfg),
        "tasks": tasks,
        "work": work,
        "needs_human": nh,
        "running": running,
        "inbox": inbox_items,
        "approvals": approvals,
        "intake": {"busy": bool(intake_busy_pid), "task": intake_busy_task},
    }


def read_task(root, name):
    if not handoff.TASK_RE.match(name):
        raise ValueError("invalid task name")
    path = os.path.join(root, "tasks", f"{name}.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(name)
    return util.read_text(path)


def read_logs(root, role, task=None):
    paths = layout.Paths(root)
    cfg = config.load(root)
    if role not in cfg.names():
        raise ValueError(f"unknown role: {role}")
    d = os.path.join(paths.logs, role)
    prefix = f"{task}_" if task else ""
    if not os.path.isdir(d):
        return {"filename": None, "events": []}
    logs = sorted(
        (os.path.getmtime(os.path.join(d, f)), f)
        for f in os.listdir(d)
        if f.endswith(".jsonl") and f.startswith(prefix)
    )
    if not logs:
        return {"filename": None, "events": []}
    filename = logs[-1][1]
    events = []
    for line in util.read_text(os.path.join(d, filename)).splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            events.append({"type": "raw", "text": line})
            continue
        kind = ev.get("type", "?")
        detail = " ".join(
            str(ev[k])
            for k in ("subtype", "name", "command", "text", "output", "result", "exit")
            if k in ev and ev[k] not in ("", None)
        )
        events.append({"type": kind, "detail": detail[:400], "raw": ev})
    return {"filename": filename, "events": events}


def read_handoffs(root, role, queue_dir):
    cfg = config.load(root)
    if role not in cfg.names():
        raise ValueError(f"unknown role: {role}")
    allowed = {"new", "in_process", "completed", "sent", "outbox"}
    if queue_dir not in allowed:
        raise ValueError(f"unknown queue dir: {queue_dir}")
    paths = layout.Paths(root)
    rp = paths.role(role)
    directory = getattr(rp, queue_dir, None) or (
        rp.outbox if queue_dir == "outbox" else None
    )
    if directory is None:
        raise ValueError(queue_dir)
    items = []
    for f in layout.handoffs(directory):
        path = os.path.join(directory, f)
        try:
            h, _ = handoff.read(path)
            items.append({
                "file": f,
                "id": h.get("id"),
                "from": h.get("from"),
                "to": h.get("to"),
                "task": h.get("task"),
                "task_id": h.get("task_id"),
                "verdict": h.get("verdict"),
                "commit": h.get("commit"),
            })
        except handoff.ParseError:
            continue
    return items


def read_inbox_item(root, iid):
    from conveyor import inbox as inbox_mod
    paths = layout.Paths(root)
    try:
        return inbox_mod.item(paths, iid)
    except inbox_mod.InboxError as e:
        raise FileNotFoundError(str(e)) from e


def list_models(root):
    cfg = config.load(root)
    bin_ = os.environ.get("CONVEYOR_AGENT_BIN", cfg.agent_bin)
    try:
        return {"models": agent.list_models(bin_), "error": None}
    except Exception as e:
        return {"models": [], "error": str(e)}


def git_commit_stat(root, sha):
    if not sha or not all(c in "0123456789abcdef" for c in sha.lower()):
        raise ValueError("invalid commit sha")
    r = subprocess.run(
        ["git", "show", "--stat", "--format=%H %s", sha],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise FileNotFoundError(sha)
    return r.stdout


REQUIRED_ROLE_HEADINGS = roles.REQUIRED_ROLE_HEADINGS
RUNNING_MSG = "loops are running; stop them first"


def loops_running(root):
    return bool(layout.running_roles(layout.Paths(root), config.load(root)))


def require_stopped(root):
    if loops_running(root):
        raise RuntimeError(RUNNING_MSG)


def _read_optional(path):
    if not os.path.isfile(path):
        return ""
    return util.read_text(path)


def _hops(cfg, name):
    return [
        {"from": a, "to": b, "verdict": v}
        for a, b, v in sorted(cfg.routes())
        if a == name
    ]


def _role_record(root, cfg, name, in_workflow):
    rec = {
        "name": name,
        "avatar": workflows.avatar(name),
        "in_workflow": in_workflow,
        "text": _read_optional(os.path.join(root, "roles", f"{name}.md")),
        "hops": _hops(cfg, name),
        "skills": roles.assigned_skills(root, name),
    }
    if in_workflow:
        r = cfg.role(name)
        rec.update({
            "model": r.model,
            "max_retries": r.max_retries,
            "max_minutes": r.max_minutes,
            "max_attempts": r.max_attempts,
        })
    return rec


def constitution_files(root):
    files = []
    if os.path.isfile(os.path.join(root, "constitution.md")):
        files.append("constitution.md")
    d = os.path.join(root, "constitution")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".md"):
                files.append(f"constitution/{f}")
    return files


def build_workflow(root):
    cfg = config.load(root)
    paths = layout.Paths(root)
    presets.ensure_seeded(paths)
    return {
        "workflow": workflows.describe(paths, cfg),
        "gate": cfg.gate_role(),
        "running": loops_running(root),
        "routes": [
            {"from": a, "to": b, "verdict": v}
            for a, b, v in sorted(cfg.routes())
        ],
        "roles": [_role_record(root, cfg, n, True) for n in cfg.names()],
        "library": [_role_record(root, cfg, n, False) for n in workflows.library_roles(root, cfg)],
        "available_skills": roles.available_skills(root),
        "constitution": constitution_files(root),
        "project": _read_optional(os.path.join(root, "project.md")),
        "project_gates": project_gates(root),
        "marks": {
            "operator": workflows.avatar("operator"),
            "done": workflows.avatar("done"),
        },
    }


def write_role(root, name, text):
    if name in ("operator", "done"):
        raise ValueError(f"reserved role: {name}")
    if not config.ROLE_RE.match(name):
        raise ValueError(f"invalid role name: {name}")
    path = os.path.join(root, "roles", f"{name}.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(name)
    try:
        roles.validate_role_text(text)
    except roles.RoleError as e:
        raise ValueError(str(e)) from e
    util.atomic_write(path, text if text.endswith("\n") else text + "\n")


def create_role(root, name, from_name=None):
    try:
        roles.create(root, name, from_name=from_name)
    except roles.RoleError as e:
        raise ValueError(str(e)) from e


def delete_role(root, name):
    cfg = config.load(root)
    paths = layout.Paths(root)
    try:
        roles.delete(root, paths, cfg, name)
    except roles.RoleError as e:
        raise ValueError(str(e)) from e


def write_role_skills(root, name, skills):
    try:
        roles.write_skills(root, name, skills)
    except roles.RoleError as e:
        raise ValueError(str(e)) from e


def write_project(root, text):
    path = os.path.join(root, "project.md")
    util.atomic_write(path, text if text.endswith("\n") else text + "\n")


def project_gates(root):
    try:
        catalog = gates.read_catalog(root)
    except gates.GateParseError:
        return []
    return [{"name": n, "argv": catalog.commands[n] or ""} for n in sorted(catalog.commands)]


def run_project_gate(root, name, role=None):
    from . import cli
    args = ["gate", "run", name]
    if role:
        args += ["--role", role]
    return cli.run(root, *args)


def _cfg(root):
    try:
        return config.load(root)
    except config.ConfigError as e:
        raise ValueError(str(e)) from e


def build_intake(root):
    cfg = _cfg(root)
    paths = layout.Paths(root)
    tr = cfg.role(config.INTAKE_ROLE)
    stored = jiralib.read(paths)
    return {
        "prompt": _read_optional(intakelib.prompt_path(root)),
        "rubric": intakelib.read_rubric(root),
        "avatar": workflows.avatar(config.INTAKE_ROLE),
        "path": intakelib.DIR + "/",
        "config": {
            "model": tr.model,
            "max_minutes": tr.max_minutes,
            "max_attempts": tr.max_attempts,
        },
        "jira": jiralib.redact(stored),
    }


def write_intake_prompt(root, text):
    for heading in REQUIRED_ROLE_HEADINGS:
        if not re.search(rf"^#+\s+{re.escape(heading)}\s*$", text, re.M):
            raise ValueError(f"role file must include heading {heading!r}")
    path = intakelib.prompt_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    util.atomic_write(path, text if text.endswith("\n") else text + "\n")


def write_intake_rubric(root, text):
    path = intakelib.rubric_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    util.atomic_write(path, text if text.endswith("\n") else text + "\n")


def write_intake_config(root, model, max_minutes, max_attempts):
    # No require_stopped: intake is one-shot and never in running_roles.
    updates = {}
    if model is not None:
        if not str(model).strip():
            raise ValueError("model is required")
        updates["ticket_reviewer_model"] = str(model).strip()
    if max_minutes is not None:
        updates["ticket_reviewer_max_minutes"] = max_minutes
    if max_attempts is not None:
        updates["ticket_reviewer_max_attempts"] = max_attempts
    try:
        config.write_inbox(root, updates)
    except config.ConfigError as e:
        raise ValueError(str(e)) from e


def write_intake_jira(root, site, email, token=None):
    paths = layout.Paths(root)
    stored = jiralib.read(paths)
    if not token:
        token = stored["token"]
    jiralib.write(paths, site if site is not None else stored["site"],
                  email if email is not None else stored["email"], token)
    return jiralib.redact(jiralib.read(paths))


def clear_intake_jira(root):
    jiralib.clear(layout.Paths(root))


def test_intake_jira(root, body=None):
    body = body or {}
    if any(k in body for k in ("site", "email", "token")):
        write_intake_jira(
            root,
            body.get("site") if "site" in body else None,
            body.get("email") if "email" in body else None,
            body.get("token") if "token" in body else None,
        )
    paths = layout.Paths(root)
    result = jiralib.check(paths, _cfg(root))
    return {**result, **jiralib.redact(jiralib.read(paths))}


def update_role_runtime(root, name, model, max_retries, max_minutes, max_attempts):
    require_stopped(root)
    cfg = config.load(root)
    if name not in cfg.names():
        raise ValueError(f"role {name!r} is not in the active workflow")
    role = cfg.role(name)
    if not model or not str(model).strip():
        raise ValueError("model is required")
    role.model = str(model).strip()
    for attr, val in (
        ("max_retries", max_retries),
        ("max_minutes", max_minutes),
        ("max_attempts", max_attempts),
    ):
        try:
            n = int(val)
        except (TypeError, ValueError):
            raise ValueError(f"{attr} must be an integer") from None
        if n < 1:
            raise ValueError(f"{attr} must be >= 1")
        setattr(role, attr, n)
    config.save(root, cfg)


# --- workflow presets (Stage 3) ----------------------------------------

_CREATED_RE = re.compile(r"\.conveyor/workflows/([^/]+)\.json")


def slug_from_message(msg):
    """Pull the slug out of the CLI's `.conveyor/workflows/<slug>.json created`."""
    m = _CREATED_RE.search(msg or "")
    return m.group(1) if m else ""


def _preset_row(p, active_slug, status):
    return {
        **p,
        "file": presets.rel_path(p["slug"]),
        "active": p["slug"] == active_slug and status == "active",
        "modified": p["slug"] == active_slug and status == "modified",
    }


def build_workflows(root):
    paths = layout.Paths(root)
    presets.ensure_seeded(paths)
    cfg = config.load(root)
    active_slug, status = presets.resolve(paths, cfg)
    rows = [_preset_row(p, active_slug, status) for p in presets.load_all(paths)]
    return {
        "active": active_slug,
        "status": status,
        "chain": cfg.chain_label(),
        "gate": cfg.gate_role(),
        "running": loops_running(root),
        "workflows": rows,
    }


def _handoff_label(roles, gate, i):
    """`ready → next`, `(held for approval)`, or the terminal role's two hops."""
    if i == len(roles) - 1:
        prev = roles[i - 1] if i else None
        return f"pass → done · findings → {prev}" if prev else "pass → done"
    if gate == roles[i]:
        return "(held for approval)"
    return f"ready → {roles[i + 1]}"


def build_workflow_detail(root, slug):
    paths = layout.Paths(root)
    presets.ensure_seeded(paths)
    cfg = config.load(root)
    p = presets.load(paths, slug)
    active_slug, status = presets.resolve(paths, cfg)
    configured = {r.name: r for r in cfg.roles}
    detail = []
    for i, name in enumerate(p["roles"]):
        av = workflows.avatar(name)
        # model and ceilings live in conveyor.conf, not in the preset. A role
        # this workflow adds has none until the workflow is made active.
        r = configured.get(name)
        detail.append({
            "name": name,
            "avatar": av,
            "owns": av["owns"],
            "model": r.model if r else None,
            "max_retries": r.max_retries if r else None,
            "max_minutes": r.max_minutes if r else None,
            "max_attempts": r.max_attempts if r else None,
            "handoff": _handoff_label(p["roles"], p["gate"], i),
        })
    return {
        **_preset_row(p, active_slug, status),
        "running": loops_running(root),
        "deletable": not (p["slug"] == active_slug and status == "active")
                     and len(presets.load_all(paths)) > 1,
        "roles_detail": detail,
        "routes": presets.routes(p),
        "marks": {"operator": workflows.avatar("operator"),
                  "done": workflows.avatar("done")},
    }
