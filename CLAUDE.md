# MERCY — orientation for Claude

MERCY is a PySide6 + SQLite desktop app: a three-way merge of **ANIKA** (part costing) + **BECKY** (HR) plus a new per-employee production tracker. The original 13-step merge is complete; post-release feature work continues.

## Read these first, cold, every session

- **[`MERGE_PLAN.md`](MERGE_PLAN.md)** — authoritative plan doc. Start at **§12.1** (step status table) and **§13** (post-release feature backlog). Historical narratives live in [`plan_archive/`](plan_archive/).
- **[`CONVENTIONS.md`](CONVENTIONS.md)** — live dev conventions and gotchas (smoke.py baseline, `fuzz_db.py` upkeep, headless Qt pitfalls).

## Baseline sanity check

Run `./Scripts/python.exe smoke.py` at the start and end of any invasive change — eleven offscreen checks, a few seconds total. It is the regression net.

## Workflow

One logical step = one commit. The plan doc drives; check §12.1 / §13 before starting work and update them when a step lands.
