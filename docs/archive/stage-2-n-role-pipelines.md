# Stage 2 — N-role pipelines with an explicit gate

**Goal:** a workflow may have any number of coding roles (≥ 1), and the human gate may
sit after any non-last role — instead of "2 or 3 roles, gate iff 3".
**Depends on:** Stage 0.
**Exit:** 104 existing tests green, plus new tests for 1-role, 4-role and
gate-after-any-role pipelines.

## Why this is first

This is the only stage with real risk. The design's headline feature is blocked on three
functions in `lib/conveyor/config.py` that are load-bearing for `bin/handoff.sh` and most
of the twelve invariant tests. Every later stage is additive UI on top of it.

The good news: the runtime surface is tiny. `holds_first_ready()` has exactly one runtime
caller and `routes()` has exactly one.

## What changes

### `lib/conveyor/config.py`

| Now | After |
| --- | --- |
| `if len(roles) not in (2, 3): raise` (line ~125) | `if not roles: raise` — require ≥ 1 |
| `holds_first_ready()` → `len(self.roles) == 3` | `gate` field on `Config`; `gate_role()` returns the role name or `None` |
| `routes()` hardcodes `n[-1] → n[-2] findings` | Same rule, but correct for `len(n) == 1` (no findings edge; `n[-2]` would wrap) |
| `next_of()` | Unchanged — already general |

New `conveyor.conf` directive, parsed alongside `role`:

```
gate <role>     # hold the first `ready` handoff leaving <role> for operator approval
```

Rules: `<role>` must be configured and must not be last. Absent = no gate. Reject with a
`ConfigError` carrying repair text, in the style of protocol §4.5.

Single-role edge cases to settle explicitly:
- `routes()` for one role = `{(operator, r, ready), (r, done, pass)}`. **No findings
  edge** — there is no previous role to bounce to.
- A gate is impossible with one role (the only role is last). Reject at parse time.

### `lib/conveyor/queue.py`

One line. `queue.py:112`:

```python
if cfg.holds_first_ready() and role == cfg.names()[0] and h["verdict"] == "ready":
```
becomes a check against `cfg.gate_role()`, so the hold fires after the gated role rather
than always after the first. Everything downstream (`approvals/pending/`,
`approve_pending`, `reject_pending`) is unchanged — but see the reject-target question.

**Decide during implementation:** `reject_pending()` currently returns the handoff to
`cfg.names()[0]`. With a gate after an arbitrary role it must return to the *gated* role.
For the existing 3-pack these are the same role, so no existing test moves.

### `lib/conveyor/packs.py`

`STARTERS` keeps `holds_first_ready` as a bool. Convert to `gate: "specifier" | None` so
presets and config speak one language. `active_pack()` matches on role tuple — leave it;
Stage 3 replaces it with slug lookup.

### `bin/handoff.sh`

No logic change — it calls `cfg.routes()`. Confirm the error message at line ~121 still
enumerates correctly when a role has no outbound findings edge (the 1-role case).

### `bin/conveyor`

`cmd_pack` still takes `two|three`. Leave it; Stage 3 replaces it with preset slugs. Add
nothing here.

### `ui/server/state.py` + `ui/src/app/models.ts`

`state.py:330` exposes `holds_first_ready: bool`. Add `gate: string | null` alongside it
and keep the bool as a derived alias for one stage, so Stage 1's UI split isn't blocked
on a model change. Remove the alias in Stage 3.

## Tasks, in order

1. Add `gate` to `Config` and parse `gate <role>` in `config.load()`; validation + repair
   text for: unknown role, gate on last role, gate with one role, duplicate `gate` line.
2. Relax the role-count check to `≥ 1`.
3. Fix `routes()` for `len(n) == 1`; add `gate_role()`; keep `holds_first_ready()` as a
   deprecated shim returning `gate_role() is not None`.
4. Teach `config.save()` to emit the `gate` line.
5. Point `queue.py:112` at `gate_role()`; point `reject_pending()` at the gated role.
6. Update `packs.py` STARTERS to carry `gate`.
7. Surface `gate` in `state.py` and `models.ts`.

## Tests

New file `test/test_pipeline_shape.py`:

- 1-role config loads; `routes()` has no findings edge; `handoff.sh` accepts
  `coder → done pass` and rejects `coder → coder findings` with the §4.5 repair text.
- 4-role config loads; `routes()` chains all three `ready` hops; findings goes from role 4
  to role 3.
- `gate reviewer` in a 4-role belt: role 2's `ready` delivers normally; reviewer's first
  `ready` lands in `.conveyor/approvals/pending/`.
- `conveyor reject` on that gated handoff returns it to **reviewer**, not to role 1.
- Parse errors: `gate coder` where coder is last; `gate nobody`; `gate` with one role.

Extend `test/test_pack.py` rather than replacing it — its 2-role and 3-role assertions are
the regression guard that this stage changed nothing for existing shapes.

Full suite must stay green: `cd test && python3 -m unittest discover -p 'test_*.py'`.

## Risks

| Risk | Mitigation |
| --- | --- |
| `routes()` change silently widens what `handoff.sh` accepts | Assert the exact route set for 1/2/3/4 roles, not just membership |
| Invariant tests assume a 2- or 3-role fixture | Read `test/harness.py` before editing; add shapes, don't change fixtures |
| `reject_pending` target change breaks the 3-pack | For a gate on the first role the target is unchanged; assert this explicitly |
| Worktrees stranded when role count shrinks | Out of scope — logged in Stage 0 §10 q3, handled in Stage 3 |
