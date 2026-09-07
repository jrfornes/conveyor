# Next chapters — after `v0.3.0-rc1`

`v0.3.0-rc1` is tagged. Work after that lands on `main`. The next
**named** snapshot is **`v0.4.0-rc1`** if the tree is thicker than
“rc1 plus the bugs it proved.” `v1.0.0` still means live Cursor (M3)
proven, not “we added more stuff.”

Fill intended 0.4 contents in [`0.4.0-rc1.md`](0.4.0-rc1.md); record
what landed in [`CHANGELOG.md`](../../CHANGELOG.md) **Unreleased**.

Stages 5–6 and PRD Appendix B stay out of 0.4 unless you move a line
into that plan. Spine for *official* is still in
[`docs/release-review.md`](../release-review.md): M3 archived → D2
documented → operator dry-run → `v1.0.0`.

---

## Versioning

Decide the number **at tag time** from what landed since `v0.3.0-rc1`:

| Tag | When to use it |
| --- | --- |
| `v0.3.0-rc2` | Thin patch of the rc1 surface only. Optional; skip if fixes ride into 0.4 |
| **`v0.4.0-rc1`** | Any new operator-facing capability, plus fixes and maintenance. M3 may still be open. **Default next tag.** |
| `v0.4.0` | Same tree if you drop the `-rc` label |
| `v1.0.0` | M3 archived + D2 written. May be the 0.4 product |

`0.1` was CLI, `0.2` workflows/UI (never tagged), `0.3` intake + cockpit.
Another product bump is **0.4**. Do not call a thicker tree `0.3.0-rc2`.
Do not jump to `1.0.0` because the changelog got long.

Day to day: commit to `main`, keep the Unreleased buckets current, tag
when the plan and the tree agree.

M3 may run against the **frozen** `v0.3.0-rc1` tag while `main` moves.
That triage log (`test/fixtures/m3/`) feeds **Fixes** in the 0.4 plan.

---

## Four kinds of work

These are buckets that can share one 0.4 tag. They are not a required
sequence.

| Kind | Job | Where it goes |
| --- | --- | --- |
| **Validate** | Prove a *tagged* product with a real agent | M3 on `v0.3.0-rc1` (or later on 0.4) |
| **Stabilize** | Fix what validation (or daily use) proved | 0.4 **Fixes** — or a thin `v0.3.0-rc2` if you need a patched rc1 |
| **Harden** | Understand + remove slop; no new surface | 0.4 **Maintenance**, or after 1.0 as `v1.0.1` / craft `v1.1.0` |
| **Expand** | New product | 0.4 **Features** if you want it in this snapshot; else later |

Write an exit for a chunk of work before its task list when the chunk
is large. The failure mode is still the same: M3 finds bugs, then
everything mixes with no changelog, and there is never a clean tag.

Plans for later chapters are **not** all written up front. Same reason
as [`README.md`](README.md): earlier work reshapes later work. The 0.4
plan is the one living brief until that tag.

---

## Chapter A — M3

**Job:** one live Cursor pipeline on a **small real repo**, against a
**tag** (`v0.3.0-rc1` first), not an untagged `HEAD`.

**Exit** ([`IMPLEMENT.md`](../../IMPLEMENT.md), PRD §9): reviewer sends
`findings` at least once; coder fixes; merge on `main`; logs archived
under `test/fixtures/m3/`.

The output is **not** a feature list. It is a triage log next to the
run. That log feeds 0.4 **Fixes**.

While you test, classify every surprise:

| Bucket | Meaning | Goes to |
| --- | --- | --- |
| **Protocol bug** | State / rename / handoff / merge wrong | Fixes + regression test |
| **Prompt/role gap** | Agent did the wrong job; harness was fine | `roles/*.md` / constitution; re-run M3 |
| **Cursor/CLI/plan** | Model, auth, `-p --force`, version | Runbook + pin `agent_version` |
| **UX paper cut** | UI blocked you but CLI worked | Features or Maintenance if you want it in 0.4 |
| **Want** | New capability | 0.4 Features only if you put it on that list |

If you want understanding *during* M3, take notes — do not refactor
the tagged tree you are proving.

---

## Chapter B — stabilize (optional thin tag)

**Job:** only if you need a patched **rc1** that is not 0.4.

**In:** protocol bugs, role/prompt gaps that blocked the run, runbook
lies, one regression test per real bug.

**Out:** new product. That makes it 0.4.

**Exit:** tag `v0.3.0-rc2` and re-run M3, **or** skip this tag and
land the same fixes on `main` for 0.4.

---

## Chapter C — Harden

**Job:** read the product as an operator, then delete/clarify — not
add. Can ride into 0.4 **Maintenance** or wait until after `v1.0.0`.

Give it a **budget and a finish line**, or it becomes a rewrite.

1. **Walk, don’t scan first.** Operator dry-run with only
   [`docs/runbook.md`](../runbook.md) (release-review step 6). Note
   every place you had to open source.
2. **Moat pass.** Re-walk [`moat-gap-scan.md`](moat-gap-scan.md):
   enforced vs prompt-only vs overclaim.
3. **Slop rules — pick 3–5, stop.**
4. **Write “what I now believe”** in one place (`bin/README.md`
   ambiguities, or `docs/plans/harden-notes.md`).

**Invariant:** the unit suite stays green; no protocol behavior change
without a test.

**Exit if after 1.0:** `v1.0.1`, or `v1.1.0` if you want “craft, no
features,” plus a one-page “we did not change X.”

Candidate list:
[`.cursor/plans/post-m3_harden_f4bbac3b.plan.md`](../../.cursor/plans/post-m3_harden_f4bbac3b.plan.md).
Copy items into [`0.4.0-rc1.md`](0.4.0-rc1.md) if they belong in 0.4.

---

## Chapter D — Expand (later than 0.4, unless listed)

Stage 5 (board fidelity / chime), Stage 6 (theme), async intake,
“Run now,” Appendix B.

Named and written, not auto-in a tag:
[`gate-review.md`](gate-review.md) — held-handoff diff vs intent; reject
comments stay findings. Not B.5 (per-file comments). Copy a line onto the
living tag plan if you want it in that snapshot.

Only if you put a named line on the 0.4 plan — otherwise after 1.0,
and only if M3 + harden still leave a **named** operator pain.
Release-review already says Stage 5–6 do not block official.

---

## Living plan (three artifacts)

1. **[`0.4.0-rc1.md`](0.4.0-rc1.md)** — what you *want* in the next tag.
2. **`CHANGELOG.md` Unreleased** — what has *landed* toward that tag.
3. **The M3 triage log** — dated, bucketed, in `test/fixtures/m3/`
   next to the run.

---

## Short version

Land features, fixes, and maintenance on `main`. Next advertised
release is **`v0.4.0-rc1`**. **`v1.0.0`** waits until M3 is archived.
Keep the 0.4 plan and the Unreleased changelog in sync; tag when they
match the tree.
