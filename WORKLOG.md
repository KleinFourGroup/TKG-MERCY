# WORKLOG — as-built record

Backward-looking narrative per landed step; **grows, newest first.** Entry length scales with the step — a one-line change gets one line, a subsystem gets paragraphs. Durable lessons graduate to [CONVENTIONS.md](CONVENTIONS.md); the rotation rule lives in [HANDOFF.md](HANDOFF.md) § The doc system. Everything through Step 83's planning is archived in [plan_archive/merge_plan.md](plan_archive/merge_plan.md) (§12.1 status table + §13 narratives) and [plan_archive/implementation_notes.md](plan_archive/implementation_notes.md); the entries below re-state only the recent steps whose details are still likely to be needed at hand.

## Step 84 — the doc split (2026-07-17)

Retired `MERGE_PLAN.md` (989 lines, 83% closed history) to [plan_archive/merge_plan.md](plan_archive/merge_plan.md) and replaced it with HANDOFF.md (orientation + the single-source 🧭 Cursor) + ROADMAP.md (forward, shrinks) + WORKLOG.md (this file). Adapted from `asciibattler`'s doc shape with three deliberate deviations for MERCY's feedback-driven flow: **permanent files with size-based rotation** instead of per-round files with an archive ritual (MERCY has no round boundaries); **entry lifecycle keyed to steps** (scoping essay in ROADMAP → as-built here → lesson to CONVENTIONS); and a **hard ~15-line Cursor cap** (asciibattler's Cursor is ~1,500 words in one cell — the rot pattern this split exists to kill). A live-obligations triage swept every ⏸/deferred/gate marker in the old §13 into ROADMAP's Blocked / Waiting sections so nothing actionable archived silently. A root `MERGE_PLAN.md` stub redirects old references; code comments citing `MERGE_PLAN §13.x` resolve to the archive unchanged. Doc-only — smoke 72 PASS before and after.

## Step 82 — whole-piece schedule quantities + H:MM press time (2026-07-16)

Fractional schedule quantities (`1008.24` pcs) fixed by **rounding the running total, not the row**: per-part cumulative press-hours with `round(cumAfter×rate) − round(cumBefore×rate)` differencing — every row whole, rows sum *exactly* to `requiredPressed`, zero drift by construction. `ScheduleRow.quantity: int`, `OrderFlag.piecesShort: int` (ceil — a genuine shortage never prints "0 short"), `formatPressHours()` for H:MM display (display-only; float `hours` stays). Found + fixed in passing: integer cells formatted with `:g` flip to scientific notation past 6 digits — moved to `:,` (now a CONVENTIONS gotcha). Header renamed "Press-hours" → "Press time". Full essay: archive §13.51.

## Step 81 (+ follow-up) — central `refreshAllViews()` retires the stale-view FK bug family (2026-07-16)

Every edit/delete success path now makes one `MainWindow.refreshAllViews()` call (~10 ms on the real DB); all 45 hand-wired per-FK `refreshTable()` fan-outs deleted. Shipped option **B**, not the planned refresh-on-show (A): A wipes the generated schedule on tab-switch, still needs per-window wiring, and fails *silently* where B fails *loudly*. Schedule tab excluded from the soft repaint (point-in-time report); pickers preserve selection **by key, never label**. The follow-up sweep over *any* receiver caught three more mutation paths incl. a real shipped bug (inventory value labels stale after edit — a *too-narrow* refresh, not a forgotten one). Smoke 69 → 72. Durable rules graduated to CONVENTIONS ("never hand-wire a refresh", picker pattern, `addX()` fixtures). Full essay: archive §13.50.

## Step 80 — scheduler consumes `Press.currentPart` as the die-hysteresis seed (2026-07-15)

Algorithm restructured from a per-order horizon walk to a **time-outer walk** so a persistent `mount: press→part` map evolves in time order. Cost rule: free on your die's press; `dieChangeHours` charged only to displace a *different* resident die; a part with a home press but no free lane **defers** rather than hop. At the default `dieChangeHours = 0.0` the mount map is pure hysteresis — zero effect on completion dates. Input-only: `schedule()` never writes `currentPart` back. **⚠ The real-floor gate is UNMET** (Cursor carried-item): drills ran on synthesized/manually-entered mounts, not floor state. Full essay: archive §13.49.

## Step 79 — `Press.currentPart` die-state capture (2026-07-15)

`Press.currentPart : str | None` (the mounted die's part; None = idle), db_version 13→14, Presses-tab combo + list column, part-rename cascade. Two manual-pass changes: the list column (die location must be visible at a glance) and **part delete blocks on a mounted die** instead of cascading to None (a silent cascade would erase hand-tracked state). Data-capture only — no scheduler change this step. Full essay: archive §13.48.

> 🗄️ **Steps 1–78** (the merge, polish, refactor, hardening, Production Scheduling, and UX blocks): status table in archive §12.1, narratives in archive §13 + [plan_archive/implementation_notes.md](plan_archive/implementation_notes.md).
