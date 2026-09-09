"""Per-run token accounting (protocol §6.9 sidecar).

One `.usage.json` beside each run log, derived from that log and never mutated.
The numbers are the agent's own; when it reports nothing they are `None`, never
an estimate — a fabricated bill is worse than no bill (PRD §5.5).
"""
import json
import os

from . import util

# Alias table: agent-reported key → our field, first hit wins. One dict so a live
# run can extend it without touching the logic (bin/README.md, Ambiguities).
ALIASES = {
    "input": ("input_tokens", "prompt_tokens", "inputTokens"),
    "output": ("output_tokens", "completion_tokens", "outputTokens"),
    "cache_read": ("cache_read_input_tokens", "cached_tokens"),
    "cache_write": ("cache_creation_input_tokens",),
    "cost_usd": ("total_cost_usd", "cost_usd"),
}
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write")
FIELDS = TOKEN_FIELDS + ("cost_usd",)

# An event that ends the stream. `type: result` is the documented shape; the
# subtypes are what a stream that types its terminal event differently uses.
RESULT_SUBTYPES = ("success", "error", "error_max_turns", "error_during_execution")


def _usage_of(ev):
    """The usage object carried by one event, at the top level or under `message`."""
    for holder in (ev, ev.get("message")):
        if isinstance(holder, dict):
            u = holder.get("usage")
            if isinstance(u, dict):
                return u
    return None


def _is_result(ev):
    return ev.get("type") == "result" or ev.get("subtype") in RESULT_SUBTYPES


def _pick(u):
    """One usage object → our fields; a field no alias covers is None."""
    out = {}
    for field, keys in ALIASES.items():
        val = None
        for k in keys:
            v = u.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                val = v
                break
        out[field] = val
    return out


def _blank(source):
    return {"source": source, **{f: None for f in FIELDS}}


def scan(text):
    """Classify a run log's usage. Never guesses: `source` names the rule that fired.

    A terminal `result` event carrying usage wins outright and per-message events
    are ignored; without one, per-message usage objects are summed. Mixing the two
    would double-bill a cumulative total, and nothing in a stream says which it is,
    so the rule that produced the number is recorded next to it.
    """
    last_result, per_message = None, []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue  # a truncated final line, or output the stamper wrapped
        if not isinstance(ev, dict):
            continue
        u = _usage_of(ev)
        if u is None:
            continue
        if _is_result(ev):
            last_result = u
        else:
            per_message.append(u)
    if last_result is not None:
        return {"source": "result", **_pick(last_result)}
    if not per_message:
        return _blank("none")
    picked = [_pick(u) for u in per_message]
    summed = {}
    for f in FIELDS:
        vals = [p[f] for p in picked if p[f] is not None]
        summed[f] = sum(vals) if vals else None
    return {"source": "messages", **summed}


def human(n):
    """A token count as the operator reads it: `-` for unknown, never `0` for it.

    `0` is a real answer (an agent that billed nothing); `-` is the absence of one.
    Shared by `conveyor cost`, `conveyor status` and the run-log usage record so the
    same number never appears in two shapes.
    """
    if n is None:
        return "-"
    n = int(n)
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def clock(seconds):
    """Wall time as `47m` (or `2h11m` past an hour) for the cost table."""
    m = int(seconds) // 60
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def path(paths, role, task, hid, attempt):
    return os.path.join(paths.logs, role, f"{task}_{hid}_a{attempt}.usage.json")


def record(paths, role, task, hid, attempt, scanned, duration_s, exit_code):
    """Write the sidecar for one agent run and return what was written.

    A run with no usage still gets a file: an absent file means the loop never
    finished the run, `source: none` means the agent told us nothing.
    """
    run = {"role": role, "task": task, "id": hid, "attempt": int(attempt),
           **{k: scanned.get(k) for k in ("source", *FIELDS)},
           "duration_s": round(float(duration_s), 1), "exit": exit_code,
           "at": util.now()}
    p = path(paths, role, task, hid, attempt)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    util.atomic_write(p, json.dumps(run, indent=2) + "\n")
    return run


def read_run(p):
    """One sidecar → its dict, with role/attempt recovered from the path if absent."""
    try:
        run = json.loads(util.read_text(p))
    except (OSError, ValueError):
        return None
    if not isinstance(run, dict):
        return None
    run.setdefault("role", os.path.basename(os.path.dirname(p)))
    name = os.path.basename(p)[: -len(".usage.json")]
    parts = name.split("_")  # <task>_<id>_a<attempt>; task names carry no underscore
    if len(parts) == 3:
        run.setdefault("task", parts[0])
        run.setdefault("id", parts[1])
        run.setdefault("attempt", int(parts[2][1:]) if parts[2][1:].isdigit() else 1)
    return run


def read_task(paths, task):
    """Every run recorded for one task, across all roles, oldest file first."""
    found = []
    try:
        roles = sorted(os.listdir(paths.logs))
    except FileNotFoundError:
        return []
    for role in roles:
        d = os.path.join(paths.logs, role)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not (f.startswith(task + "_") and f.endswith(".usage.json")):
                continue
            p = os.path.join(d, f)
            run = read_run(p)
            if run is not None:
                found.append((os.path.getmtime(p), int(run.get("attempt", 1)), run))
    return [r for _, _, r in sorted(found, key=lambda t: (t[0], t[1]))]


def read_all(paths):
    """{task: [runs]} for every task with a sidecar on disk."""
    out = {}
    try:
        roles = sorted(os.listdir(paths.logs))
    except FileNotFoundError:
        return out
    for role in roles:
        d = os.path.join(paths.logs, role)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".usage.json"):
                continue
            run = read_run(os.path.join(d, f))
            if run is not None:
                out.setdefault(run["task"], []).append(
                    (os.path.getmtime(os.path.join(d, f)), int(run.get("attempt", 1)), run))
    return {t: [r for _, _, r in sorted(v, key=lambda x: (x[0], x[1]))] for t, v in out.items()}


def total(runs):
    """Sum a list of runs. `unknown` counts the runs that reported nothing; they are
    never treated as zero, and a set of runs that reported nothing at all sums to
    `None` -- unknown, not free. Wall time is always known, so it always adds up."""
    t = {"runs": len(runs), "input": 0, "output": 0, "total": 0, "wall_s": 0.0,
         "unknown": 0, "known": 0}
    for r in runs:
        t["wall_s"] += float(r.get("duration_s") or 0)
        if r.get("source") in (None, "none"):
            t["unknown"] += 1
            continue
        t["known"] += 1
        t["input"] += int(r.get("input") or 0)
        t["output"] += int(r.get("output") or 0)
    if t["known"] == 0:
        t["input"] = t["output"] = t["total"] = None
    else:
        t["total"] = t["input"] + t["output"]
    return t


def task_total(paths, task):
    """Total tokens billed to one task across every role and attempt, or None when
    no run reported usage — an unknown total can never fire a ceiling (decision 9)."""
    t = total(read_task(paths, task))
    return None if t["known"] == 0 else t["total"]
