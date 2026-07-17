# MERCY — orientation for Claude

MERCY is a PySide6 + SQLite desktop app: a three-way merge of **ANIKA** (part costing) + **BECKY** (HR) plus a new per-employee production tracker. The original 13-step merge is complete; post-release feature work continues.

## Read these first, cold, every session

- **[`HANDOFF.md`](HANDOFF.md)** — orientation + the **🧭 Cursor**, the ONE home for live status (next step, last landed, smoke baseline, carried watch-items). Start here.
- **[`CONVENTIONS.md`](CONVENTIONS.md)** — live dev conventions and gotchas (smoke baseline, `fuzz_db.py` upkeep, headless Qt pitfalls).

Then as needed: **[`ROADMAP.md`](ROADMAP.md)** (planned steps + their scoping essays; shrinks) and **[`WORKLOG.md`](WORKLOG.md)** (as-built record; grows). Closed history — including the retired `MERGE_PLAN.md`, which code comments still cite by §-number — lives in [`plan_archive/`](plan_archive/).

## Baseline sanity check

Run `./Scripts/python.exe -m smoke` at the start and end of any invasive change — the offscreen check battery runs in a few seconds and is the regression net. The `smoke/` package re-exports every check function; each carries a docstring describing what it covers.

## Workflow

One logical step = one commit. The Cursor + ROADMAP drive; when a step lands, the same commit adds its WORKLOG entry, deletes its ROADMAP entry, and updates the Cursor (the lifecycle in HANDOFF § The doc system).
