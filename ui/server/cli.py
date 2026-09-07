"""Mutations via bin/conveyor (CLI owns protocol rules)."""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONVEYOR = os.path.join(REPO, "bin", "conveyor")


def run(root, *args, input_text=None):
    r = subprocess.run(
        [CONVEYOR, *args],
        cwd=root,
        input=input_text,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "command failed").strip()
        raise RuntimeError(msg)
    return (r.stdout or "").strip()


def create_task(root, name, text):
    return run(root, "task", name, input_text=text)


def delete_task(root, name):
    return run(root, "task", name, "--delete")


def resume_task(root, task, to=None):
    args = ["resume", task]
    if to:
        args += ["--to", to]
    return run(root, *args)


def start(root):
    return run(root, "start", "--no-smoke")


def stop(root, now=False):
    return run(root, "stop", *(["--now"] if now else []))


def import_tickets(root, source, title="", body=""):
    args = ["import", "--source", source]
    if title:
        args += ["--title", title]
    return run(root, *args, input_text=body or "")


def refresh_import(root, iid):
    try:
        return run(root, "import", "--refresh", iid)
    except RuntimeError as e:
        raise ValueError(str(e)) from e


def replace_inbox_source(root, iid, text):
    try:
        return run(root, "import", "--replace", iid, input_text=text)
    except RuntimeError as e:
        raise ValueError(str(e)) from e


def intake(root, iid, improve=False, comments=None):
    if comments:
        sys.path.insert(0, os.path.join(REPO, "lib"))
        from conveyor import inbox, layout
        inbox.write_file(layout.Paths(root), iid, "comments.txt", comments)
    args = ["intake", iid]
    if improve:
        args.append("--improve")
    return run(root, *args)


def inbox_approve(root, iid, name=None, text=None):
    if text:
        sys.path.insert(0, os.path.join(REPO, "lib"))
        from conveyor import inbox, layout
        inbox.write_file(layout.Paths(root), iid, "proposed-task.md", text)
    args = ["inbox", "approve", iid]
    if name:
        args += ["--name", name]
    return run(root, *args)


def inbox_skip(root, iid):
    return run(root, "inbox", "skip", iid)


def inbox_attachments(root, iid, select=None):
    if select is None:
        return run(root, "inbox", "attachments", iid)
    if select == "none" or select == []:
        args = ["inbox", "attachments", iid, "--select", "none"]
    elif isinstance(select, str):
        args = ["inbox", "attachments", iid, "--select", select]
    else:
        args = ["inbox", "attachments", iid, "--select", ",".join(str(x) for x in select)]
    try:
        return run(root, *args)
    except RuntimeError as e:
        raise ValueError(str(e)) from e


def start_task(root, name):
    return run(root, "start-task", name)


def approve(root, hid):
    return run(root, "approve", hid)


def reject(root, hid, comments=""):
    return run(root, "reject", hid, input_text=comments)


def activate_workflow(root, slug):
    return run(root, "workflow", "activate", slug)


def create_workflow(root, body):
    args = ["workflow", "new", body["name"], "--roles", ",".join(body["roles"])]
    if body.get("gate"):
        args += ["--gate", body["gate"]]
    if body.get("description"):
        args += ["--description", body["description"]]
    return run(root, *args)


def save_workflow(root, slug, body):
    args = ["workflow", "edit", slug]
    if "name" in body:
        args += ["--name", body["name"]]
    if "description" in body:
        args += ["--description", body["description"]]
    if "roles" in body:
        args += ["--roles", ",".join(body["roles"])]
    if "gate" in body:
        args += ["--gate", body["gate"]] if body["gate"] else ["--no-gate"]
    return run(root, *args)


def delete_workflow(root, slug):
    return run(root, "workflow", "delete", slug)


def create_role(root, name, from_name=None):
    args = ["role", "new", name]
    if from_name:
        args += ["--from", from_name]
    return run(root, *args)


def delete_role(root, name):
    return run(root, "role", "delete", name)


def set_role_skills(root, name, skills):
    return run(root, "role", "skills", name, "--set", ",".join(skills))
