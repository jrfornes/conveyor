"""Talk to the configured agent binary (cursor-agent or a test double)."""
import os
import shutil
import subprocess

TIMEOUT = 15

# Conveyor's fixed argument list (docs/plans/cursor-cli-runtime.md decision 1):
# the flags the loop needs to run correctly whatever ~/.cursor/cli-config.json
# says. `--model` and `--output-format` follow, parameterised by the caller.
FIXED_ARGS = ["-p", "--force", "--trust", "--sandbox", "disabled"]
# Fixed flags that carry no value; a bare copy in agent_args / cli-args is dropped.
_VALUELESS = frozenset({"-p", "--force", "--trust"})


class AgentError(Exception):
    pass


def compose(agent, model, extra, *, output_format=None):
    """Assemble the agent command line: the binary, Conveyor's fixed list,
    `--model`, an optional `--output-format`, then the operator's `extra`
    (agent_args + a role's cli-args) with any token Conveyor already sets
    deduped out (plan decisions 1 and 2).

    Dedupe is exact-match. A bare fixed flag (`-p`, `--force`, `--trust`) in
    `extra` is dropped. A value flag Conveyor sets (`--sandbox`, `--model`,
    `--output-format`) is dropped with its value only when the value also
    matches Conveyor's; a differing value survives, so `--sandbox enabled` in a
    role's cli-args lands after `--sandbox disabled` and Cursor's own parser
    takes the later one. Nothing else in `extra` is touched.
    """
    cmd = [agent, *FIXED_ARGS, "--model", model]
    if output_format:
        cmd += ["--output-format", output_format]
    values = {"--sandbox": "disabled", "--model": model}
    if output_format:
        values["--output-format"] = output_format
    return cmd + _dedupe(list(extra), values)


def _dedupe(extra, values):
    out, i, n = [], 0, len(extra)
    while i < n:
        tok = extra[i]
        if tok in _VALUELESS:
            i += 1
            continue
        if tok in values:
            val = extra[i + 1] if i + 1 < n else None
            if val == values[tok]:  # exact dup of what Conveyor already set
                i += 2
                continue
            out.append(tok)
            if val is None:
                i += 1
            else:
                out.append(val)  # operator override; the later token wins in Cursor
                i += 2
            continue
        out.append(tok)
        i += 1
    return out


def resolve(agent, cwd):
    """Absolute path Popen(cwd=cwd) will run, or None — the same resolution the
    loop's agent_binary() does. A name with a separator is taken as-is (a
    relative one against `cwd`, the agent's working directory); a bare name is
    looked up on PATH."""
    if os.sep in agent or (os.altsep and os.altsep in agent):
        cand = agent if os.path.isabs(agent) else os.path.join(cwd, agent)
        return cand if os.path.isfile(cand) and os.access(cand, os.X_OK) else None
    return shutil.which(agent)


def version(agent):
    """`<agent> --version` output, stripped, or "" when it cannot be read.
    Same 15 s timeout as list_models; never raises."""
    try:
        r = subprocess.run([agent, "--version"], capture_output=True, text=True,
                           timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (r.stdout or "").strip()


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
