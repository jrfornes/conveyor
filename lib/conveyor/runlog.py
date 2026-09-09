"""Read Conveyor's own records back out of a run log (protocol §6.9).

A run log is the agent's stream-json plus the loop's `type: conveyor` records.
Nothing here decides anything -- the outbox stays the only signal -- this is
what `conveyor log` and the cockpit show the operator.
"""
import json


def records(text, event=None):
    """Conveyor's records in a run log, oldest first; `event` narrows to one kind.
    Agent output and lines that are not JSON are skipped, never interpreted."""
    out = []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict) or ev.get("type") != "conveyor":
            continue
        if event is None or ev.get("event") == event:
            out.append(ev)
    return out


def last_prompt(text):
    """The prompt of the last run in the log, verbatim, or None for a log
    written before prompts were recorded. A run re-launched after `stop --now`
    appends to the same file, so the last record is the one the agent that is
    running now actually received."""
    found = [ev for ev in records(text, "prompt") if isinstance(ev.get("prompt"), str)]
    return found[-1]["prompt"] if found else None
