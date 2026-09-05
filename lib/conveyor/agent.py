"""Talk to the configured agent binary (cursor-agent or a test double)."""
import subprocess

TIMEOUT = 15


class AgentError(Exception):
    pass


def parse_models(text):
    """Turn `--list-models` / `models` stdout into [{id, label}, ...].

    Skips blanks and an `Available models` header. A line `id - Label` becomes
    those two fields; a bare token is used as both id and label.
    """
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower() == "available models":
            continue
        if " - " in line:
            mid, _, label = line.partition(" - ")
            mid, label = mid.strip(), label.strip()
            if mid:
                out.append({"id": mid, "label": label or mid})
        else:
            out.append({"id": line, "label": line})
    return out


def list_models(agent):
    """Return [{id, label}, ...] from the agent. Prefer `--list-models`."""
    errors = []
    for args in (("--list-models",), ("models",)):
        try:
            r = subprocess.run(
                [agent, *args], capture_output=True, text=True, timeout=TIMEOUT,
            )
        except FileNotFoundError as e:
            raise AgentError(f"agent not found: {agent}") from e
        except subprocess.TimeoutExpired:
            errors.append(f"`{agent} {args[0]}` timed out")
            continue
        if r.returncode != 0:
            detail = (r.stderr or r.stdout).strip() or f"exit {r.returncode}"
            errors.append(f"`{agent} {args[0]}` failed: {detail}")
            continue
        return parse_models(r.stdout)
    raise AgentError("could not list models: " + "; ".join(errors))
