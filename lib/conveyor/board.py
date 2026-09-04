"""board.tsv (protocol §8). Every write: lock, rewrite whole file, rename."""
import os

from . import util

COLS = ("name", "lane", "created_at", "updated_at", "task_id",
        "audit_count", "retry_count", "started_at")


def _load(paths):
    rows, raw = [], []
    try:
        text = util.read_text(paths.board)
    except FileNotFoundError:
        return rows, raw
    for line in text.split("\n"):
        if not line:
            continue
        cells = line.split("\t")
        if len(cells) == len(COLS):
            rows.append(dict(zip(COLS, cells)))
        else:
            raw.append(line)  # malformed: preserved verbatim, never edited
    return rows, raw


def _save(paths, rows, raw):
    lines = ["\t".join(r[c] for c in COLS) for r in rows] + raw
    util.atomic_write(paths.board, "".join(l + "\n" for l in lines))


def read(paths):
    return _load(paths)[0]


def get(paths, name):
    for r in read(paths):
        if r["name"] == name:
            return r
    return None


def add(paths, name, lane):
    ts = util.now()
    row = {"name": name, "lane": lane, "created_at": ts, "updated_at": ts,
           "task_id": f"{util.compact(ts)}-{name}", "audit_count": "0",
           "retry_count": "0", "started_at": "-"}
    with util.lock(paths.board_lock):
        rows, raw = _load(paths)
        if any(r["name"] == name for r in rows):
            raise KeyError(name)
        _save(paths, rows + [row], raw)
    return row


def update(paths, name, **changes):
    """Apply changes to one row under the lock. Ints may be given as '+1'."""
    with util.lock(paths.board_lock):
        rows, raw = _load(paths)
        for r in rows:
            if r["name"] == name:
                for k, v in changes.items():
                    v = str(v)
                    r[k] = str(int(r[k]) + int(v[1:])) if v.startswith("+") else v
                r["updated_at"] = util.now()
                _save(paths, rows, raw)
                return r
    raise KeyError(name)


def delete(paths, name):
    with util.lock(paths.board_lock):
        rows, raw = _load(paths)
        _save(paths, [r for r in rows if r["name"] != name], raw)
