# HANDOFF — MERCY session pickup

Fresh-session orientation for MERCY, a PySide6 + SQLite desktop app: part costing (ANIKA) + HR (BECKY) + per-employee production tracking + the production-scheduling subsystem. Read this file cold at the start of every session; dive into the other docs only where they're called out.

## 🧭 Cursor

**The ONE home for live status.** Every other doc (and the agent memory) points here instead of restating it; when state changes, this table is the single place that updates. **Hard cap: ~15 lines.** If something doesn't fit, it belongs in ROADMAP (forward) or WORKLOG (backward), with at most a pointer here — a Cursor that only grows is how the last doc died.

| | |
|---|---|
| **NEXT** | **FROZEN** (2026-09, transition decision 8) — desktop is **bugfix-only**; the web rebuild drives from [TKG-Software/mercy-web](https://github.com/TKG-Software/mercy-web) (its `TRANSITION_PLAN.md` is the plan of record). Step 86+ shelved in [ROADMAP](ROADMAP.md). |
| **Last landed** | **Step 85** — the single-source facts are now machine-enforced: `docs_single_source` asserts this Cursor's baseline == `smoke.CHECKS`, that no other live doc restates it, and that nothing with a WORKLOG entry is still planned in ROADMAP; the check registry moved into `smoke/__init__.py` (one place, was two). Before it: 84-post-triage (the "wiped DB" divide-by-zero on a 100%-LOI material), 83 (order-status due date + open-orders filter), 84 (the doc split; `MERGE_PLAN.md` retired to [plan_archive/merge_plan.md](plan_archive/merge_plan.md)), 82. |
| **Smoke baseline** | **76 PASS** — `./Scripts/python.exe -m smoke`. Quoted here and nowhere else, and `docs_single_source` now fails if that stops being true. |
| **Branch / tree** | `main`, working tree clean at last close |
| **Carried watch-items** | Step 80's real-floor gate **unmet** (dies-stop-hopping needs a deployed schedule + real `Press.currentPart` data); `dieChangeHours` deliberately **0.0** — do **not** invent a value; scheduler-vs-real-orders validation open. All tracked in [ROADMAP](ROADMAP.md) § Blocked on real data. |

**Two rules for reading step status (both load-bearing):**

1. **"Landed" means the code shipped and its automated checks pass — NOT that the step's real-data / floor gate cleared.** Live example: Step 80. When a step's *confidence* matters, read its WORKLOG entry, not the tick.
2. **Steps land out of numeric order** (Step 82 shipped before 81). Derive release scope from the actual tag range, never from step numbers.

## The doc system

Adopted at Step 84 (2026-07-17), adapting the shape of Matthew's `asciibattler` project to MERCY's flow: no pre-specced rounds here — work arrives as team feedback, from one-line changes to multi-step blocks, so the files are **permanent** and rotate by size, not per-round.

- **[HANDOFF.md](HANDOFF.md)** (this file) — orientation + the 🧭 Cursor. Rarely changes outside the Cursor.
- **[ROADMAP.md](ROADMAP.md)** — forward-looking only; **shrinks** as work lands. Holds each planned step's scoping essay plus the blocked / waiting backlogs.
- **[WORKLOG.md](WORKLOG.md)** — backward-looking as-built record; **grows**, newest first. Entry length scales with the step: a one-line change gets one line, a subsystem gets paragraphs.
- **[CONVENTIONS.md](CONVENTIONS.md)** — durable dev conventions + gotchas. The graduation target: when a WORKLOG narrative carries a lesson future work must obey, the *lesson* moves here and the narrative stays history.
- **[plan_archive/](plan_archive/)** — closed history, including the retired **[merge_plan.md](plan_archive/merge_plan.md)** (the original merge design + Steps 1–83 scoping/as-built essays). `MERGE_PLAN §12.x / §13.x` references in code comments resolve there.

**Lifecycle of a step:** team request → scoping essay in ROADMAP → build (one step = one commit) → in the landing commit: as-built entry in WORKLOG, ROADMAP entry deleted, Cursor updated → durable lessons graduate to CONVENTIONS.

**Rotation rule** (what keeps WORKLOG from becoming the next behemoth): when WORKLOG passes ~300 lines, rotate everything but the newest ~10 steps to a dated `plan_archive/worklog_YYYY-MM.md`, first condensing any still-load-bearing facts into CONVENTIONS or a Cursor carried-item. A completed multi-step block may rotate as a unit sooner.

**Single-source rule:** a live fact (smoke count, next step, current real-DB filename) lives in exactly **one** doc; everything else points at it. Every doc rot found in the 2026-07-16 cold-read audit was one fact stated twice with one copy updated.

## History in one breath

The original ANIKA + BECKY three-way merge completed at Step 13 (2026-04); everything since is post-release work driven by team feedback. The blocks: UI / report polish (14–27) · refactor + code quality (28–36) · UI-test + crash-fuzz hardening (37–41, 55–62) · the **Production Scheduling subsystem** (42–54 — spec: [prod-sched-spec.md](plan_archive/prod-sched-spec.md), algorithm: [prod-sched-algorithm.md](plan_archive/prod-sched-algorithm.md)) · press-preference grids + presser staffing + report UX (63–68) · trucks entry + sort modes + schedule-tab polish (69–75) · die constraint + orders PDF report (76–78) · die tracking + hysteresis + whole-piece quantities (79–82) · the doc split (84). Full narratives: [plan_archive/merge_plan.md](plan_archive/merge_plan.md) §13 + [plan_archive/implementation_notes.md](plan_archive/implementation_notes.md).

## Baseline workflow

Run `./Scripts/python.exe -m smoke` at the start and end of any invasive change — the offscreen check battery takes a few seconds and is the regression net (details, real-DB drill rules, and headless-Qt gotchas: [CONVENTIONS.md](CONVENTIONS.md)). **Manual GUI testing on Matthew's Windows machine is the acceptance bar for anything user-facing** — smoke can't reach combo visibility / rebuild / selection / in-cell commit paths, so pause for his sweep before committing Qt-UI-heavy work.
