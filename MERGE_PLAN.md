# MERCY — Manufacturing and Employee Records: Costing and Yield
## Merge & Implementation Plan

**Date:** 2026-04-16  
**Author:** Matthew Kilgore  
**Status:** Implementation complete — all 13 planned steps landed as of 2026-04-19, plus Step 9.5 (vestigial `Part` attribute cleanup). Step 7 was run as sub-steps (7a correctness → 7b signature → 7c-1 asserts → 7c-2 logging → 7c-3 polish → 7d double-negation → 7e window centering); Step 13 verified the build end-to-end against real legacy ANIKA + BECKY files (see [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md)). Post-release feature backlog requested by the team during Step 13 is tracked in §13.

**See also:** [`CONVENTIONS.md`](CONVENTIONS.md) — live dev conventions and gotchas (smoke baseline, `fuzz_db.py` upkeep, headless Qt + `Employee` construction pitfalls).

---

## 1–11. Original merge design (archived)

The original three-way merge of ANIKA (part costing) + BECKY (HR) + the new per-employee production tracker is **complete** — Steps 1–13 landed 2026-04 (plus the Step 9.5 polish). The full original design — background and motivation, technical inventory, the schema-fix catalog, the unified 19-table schema, production-tracking design, file structure, the existing-user migration plan, the 13-step implementation order, and the resolved design decisions (original §§1–11) — has been moved **verbatim** to [`plan_archive/original_merge_plan.md`](plan_archive/original_merge_plan.md).

This keeps the live plan focused on current status (§12.1) and the active backlog (§13). The archived schema and design decisions remain the reference for how the shipped app is structured — consult them when touching the data model or migrations.

---

## 12. Implementation Progress

*Last updated 2026-07-02. The original 13-step merge is complete (plus the Step 9.5 polish); Step 13 verified the end-to-end path against real legacy ANIKA + BECKY files — see [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md). Post-release work continues as a running backlog in §13: Steps 14–41 have all landed — per-step status in §12.1, full narratives in [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md). Broadly: UI / report polish (Steps 14–27), a refactor / package-split + code-quality run (28–36 — the `records/`, `file_manager/`, `report/`, and `smoke/` splits plus the vulture and pyright sweeps), and a UI-test + crash-fuzz hardening run (37–41). Each step is one commit on `main` whose message names the step.*

*Step 7 was split into sub-steps 7a–7e to keep each review surface small — see §12.1 for row-by-row status and [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) for the per-substep narrative.*

*2026-06-24: with the Production Scheduling subsystem spec approved by the team, Steps 42–54 were planned as its implementation series — see §13.30 for the roadmap and [`prod-sched-spec.md`](plan_archive/prod-sched-spec.md) for the approved spec. Steps 42 (tab shell), 43 (Press table + first schema/migration to db_version 5), 44 (Pressers table → db_version 6), 45 (Shift Workweek → db_version 7), 46 (Client table → db_version 8, first Sales-group table), 47 (Order table → db_version 9, with the first block-on-delete FK guards) and 48 (Part-Press Preference nested editor → db_version 10, the first nested relational editor) have landed, as has 49 (Order Status nested editor → db_version 11, dated per-order remaining-to-press / remaining-to-ship snapshots), and now Step 50 (scheduling-algorithm design round) has landed as a team-approved addendum ([`prod-sched-algorithm.md`](plan_archive/prod-sched-algorithm.md)) — see §13.38, and Step 51 (scheduling primitives) followed in [`scheduling.py`](scheduling.py) — see §13.39, and now Step 52 (scheduler core) lands the greedy earliest-deadline-first `schedule()` seam in the same module — see §13.40, and now Step 53 (Production Schedule Report UI + PDF export) completes the report front end — see §13.42, and Step 54 (end-to-end verification + v4→v11 migration-chain replay on a real DB + atomic-save rollback) closes the series — see §13.43. **The Production Scheduling subsystem (Steps 42–54) is complete and verified ready to ship.***

*2026-07-02: two further post-release blocks have since landed. **Steps 55–62** hardened the UI-test net and fixed the latent bug classes it surfaced — the Step 55 stale-view invariant + row-selection fuzzing exposed stale projection tabs, `del`-by-stale-key HR editors, the silent `updateEmployee` re-id FK orphan (its own dedicated check), the `updateX` rekey helpers, and the shared `getComboBox` prefill, each fixed and graduated into the always-on baseline. **Steps 63–67** are the press-preference redesign + presser-scheduling + report/UX-polish block: high-contrast selected-tab styling (63), the interactive part-press and presser-press preference grids (64–65, `db_version` 11→12), the scheduler staffing pressers onto presses (66, greedy preference match behind a policy seam), and the date/shift-grouped Production Schedule Report with per-shift / date-range view variants (67). **Step 68** then knocked out the first **§13.45** deferred follow-up — the Open / Save As / Import file dialogs now remember the last-used directory (`QSettings` `lastDir`, mirroring the Step 20 `lastDbPath` pattern) instead of always opening at home. Smoke is at **63 PASS**. Remaining work is the rest of the optional **§13.45** deferred-follow-ups backlog — nothing blocking; the app is in a shippable state.*

> **⚠ The paragraph above is frozen at 2026-07-02 and is now WRONG on both counts — trust §12.1, not this preamble.** Steps 69–83 all postdate it: the smoke count it quotes is long stale (**§12.1 carries the live number — deliberately quoted in exactly one place, so don't restate it here**), and the §13.45 backlog is no longer "the remaining work" — its headline item ("Lever 1") landed as **Step 81**. The live next-step pointer and the rules for reading it are in **§12.1** below. *This block is kept rather than rewritten because the paragraphs above it are dated as-built narrative; the table is the maintained surface. Updated 2026-07-16.*

### 12.1 Step status

> **How to read this table (2 rules, both load-bearing):**
> 1. **✅ means the code landed and its automated checks pass. It does NOT mean the step's real-data / floor gate was cleared.** Live example: **Step 80 is ✅, but its own "eyeball that dies stop hopping on real data" gate is still unmet** (§13.49) — the team hasn't deployed a schedule. When a step's *confidence* matters, read its §13 narrative, not the tick.
> 2. **Steps land out of numeric order.** Step 82 shipped *before* Step 81, so §13's smoke counts read "69" (Step 82) then "69 → 71" (Step 81) — monotonic in real time, not a regression. **Current smoke baseline: 72 PASS.** Derive release scope from the actual tag range, never from step numbers.

| Step | Status | Commit subject |
|------|--------|----------------|
| 1  | ✅ Done | Merge plan Step 1 |
| 2  | ✅ Done | Merge plan Steps 2–3: shared files and records.py |
| 3  | ✅ Done | (same commit as Step 2) |
| 4  | ✅ Done | Merge plan Step 4: unified file_manager.py |
| 5  | ✅ Done | Merge plan Step 5: BECKY tabs + new tab layout |
| 6  | ✅ Done | Merge plan Step 6: merged report.py |
| 7a | ✅ Done | Merge plan Step 7a: correctness fixes |
| 7b | ✅ Done | Merge plan Step 7b: tighten Database signature |
| 7c-1 | ✅ Done | Merge plan Step 7c-1: assert → raise sweep |
| 7c-2 | ✅ Done | Merge plan Step 7c-2: print → logging |
| 7c-3 | ✅ Done | Merge plan Step 7c-3: polish sweep |
| 7d | ✅ Done | Merge plan Step 7d: clean up double-negation leftovers |
| 7e | ✅ Done | Merge plan Step 7e: restore window centering |
| 8  | ✅ Done | Merge plan Step 8: ANIKA schema migration |
| 9  | ✅ Done | Merge plan Step 9: BECKY schema migration |
| 9.5 | ✅ Done | Merge plan Step 9.5: drop vestigial Part attributes |
| 10 | ✅ Done | Merge plan Step 10: DB merge / import |
| 11 | ✅ Done | Merge plan Step 11: production tracking UI |
| 12 | ✅ Done | Merge plan Step 12: production reports |
| 13 | ✅ Done | Merge plan Step 13: end-to-end verification on real data |
| 14 | ✅ Done | Merge plan Step 14: reports skip save dialog, open via temp file |
| 15 | ✅ Done | Merge plan Step 15: production tab refresh when an employee is deleted |
| 16 | ✅ Done | Merge plan Step 16: production batch entry dialog |
| 17 | ✅ Done | Merge plan Step 17: production hours field |
| 18 | ✅ Done | Merge plan Step 18: productivity rate reports |
| 19 | ✅ Done | Merge plan Step 19: trend reports (graphs, 30-day rolling averages) — see §13.6 |
| 20 | ✅ Done | Merge plan Step 20: remember last DB, prompt to reopen on startup |
| 21 | ✅ Done | Split MERGE_PLAN.md: move §12.2/§12.4/§12.5 bodies into plan_archive/, extract live conventions into CONVENTIONS.md |
| 22 | ✅ Done | Merge plan Step 22: add Tool Change production action — see §13.10 |
| 23 | ✅ Done | Merge plan Step 23: production quantity positive check — see §13.11 |
| 24 | ✅ Done | Merge plan Step 24: per-employee productivity report — see §13.12 |
| 25 | ✅ Done | Merge plan Step 25: confirm-on-close dialog (Save / Don't Save / Cancel) — see §13.13 |
| 26 | ✅ Done | Merge plan Step 26: rate columns on production reports — see §13.14 |
| 27 | ✅ Done | Merge plan Step 27: Employee Productivity polish (default-to-All + Tool Change count) — see §13.15 |
| 28 | ✅ Done | Merge plan Step 28: split `records.py` into a `records/` package — see §13.16 |
| 29 | ✅ Done | Merge plan Step 29: code hygiene sweep — see §13.17 |
| 30 | ✅ Done | Merge plan Step 30: selector helper widget — see §13.18 |
| 31 | ✅ Done | Merge plan Step 31: split `smoke.py` into a `smoke/` package — see §13.19 |
| 32 | ✅ Done | Merge plan Step 32: split `file_manager.py` into a `file_manager/` package — see §13.20 |
| 33 | ✅ Done | Merge plan Step 33: split `report.py` into a `report/` package — see §13.21 |
| 34 | ✅ Done | Merge plan Step 34: dead-code sweep with vulture — see §13.22 |
| 35 | ✅ Done | Merge plan Step 35: smoke render every report against fuzzed data — see §13.23 |
| 36 | ✅ Done | Pyright sweep across the codebase — split into 36a-g; see §13.24 |
| 36a | ✅ Done | Merge plan Step 36a: pyright setup + triage |
| 36b | ✅ Done | Merge plan Step 36b: file_manager/ Optional sweep |
| 36c | ✅ Done | Merge plan Step 36c: records/products.py Database TYPE_CHECKING |
| 36d | ✅ Done | Merge plan Step 36d: declarative attribute batch |
| 36e1 | ✅ Done | Merge plan Step 36e1: HR Optional sweep — group A (notes / points / reviews / training) |
| 36e2 | ✅ Done | Merge plan Step 36e2: HR Optional sweep — group B (pto / parts / employees / holidays) |
| 36f | ✅ Done | Merge plan Step 36f: production-side cleanup (report/production.py + production_tab.py + report/employees.py + app.py + employee_detail_tab.py) |
| 36g | ✅ Done | Merge plan Step 36g: bake `pyright --outputjson` into the smoke baseline |
| 37 | ✅ Done | UI regression coverage (smoke checks that replace Step 36-style manual sweeps) — landed across 37a-c |
| 37a | ✅ Done | Merge plan Step 37a: parts_tab_crud + employees_tab_crud (records-side; widget naming for testability) |
| 37b | ✅ Done | Merge plan Step 37b: employee_detail_populates + 5 dialog_roundtrip checks + cascade |
| 37c | ✅ Done | Merge plan Step 37c: holidays_tab_observances + holidays_tab_defaults_crud |
| 38 | ✅ Done | UI crash fuzzer (random-walk through enabled actions, seed-reproducible) — see §13.26 |
| 39 | ✅ Done | inventory_tab dup-date guard loopholes (Create-in-Edit + Update-same-date) — see §13.27 |
| 40 | ✅ Done | PTO carryover dialog stale-snapshot fix + fuzz_db carry-type invariant — see §13.28 |
| 41 | ✅ Done | Graduate `crash_fuzz` to smoke baseline (final fuzz_db invariant + dispatcher wire-in) — see §13.29 |
| 42 | ✅ Done | Merge plan Step 42: Production and Scheduling tab shell (rename + nested sub-tab skeleton) — see §13.30 |
| 43 | ✅ Done | Merge plan Step 43: Press table (full vertical slice) — see §13.30 |
| 44 | ✅ Done | Merge plan Step 44: Pressers table (full vertical slice) — see §13.30 |
| 45 | ✅ Done | Merge plan Step 45: Shift Workweek table (full vertical slice) — see §13.30 |
| 46 | ✅ Done | Merge plan Step 46: Client table (full vertical slice) — see §13.30 |
| 47 | ✅ Done | Merge plan Step 47: Order (shop order) table (full vertical slice) — see §13.30 |
| 48 | ✅ Done | Merge plan Step 48: Part-Press Preference nested editor (full vertical slice) — see §13.30 |
| 49 | ✅ Done | Merge plan Step 49: Order Status nested editor (full vertical slice) — see §13.30 |
| 50 | ✅ Done | Production Scheduling: scheduling-algorithm design round (addendum doc) — see §13.38 |
| 51 | ✅ Done | Production Scheduling: scheduling primitives (calendar / capacity / rate / scrap / deadline helpers) — see §13.39 |
| 52 | ✅ Done | Production Scheduling: scheduler core (greedy EDF `schedule()` seam + infeasibility detection) — see §13.40 |
| 53 | ✅ Done | Production Scheduling: Production Schedule Report UI + PDF export (Schedule tab + report/scheduling.py mixin) — see §13.42 |
| 54 | ✅ Done | Production Scheduling: end-to-end verification + v4→v11 migration-chain replay (real DB) + atomic-save rollback — see §13.43 |
| 55 | ✅ Done | UI-test hardening: stale-view invariant in `crash_fuzz` + gated `_TABLE` row-selection capability — see §13.31 |
| 56 | ✅ Done | Fix Pressers (+ Production) stale-view on employee rename; flagged the `updateEmployee` re-id FK-orphan data bug — see §13.32 |
| 57 | ✅ Done | Fix HR sub-editor Update crashes: pop-with-default on stale keys (reviews/points/notes/training/PTO) + holidays original-key delete — see §13.33 |
| 58 | ✅ Done | Graduate `crash_fuzz` row-selection into the baseline (`select_rows` default on, runs green) — see §13.34 |
| 59 | ✅ Done | Fix `updateEmployee` re-id FK orphan: cascade pressers + production to the new id (+ `employee_reid_cascades` check) — see §13.35 |
| 60 | ✅ Done | Harden the `db.updateX(old, new)` rekey helpers against a missing original key (stale-window Update) — prereq for Step 58 — see §13.36 |
| 61 | ✅ Done | Harden `getComboBox` against a stored value missing from its options (combo-prefill crash) — prereq for Step 58 — see §13.37 |
| 62 | ✅ Done | Fix inventory edit `readData` crash class (date guarded before indexing; part editor checks `.parts`) — fuzzer-found, audited as a class — see §13.41 |
| 63 | ✅ Done | Selected tab / sub-tab high-contrast styling — first global QSS, mode-aware — see §13.44 |
| 64 | ✅ Done | Interactive press-preference grid (parts × presses, in-cell drop-downs) + "Not set" rename + 5↔1 heat-map cue — see §13.44 |
| 65 | ✅ Done | Presser → Press preference table + tab (reuses the Step 64 grid; db_version 11→12) — see §13.44 |
| 66 | ✅ Done | Scheduler assigns pressers (secondary to presses; greedy preference match, balanced reserved behind the seam) — see §13.44 |
| 67 | ✅ Done | Schedule report: date/shift-grouped layout + per-shift / date-range view variants — see §13.44 |
| 68 | ✅ Done | File dialogs remember last-used directory (`QSettings` `lastDir`; Open / Save As / Import) — see §13.45 |
| 69 | ✅ Done | Order sort modes (due date / client name, never order #) on the Orders + Order Updates tabs — see §13.46 |
| 70 | ✅ Done | De-emphasize the schedule Horizon knob (collapsed "Advanced" panel; clarifies it's plan-ahead depth, not a display filter) — see §13.46 |
| 71 | ✅ Done | Unified schedule report row (Generate + built-in From/To/Shift live filter + one Export) — see §13.46 |
| 72 | ✅ Done | Condense flagged orders/parts to one-line summaries + detail windows — see §13.46 (same commit as Step 71) |
| 73 | ✅ Done | Flagged orders show client + sort by due date (detail window + PDF) — see §13.46 (same commit as Step 71) |
| 74a | ✅ Done | Parts-per-truck config: `part_truck` table (db_version 12→13) + **Parts per Truck** in-cell grid tab under Scheduling config — see §13.46 |
| 74b | ✅ Done | Trucks-mode Order Status entry ("Enter in trucks" checkbox; half-trucks → pieces via `part_truck`, stores/shows pieces; hybrid block) — see §13.46 |
| 75 | ✅ Done | Harden `db.updatePresser` against a stale original id (crash_fuzz-found; Step 60 class) + deterministic guard — see §13.46 |
| 76 | ✅ Done | Trucks toggle applies to remaining-to-press only; remaining-to-ship is always pieces — see §13.47 |
| 77 | ✅ Done | Orders/Order-Status PDF report + helper window (linked on the Orders + Order Status tabs; landscape, value + total) — see §13.47 |
| 78 | ✅ Done | One-press-per-part scheduler constraint (die) + die-change-cost seam — see §13.47 |
| 79 | ✅ Done | Press current-die state: `Press.currentPart` (part whose die is mounted, None=idle); Presses-tab combo + list column; part rename cascade + delete-blocks-on-mounted-die; one-off Presses-tab stale-view fix; db_version 13→14; no scheduler change (data-capture only) — see §13.48 |
| 80 | ✅ Done | Scheduler consumes `Press.currentPart` as the die-placement / hysteresis seed (costed placement: time-threaded `mount` map, die moves charged against `dieChangeHours`, incumbent-die-wins) so dies stop hopping between presses; algorithm change, no schema — see §13.49 |
| 81 | ✅ Done | Permanent fix for the stale-view FK-refresh bug family — central `MainWindow.refreshAllViews()` on every edit path (option **B**, not the planned refresh-on-show); all 45 per-FK `refreshTable()` fan-outs stripped — see §13.50 |
| 82 | ✅ Done | Whole-piece schedule quantities via drift-free running-total rounding (`ScheduleRow.quantity` → int) + H:MM press time in the tab/PDF (+ `:g` scientific-notation bug on piece counts fixed) — see §13.51 |
| 83 | 🔲 Planned | Shared `EditWindow` base class: lift the 20 copy-pasted `__init__` preambles + `updateX`/`newX` handlers (and Step 81's `refreshAllViews()` call) onto an inherited commit path — pure refactor, no behaviour change — see §13.52 |

### 12.2 Decisions / deviations worth knowing before Step 6+

*Step-by-step implementation narratives moved to [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) on 2026-04-22 to keep this doc lean. See that file for what actually shipped for each step, and why.*

### 12.3 Known deferred issues visible in the current build

- *(All three previously listed items — bare `== None` residuals, the DeMorgan-able condition in `file_manager.py`, and the `MainTab` class name — were resolved by Step 29's hygiene sweep, 2026-05-10. See §13.17.)*
- *(`employees_tab.py`'s `EmployeeOverviewTab` was renamed to `EmployeeListTab` on 2026-05-13 to match the tab label, closing the rename Step 29 deferred. Manual UI sweep across Active / Inactive sub-tabs and the New / Edit / Toggle / Delete / Report buttons confirmed identical behavior.)*

### 12.4 Test conventions used so far

*Historical smoke-check list moved to [`plan_archive/test_conventions.md`](plan_archive/test_conventions.md) on 2026-04-22. Live dev conventions (always-on smoke baseline, `fuzz_db.py` upkeep, headless-construction gotchas) now live in [`CONVENTIONS.md`](CONVENTIONS.md) at repo root.*

### 12.5 Step 13 — end-to-end verification on real data (findings)

*Step 13 real-data drill findings moved to [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md) on 2026-04-22. See that file for the five drill results and the regression hooks that remain.*

---

## 13. Post-release feature backlog

Requests from the team after their first look at MERCY. Each item is small enough to be one step and one commit in the §12 style; open questions resolved in-session on 2026-04-19 are recorded inline. Order is deliberate: smallest / lowest-risk first, so tomorrow's session can ship increments rather than gating the whole backlog behind the biggest item.

### 13.1 Step 14 — reports: skip save dialog, open via temp file ✅ Done

Landed 2026-04-20. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 14 for implementation notes and deviations.

### 13.2 Step 15 — production tab refresh when an employee is deleted ✅ Done

Landed 2026-04-20. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 15 for implementation notes and the scope decisions.

### 13.3 Step 16 — production tab: batch entry ✅ Done

Landed 2026-04-20. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 16 for implementation notes and the scope decisions.

### 13.4 Step 17 — production hours field ✅ Done

Landed 2026-04-21. Surfaced in Matthew's first post-release feedback session: the team had forgotten to include duration/hours in the production schema. One-session add — new `hours REAL DEFAULT 0` column on `production`, wired through records / save / load / table / Quick Entry / Batch Entry / all four reports. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 17 for implementation notes, the Case-4 stamping fix it piggybacked, and the report-formatting decisions.

### 13.5 Step 18 — productivity rate reports (tables, feeds costing) ✅ Done

Landed 2026-04-24. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 18 for the team spec as delivered, the four-case layout, the Tool Change collapse, the bold-totals convention it surfaced (now in [`CONVENTIONS.md`](CONVENTIONS.md)), and verification details.

### 13.6 Step 19 — trend reports (graphs, 30-day rolling averages) ✅ Done

Landed 2026-04-24, back-to-back with Step 18. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 19 for the team spec as delivered, the layout shapes across all four selection combos + Tool Change, the rolling-mode flag surface, the sum-vs-mean call on Tool Change time-spent (open for team confirmation), and verification details. Pre-implementation planning notes preserved in the same archive entry under "Step 19 planning notes (preserved)".

### 13.7 Step 20 — remember last DB, prompt to reopen on startup ✅ Done

Landed 2026-04-22. Fifth post-release feature item from Matthew's backlog: MERCY previously booted into an empty DB every session. Quality-of-life add — `QSettings`-backed `lastDbPath` persisted after every successful `open()`/`saveAs()`, loaded on startup via a new `MainWindow._loadPath(path) -> bool` helper, prompted through a `QMessageBox.question` in `main.py` between `window.show()` and `app.exec()`. Zero new deps (`QSettings` is already in the PySide6 stack). See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 20 for implementation notes, the decision to keep the prompt modal every time (no "always reopen" checkbox yet), and the stale-path-silent-skip behavior.

**Follow-up still open (not part of Step 20).** Confirm with Matthew whether to also remember the last *import* path for the Import Database dialog, since that currently hard-codes `os.path.expanduser("~")`. Separate feature, separate step.

### 13.8 Dev tooling landed

Not step commits but worth cataloging so a cold pickup knows they exist:

- **`mock_reports.py`** — Step 18 planning artifact, landed 2026-04-21 (commit `5bd3433`). Generates three candidate productivity-rate-report layouts (A/hierarchical, B/flat-with-fleet-comparison, C/action-by-part matrix), each with a reportlab-native grouped bar chart. Output writes to `mock_reports/` (gitignored). Deletable once the team picks a design.
- **`fuzz_db.py`** — fake-data DB generator, landed 2026-04-22 (commit `e4246ee`). Writes a fully-populated MERCY DB through the real `FileManager.saveFile()` pipeline: every record type (materials, mixtures, packaging, parts, inventory, employees, reviews, training, attendance, PTO including CARRY/CASH/DROP, notes, holidays + observances, production) gets plausible random data. Deterministic with `--seed`; scales `tiny|small|medium|large` (medium → ~1.7k production records over 90 days). Verified end-to-end: generated DBs roundtrip through `MainWindow.loadFile()`, the Part → Mix → Material cost chain computes cleanly, `PDFReport.productionSummaryReport` renders against them, and a given seed is byte-equivalent across all 12 populated tables on re-run. Good for stress-testing any report (including Step 18's future output) without needing real team numbers.
- **`version.py` + `main.spec` auto-versioning** — landed 2026-04-22. `app.py`'s `VERSION` constant is no longer hand-edited; `version.py` derives it from `git describe --tags --always --dirty` at import time (leading `v` stripped). Frozen PyInstaller exes can't call git at runtime, so `main.spec` runs the same describe at build time, writes `_version.py` (gitignored, bundled into the exe via normal Analysis pickup) as the fallback, and names the output `mercy-{VERSION}.exe`. Release flow collapses to `git tag vX.Y.Z && pyinstaller main.spec`. `main.spec` is now tracked (was `.gitignore`d by the generic `*.spec` rule; carved out with `!main.spec`) so the build logic rides the repo. See [`CONVENTIONS.md`](CONVENTIONS.md) "Versioning & builds" for day-to-day usage.

### 13.9 Step 21 — split MERGE_PLAN.md into archive files ✅ Done

Landed 2026-04-22. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 21 for what moved where, what stayed live, and the pointer-redirection work.

### 13.10 Step 22 — add Tool Change production action ✅ Done

Landed 2026-04-22 alongside a VERSION bump to `1.0rc3`. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 22 for the team spec, scope across `defaults.py` / `records.py` / `production_tab.py` / `report.py` / `fuzz_db.py`, and the verification details. The Tool-Change-in-reports follow-up was resolved 2026-04-24 — see §13.5 / §13.6 for the call.

### 13.11 Step 23 — production quantity: positive, not non-negative ✅ Done

Landed 2026-04-24 alongside the second-feedback-round backlog refresh. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 23 for the two-line fix, why `ProductionRecord.setRecord` deliberately doesn't get a belt-and-suspenders guard, and the new `production_quantity_validation` smoke check (regression-verified via stash dance).

### 13.12 Step 24 — per-employee productivity report ✅ Done

Landed 2026-05-08, table-only first cut (Trend variant deferred). See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 24 for the shipped four-case shape, selector wiring, deviations from the pre-confirmation skeleton, and the pre-confirmation planning notes preserved alongside.

### 13.13 Step 25 — confirm-on-close dialog (Save / Don't Save / Cancel) ✅ Done

Landed 2026-04-24, back-to-back with Steps 18/19 and Step 23. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 25 for the shipped shape, the smoke-check factoring, and the dirty-tracking follow-up. Pre-implementation planning notes preserved in the same archive entry under "Step 25 planning notes (preserved)".

### 13.14 Step 26 — rate columns on production reports ✅ Done

Landed 2026-05-08. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 26 for the rationale (team confusion between production and productivity reports), the new `_fmtRate` helper, the per-report column additions, and the Tool-Change-suppression gating.

### 13.15 Step 27 — Employee Productivity polish ✅ Done

Landed 2026-05-08, same-session follow-up to Step 24. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 27 for the two paper-cuts fixed (default-to-All on mode entry; Tool Change quantity rendered as record count in overview tables) and the rationale for the cross-action total dashes.

### 13.16 Step 28 — split `records.py` into a `records/` package ✅ Done

Landed 2026-05-11. Smoke 17 PASS pre- and post-change, on the first run. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 28 for the four-file shape (`products.py` / `employees.py` / `production.py` / `database.py`), the `__init__.py` re-export shim that keeps all ~20 existing `from records import X` sites working unchanged, and the annotation-evaluation gotcha that turned out not to matter (function-body annotations on complex targets like `self.db: Database | None = None` aren't evaluated at runtime, so there's no circular-import problem to manage).

The follow-up Step 28.1 ("simplify the bundled `from records import (...)` lines in `file_manager.py` / `smoke.py` / `fuzz_db.py` to per-module imports") landed 2026-05-13 — `file_manager/load.py` and `fuzz_db.py` now import directly from `records.products` / `records.employees` / `records.production`. (`smoke/` was already absorbed during Step 31's split, where each submodule inlines its own per-call records imports.) Smoke 17 PASS pre- and post-change.

**Why not also split `report.py`?** Same length, harder to split — every method belongs to one `PDFReport` class. Splitting requires either composing `PDFReport` from per-domain mixins or converting per-domain reports to free functions. The smaller-files instinct held after Steps 30/31/32 landed; the mixin-composition path won (Step 33, 2026-05-13). See §13.21.

### 13.17 Step 29 — code hygiene sweep ✅ Done

Landed 2026-05-10 as one umbrella commit; 17 PASS pre- and post-change. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 29 for the five-item rundown — `mock_reports.py` deletion, `fmtRate` consolidation, `== None` sweep, DeMorgan cleanup, and the `MainTab` → `EmployeeDetailTab` rename (which deviated from the planned `EmployeeOverviewTab` due to a collision in `employees_tab.py`).

### 13.18 Step 30 — selector helper widget ✅ Done

Landed 2026-05-11, immediately after Step 28. Smoke 17 PASS post-refactor; manual UI sweep across all seven modes confirmed visibility / rebuild / selection-persistence behavior identical to the pre-refactor build. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 30 for the shipped API shape, the two resolved open questions (separate file; getter properties not Qt signals), and the line-count savings.

### 13.19 Step 31 — `smoke.py` split ✅ Done

Landed 2026-05-11, immediately after Step 30. CLI shifted from `./Scripts/python.exe smoke.py` to `./Scripts/python.exe -m smoke`; CLAUDE.md and CONVENTIONS.md updated to match. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 31 for the four-file shape, the throwaway AST-based splitter that was used to relocate the 17 check functions verbatim, and the one fix that surfaced during verification (the original splitter under-imported `datetime_date` for two submodules; smoke caught it on the first run).

### 13.20 Step 32 — `file_manager.py` split ✅ Done

Landed 2026-05-11, immediately after Step 31 — closes the refactor backlog. Mixin composition, six-file package; smoke 17 PASS first try; fuzz-DB load → save → reload roundtrip across 19 populated tables (3522 production records) row-for-row identical post-save. Real-world legacy-DB sweep on Matthew's machine cleared the final acceptance gate. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 32 for the shipped six-file shape, the mixin-vs-pure-helper decision, the orchestration-vs-domain-work boundary that drove `initFile`/`setFile` placement, the deferred-import dance for the `ImportMixin` ↔ `FileManager` cycle, and fuzz-roundtrip mechanics. The Step 28.1 follow-up for `file_manager/load.py` landed 2026-05-13 — see §13.16.

### 13.21 Step 33 — split `report.py` into a `report/` package ✅ Done

Landed 2026-05-13. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 33 for the four-file mixin composition, the eventual goal of one-report-per-mixin once layouts settle in the field, and the `TREND_MODE` smoke-side touch.

### 13.22 Step 34 — dead-code sweep with vulture ✅ Done

Landed 2026-05-14. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 34 for the 8 distinct dead-code classes deleted at confidence 80, the `Inventory.delMaterialRecord/delPartRecord` same-session restore for symmetry, and the false positives left in place at confidence 60.

### 13.23 Step 35 — smoke: render every report against fuzzed data ✅ Done

Landed 2026-05-14, same session as Step 34. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 35 for the 9-report coverage shape (drives `fuzz_db.populate*` directly against `MainWindow().db` — no file I/O, no captured stdout), the seed-1 reproducibility, and the `%PDF-` magic-byte gate.

### 13.24 Step 36 — Pyright sweep across the codebase ✅ Done

Landed 2026-05-14 / 2026-05-15 across seven substeps (36a-g). **Baseline 219 → 0 errors; smoke gained a `pyright_baseline` check (18 → 19 PASS).** See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 36 for the substep-by-substep narrative — pyrightconfig setup, file_manager/ sweep, records/products.py TYPE_CHECKING shim, declarative-attribute batch, the HR Optional sweep (split into group A / group B per call-site judgment), production-side cleanup including the reportlab library-stub strategy, and the smoke-gate design.

The dual-mandate-on-failure-handling guidance Matthew established during 36e1 (user-visible-degradation > loud crash > silent fail; readability tiebreaker; ask when they pull apart) is recorded in `~/.claude/.../feedback_failure_mandate.md` and now applies repo-wide.

### 13.25 Step 37 — UI regression coverage (replace manual sweeps) ✅ Done

Landed across 37a-c on 2026-05-15. **Smoke 19 → 30 PASS** (11 new checks). See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 37 for the widget-naming-for-testability change (Edit/Select dialogs expose `self.*Edit` / `self.*Combo` instead of `mainLayout[i][j]` indexes), the shared `smoke/ui.py` helpers, and the per-check breakdown.

### 13.26 Step 38 — UI crash fuzzer (random-walk, seed-reproducible) ✅ Done

Landed 2026-05-15. New `smoke/ui_fuzz.py` with `crash_fuzz(seed=None, iterations=2000)` — random-walk over enabled widgets, with a `sys.excepthook` installed to catch the `RuntimeError`s that Qt's signal-slot wrapper otherwise swallows; `walk_rng` + `fixture_rng` both derive from the one `seed`. Shipped **deliberately unwired** from the dispatcher because the first three seeds surfaced two real root causes (inventory dup-date guard; PTO `getCarryHours` `count <= 1` invariant). See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 38 for the action/silencing design and the full bug analysis; both root causes were fixed in Steps 39–40 and the check wired in by Step 41.

### 13.27 Step 39 — inventory_tab dup-date guard loopholes ✅ Done

Landed 2026-05-15. First Step-38 follow-up: closed two [`inventory_tab.py`](inventory_tab.py) dup-date loopholes (Create-in-Edit hitting an existing date; Update with an unchanged date) that bypassed the `errorMessage` dialog into the db layer's `RuntimeError` guards. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 39 for the mode-split `readData` check, the preserved variant-create workflow, and the crash_fuzz repro seeds. Smoke baseline 30 PASS.

### 13.28 Step 40 — PTO carryover stale-snapshot + fuzz_db carry-type invariant ✅ Done

Landed 2026-05-15. Second Step-38 follow-up: fixed `getCarryHours` / `getCarryType` `RuntimeError('count <= 1')` crashes from two complementary bugs — `fuzz_db.populatePTO` generating multiple carry-type entries per year, and `PTOCarryWindow` acting on a stale `unusedType` snapshot. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 40 for both fixes and why both were needed. Smoke baseline 30 PASS.

### 13.29 Step 41 — graduate `crash_fuzz` to smoke baseline ✅ Done

Landed 2026-05-15, same session as Steps 39–40. With both follow-ups in, `crash_fuzz` runs clean on `seed=None`; lowered `DEFAULT_ITERATIONS` 2000 → 1000 and wired it in as the **31st smoke check** (30 → 31 PASS), plus a final `fuzz_db` clip closing a year-spanning-PTO invariant gap. See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 41 for timing data and the self-sustaining-regression-net rationale.

### 13.30 Production Scheduling subsystem (approved 2026-06-24) — Steps 42–54

New post-release subsystem: order tracking plus a **Production Schedule Report** (which parts to press, on which presses / shifts / days, to hit order deadlines). The approved spec lives standalone in [`prod-sched-spec.md`](plan_archive/prod-sched-spec.md) — Part 1 is the resolved-decisions log (two review rounds, all questions answered); Part 2 is the spec. That doc is the authoritative reference for the build; this section is the implementation roadmap.

**Shape of the work:** ~7 new tables (`presses`, `pressers`, `shift_workweek`, `part_press_pref`, `clients`, `orders`, `order_status`), a "Production" → "Production and Scheduling" tab rename with a nested sub-tab skeleton, the two design rounds the spec calls for (UI layout — realized in Step 42; scheduling algorithm — Step 50), and finally the scheduler + report. New record classes land in two domain modules under the `records/` package — `records/scheduling.py` (Press, Presser, ShiftWorkweek, PartPressPref) and `records/sales.py` (Client, Order, OrderStatus) — aggregated into `Database` behind the existing re-export shim. The schedule report becomes a new `report/scheduling.py` mixin composed into `PDFReport` the way Step 33 split the others.

**Ordering rationale:** smallest / lowest-risk first — the tab shell, then flat CRUD tables, then the two nested editors, then the algorithm design gate, then the scheduler and report, then an end-to-end verification gate. Dependencies drive the few hard orderings: Part-Press Preference needs `presses` (Step 43); Order needs `clients` (Step 46); Order Status needs `orders` (Step 47); the scheduler (Step 52) needs everything.

| Step | Description | Risk | Testable milestone |
|------|-------------|------|--------------------|
| 42 | Rename the Production tab → **"Production and Scheduling"**; build the nested sub-tab skeleton — keep **Daily Entry / Reports**, add empty **Sales**, **Scheduling config**, and **Schedule** groups. `app.py` wiring only. | Med | Renamed tab + 4 groups render; all existing production CRUD/reports unchanged. Manual UI gate. |
| 43 | **Press** table (`name` PK). Full vertical slice (see note below); Presses tab under Scheduling config. First schema step — establishes the `db_version`-bump + additive-migration pattern. | Low | Create/edit/delete presses; survives save → reload. |
| 44 | **Pressers** table (`employeeId` FK → `employees.idNum`, `hoursPerShift`). Vertical slice; Pressers tab. | Low | Presser rows CRUD against existing employees; roundtrips. |
| 45 | **Shift Workweek** table (which weekdays each shift 1–3 works). Vertical slice; Workweek tab. | Low | Set/clear working weekdays per shift; roundtrips. |
| 46 | **Client** table (`name` PK, `transportDays` — business days). Vertical slice; Clients tab under Sales. | Low | Client CRUD; roundtrips. |
| 47 | **Order** (shop order) table (`orderNum` PK; `client` + `part` FKs; `quantity`, `price` = order total, `dueDate`). Vertical slice; Orders tab under Sales. | Low-Med | Order CRUD against existing clients/parts; roundtrips. |
| 48 | **Part-Press Preference** nested editor — `(part, press, score)` with `UNIQUE(part, press)`, score 1–5, missing pair = neutral. Mixtures / part-pads-style sub-editor under Scheduling config. | Med | Score presses per part; roundtrips. Manual UI gate. |
| 49 | **Order Status** nested editor — per order, dated snapshots of `remainingToPress` + `remainingToShip` (two independent fields). Sub-editor under Sales. | Med | Add/edit dated snapshots; latest-by-date wins; order shows fulfilled when ship-remaining hits 0. Manual UI gate. |
| 50 | **Scheduling-algorithm design round** — addendum doc fixing the heuristic, objective order, capacity/idle-press model, rate/scrap/deadline math, and infeasibility handling. Team review before any scheduler code. | Low (doc) | Approved algorithm addendum. |
| 51 | **Scheduling primitives** (pure logic, no UI): shift-works-on-date (workweek + observances), presser-hours per shift per day (pressers + PTO, coarse), concurrent-press cap = `min(pressers present, presses)`, per-part empirical rate with `Part.pressing` fallback, scrap inflation `N/(1−greenScrap)/(1−fireScrap)`, effective press-by date (`due − transport business days − slack`). | Med | Each helper covered by deterministic `smoke/` checks. |
| 52 | **Scheduler core** — greedy earliest-deadline-first, ties broken by order price (revenue), preferred-press assignment, slack buffer, honoring capacity and idle presses. Emits `(date, shift, press, part) → quantity` plus a late / at-risk list. | High | Schedule respects working days + capacity; infeasible orders are flagged, never silently dropped. smoke asserts invariants on `fuzz_db` data. |
| 53 | **Production Schedule Report** — on-screen regenerable table (Schedule group) + horizon control + an explicit late-orders section + reportlab PDF export. | Med | Generate the schedule on screen and as PDF; late section visible. Manual UI gate. |
| 54 | **End-to-end verification** on realistic fuzzed (and, if available, real) data; replay the full migration chain on an existing DB the way Step 13 did; backup/restore check. | — | Subsystem ready to ship. |

**What "full vertical slice" means for the table steps (43–47):** one commit each that lands the record class (`records/scheduling.py` or `records/sales.py`), the `CREATE TABLE` in `file_manager/schema.py`, an additive idempotent migration in `file_manager/migrate.py` with a `db_version` bump, the save/load mixin additions, `fuzz_db.py` population so the table stays fully populated, a CRUD tab wired into `app.py`, a `smoke/` CRUD-roundtrip check, and a `crash_fuzz` dispatcher wire-in so the UI fuzzer exercises the new tab. Migrations are additive (`CREATE TABLE IF NOT EXISTS`), so the chain replays cleanly — Step 54 re-runs the whole chain against a real DB.

**Manual UI gate** (per the standing rule that smoke can't cover combo visibility / nested-editor rebuild / selection logic): Steps **42, 45, 48, 49, 53** are the Qt-UI-heavy ones — pause for Matthew's manual sweep before committing each. (Step 45 was added to this list at build time: its fixed shift×weekday checkbox grid is a custom widget, not the flat-CRUD template, so it earned a sweep.)

**Two design rounds, as the spec requires:** Step 42 realizes the already-approved UI layout from the spec's §7, so it's implementation rather than a fresh design pass. Step 50 is a genuine design gate — the scheduling heuristic doesn't exist yet, so it lands as a reviewable addendum doc before Steps 51–53 build on a blessed approach. If Step 52 turns out large at review time, split it sub-step-style (à la Step 7 / Step 36): primitives are already carved off into Step 51 to keep the core's surface small.

### 13.31 Step 55 — provable stale-view net: tab-refresh invariant in the UI fuzzer ✅ Done

**Motivation.** The downstream-refresh bug has now recurred twice. When one edit changes another table's *contents* — an FK **rename** propagated by `Database.update<X>` (client/part → orders), or a **cascade-delete** by a `del<X>` (order delete → `orderStatus`) — the originating data mutation is correct, but the downstream tab's cached `self.data` isn't re-rendered, so the on-screen table goes stale. Step 47's manual sweep caught the rename half (client/part → Orders); Step 49's caught the delete twin (order delete → Order Status). The "refresh every downstream tab you touch" convention and per-step smoke assertions patch *instances*, but nothing **proves** the class is closed — and a `getTuple()`/dict-level smoke check passes right over a stale view because the *data* is right; only the render is wrong.

**What this step adds.** "Lever 2" from the 2026-06-25 design discussion: a post-action invariant in [`smoke/ui_fuzz.py`](smoke/ui_fuzz.py)'s `crash_fuzz` random walk. After each executed action, for every registered *projection tab*, compare the on-screen rows against a fresh recompute from `db`; any divergence is a seed-reproducible failure naming the tab, the action, and the seed. This converts the entire downstream-refresh bug class — present and future, every tab, every mutation path nobody has thought of yet — into an automatic smoke failure **before commit**, instead of something a human must remember to assert step by step.

**A "projection tab"** is one whose displayed rows are a pure function of a `db` collection via `genTableData()` — the FK-reference CRUD/list tabs: materials, mixtures, packaging, parts, presses, pressers, clients, orders, order status, part-press preference, shift workweek, holiday defaults, and the active/inactive employee lists. These are exactly where the bug lives.

**Explicitly excluded** (their view legitimately differs from a naïve full-collection recompute because they carry view-local filter/selection state, which would yield false positives): the production tab (employee / date / action filters), employee overview & detail (per-employee selection), inventory (date selection), and anything whose `genTableData` reads a combo/selection rather than the whole collection. The registry is curated, and each entry is confirmed selection-independent before inclusion.

**Design sketch** (per registered tab, after each fuzz action):

```
displayed = list(tab.table.dbModel._data)   # what's currently on screen
tab.genTableData()                          # recompute self.data from db (no view push)
if displayed != tab.data:                   # view diverged from truth -> a tab went stale
    return [f"seed={seed} step={i}: {tab} stale after {label} ..."]
tab.table.setData(tab.data)                 # resync to truth so the walk continues honestly
```

- The check must **not** call `refreshTable()` *before* comparing — that would self-heal and mask the very bug it's hunting. It resyncs *after* the comparison so later steps still run against correct data.
- Needs a small registry mapping each projection tab to its `(genTableData, data, table)` triple; most tabs already follow that convention, so the registry is a list of `mainApp` attribute names plus the recompute call. The per-order / per-part nested editors are separate windows, not registered tabs, so they're out of scope.
- It also catches a tab accidentally omitted from `MainWindow._refreshAllTabs()` (its rows would diverge after a load or mutation), so it doubles as a registration guard.

**Risk:** Medium — touches the fuzzer's hot loop and depends on the registry excluding filter-state tabs to avoid false positives.

**Testable milestone.** With the invariant wired in, reverting any one downstream refresh (e.g. the Step 49 `OrdersTab.deleteSelection` → `orderStatusTab.refreshTable()` line) makes `crash_fuzz` fail with a seed-reproducible stale-view report naming the tab; restoring it returns to green. The net runs clean on the current build, and `crash_fuzz` stays within its smoke time budget.

**Sequencing.** Independent of the scheduler series (Steps 50–54) — it only touches the smoke/fuzz harness — so it can be pulled forward (e.g. done before Step 50) or taken after the subsystem lands; numbered 55 to keep the Production Scheduling series (42–54) contiguous. A companion **"Lever 1"** (route every edit/delete success path through `_refreshAllTabs()`, collapsing the N×M refresh-wiring obligation to one registration list) is a possible follow-up but is **out of scope** here **[⚠ Lever 1 SHIPPED as Step 81 on 2026-07-16 — see §13.50. Don't build it again.]** — this step is detection-only.

**As-built (landed 2026-06-25, pulled forward ahead of Step 50).** The net (`_checkStaleViews` + a curated `_projectionTabs` registry in [`smoke/ui_fuzz.py`](smoke/ui_fuzz.py)) landed as designed, with two reality checks against the sketch:

- *The "(genTableData, data, table) triple" isn't uniform.* The fresh-data attribute varies by tab — most use `data`, the products tables predate it (`materials` / `mixtures` / `parts`), and the employee / holiday-defaults lists use `tableData` — so the registry parameterizes the attribute name per entry. `genTableData` and `tab.table` *are* uniform. The sketch's `shift workweek` entry was **dropped**: `WorkweekTab` is a checkbox grid with no `DBTable` and caches no row projection (`refreshTable` re-syncs each checkbox live from `db`), so nothing there can go stale. The resync via `setData` was verified not to clear `tab.selection`, so it doesn't weaken the walk.
- *The fuzzer couldn't reach the bug class.* `crash_fuzz` only ever clicked buttons/combos/line-edits — it **never selected table rows**, and Edit/Delete read `self.selection` (populated only by a row click). So the walk could *create* entities but never *rename* or *delete* them, leaving the FK-rename / cascade-delete paths the net targets unreachable (reverting the Step 49 `orderStatusTab` refresh produced **zero** failures across 5,000 iterations). Fixed by adding a `_TABLE` row-selection action, **gated behind a `select_rows` flag (default off)**.

With `select_rows=True` the net immediately earned its keep — it caught a **real, previously-unspotted** downstream-refresh miss (employee rename doesn't refresh the Pressers tab, whose rows show employee-derived labels) — and a deterministic harness confirmed the §13.31 milestone literally (revert the `OrdersTab` → `orderStatusTab` refresh ⇒ net reports `orderStatusTab` stale; restore ⇒ green). But enabling row-selection also surfaced a backlog of **pre-existing** edit-dialog crashes that were simply never fuzzed before (HR sub-editors that `del db[<changed key>]` on rename). So, exactly as **Step 38 shipped the fuzzer unwired and Steps 39–41 cleaned up and graduated it**, `select_rows` defaults **off** — the always-on baseline (`crash_fuzz` called bare) stays green at **45 PASS** — and the cleanup + graduation are split into Steps 56–58. crash_fuzz stays within budget (`select_rows=False`: 9.3–14.4 s; the net's per-step recompute is cheap on tiny fuzz data).

**Repro seeds (`crash_fuzz(seed=S, select_rows=True)`):** Pressers stale-view → `seed=4`; holiday-default rename crash → `seed=5`/`6`/`7`; review rename crash → `seed=2`; note rename crash → `seed=15`.

### 13.32 Step 56 — Pressers (+ Production) stale-view on employee rename ✅ Done

Landed 2026-06-25. The first bug the Step 55 net found with row-selection on: `EmployeeEditWindow.readData` refreshed the overview + active/inactive employee lists, but **not** `pressersTab`, whose rows are `_presserLabel(db, empId)` strings derived live from `db.employees`. Rename an employee and the Pressers tab kept showing the old name (e.g. on-screen `WALSH Morgan (4106)` vs recompute `8G52 Morgan (4106)`).

Fix: in the employee-edit success path, refresh **both** employee-derived tabs — `self.mainApp.pressersTab.refreshTable()` and `self.mainApp.productionTab.refresh()`. Production was included as the Pressers twin: its table + filter render the same `_employeeLabel`, so a rename stales it identically; the Step 55 net didn't flag it only because Production is excluded from the registry (filter-stateful), and the fuzzer's `_seedFuzzData` doesn't populate production rows so the staleness can't surface there at all. The standing "refresh every downstream tab you touch" convention (cf. [`feedback_fk_rename_refresh`]) covers both. **[⚠ Superseded 2026-07-16 — that convention was RETIRED by Step 81 (§13.50): edit paths now make one `refreshAllViews()` call and hand-wired fan-outs like the two named in this paragraph are gone. Kept as the record of what shipped at Step 56; do not follow it.]** Verified: deterministic name-edit through the real dialog leaves the net clean, and `crash_fuzz(seed=4, select_rows=True)` now runs clean to completion. Smoke green (45 PASS).

**Discovered while fixing — a separate, deeper `updateEmployee` data bug (not yet fixed).** `records/database.py:updateEmployee(oldID, newID)` (the re-id path, reachable by editing the ID field) rekeys `employees / reviews / training / attendance / PTO / notes` but **not `pressers` and not production `employeeId`** — so changing an employee's ID **silently orphans their presser row** (confirmed: presser stays keyed by the old ID, `(missing #id)`) and strands their production records at the old ID. This is silent FK corruption (the worst quadrant of the dual-mandate, [`feedback_failure_mandate`]), distinct from the view-refresh class, and the Step 55 net can't catch it (both displayed and recompute agree on the orphan, so no divergence). The presser orphan is clearly a bug — a presser is "current config tied 1:1 to a live employee" ([`delEmployee`] cascades it). Whether production *history* should follow a re-id is a product call (delete intentionally leaves production as `(missing #id)`). Not folded into Step 56 because it's a db-layer cascade fix, not a UI refresh. **Resolved as Step 59 (§13.35) — fixed immediately, pressers + production both cascade.**

### 13.33 Step 57 — HR sub-editor Update crashes on stale/renamed keys ✅ Done

Landed 2026-06-25. A cluster of pre-existing `KeyError` crashes the Step 55 row-selection fuzzer surfaced on the Update path of the hand-rolled HR edit dialogs, in **two shapes**:

- **`reviews` / `points` / `notes` / `training` / `PTO`** delete by the *original* key (`self.<record>.<datefield>`) — correct for a rename — but crash when that record was deleted out from under a still-open edit window (now reachable: row-selection lets the walk delete a row from the sub-tab while its editor is open; the dialog's calendar isn't a fuzzer-touchable widget, so this is the external-delete path, not a changed-key one). Fix: `dict.pop(key, None)` instead of `del`, so Update degrades to a safe re-add (each already guards the *new*-key collision, so the upsert can't clobber a different record).
- **`holidays` (default holidays)** is the genuine *changed-key* shape: `readData` deleted `defaults[self.holidayName.text()]` — the **new** name — which both `KeyError`s on a rename and orphans the old entry. Fix: drop the *original* name (`self.holiday`) via pop-with-default, and add a rename-collision guard (renaming onto a different existing holiday now errors instead of silently overwriting it).

These are distinct from the name-keyed CRUD tables (materials / clients / presses / orders / parts), which route renames through `db.updateX(old, new)`. Per the dual-mandate ([`feedback_failure_mandate`]), the pop-with-default keeps the user's save working (no corruption, no crash) rather than erroring on a rare concurrent-edit race.

Verified: the three repro seeds (2, 5/6/7, 15) plus a deterministic holidays-rename test now run clean; full smoke green (46 PASS); a 25-seed `select_rows=True` sweep went **24/25 clean** (was 9/15 before Steps 56–57).

**The one remaining sweep failure is a different class → Step 60.** `seed=18` crashes in `db.updatePress` (`self.presses[name].name = name` after a no-op rekey): the *same* stale-window-after-external-delete theme, but in the name-keyed `updateX` rekey helper rather than a dialog `del` — if the original name was deleted elsewhere, the `{new if k==entry else k …}` comprehension never creates `new`, so the follow-up index `KeyError`s. Almost certainly shared by the sibling helpers (`updateClient` / `updatePart` / `updateMaterial` / `updateMixture` / `updatePackaging` / `updateOrder`). Out of Step 57's scope (not HR, not a dialog `del`); spun out as Step 60 (§13.36) and a **prerequisite for Step 58** (the baseline can't graduate `select_rows=True` until the sweep is fully clean).

### 13.34 Step 58 — graduate `crash_fuzz` row-selection into the baseline ✅ Done

Landed 2026-06-25, closing the Step 55 series. With every bug the row-selection fuzzer surfaced now fixed (Steps 56–57, 59–61), flipped the `select_rows` default `False → True` (the baseline calls `crash_fuzz` bare, so the default *is* the lever), so the always-on smoke net now guards the full rename / delete / cascade / stale-window bug class — the Step 41 move for this capability. Gate met before flipping: a 40-seed `select_rows=True` sweep ran **40/40 clean**, full-run time held at **~14s** (12.4–15.5s, within the 10–20s budget, so `DEFAULT_ITERATIONS` stayed at 1000), and after the flip full smoke passed plus five bare `crash_fuzz()` (= baseline) runs were clean at 11–14s.

**Series retrospective.** The Step 55 net paid for itself many times over: row-selection turned `crash_fuzz` from a create-only walk into one that renames/deletes/edits existing rows, and that surfaced four distinct, pre-existing latent bug *classes* nobody was looking for — a stale projection view (56), `del`-by-stale/changed-key in six HR sub-editors (57), a silent FK-orphan on employee re-id the net structurally can't see (59, hence its own dedicated check), `KeyError` in seven `updateX` rekey helpers (60), and a `ValueError` in the shared `getComboBox` prefill (61). The sweep convergence (9/15 → 24/25 → 39/40 → 40/40) tracked each class fix. Net is now self-sustaining: any future downstream-refresh miss or stale-window edit crash becomes a seed-reproducible smoke failure before commit.

### 13.35 Step 59 — `updateEmployee` re-id FK orphan: cascade pressers + production ✅ Done

Landed 2026-06-25, pulled forward right after Step 56 (the bug was discovered there). `records/database.py:updateEmployee(oldID, newID)` rekeyed the HR sub-DBs (`reviews / training / attendance / PTO / notes`) but **not** `pressers` (keyed by employeeId, stored as `Presser.employeeId`) or production (keyed by `rec.key()`, a tuple beginning with employeeId). So re-id'ing an employee silently orphaned their presser row and stranded their production records at the dead id. A re-id keeps the employee alive — unlike `delEmployee`, which intentionally leaves production as a `(missing #id)` tombstone — so the team's call (session 2026-06-25) was that **both follow the new id**, keeping the employee + presser config + production history together (and productivity/costing reports whole).

Fix: extend `updateEmployee` to rekey `pressers` (and set the moved `Presser.employeeId`) and to update each production record's `employeeId` then rebuild `self.production` off the new keys. No collision risk — the edit dialog guarantees `newID` isn't an existing employee, so it has no pre-existing presser/production rows. Guarded by a new **`employee_reid_cascades`** smoke check (46 PASS) that drives the real `EmployeeEditWindow` re-id and asserts presser + production follow, both in memory and across a save/reload roundtrip. This is the *only* automated guard for this bug — the Step 55 net can't see it (an orphan reads identically in the view and a fresh recompute, so there's no divergence to flag).

### 13.36 Step 60 — harden the `db.updateX` rekey helpers against a missing original key ✅ Done

Landed 2026-06-25. Surfaced by the Step 57 wider sweep (`seed=18`, `select_rows=True`): `db.updatePress(entry, name)` does `presses = {name if k == entry else k: v …}; self.presses[name].name = name`. If `entry` (the original name) is no longer present — a stale `PressEditWindow` whose press was deleted from the Presses tab while the editor stayed open — the comprehension copies the dict unchanged (no key matches `entry`), so the follow-up `self.presses[name]` `KeyError`s. Same stale-window-after-external-delete theme as Step 57, but in the name-keyed rekey helper rather than a dialog `del`.

Fixed the whole family uniformly — `updatePart`, `updatePackaging`, `updateMixture`, `updateMaterial`, `updatePress`, `updateClient`, `updateOrder` each gained an `and <key> in self.<coll>` clause on its rename guard, so a rename whose original key is gone no-ops cleanly instead of rekeying to a key the comprehension never created. (`updateEmployee` already guarded every rekey with `if oldID in coll`, including the Step 59 pressers/production additions, so it needed no change.) The dialog layer was left as-is: the no-op means a stale Update silently does nothing and still reports success — acceptable per the dual-mandate (no crash, no corruption); a dialog-layer "this record no longer exists" re-validation is possible future polish, not done here. The happy-path renames stay covered by the existing CRUD roundtrip smoke checks; once Step 58 graduates `select_rows=True`, the net guards regressions of the stale-window crash directly. Verified: `crash_fuzz(seed=18, select_rows=True)` now clean; full smoke green (46 PASS).

### 13.37 Step 61 — `getComboBox` tolerant of a stale/unknown stored value ✅ Done

Landed 2026-06-25. The Step 60 sweep's last straggler (`seed=30`, `select_rows=True`): opening `PartsEditWindow` crashed at `getComboBox(pads, part.pad[i])` → `items.index(item)` `ValueError`, because the part referenced a pad-kind packaging no longer in the current pad list (a kind/availability change leaves the stored value stale). `getComboBox` ([`utils.py`](utils.py)) is a prefill helper used across the edit dialogs, and it assumed every stored value is still a valid option — a pre-existing ANIKA fragility, independent of the scheduling work. Fix: if the stored value isn't among the options, append it (so it stays visible and selected) rather than `ValueError`-ing on `items.index()` or silently dropping it — the user sees the now-invalid value and can correct it (dual-mandate: no crash, no silent corruption). Hardens the whole combo-prefill class in one place. Verified: `seed=30` clean; full smoke green (46 PASS); existing CRUD checks (which prefill valid values) unaffected.

### 13.38 Step 50 — scheduling-algorithm design round (addendum doc) ✅ Done

Landed 2026-06-25. The second design gate the spec requires (prod-sched-spec §6 / §8): a reviewable addendum, [`prod-sched-algorithm.md`](plan_archive/prod-sched-algorithm.md), that fixes the scheduler heuristic **before** any scheduler code so Steps 51–53 are well-posed. No code — the deliverable is the approved doc. Grounded throughout in the records that shipped in Steps 43–49 (real field names) and the reused costing / HR data.

**What it fixes.** The §2 primitives (Step 51): shift-works-on-date (workweek ∧ not a shift-specific observance), pressers-present (shift via `Employee.shift`, coarse PTO-day removal, active-only), empirical pressing rate (`sum(qty)/sum(hours)` over `Pressing` records → `Part.pressing` cold-start fallback → infeasible), the **multiplicative** scrap inflation — deliberately *not* costing's additive `Part.getScrap()` (flagged so nobody "simplifies" it), effective press-by date, and a **press-hours** capacity model with idle presses. The §3 core (Step 52): greedy front-loaded EDF — sort by `(effectivePressBy, −price, orderNum)`, place each order's press-hours into the earliest working shift-day capacity, then pin shift-day work onto specific press lanes by preference score. §4 infeasibility: three quantified flags (`LATE` / `NO_CAPACITY` / `NO_RATE`) plus soft warnings, with a never-drop rule. §5 determinism (total tiebreaks → a smoke invariant is possible against `fuzz_db` data).

**Team review (2026-06-25)** resolved the six open questions (§8): **front-load** over JIT; **2 business days** of slack — a unilateral pull-in to absorb the known cold-start rate noise, to be dialed in once real performance is visible; **weekends-only** transport business days for v1 (no carrier shipping-holiday calendar exists; the shift-specific `observances` are the wrong list); and confirmed the three lighter calls (180-day / 4-hour empirical-rate window, neutral press preference = midpoint 3, highest-`hoursPerShift` lanes when pressers > presses).

**Standing directive into the build (§10):** real order data isn't in hand yet, so the greedy core is **provisional**. Step 52 keeps it behind a single `schedule(db, T, config) -> ScheduleResult` seam with config-driven policy, so a better optimizer or a less-front-loaded variant rips out cheaply without touching the §2 primitives, the report, or any schema (the scheduler is stateless — no `db_version` bump). Smoke unchanged (doc-only; baseline stays 46 PASS).

### 13.39 Step 51 — scheduling primitives (pure logic) ✅ Done

Landed 2026-06-25. The first code of the scheduler series: the six addendum §2 primitives as pure, deterministic logic in a new top-level [`scheduling.py`](scheduling.py) — the "scheduling logic module," distinct from `records/scheduling.py` (the record classes). No UI, no I/O, no persisted state; the stable foundation the swappable Step 52 core (addendum §10) sits on. Not a manual-UI-gate step (§13.30 lists only 42/45/48/49/53).

**Shipped:** `shiftWorksOn` (workweek ∧ not a shift-specific observance), `onPTO` + `pressersPresent` (active-only, coarse PTO-day removal, CARRY/CASH/DROP sentinels skipped), `concurrentPresses` + `capacityHours` (the press-hours lane model — idle presses when pressers < presses, top-by-hours lanes when pressers > presses), `pressingRate` (empirical `sum(qty)/sum(hours)` over `Pressing` records in the 180-day window → `Part.pressing` fallback → None), `requiredPressed` (multiplicative scrap, greenScrap percent→fraction, missing fireScrap → 0, ≥100% clamped so impossible scrap is absurd-but-finite rather than a divide-by-zero — deliberately *not* costing's additive `Part.getScrap()`), and `subBusinessDays` / `shipBy` / `effectivePressBy` (weekend-only business days, transport back-out, slack pull-in).

**Six new smoke checks (46 → 52 PASS):** five hand-built-fixture checks (one per §2 area, exact expected values — e.g. shift-specific holiday closure, idle-press capacity, empirical-beats-fallback rate, the scrap percent-conversion, weekend-skipping deadlines) plus `scheduling_primitives_fuzz`, which runs every primitive over a tiny seed=1 fuzzed DB asserting invariants only (no crash; sane ranges; non-working shift-days have zero capacity; scrap never shrinks a quantity; ship-by ≤ due date; press-by ≤ ship-by) — the Step 35 "render against fuzzed data" spirit applied to logic. `compile_all` picks up the new root module for free; the pyright baseline stays clean.

**As-built vs the addendum's pseudocode.** The §2 sketches used illustrative names; the real reads are `db.holidays` (not `db.observances`) for the ObservancesDB and `db.production.values()` (production is a `dict[tuple, …]`, not a list). `MAX_HORIZON_DAYS` is deferred to Step 52 — it bounds the scheduler's forward walk, not any primitive, so it lands with the core that uses it (no unused constant left lying around). The three tunables the primitives do use (slack, rate window, rate min-hours) are module constants now; Step 52 lifts them onto the `schedule(db, T, config)` config object per §10.

### 13.40 Step 52 — scheduler core (greedy EDF + infeasibility) ✅ Done

Landed 2026-06-25. The scheduler itself, implementing addendum §3 (sequencing /
timeline / allocation / assignment) + §4 (infeasibility) as pure logic appended
to [`scheduling.py`](scheduling.py) — the single `schedule(db, today, config) ->
ScheduleResult` seam the addendum §10 mandates, so the report (Step 53) and smoke
consume the *result*, never the algorithm. Stateless (spec §5.1): no schema, no
`db_version` bump, recomputed on demand. Not a manual-UI-gate step (§13.30 lists
only 42/45/48/49/53) — pure logic + smoke, like Step 51.

**Shipped.** Greedy earliest-deadline-first, front-loaded:

- **Result types** (frozen dataclasses): `ScheduleRow` (`date, shift, press,
  part, quantity, hours`, the §3.5 output cell), `OrderFlag` (`kind` +
  magnitude), `ScheduleWarning` (soft, per-part), `ScheduleResult` (rows / flags
  / warnings / `today`), and `ScheduleConfig` — the §6 tunables (slack, rate
  window, rate min-hours, the new `MAX_HORIZON_DAYS = 365`) on one object so
  "front-load less / more slack" is a parameter change, not surgery (§10).
- **Eligibility + sequencing** (§1, §3.1): outstanding-to-press > 0 and not
  fulfilled; sorted by `(effectivePressBy, −price, orderNum)` — EDF, revenue
  tiebreak, total order for determinism. No-due-date orders sort last and can
  never be flagged late.
- **Allocation** (§3.3): each order's scrap-inflated press-hours
  (`requiredPressed / pressingRate`) placed into the earliest working shift-day
  capacity, front to back from `today`, decrementing a lazily-computed,
  memoized `remainingHours[(date, shift)]`.
- **Press assignment** (§3.4): a second pass pins each shift-day's pooled
  `(part → hours)` onto specific press lanes — the `min(present, presses)`
  running lanes with top-by-hours presser budgets, presses chosen by aggregate
  `PartPressPref` score (neutral = midpoint 3, decision #5; press name breaks
  ties), each part placed preferring its score and split across lanes when one
  runs short. Best-effort bin-packing; never changes *whether* work fits (§3.3
  settled that against the pooled hours), only *which lane*.
- **Infeasibility** (§4), never-drop: `INFEASIBLE_NO_RATE` (no empirical history
  *and* no `Part.pressing`), `INFEASIBLE_NO_CAPACITY` (demand unplaced at the
  horizon, carrying short press-hours + pieces), `LATE` (placed but past the
  effective press-by, carrying calendar days late + pieces short at the
  deadline). LATE and NO_CAPACITY are mutually exclusive per order —
  NO_CAPACITY subsumes lateness (the actionable number is the residual). Soft
  warnings: cold-start fallback rate, missing `fireScrap`.

**Refactor.** `pressingRate` split out `empiricalPressingRate` (the empirical
half), so the scheduler can tell whether a part's rate is empirically grounded
or riding the `Part.pressing` fallback (the §4 fallback warning) without
recomputing — public `pressingRate` behavior unchanged, Step 51 checks
untouched.

**Two new smoke checks (52 → 54 PASS):** `scheduling_scheduler` — five
hand-built fixtures with exact expected output (front-loaded 8/8/4 multi-day
placement; LATE with `daysLate`/`piecesShort`; `INFEASIBLE_NO_RATE` with no
rows; `INFEASIBLE_NO_CAPACITY` under a capped horizon; preference-ranked lane
splitting where a 5-scored press fills before a neutral one) plus a determinism
assertion — and `scheduling_scheduler_fuzz`, which runs `schedule()` over a tiny
seed=1 fuzzed DB asserting the §4/§5 invariants (deterministic re-run; every row
on a working shift-day / real press / real part; placed press-hours ≤ capacity
per shift-day; every eligible order scheduled or flagged, never silently
dropped; non-negative flag magnitudes). `compile_all` + the pyright baseline
stay clean.

**As-built vs the addendum.** The greedy core is **provisional** (§10) — kept
behind the one `schedule()` seam so a better optimizer or a less-front-loaded
policy rips out without touching the §2 primitives, the result types, or any
schema. The §6 tunables moved from the primitives' default args onto
`ScheduleConfig`; order sequencing now reads the config's slack (not the
primitive default) so a single `schedule()` call is internally consistent.

### 13.41 Step 62 — inventory edit `readData` crash class (date guard + `.parts`) ✅ Done

Landed 2026-06-25, right after Step 52. Surfaced while running the Step 52 final
smoke battery: the always-on `crash_fuzz` baseline (`seed=None`) went
**intermittently red** with a `KeyError` in [`inventory_tab.py`](inventory_tab.py)
`readData`. Independent of the scheduler work (`crash_fuzz` never touches
`scheduling.py`) — a pre-existing latent bug the fuzzer hits only on sparse,
time-based seeds (a 0-39 fixed-seed sweep is clean, which is why Step 58's sweep
missed it).

**The bug class — "checked-then-dereferenced-anyway."** Both inventory record
editors' `readData` flag a missing date up top
(`if not self.date in db.inventories: errors.append(...)`) but then the
duplicate-record check below it indexed `db.inventories[self.date]`
*unconditionally*, `KeyError`-ing on a stale/absent date **before** the queued
error could reach the gate — the validation detects the bad state, then crashes
on it. The fuzzer reaches it because its fixture never populates inventory, so
every date is absent and any inventory-editor Create trips it. The part editor
carried a **second** bug on the same line: it checked `.materials` (not
`.parts`), so it both missed real duplicate-part collisions *and* then crashed in
`addPartRecord`'s own dup guard.

**Audited as a class before fixing** (per Matthew's call): swept all 21 app
`readData` methods (3 parallel review agents) for the same shape — an early
membership/None check that appends an error, then an unconditional index/deref of
that same value before the `if len(errors)==0` gate. **Exactly two instances, both
in `inventory_tab.py`** (the material editor and its part twin); the other 19 are
clean (safe `key in coll` membership tests, post-gate derefs, or deliberate
`raise RuntimeError` invariants). One near-miss ruled out: `pto_tab.py`'s
`used + hours` — `checkInput` returns `1` (not `None`) on a parse failure, so the
arithmetic never sees `None`.

**Fix.** Both editors now guard `self.date in db.inventories and …` before
indexing (so a stale date degrades to the already-queued error), and the part
editor reads `.parts`. New deterministic smoke check `inventory_edit_missing_date`
(55 PASS) drives both editors headlessly on the absent-date path and the part
editor on a real duplicate — verified to fail pre-fix (two date `KeyError`s + the
`.parts` `RuntimeError`) and pass post-fix. Full smoke now runs green 3×
back-to-back including the previously-flaky `crash_fuzz`. Same dual-mandate as the
Step 57 HR-editor fixes ([`feedback_failure_mandate`]): a user clicking Create in
the inventory editor for a date with no snapshot now sees the error dialog instead
of a hard crash.

### 13.42 Step 53 — Production Schedule Report (Schedule tab + PDF export) ✅ Done

Landed 2026-06-25. The report front end for the scheduler series: the **Schedule**
sub-tab (Step 42's placeholder) now renders the stateless `schedule()` result on
screen and exports it to PDF — the Step 33 mixin pattern applied to a new
[`report/scheduling.py`](report/scheduling.py) (`ScheduleReportsMixin` composed
into `PDFReport`). Consumes a `ScheduleResult` from the single
`schedule(db, today, config)` seam (addendum §10) — never the algorithm internals
— so a future optimizer swap touches nothing here. Manual UI gate cleared
(Matthew's sweep, 2026-06-25).

**Shipped.**

- [`schedule_tab.py`](schedule_tab.py) `ScheduleTab`: a **horizon** spinbox
  (1..`MAX_HORIZON_DAYS`, default 365 = "project until all outstanding orders are
  placed", spec §5.1) mapped onto `ScheduleConfig.maxHorizonDays`, **Generate
  Schedule** + **Export PDF** buttons, two on-screen `DBTable`s (the
  `(date, shift, press, part) → quantity / press-hours` grid + an explicit
  flagged-orders section: Late / No capacity / No rate with §4 magnitudes), a
  soft-warnings line, and a status line. Read-only views (no `parentTab`, so row
  selection is a no-op). Stateless: holds the last `ScheduleResult` only to feed
  Export; `exportPdf` writes a `tempReportPath` PDF and `startfile`s it (the Step
  14 open-via-temp convention).
- [`report/scheduling.py`](report/scheduling.py) `scheduleReport(result,
  horizonDays)`: a title/subtitle banner + three paginated sections (Schedule /
  Flagged Orders / Warnings-when-present) via a private `_scheduleSection` helper
  that re-draws the banner and a "-- Continued" heading per overflow page,
  mirroring the production reports.
- [`app.py`](app.py): the placeholder swapped for the real tab, and
  `scheduleTab.refresh()` added to `_refreshAllTabs` so a freshly-loaded DB clears
  any schedule from the prior file rather than showing a stale one (the scheduler
  is recomputed on demand, never persisted — spec §5.1).

**Design calls.** Horizon is the one exposed control; **slack stays at the config
default** (the addendum §6 lists slack as optional — "possibly" — so v1 keeps the
surface lean). Generate is explicit (no auto-regenerate on every edit) — matches
the on-demand report convention and avoids re-walking 365 days on each refresh.
Deliberately *not* in the Step-55 projection registry: a generated schedule is
intentionally stale-until-regenerated (like the production tab), so the stale-view
net excludes it.

**Two new smoke checks (55 → 57 PASS):** `schedule_report` renders the PDF across
three scenarios (empty DB → "No production scheduled."; tiny fuzz DB through the
real `schedule()`; a hand-built `ScheduleResult` carrying all three flag kinds +
both warning kinds), asserting non-empty + `%PDF-` magic; `schedule_tab_generates`
drives the tab headlessly — Generate matches a direct `schedule()` call
row-for-row, Export writes a real `%PDF-` (with `startfile` stubbed), and
`refresh()` clears the result + tables + re-disables Export. `crash_fuzz` already
exercises the tab's buttons / horizon spinbox (it walks enabled widgets regardless
of the visible tab), so the always-on baseline guards it too. `compile_all` + the
pyright baseline stay clean.

Only Step 54 (end-to-end verification + migration-chain replay) remains in the
Production Scheduling series.

### 13.43 Step 54 — end-to-end verification + migration-chain replay ✅ Done

Landed 2026-06-25, closing the Production Scheduling series (Steps 42–54). The
"subsystem ready to ship" gate, modeled on Step 13: a real-data drill plus two
durable synthetic smoke checks. No production-code changes — verification only.

**Real-data drill (the way Step 13 did it).** A throwaway driver
(`step54_real_data.py`, **not committed** — machine-specific, like Step 13's) ran
offscreen against a **copy** of Matthew's real `Mercy DB 6-1-26.db` — the latest
db file before the feature block, a genuine `db_version=4` MERCY DB with 165 parts,
48 employees, 296 production records. Full findings in
[`plan_archive/scheduling_real_data_findings.md`](plan_archive/scheduling_real_data_findings.md);
in brief: the **v4→v11 additive chain** created all 7 scheduling/sales tables empty,
left every pre-existing count identical, and wrote **no `.bak`** (the additive-chain
invariant, previously asserted nowhere); fuzzed orders on the real parts/employees
roundtripped through save/reload; and `schedule()` + `scheduleReport` ran end-to-end
(32 rows, 0 late flags, 6 genuine cold-start warnings on real parts with unset
`fireScrap` / no pressing history). The original file was SHA-256 **byte-identical**
afterward (only the copy was opened). No real order data exists yet (per the
addendum), so orders were fuzzed — a re-run against real orders is future work, no
code needed.

**Two new smoke checks (57 → 59 PASS), the durable net:**
- `mercy_v4_to_v11_end_to_end` — the automated twin of the real-data drill. Builds a
  realistic v11 DB (fuzz_db), **downgrades it on disk** to a v4 shape (drops the 7
  tables, stamps `db_version=4`) so it's byte-for-byte a pre-Step-43 file with real
  costing/HR/production data, then replays v4→v11 and asserts: terminal version 11,
  all 7 tables created empty, pre-existing data untouched, **no backup written**;
  then populates scheduling/sales, roundtrips save→reload, and runs
  `schedule()` + `scheduleReport` (rows on real working shift-days/presses/parts,
  every eligible order scheduled or flagged, PDF renders). Where the per-version
  checks (v3→v4 … v10→v11) migrate a 1-row fixture and only assert the tables
  appear, this proves the *whole pipeline* on a migrated DB.
- `scheduling_save_rollback` — Step 13's atomic-save drill (check 2b), re-run now
  that `_saveFileBody` writes the 7 new tables: an injected `RuntimeError` after the
  body but before saveFile's outer commit must roll back, leaving the on-disk
  scheduling/sales tables byte-identical and a sentinel press off disk. Confirms the
  try/rollback/commit wrapper reverts a failed save across the new tables, not just
  the original ones.

`compile_all` + the pyright baseline stay clean. **The Production Scheduling
subsystem (Steps 42–54) is complete: order tracking, the scheduler, the report, and
now end-to-end verification on real data.**

### 13.44 Press-preference redesign + presser scheduling + report/UX polish (planned 2026-07-02) — Steps 63–67

Second post-release feature block from the team (relayed by Matthew, 2026-07-02) after living with the Production Scheduling subsystem (Steps 42–54). Five requests, sequenced smallest / lowest-risk first in the §13 tradition; each is one step / one commit. Design calls settled in this planning session are recorded inline.

**The five asks.**
1. Replace the Part-Press Preference list+modal editor with an **interactive grid** — rows = parts, columns = the registered presses, each cell a drop-down the team sets directly (no edit window). Rename the unscored option "Neutral" → **"Not set"** (still treated as 3 for scheduling). Add a visual cue that **5 = most preferred, 1 = least**.
2. An **analogous Presser → Press preference** table + tab: any presser can work any press, but they specialize; same "pure preference, no measured throughput effect yet" treatment as parts.
3. Have the schedule **assign pressers** too — strictly **secondary** to assigning work to presses: reuse the presser-press preference to staff people onto the already-decided press work.
4. Schedule report **per-shift** and **date-range-limited** variants (e.g. "third shift's schedule for the next three days").
5. A **stronger, higher-contrast selected** appearance for the tab / sub-tab ribbon.

**Shape of the work.** Only Step 65 touches the schema (a new `presser_press_pref` table, `db_version` 11→12, additive migration — the §13.30 vertical-slice template). Step 64 is a UI-only refactor: the `PartPressPref` record, its table, save/load, and migration are all unchanged — "Not set" is still `None` / no row, which `scheduling._prefScore` already reads as `NEUTRAL_PRESS_SCORE = 3`. Step 66 extends the stateless scheduler (no schema — a new `ScheduleRow.presser` field + an assignment pass behind the existing `schedule(db, today, config)` seam). Steps 63 and 67 are pure UI. The reusable **grid widget** built in Step 64 is the same one Step 65's tab reuses, so 64 lands first.

**Ordering / dependencies.** 63 (standalone, any time) → **64** (builds the grid) → **65** (reuses the grid; produces the presser-press data) → **66** (consumes it) → **67**. Steps 64 and 65 may split sub-step-style (grid widget / adopt-for-part-press; e.g. 64a/64b) if the review surface is large, à la Steps 7 / 36 / 52.

| Step | Description | Risk | Testable milestone |
|------|-------------|------|--------------------|
| 63 | **Selected-tab contrast.** First global QSS in the app (there is none today — pure native Qt): a stylesheet on `QApplication` targeting `QTabBar::tab:selected` (and the nested `QTabWidget`s) for a high-contrast selected (sub)tab. Optionally a small `colors.py` so the accent has one home. `main.py` / new stylesheet only. | Low | Selected (sub)tab is visibly higher-contrast at every tab level; no other visual regressions. Manual UI gate. |
| 64 | **Press-preference grid.** New reusable delegate-based grid widget (rows = parts, columns = presses, each cell a `Not set / 1–5` drop-down via a `QStyledItemDelegate` — the app's first in-cell-editing pattern); green→amber→red heat-map fill + legend, "Not set" a distinct gray. Rewrite `part_press_pref_tab.py` onto it; rename "Neutral" → "Not set". **No schema / record / migration change** — `PartPressPref` semantics unchanged. | Med | Set scores directly in-cell; roundtrips through save/reload; scheduler output identical to pre-refactor. Manual UI gate. May split 64a (widget) / 64b (adopt). |
| 65 | **Presser → Press preference.** Full vertical slice (§13.30 template): `records/scheduling.py:PresserPressPref` (keyed by `employeeId`, `scores: dict[press → 1–5]`, missing = neutral), `CREATE TABLE presser_press_pref`, additive `_migrateV11ToV12` (**db_version 11→12**), save/load, `database.py` dict + `setPresserPressScore` + cascades (press rename/delete, presser delete), `fuzz_db` populator, a **Presser-Press Preference** tab under Scheduling config reusing the Step 64 grid, smoke CRUD + crash_fuzz dispatcher + projection-tab registry. | Med | Score presses per presser in the grid; roundtrips; full migration chain replays on a real DB. Manual UI gate. |
| 66 | **Scheduler assigns pressers** (secondary). `ScheduleRow` gains `presser: int \| None`. After `_assignLanes` fixes which presses run and what they press (unchanged, part-preference-driven), a matching pass assigns the present pressers (`pressersPresent`) to those presses maximizing total presser→press score (Not set = `presserNeutralScore`, deterministic tiebreak). `ScheduleConfig` gains `presserNeutralScore = 3` and a `presserAssignment = "preference"` policy seam (`"balanced"` / `rotationWeight` reserved but unimplemented — the §10 provisional-heuristic pattern). Thread a Presser column through `schedule_tab` + the `report/scheduling` PDF. Short presser-heuristic note appended to `prod-sched-algorithm.md`. **No schema change** (stateless). | Med-High | Each running press on a working shift-day gets one present presser by preference; surplus pressers unassigned; deterministic re-run; smoke invariants on fuzz data. |
| 67 | **Schedule report variants.** Two new **named report actions** on the Schedule tab — a per-shift schedule and a date-range-limited schedule (a single focused action may take **both** a shift and a start/end range, per the team's "third shift, next three days" example). Both **filter the full computed `ScheduleResult` for display / PDF** — a view slice, **not** a shortened scheduler horizon (shortening the horizon would corrupt downstream placement and misflag capacity). `schedule_tab.py` + `report/scheduling.py`. Open sub-decision: whether the order-level, dateless flagged-orders / warnings sections show in full or are annotated on a filtered variant. | Med | Generate/export a single-shift schedule and a date-range schedule (including combined) on screen and as PDF. Manual UI gate. |

**Design calls settled 2026-07-02 (this planning session).**
- **Grid cells:** colored cell + click-to-open drop-down (a Qt item delegate), *not* a persistent combo box in every cell — the real DB has ~165 parts, so hundreds of always-live widgets would be heavy; the delegate scales and reads like a spreadsheet.
- **Visual cue:** green→amber→red heat map with a legend; "Not set" rendered plain / gray so unset is visibly distinct from an explicit 3 (even though the scheduler treats both as 3).
- **Presser assignment:** *preference-only* now (pure max-score matching + `presserNeutralScore`), with `"balanced"` / rotation reserved behind the config seam and left unimplemented until real production weeks show whether reshuffling annoys anyone. Invariant: presser preference never changes *what* is produced or *which* presses run — only *who stands where*. Normal case is pressers < presses (nobody starved); the rare inverse (pressers > presses) leaves surplus pressers unassigned that shift.
- **Report variants:** separate named report actions, not inline filters on the main Generate / Export controls.

**Manual UI gates** (standing rule — smoke can't cover in-cell editing / heat-map render / tab styling / selection logic): Steps **63, 64, 65, 67**. Step 66 is logic-first (like Steps 51 / 52); its Presser column is a mechanical add covered by smoke, but worth a glance.

**Migration-version-churn upkeep (Step 65 only):** bumping `db_version` 11→12 forces updating the hardcoded terminal-version literals + docstrings in `smoke/migrations.py`, registering the new CRUD check in both `smoke/__init__.py` and `smoke/__main__.py`, and adding the new table via migration + fresh-schema path **only** — never into `UNIFIED_TABLES` (the format fingerprint stays frozen at the v4 shape), per CONVENTIONS.md.

**Step 63 landed 2026-07-02.** First global QSS in the app: a new [`style.py`](style.py) owns the accent + tab stylesheet, applied on the `QApplication` in [`main.py`](main.py). The selected (sub)tab is a fixed filled blue (`#1a6dd8`) with bold white text and a slight height bump; the unselected face / hover / borders draw from `palette(...)` roles so the tab bar follows the system light/dark theme — the first cut hardcoded light greys that stood out in dark mode, fixed to palette-driven before commit. Manual UI sweep cleared (light + dark, per the standing UI gate). Smoke 59 PASS (`compile_all` picks up the new root module; `pyright_baseline` clean).

**Step 64 landed 2026-07-02.** The Part-Press Preference editor is now an interactive grid — the Step 48 list + per-part `PartPressPrefEditWindow` modal is gone. New reusable widget [`pref_grid.py`](pref_grid.py) (`PrefGrid` / `PrefGridModel` / `ScoreDelegate` + a `makeHeatLegend()`): rows = parts, columns = the registered presses, each score cell a click-to-open `Not set / 1-5` drop-down via a `QStyledItemDelegate` — **the app's first in-cell-editing pattern** (design call 2026-07-02: a delegate scales to ~165 parts where hundreds of always-live combos would not). Edits are live (no Update button — the team "sets directly"), written straight through the unchanged `Database.setPartPressScore`. "Neutral" → **"Not set"** (UI label only). **No schema / record / migration change** — `PartPressPref` is still `None` / no-row for unset and `scheduling._prefScore` still reads that as the neutral midpoint 3, so scheduler output is identical to pre-refactor (the `scheduling_scheduler*` checks stay green). [`part_press_pref_tab.py`](part_press_pref_tab.py) was rewritten onto the widget; [`parts_tab.py`](parts_tab.py) got one stale-comment fix.

*Visual:* green (5, most preferred) → amber (3) → red (1, least) heat-map fill with a legend; the numeral is a fixed dark colour chosen to stay legible on all five fills in **both** themes, while the chrome (headers, gridlines, borders) and the "Not set" tint (a low-alpha gray that blends over the palette base) are palette-driven so the grid follows the system light/dark theme (verified via an offscreen light+dark grab and Matthew's manual sweep, per the standing UI gate). *Testability:* `PrefGrid` mirrors `table.DBTable`'s duck-typed contract (`dbModel._data`, `setData`, `parentTab` + `onSelect`), so the Step 55 stale-view net and `crash_fuzz` treat it like any flat CRUD table — the `partPressPrefTab` projection-registry entry is unchanged. The [`smoke/ui.py`](smoke/ui.py) `part_press_pref_crud` check was rewritten to drive the grid through its `ScoreDelegate` (prefill + in-cell edit) while keeping the rename / cascade / save-reload assertions. Smoke 59 PASS (`pyright_baseline` clean).

**Open, deferred to team feedback (not a blocker):** the in-cell **edit-trigger feel** ships at double-click / click-an-already-selected-cell (+ F2) opens the drop-down. Matthew's own preference leans single-click-opens, but he flagged his UI taste differs from the team's, so this waits on their input — a one-line switch to `QAbstractItemView.EditTrigger.AllEditTriggers` in `PrefGrid.__init__` if they want single-click. Everything else is settled.

**Step 65 landed 2026-07-02.** Presser → Press preference — the first *reuse* of the Step 64 [`pref_grid.py`](pref_grid.py) `PrefGrid`, and the only step in this block that touches the schema. A full §13.30 vertical slice: new [`records/scheduling.py`](records/scheduling.py) `PresserPressPref` (the exact twin of `PartPressPref` but keyed by `employeeId`), a `presser_press_pref(employeeId, press, score)` table (`_createSchedulingTables` + additive idempotent `_migrateV11ToV12`, **db_version 11→12**), save/load blocks, a `fuzz_db.populatePresserPressPref` populator, and a new [`presser_press_pref_tab.py`](presser_press_pref_tab.py) `PresserPressPrefTab` under "Production and Scheduling" → "Scheduling config". Manual UI gate cleared (Matthew's sweep, light + dark — the heat-map / legend are the same widget already blessed in Step 64).

*The one structural wrinkle vs the part grid:* a presser's stable key is its `employeeId` (an int) but the row is *labeled* by the employee name. `PrefGrid` already separates the two — it carries `rowKeys` (handed to `setScore`) alongside the column-0 label in each data row — so the tab passes employeeIds as `rowKeys` and `_presserLabel(...)` as the visible column-0 value; rows sort by `(label, employeeId)` for a deterministic, alphabetical display the Step 55 net can diff. *Cascade rule (the settled design call):* `presserPressPref` is keyed by `employeeId` exactly like `pressers`, so it **mirrors the `pressers` dict on every rekey/delete** — `updateEmployee` re-id, `updatePresser` reassign, `delPresser`, and `delEmployee` all move/drop it in lockstep; press rename/delete propagate through every presser's score map (the twin of the Step 48 part cascades). No silent FK orphans (the dual-mandate). *Downstream refreshes:* press rename/delete refresh both pref grids (columns), and employee rename/delete + presser CRUD refresh the presser grid (rows/labels are employee-derived). *Schema semantics unchanged for scheduling:* `scheduling._prefScore` doesn't read presser prefs yet — Step 66 does — so `schedule()` output is byte-identical (the `scheduling_scheduler*` checks stay green).

*Smoke 59 → 61 PASS:* new `presser_press_pref_crud` (drives the grid through its `ScoreDelegate` + press-rename/delete and presser-delete cascades + save/reload roundtrip; the presser twin of `part_press_pref_crud`) and `mercy_v11_to_v12_migration` (seeds a v11 DB, asserts `presser_press_pref` created empty + data survives + roundtrip). The `employee_reid_cascades` check gained a presser-press-pref-follows-the-re-id assertion; the `presserPressPrefTab` projection-registry entry lets the Step 55 stale-view net + `crash_fuzz` guard it. Migration-version churn handled per the upkeep note (terminal-version literals 11→12 + docstrings across `smoke/migrations.py`; `mercy_v4_to_v11_end_to_end` → `mercy_v4_to_v12_end_to_end`; `_SCHED_SALES_TABLES` now 8 tables; new table via migration + fresh-schema path only — never `UNIFIED_TABLES`). `compile_all` + `pyright_baseline` stay clean.

**Step 66 landed 2026-07-02.** The scheduler now staffs a specific presser onto each running press — secondary to the press/part decision, consuming the Step 65 presser→press data. `ScheduleRow` gains `presser: int | None`; `ScheduleConfig` gains `presserNeutralScore = 3` (the presser twin of `NEUTRAL_PRESS_SCORE`) and a `presserAssignment = "preference"` policy seam (`PRESSER_ASSIGNMENT_PREFERENCE`; `"balanced"` / rotation reserved-but-unimplemented, and an unrecognized policy **raises** rather than silently mis-staffing — the §10 provisional pattern). After `_assignLanes` fixes which presses run and what they press (**untouched**, part-preference-driven), a new `_assignPressers` pass runs once per (date, shift): **greedy max-score matching** (design call 2026-07-02 — the lighter of greedy-vs-optimal, chosen to match the greedy EDF core; no per-presser throughput effect makes marginal suboptimality cosmetic) scores every (running press, present presser) pair by `_presserPrefScore` (missing pair = `presserNeutralScore`), then assigns top-down — highest score first, **press name then employeeId** breaking ties for §5 determinism — so each running press gets exactly one present presser. Rows are frozen, so it rebuilds them via `dataclasses.replace`. *Invariant (design call 2026-07-02) held:* presser assignment never changes *what* is produced or *which* presses run — only *who stands where*; running presses = `min(present, presses)` ≤ present, so every running press is staffable, and the rarer pressers > presses direction leaves the surplus present pressers unassigned that shift. A **Presser** column is threaded through [`schedule_tab.py`](schedule_tab.py) (via `pressers_tab._presserLabel`) and the [`report/scheduling.py`](report/scheduling.py) PDF (inline `_presserCell`, so the report layer stays decoupled from the Qt tabs, matching `report/employees.py`); a §11 presser-heuristic addendum was appended to [`prod-sched-algorithm.md`](plan_archive/prod-sched-algorithm.md). **No schema change** (the scheduler is stateless — no `db_version` bump), so `schedule()`'s placement output is byte-identical to pre-Step-66 (only the new `presser` field is added). *Smoke stays 61 PASS* (checks extended, not added): `scheduling_scheduler` gained three presser fixtures (a preference win, the all-neutral id-order tiebreak, and preference beating the tiebreak) with exact expected staffing; `scheduling_scheduler_fuzz` populates `presser_press_pref` and asserts the staffing contract (each running press staffed by exactly one present, non-double-booked presser); the Step 53 report/tab checks were unaffected (row-count / index-based). `compile_all` + `pyright_baseline` stay clean. Manual glance: Matthew reviewed the Presser column and flagged that the full-name labels (`WALSH Morgan (4106)`-style) make the now-7-column PDF too wide — **the fix is deliberately folded into Step 67** (design call 2026-07-02), not a stopgap here.

**Width follow-up → Step 67 (design call 2026-07-02).** Rather than shrink the presser cell, **promote the repetitive `Date` + `Shift` columns to group subheaders** — the schedule report becomes per-`(date, shift)` subsections (a subheading like `2026-07-06 — Shift 1` over a 5-column `Press / Part / Quantity / Press-hours / Presser` table), freeing the width the Presser column needs. This isn't just a width fix: date and shift are exactly the axes Step 67's **per-shift** and **date-range** variants slice on, so the grouped layout is the natural base those variants sit on — hence it opens Step 67 rather than bloating Step 66's logic commit. *Open design detail for 67:* the PDF regroup is trivial (`drawSection` per group), but the on-screen [`table.py`](table.py) `DBTable` is a flat `QTableView` with no native grouping — so on-screen either gets fake separator rows (mirrors the PDF) or stays columnar with only the PDF regrouped (screen has width + horizontal scroll, so the cramping is really a PDF-only problem). Decide when building 67.

**Step 67 landed 2026-07-02.** Closes the Steps 63–67 block. Pure UI — no schema, no scheduler change (stateless). Two parts:

*Date/Shift → subheader regroup (the Step 66 width fix + grouped base layout).* The Schedule display is now grouped by `(date, shift)`: Date and Shift move out of the repeated columns into a bold subheading (`scheduleGroupHeading` → e.g. `Mon 2026-07-06 — Shift 1`, a fixed-table weekday so it's locale-independent), each over a 5-col `Press / Part / Quantity / Press-hours / Presser` table — freeing the width the Presser column needed. On screen ([`schedule_tab.py`](schedule_tab.py)) this is a `QScrollArea` of `(bold QLabel + a content-sized read-only DBTable)` per group (the chosen "grouped sub-tables" option, 2026-07-02); in the PDF ([`report/scheduling.py`](report/scheduling.py)) a new `_groupedScheduleSection` + `_subHeading` flow the groups across pages, repeating the banner (`-- Continued`) and a group's subheading (`(cont.)`) on overflow. A shared `_scheduleBanner` draws each page header — the bold subtitle is just the generation date, with horizon + active filter on a **wrapped normal-weight line** below it (a long filter description had run off the fixed-width bold subtitle; `drawSubtitle` doesn't wrap — caught in Matthew's sweep and fixed before commit).

*Per-shift / date-range variants.* A separate filter row (Shift `All/1/2/3` + From/To date pickers, kept off the main Generate/Export controls per the 2026-07-02 design call) with **Show Filtered** + **Export Filtered PDF** actions. Both slice the already-computed full `ScheduleResult` via the pure `filterSchedule` (never a shortened horizon — that would corrupt placement / misflag capacity); the date pickers auto-bound to the schedule's span (so an unmodified filter is shift-only), and "third shift, next three days" is just `shift=3` + a 3-day range. Flags/warnings are order-level / dateless, so a filtered view **shows them in full** (design call — a slice must never hide a late order); the subtitle + a `(all orders)` section-name suffix say so. New pure helpers (`filterSchedule` / `groupScheduleRows` / `scheduleGroupHeading` / `scheduleFilterDescription`) live in [`scheduling.py`](scheduling.py), shared by tab + PDF so they read identically.

*Smoke 61 → 62 PASS:* new `scheduling_view_slice` (exact filter/group/heading/description values); `schedule_tab_generates` rewritten for the grouped structure (one mini-table per group, rows union back to the full schedule; Show Filtered slices to one shift while flags stay full; both exports write `%PDF-`; refresh clears); `schedule_report` gained a filtered-render scenario. Registered in `smoke/__init__.py` + `smoke/__main__.py`; `compile_all` + `pyright_baseline` clean (QDate→date built from components since `toPython` is typed `object`). Verified end-to-end on a `small` fuzz DB: 58 rows / 25 groups, every row presser-staffed, full + filtered PDFs render. **No hardcoded colours** (headings inherit the palette), so the grid follows the system light/dark theme. Manual UI gate: **cleared** (Matthew's sweep, 2026-07-02 — grouped display + Presser column fit; filter by shift + range; both PDF exports). The one issue found — a long filter description running off the fixed-width bold subtitle — was fixed before commit (the wrapped `_scheduleBanner` meta line above).

### 13.45 Deferred follow-ups backlog (consolidated 2026-07-02)

Optional, non-blocking follow-ups that had accumulated as inline notes across §13 and [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md), pulled into one place so they stop hiding. **None is a known bug** — the app is in a shippable state; these are polish, hardening, and blocked-on-data items. Ordered by effort/value, smallest first (the §13 tradition). One stale-comment item — the Schedule-tab "placeholder until Step 53" comment in [`app.py`](app.py) — was cleaned up in passing when this list was compiled (Step 53's real tab has long since shipped), so it isn't carried below.

**Small features (one commit each, low risk):**
- **File-dialog directory memory.** ✅ **Done — Step 68 (landed 2026-07-02).** The Open / Save-As / Import dialogs ([`app.py`](app.py)) previously hardcoded `os.path.expanduser("~")` as their start dir. Now a single remembered `lastDir` `QSettings` key (read via `MainWindow._lastDir()`, written via `_rememberDir()` on any non-empty pick) seeds all three, mirroring the Step 20 `lastDbPath` pattern; a stale/deleted remembered dir falls back to home (guarded by `os.path.isdir`) so a bad path is never surfaced. Covered by the `file_dialog_dir_memory` smoke check (63 PASS). (§13.7 had flagged only the Import path; it was really all three dialogs.)
- **~~"App Info" Settings sub-tab~~ → re-scope as an optional About / Diagnostics panel.** The §7.1 App Info (version / about) sub-tab was skipped in Step 5 as trivial polish. **As-scoped it's now redundant and should be dropped** — the app name + version already live in the title bar ([`app.py`](app.py) `setWindowTitle`), so a literal version/about tab just duplicates it (call, Matthew + Claude, 2026-07-02). The only version worth building is a **support/diagnostics** panel showing what the title bar *doesn't*: the open DB's schema `db_version` (currently **14** as of Step 79 — the actually-useful migration-support diagnostic, nowhere visible in the UI today; don't hardcode this number, read `MERCY_DB_VERSION`), the full build id (git hash/dirty from [`version.py`](version.py)), and the open DB path / `QSettings` location. Build only if the team hits support friction — it's a different, better feature than the original note, not a tonight item.
- **Trend (graph) variant of the per-employee productivity report.** Step 24 (§13.12) shipped table-only; the Trend variant was deferred. Reuses the existing trend-report machinery. Wants a team "yes, we'd use it."

**Hardening / architecture (medium):**
- **~~"Lever 1" — one-registration-list downstream refresh.~~** ✅ **Done — Step 81 (landed 2026-07-16; see §13.50).** Every edit/delete success path now routes through the single `MainWindow.refreshAllViews()`, killing the stale-view bug *class* at the source (detection / "Lever 2" shipped earlier as the Step 55 net, §13.31). **This entry's 2026-07-02 warning was exactly right and is worth remembering as a track record:** it predicted that a blanket refresh would reset the drop-down-driven tabs (production filters, employee overview/detail, inventory date) and that Lever 1 therefore needed those combos reworked to refresh **selection-preservingly** first. Matthew independently re-raised the same objection before Step 81 was built, and it was the one real risk in the step. It came in **under** the "multi-step effort, not a one-commit rewire" estimate — one commit — because by 2026-07-16 `production_tab` had *already* grown the selection-preserving pattern (`_populateEmployeeFilter`: preserve by stable key via `itemData` + `blockSignals`), leaving only two combos to bring up to it. **Lesson for future planning: this list of at-risk combo-driven tabs was accurate months ahead — read §13.45 before scoping anything that touches refresh.**
- **Proper dirty-tracking + never-saved-data close gate.** The confirm-on-close dialog (Step 25, §13.13) currently prompts whenever a file is loaded; a proper version flags per-mutation across the ~20+ edit sites (CRUD dialogs, inline table edits, batch-entry save, …), clears the flag on save / load, and prompts only when dirty. Paired with the *never-saved-but-has-data* edge case: the `filePath is None` close gate silently discards an unsaved in-memory DB — once dirty tracking exists it becomes `dirty and (filePath is not None or hasAnyData)`, with a Save-As route for the `None` branch. Deferred per Matthew 2026-04-24 ("most don't save until the very end anyway"); revisit if the always-prompt nag becomes painful. (Originally floated as "Step 26," later reclaimed by the rate-columns work — number now TBD.)

**Blocked on real data / field feedback (no code yet):**
- **Validate the greedy scheduler against real order data.** The greedy EDF core is explicitly *provisional* (algorithm addendum §10 / §13.43): once real orders exist, re-run, judge whether front-load + the 2-business-day slack are right, and — if not — swap the allocator (ILP / CP-SAT / a less-front-loaded variant) behind the unchanged `schedule(db, today, config)` seam. No schema, nothing downstream changes.
- **Presser `"balanced"` / rotation-weighted assignment.** The reserved `presserAssignment` policy seam (Step 66, §13.44): build the spread-the-work variant only if real production weeks show that pure-preference reshuffling annoys the crew. Seam + `NotImplementedError` guard already in place, so it drops in without touching the rest of the scheduler.

**Cosmetic — likely skip:**
- **`file_manager/load.py` bundled `from records import (...)` → per-method imports** (the last Step 28.1 leftover, §13.16). Explicitly judged cosmetic-only and left as-is; do it only if that file is being touched anyway.

### 13.46 Truck-based order entry + scheduling-tab UX polish + order sort modes (planned 2026-07-03) — Steps 69–74

Third post-release feature block from the team (relayed by Matthew, 2026-07-03) after living with the Steps 63–67 scheduling-UX work. Six asks; sequenced smallest / lowest-risk first in the §13 tradition (the team asked for the quick UI wins ahead of the headline data-entry feature). Each is one step / one commit. Design calls settled in this planning session are recorded inline.

**The six asks.**
1. **Trucks-based order-update entry.** Every part gains a *parts-per-truck* figure; a **remaining-to-press / remaining-to-ship** snapshot can be entered in **trucks** (half-truck precision) instead of raw pieces — a data-entry convenience they intend to phase out. Everything stays **stored in pieces internally and shown in pieces externally**; trucks are purely an input reinterpretation. The mode is **togglable**.
2. **Hide the Horizon knob** from the average user (they read it as "show the next X days"). De-emphasize — bottom of the controls / behind an advanced affordance — rather than remove.
3. **One unified schedule report row.** Fold today's two rows (main Generate/Export + the Step 67 Show-Filtered / Export-Filtered row) into one, with the date range built into the display à la the Daily Reports tab: `[Generate Schedule] [From ▸] [To ▸] [Shift] [Export PDF]`. One export that draws from the on-screen filter.
4. **Condense the flagged-orders / fallback-warnings area** — it crowds out the schedule scroll area. Replace the full flags table + wrapped warnings label with one-line summaries + detail buttons: `["N orders flagged"] [Flagged Orders]  ["M parts flagged"] [Flagged Parts]`.
5. **Flagged orders sorted by due date + showing the client** — in both the detail window (ask 4) and the PDF report.
6. **Sort-mode toggle on the Orders and Order Updates tabs** — by **due date** or by **client name** (explicitly *not* by order number).

**Shape of the work.** Only **Step 74a** touches the schema (a new `part_truck` table, `db_version` 12→13, additive migration — the §13.30 vertical-slice template). Steps 69–73 are UI-only. Step 73 is presentation-only: `OrderFlag` still carries just `orderNum`/`part` ([scheduling.py](scheduling.py)); the tab detail dialog and the PDF both look up `db.orders[num].client` / `.dueDate` at render time and sort by due date, so the record stays a pure data carrier. Step 74b is UI-only: a live checkbox on the snapshot editor reinterprets the two input fields as trucks and converts to pieces via `part_truck` before storing — no persistence, no scheduler change.

**Ordering / dependencies.** 69 (standalone) → 70 (standalone) → **71 → 72 → 73** (all in [`schedule_tab.py`](schedule_tab.py) / [`report/scheduling.py`](report/scheduling.py); done back-to-back to avoid layout churn — 73 renders in the detail dialog 72 builds) → **74a** (schema + config tab) → **74b** (consumes `part_truck`). 74a/74b may split further if the review surface is large, à la Steps 64/65.

| Step | Description | Risk | Testable milestone |
|------|-------------|------|--------------------|
| 69 | **Order sort modes.** A sort-mode selector (due date / client name) on the Orders and Order Updates tabs; both currently hard-sort by order # (`row[0]`). Data (client, due date) is already in `genTableData`'s reach — Order Updates looks due date up from `db.orders`. No order-number sort option. [`orders_tab.py`](orders_tab.py) + [`order_status_tab.py`](order_status_tab.py). | Low | Toggle re-sorts both tables live; survives refresh; selection preserved. Manual UI gate. |
| 70 | **De-emphasize Horizon.** Move the horizon spin box out of the primary controls to the bottom / an "Advanced" affordance in [`schedule_tab.py`](schedule_tab.py). Pure layout; still feeds `ScheduleConfig.maxHorizonDays`. | Low | Horizon no longer prominent; schedule output unchanged. |
| 71 | **Unified schedule report row.** Collapse the two control rows into one — `[Generate] [From] [To] [Shift] [Export PDF]` — with the date/shift widgets always filtering the on-screen view and a single Export exporting the shown slice (the Daily Reports pattern). Removes the separate Show-Filtered / Export-Filtered actions (Step 67). Flags/warnings still render in **full** regardless of filter (the Step 67 "a slice must never hide a late order" rule). [`schedule_tab.py`](schedule_tab.py). | Med | One row drives display + export; filter never hides flags. Manual UI gate. |
| 72 | **Condense flags/warnings to summaries + details.** Replace the flags `DBTable` + wrapped warnings label with `["N orders flagged"] [Flagged Orders]` + `["M parts flagged"] [Flagged Parts]` one-liners opening detail dialogs; "parts flagged" = the part-level `warnings` (fallback-rate / missing fireScrap), "orders flagged" = `flags`. Frees the schedule scroll area. [`schedule_tab.py`](schedule_tab.py). | Med | Summaries + detail dialogs; schedule area visibly larger. Manual UI gate. |
| 73 | **Flagged orders: due-date sort + client.** The flagged-orders detail dialog (Step 72) and the PDF flagged-orders section gain a **Client** column and sort by **due date**, both via a render-time `db.orders` lookup. `OrderFlag` unchanged. [`schedule_tab.py`](schedule_tab.py) + [`report/scheduling.py`](report/scheduling.py). | Low-Med | Flagged orders show client, ordered by due date, on screen + PDF. |
| 74a | **Parts-per-truck config (schema).** Full §13.30 vertical slice: `part_truck(part PRIMARY KEY, partsPerTruck INTEGER)`, `_createSchedulingTables` + additive `_migrateV12ToV13` (**db_version 12→13**), record + save/load, `database.py` dict + setter + **cascades on part rename/delete** (mirrors the Step 48 part-press-pref cascades — no FK orphans), `fuzz_db` populator, a new **Parts per Truck** tab under "Scheduling config", smoke CRUD + crash_fuzz dispatcher + projection-tab registry. | Med | Set parts-per-truck per part; roundtrips; full migration chain replays on a real DB. Manual UI gate. |
| 74b | **Trucks-mode snapshot entry.** A live **"Enter in trucks"** checkbox on the Order Status snapshot editor ([`order_status_tab.py`](order_status_tab.py)): when checked, the remaining-to-press / -ship fields accept **half-truck** values and convert to pieces via the order's `part_truck` value before storing. **Stored + displayed always in pieces.** No persistence (see toggle design call). | Med | Trucks input yields the right piece counts, stored/shown in pieces; blocks per the validation call below. |

**Design calls settled 2026-07-03 (this planning session).**
- **Parts-per-truck lives in its own table + tab**, not a column on the costing Parts tab — mirrors the `part_press_pref` precedent, keeps the ANIKA costing part editor clean, and is literally the "another configuration database" the team asked for.
- **Toggle = a live, unpersisted checkbox on the snapshot editor**, *not* a per-DB global or a `QSettings` machine setting. Rationale (Matthew, 2026-07-03): the team shares workstations and different people enter differently, so a remembered mode would fight them; a per-window checkbox lets each person pick per session. The checkbox only reinterprets the input fields — internal storage and every display stay in pieces.
- **Missing / odd handling = block, don't guess.** Truck entry requires the part to have a parts-per-truck value set — otherwise a clear error telling them to set it first (a genuine data gap, per the dual-mandate: fail loudly, corrupt nothing). A half-truck of an *odd* parts-per-truck (which would land on a non-integer piece count) is rejected rather than silently rounded. Half-truck precision is enforced by the input widget (step 0.5).
- **Unified report row supersedes the Step 67 split.** The separate Show-Filtered / Export-Filtered actions land only ~1 day; folding them into the always-on filter row is the team's correction to that design, not a reversal of the underlying `filterSchedule` slice logic (which stays — flags still show in full).

**Manual UI gates** (standing rule — smoke can't cover combo visibility / rebuild / selection logic / in-cell layout): Steps **69, 71, 72, 74a**, plus a glance at **73** and **74b**. Step 70 is trivial layout.

**Migration-version-churn upkeep (Step 74a only):** bumping `db_version` 12→13 forces updating the hardcoded terminal-version literals + docstrings in [`smoke/migrations.py`](smoke/migrations.py), registering the new CRUD check in both `smoke/__init__.py` and `smoke/__main__.py`, and adding `part_truck` via the migration + fresh-schema path **only** — never into `UNIFIED_TABLES` (the format fingerprint stays frozen at the v4 shape), per [`CONVENTIONS.md`](CONVENTIONS.md).

**Steps 69–73 + 75 landed 2026-07-03.** The five UI-only asks shipped in one session (74a/74b — the parts-per-truck schema step + trucks-mode entry — deferred to a fresh session, see below). Smoke ended at **63 PASS** throughout; `pyright_baseline` clean.

- **Step 69** ([fa4bc5d]) — order sort modes. Shared `orderSortCombo` / `orderSortKey` in [`utils.py`](utils.py) drive a "Sort by" combo (Due date / Client name, never order #) on [`orders_tab.py`](orders_tab.py) + [`order_status_tab.py`](order_status_tab.py); client name case-insensitive, due date sinks undated orders last, orderNum breaks ties, routed through `refreshTable` so selection survives. Default Due date.
- **Step 70** ([09b4c44]) — the Horizon `QSpinBox` moved out of the primary controls into a collapsed **"Advanced ▸"** panel at the bottom of [`schedule_tab.py`](schedule_tab.py), with a one-line "not a display filter" clarification. Behavior unchanged (`_config`/`exportPdf` still read `horizonSpin.value()`).
- **Steps 71–73** ([cb40c2a], one commit — they intermingle in `schedule_tab.py`). **71:** the Step 67 two-row split collapses to one row — `[Generate] [From] [To] [Shift] [Export PDF]` — where From/To/Shift live-filter the shown schedule (`filterSchedule` view slice, never a shortened horizon) and Export writes exactly what's on screen; the `showFiltered`/`exportFilteredPdf` methods + their buttons are gone. **72:** the flags `DBTable` + warnings label become one-line summaries + detail buttons (`_FlagListWindow`), disabled at count 0. **73:** flagged orders gain a **Client** column and sort by **due date** in both the detail window and the PDF ([`report/scheduling.py`](report/scheduling.py)), via a render-time `db.orders` lookup — `OrderFlag` stays a pure data carrier. *Post-sweep polish (Matthew, 2026-07-03):* group mini-tables now size to full content height (header `sizeHint` + vertical-header `length`, fixing a last-row clip) and width so the outer scroll area does all scrolling (no scroll-inside-a-scroll); `_FlagListWindow` sizes to its columns (default `QTableView` size hint was too narrow).
- **Step 75** ([0685776]) — **not a §13.46 ask; a crash_fuzz-found pre-existing bug fixed in passing.** The random-seed baseline `crash_fuzz` reached a stale-key crash in `db.updatePresser` (KeyError on `self.pressers[newId]` when the original id was already gone — the last `updateX` rekey helper missing the Step 60 guard). Hardened to mirror `updateEmployee` (missing `oldId` → no-op) + a deterministic guard in `pressers_tab_crud`. Reshuffling the Schedule-tab widget set (Steps 71/72) changed the fuzz walk and surfaced it; it predated the whole batch.

**Step 74a landed 2026-07-03.** The parts-per-truck schema slice — the only schema step in §13.46 — shipped the §13.30 vertical-slice template, mirroring the Step 65 `presser_press_pref` precedent. Smoke ended at **65 PASS** (+`mercy_v12_to_v13_migration`, +`part_truck_crud`); `pyright_baseline` clean.

- **Step 74a** — `part_truck(part PRIMARY KEY, partsPerTruck INTEGER)` + additive `_migrateV12ToV13` (**db_version 12→13**) + `_createSchedulingTables` (fresh-schema path; deliberately *not* `UNIFIED_TABLES` — fingerprint stays at the v4 shape). `PartTruck` record is the **scalar twin of `Presser`** (keyed field + one value column, `getTuple`/`fromTuple`), *not* the nested-relational `PartPressPref` shape, since parts-per-truck is a single figure per part. `db.partTruck` dict + `setPartTruck` setter (lockstep: unset drops the row) + **part rename → rekey / part delete → drop cascades** (mirror the Step 48 part-press cascades) + save (`clearOld` scalar shape, like `clients`) + load. New **Parts per Truck** tab under Scheduling config: a purpose-built single-column in-cell integer grid ([`part_truck_tab.py`](part_truck_tab.py)) showing **all** parts (blank = unset; blank/0/non-digit clears the row), mirroring `DBTable`'s duck-typed contract like `pref_grid` — a separate widget rather than reusing `PrefGrid` (whose 1–5 score drop-down + heat map across N press columns don't fit a single free-integer column). `fuzz_db` populator; `mercy_v12_to_v13_migration` + `part_truck_crud` smoke checks; `mercy_v4_to_v12_end_to_end` renamed → `_v13_` (+`part_truck` in `_SCHED_SALES_TABLES`, roundtrip tuple); migration-version-churn upkeep done (all terminal-`12` literals/docstrings → `13`); projection-tab registry + empty-roundtrip list updated. *Manual-gate find (Matthew, 2026-07-03):* a first cut used `QIntValidator(1, …)` on the cell editor, which marks an empty field **unacceptable** — Qt's delegate commit gate then silently refuses to write the blank (reverts to the old value), making "clear to unset" unreachable in the UI. Fixed by a digits-only `QRegularExpressionValidator([0-9]{0,7})` that keeps the empty string acceptable; a smoke guard now asserts `hasAcceptableInput()` on an empty editor (the offscreen-testable proxy — the full commit gate isn't reachable headless, which is why smoke passed the broken cut). Verified end-to-end on a **copy** of the real `Mercy DB 6-1-26.db` (v12→v13, `part_truck` created empty, all 165 parts survived, additive/no `.bak`, set→save→reload roundtrip).

**Step 74b landed 2026-07-03 — §13.46 block complete.** The trucks-mode entry, UI-only, consuming the Step 74a `part_truck`. Smoke ended at **66 PASS** (+`order_status_trucks_entry`); `pyright_baseline` clean.

- **Step 74b** — a live, unpersisted **"Enter in trucks"** `QCheckBox` on the Order Status snapshot editor ([`order_status_tab.py`](order_status_tab.py), `OrderStatusEditWindow`). When checked, the remaining-to-press/-ship `QLineEdit`s are read as trucks and converted to pieces via `db.partTruck[part].partsPerTruck` at commit (`_readRemaining`); **stored + displayed always in pieces** (the sub-table, prefill, and outer tab are untouched). Two settled UX calls (2026-07-03): **(1) toggle = clear + relabel** — toggling clears both fields and flips the labels `(pieces)`↔`(trucks)`, never auto-converting, so a prefilled pieces value can't be misread as trucks (selecting a stored snapshot forces pieces mode before prefilling). **(2) hybrid block** — an **unset** part is blocked the instant "Enter in trucks" is ticked (error + the checkbox snaps back off, via `blockSignals`, since it's knowable immediately), while the **fractional-piece** cases (a half-truck of an odd count, or a non-0.5-step value) are caught at commit in `_readRemaining` (they depend on the typed value). Half-truck precision is enforced at parse time (`(trucks*2) % 1 != 0` → reject) rather than a spin widget, keeping the existing `QLineEdit` + `checkInput` flow. `order_status_trucks_entry` smoke check covers toggle-revert/engage, the 2.5-truck conversion, the odd-count + non-0.5 rejections, and pieces-mode prefill. No schema / scheduler / persistence change.

**§13.46 block done (Steps 69–75).** All six team asks + the crash_fuzz fix shipped. No open follow-ups from this block; the next scheduler-validation work remains the standing §13 items (real-order re-run, presser `"balanced"` policy).

### 13.47 One-press-per-part scheduling + trucks-scope fix + orders report (planned 2026-07-14) — Steps 76–78

Fourth post-release feature block from the team (relayed by Matthew, 2026-07-14). Three asks — one **algorithmic** (a die constraint on the scheduler), one small UI correction, one new report — sequenced smallest / lowest-risk first in the §13 tradition; each is one step / one commit. The three are independent (no cross-dependencies), so the riskiest (the scheduler change) goes last. Design calls settled in this planning session are recorded inline.

**The three asks.**
1. **A part can only be produced on one press at a time.** IRL a part needs a die and each part has exactly one die, so the same part / order can't run on multiple presses simultaneously. The scheduler today violates this in two places: allocation pools *all* of a shift-day's lane hours so one part can consume the whole day's capacity, and `_assignLanes` explicitly **splits a part across presses**. The headline effect of the fix: a single large order can no longer be parallelized across presses — it presses on one press at one press's rate, however many shift-days that takes (→ more LATE flags for big orders, correctly).
2. **The trucks toggle should reinterpret only remaining-to-press.** Remaining-to-ship is *always* entered in pieces (Step 74b applied the trucks reinterpretation to both fields).
3. **An orders PDF report** with a date range (on **due date**), an order-status filter (open / closed / all, where *closed* = none remaining to ship), a customer filter (one / all), a part filter (one / all), and a **Status details** checkbox (checked → show the actual remaining-to-press / -ship figures; unchecked → a single Open/Closed column). Same UI paradigm as the production reports: a **Report** button opens a small helper window of options. Linked from **both** the Orders and Order Status tabs (the team didn't specify which, and won't know until they test — so surface it in both).

**Shape of the work.** **No schema change anywhere in this block** (`db_version` stays 13). Step 76 is a two-field UI asymmetry fix. Step 77 is a new report mixin + helper window + two buttons — the `ProductionReportWindow` paradigm applied to sales, no records/scheduler touch. Step 78 rewrites the scheduler's allocation + lane assignment behind the unchanged `schedule(db, today, config)` seam (stateless — no schema, no `db_version` bump) so the report and every smoke consumer see only different rows, never a different result shape.

**Ordering / dependencies.** 76 (standalone, lowest risk) → 77 (standalone new feature) → **78** (the algorithmic change, riskiest, last). 77 may split 77a (PDF mixin, pure + smoke) / 77b (helper window + both-tab buttons) if the review surface is large, à la Steps 64/65.

| Step | Description | Risk | Testable milestone |
|------|-------------|------|--------------------|
| 76 | **Trucks toggle → remaining-to-press only.** In [`order_status_tab.py`](order_status_tab.py) `OrderStatusEditWindow`: only `pressEdit` / `pressLabel` flip to trucks; `shipEdit` is always pieces (label fixed `(pieces)`, always read as a non-negative `int`, left untouched on toggle, prefilled directly). `onTrucksToggled` clears / relabels only the press field; the unset-part block + `_readRemaining` half-truck / odd-count / fractional-piece rejections all move to the press path only. No schema / scheduler / persistence change. | Low | Trucks mode converts the press field only; ship stays pieces in both modes. `order_status_trucks_entry` smoke extended to assert ship-is-always-pieces. Manual glance. |
| 77 | **Orders/Order-Status PDF report + helper window.** New [`report/sales.py`](report/sales.py) `OrderReportsMixin` composed into `PDFReport` (`orderStatusReport(start, end, status, client, part, showDetails)`); new `order_report_window.py` `OrderReportWindow` (From/To date, Status Open/Closed/All, Client All-or-one, Part All-or-one, "Status details" checkbox, Generate → `tempReportPath` + `startfile`, the Step 14 open-via-temp convention); a **Report** button wired on **both** `OrdersTab` and `OrderStatusTab`. | Med | Report renders `%PDF-` across the filter matrix (all / open / closed × client / part × details on/off); both tab buttons open the window. New `order_status_report` + `order_report_window_generates` smoke checks. Manual UI gate. |
| 78 | **One-press-per-part scheduler + die-change seam.** No schema (stateless). Rewrite allocation to be lane-aware — a part occupies **≤ 1 lane per `(date, shift)`** (the die constraint), sequential sharing allowed (a lane can run several parts across the shift); a part whose lane fills spills to the *next shift-day*, never a second lane the same shift. Rewrite `_assignLanes` to assign one press per used lane by aggregate part preference with **no part split**. `ScheduleConfig.dieChangeHours` seam (default `0.0` = instantaneous). `_assignPressers` unchanged. | Med-High | A single big order serializes onto one press across shift-days; two small parts share a press in one shift; `dieChangeHours > 0` reduces a lane's throughput. Fixtures recomputed + new fuzz invariant (no part on 2+ presses in one `(date, shift)`). Manual glance (logic-first). |

**Design calls settled 2026-07-14 (this planning session).**
- **Die sharing = sequential, not exclusive (ask 1).** The constraint forbids only the physically-impossible case — the same part on two presses *simultaneously*. A press may still run different parts across one shift (a mid-shift die swap). This is the minimal faithful reading of the ask; it removes single-part parallelism but doesn't add an unrequested "one part per press per shift" rule that would artificially serialize small orders. Implemented as per-lane greedy allocation (a part picks one lane per shift-day and spills to the next shift-day when full) + no-split lane assignment.
- **Die-change-cost seam (ask 1, Matthew's addition).** Die changes are what the **Tool Change** production event logs (its `hours`). v1 assumes changes are **instantaneous** (`ScheduleConfig.dieChangeHours = 0.0`) — not enough real data yet to know the real cost — but the mechanism is built now: the first time a *new distinct* part lands on a lane that already ran a different part that shift-day, `dieChangeHours` is charged to that lane's budget. With the default 0 it's a no-op (pure sequential sharing). Flipping to a **fixed** cost (e.g. 10 min = `10/60`) is then a one-field change; an **empirical** cost drops in via a reserved `empiricalDieChangeHours(db, today)` helper (avg Tool Change record hours, mirroring `empiricalPressingRate` / the reserved presser `"balanced"` policy). The seam is the config field + the charging mechanism; the empirical helper itself is a reserved follow-up.
- **Report date range = due date (ask 3).** Orders carry only a `dueDate` (no order-placed / created date), so the range filters on due date. **Undated orders (`dueDate is None`) are always included** regardless of range — there's no date to filter them on, and dropping them would silently hide open orders (a safety net; per Matthew, you can't currently even enter an order without a due date, so this is defensive). Rendered with due date `?`.
- **Report status semantics (ask 3).** Open = `not OrderStatus.isFulfilled()` (remaining-to-ship > 0, or no snapshot yet → defaults to open); Closed = `isFulfilled()` (remaining-to-ship 0). Rows sorted by due date (undated last), client tiebreak (the Step 73 pattern). Details-off columns: `Order # · Client · Part · Quantity · Due Date · Status`; details-on adds `Latest Snapshot · Rem. to Press · Rem. to Ship`.
- **Report linked on both tabs (ask 4).** Same `OrderReportWindow` opened from a Report button on Orders *and* Order Status — the team didn't specify which and wants to decide after testing.

**Manual UI gates** (standing rule — smoke can't cover combo visibility / rebuild / selection logic / in-cell layout): Step **77**, plus a glance at **76** and **78** (78 is logic-first like Steps 52 / 66, but worth confirming the schedule tab + PDF still render sane rows).

**Scheduler-validation note (Step 78).** The die constraint materially changes throughput for large single-part orders (they can no longer be parallelized), so it feeds directly into the standing §13.45 item "validate the greedy scheduler against real order data" — the re-run against real orders should judge the die constraint + whether a non-zero `dieChangeHours` is warranted. A die-constraint + seam note gets appended to [`prod-sched-algorithm.md`](plan_archive/prod-sched-algorithm.md).

**Step 76 landed 2026-07-14.** The trucks-scope fix — UI-only, [`order_status_tab.py`](order_status_tab.py) `OrderStatusEditWindow`. The "Enter in trucks" checkbox now reinterprets **only** the remaining-to-press field; remaining-to-ship is always pieces (fixed `(pieces)` label, always read as a non-negative `int`, left untouched when the toggle flips). `_readRemaining` → `_readPressRemaining` (press-only; the unset-part block + half-truck / odd-count / fractional-piece rejections all live on the press path now), and `addSnapshot` reads ship directly in pieces. The `order_status_trucks_entry` smoke check was updated — a 1-truck ship input now stores `1` piece (not `1 × partsPerTruck`), plus new assertions that the toggle leaves the ship field + its label alone and that a stored snapshot prefills ship in pieces. **Smoke 66 PASS**; `pyright_baseline` clean. No schema / scheduler / persistence change.

**Step 77 landed 2026-07-14.** The orders / order-status PDF report — a new feature, no schema, no scheduler. New [`report/sales.py`](report/sales.py) `OrderReportsMixin` (composed into `PDFReport`) with `orderStatusReport(start, end, statusFilter, client, part, showDetails)`: filters `db.orders` by due-date range (inclusive; **undated orders always included** — the §13.47 safety net), open/closed status (`OrderStatus.isFulfilled`), client, and part; sorts by due date (undated last) / client / orderNum (the Step 73 order); and renders a paginated table with the house `drawTable([], totalsRow)` bold **Total line** at the end. A new [`order_report_window.py`](order_report_window.py) `OrderReportWindow` (From/To due-date pickers defaulting to the dated-order span, Status All/Open/Closed, Client All-or-one, Part All-or-one, "Status details" checkbox, Generate → `tempReportPath` + `startfile`) is opened from a **Report** button on **both** [`orders_tab.py`](orders_tab.py) and [`order_status_tab.py`](order_status_tab.py) (import-deferred inside `openReport` to keep the app→tab import chain acyclic).

*Manual-sweep additions (Matthew, 2026-07-14).* Two team asks surfaced on first look at the PDF and were folded in before commit: **(1) order value + total** — an order's value is `Order.price` (the order total, no quantity multiply), shown as a `Value` column and summed into the bold Total line; **(2) the table was too cramped** — the fix is **landscape orientation + content-proportional column widths**, not just a smaller font. [`report/core.py`](report/core.py) gained a `pageSize` param (default portrait `letter`, so every existing report is byte-identical) that `calculateMargins` now derives all geometry from; the window constructs the report in `landscape(letter)` (9″ usable vs 6.5″). `report/sales.py` sizes each column proportionally to the usable width (wide order-code / client / part / date columns, narrow counts) and drops the body font 12→10 — enough that only long client names wrap. Detail mode is 9 columns (`Order # · Client · Part · Quantity · Value · Due Date · Latest Snapshot · Rem. Press · Rem. Ship`); simple mode is 7 (`… · Value · Due Date · Status`, Open/Closed). Both modes render landscape for consistency.

*Smoke 66 → 68 PASS:* `order_status_report` (renders 8 filter-matrix variants + a landscape variant exercising the new `pageSize` path; asserts `_filterOrders` covers all orders on a wide range, open+closed partition the set, and a client filter is a correct subset) and `order_report_window_generates` (drives `OrderReportWindow` — combos carry the All sentinel + names, the default range spans dated orders, Generate writes a real `%PDF-` with `startfile` stubbed, From-after-To is rejected). Registered in `smoke/__init__.py` + `smoke/__main__.py`; `compile_all` picks up the two new root modules; `pyright_baseline` clean. No `db_version` bump. Manual UI gate cleared (Matthew's sweep — both tabs' Report button, the filter matrix, Open/Closed, undated-always-shown, the value + Total line, and the landscape layout).

**Step 78 landed 2026-07-14 — §13.47 block complete.** The one-press-per-part die constraint — the algorithmic ask. Stateless (no schema, no `db_version` bump); the whole rewrite sits behind the unchanged `schedule(db, today, config)` seam, so the report / tab / every consumer see only different rows, never a different shape. A §12 die-constraint addendum was appended to [`prod-sched-algorithm.md`](plan_archive/prod-sched-algorithm.md).

- **The constraint.** A part is pressed with a die and each part has one die, so a part runs on **at most one press per `(date, shift)`** (the "instant" quantum — shifts don't overlap). Allocation was pooling the whole shift-day's press-hours and `_assignLanes` split a part across presses — a physically-impossible plan. [`scheduling.py`](scheduling.py) now allocates **per-lane**: a new `laneBudgets(db, shift, d)` gives the per-lane split of the §2.6 capacity (`capacityHours` is now its sum); the `schedule()` inner loop places each part into **one lane** per shift-day (`_place`, pinning the part to that lane, spilling to the next shift-day when the lane fills — never opening a second lane the same shift-day); and `_assignLanes` → `_assignPresses` pins each occupied lane to a distinct press by hours-weighted `PartPressPref` score with **no part split**. `_assignPressers` (Step 66) is unchanged. **Headline effect:** a large single-part order can no longer be parallelized across presses — it runs on one press at one press's rate over as many shift-days as it needs (verified on a `small` fuzz DB: a big order serialized across 20 shift-days on one press), earning more LATE / NO_CAPACITY flags than the old pooled model — correctly.
- **Sequential sharing allowed** (design call — the minimal faithful reading): the rule forbids only a part on two presses *simultaneously*; a press may still run several parts across a shift.
- **Die-change-cost seam** (Matthew's addition): a die swap is what the **Tool Change** event logs. `ScheduleConfig.dieChangeHours` defaults to **0.0** (instantaneous v1); when a *new distinct* part lands on a lane already running a different part, it's charged against that lane's budget. A fixed cost is a literal (`10/60`); an empirical cost drops in via the reserved `empiricalDieChangeHours(db, today)` helper (avg Tool Change record hours, the twin of `empiricalPressingRate`) — not wired as default, mirroring the presser `"balanced"` seam.
- *Smoke stays 68 PASS (checks extended, not added):* `scheduling_scheduler` fixtures recomputed for the die constraint — D is now the **die cap** (one part, two presses free, uses one press across two shift-days, not split), plus new **I** (sequential sharing — two parts share one press in a shift), **J** (the die-change cost pushing a spill to the next day, with a cost-0 contrast), and **K** (two parts → two presses running concurrently + the Step 66 presser-staffing variants that used to piggyback on the removed splitting). `scheduling_scheduler_fuzz` gained the machine-checkable feature invariant — **no part on two different presses within one `(date, shift)`** (0 violations on `small` fuzz data); `scheduling_presser_capacity` asserts `laneBudgets`. `compile_all` + `pyright_baseline` clean; `crash_fuzz` (which drives the Schedule tab's Generate) stable 3×. **Logic-first** (like Steps 52 / 66) — the schedule tab + PDF render the same structure. The die constraint materially changes throughput for big orders, so it feeds the standing §13.45 "validate the greedy scheduler against real order data" item (re-judge front-load / slack / whether a non-zero `dieChangeHours` is warranted, once real orders exist).

**§13.47 block done (Steps 76–78).** All three team asks shipped — the trucks-scope fix, the orders/order-status PDF report, and the one-press-per-part die constraint with its die-change-cost seam. Open follow-ups remain the standing §13.45 items (real-order scheduler validation, now including the die constraint + die-change price; presser `"balanced"` policy).

### 13.48 Press current-die state (planned 2026-07-14) — Step 79 (+ deferred scheduler consumption)

Follow-up from the Step 78 die constraint (relayed by Matthew, 2026-07-14). Generating a sample schedule surfaced that a part's die "hops" between presses across shift-days / regenerations — legal under the per-`(date, shift)` constraint (never two presses at once) but operationally wrong (a mounted die shouldn't physically move). After a design discussion of how to get **hysteresis between schedule generations** (a stateless scheduler has no memory of where a die physically ended up), the team's decision: **record the current die state of each press** to serve as a scheduling starting point (the hysteresis source of truth). This block is the **data-capture layer only** — the scheduler algorithm is deliberately **unchanged** this round (team call: "don't change the algorithm"); wiring the recorded state into `schedule()` is the deferred follow-up below.

**Design calls settled 2026-07-14 (this planning session).**
- **Store it on the Press record, not a separate table** (the team's chosen shape of "Option B" from the hysteresis discussion — an explicit, persisted, team-maintained die location). A press mounts one die at a time, so **press → part** is a natural 1:1 field. A `Press` gains **`currentPart`** — the part whose die is currently mounted, or **`None`** (no die / idle, the default). Reuses the existing Presses tab + `presses` table (a new nullable column) rather than a new tab/table. *(Interpretation note: Matthew's phrasing was "the press it's currently set to"; in context this is the **part** a press is set up to run — i.e. the mounted die. The new session should confirm if there's any doubt, but everything here is built around `Press.currentPart : part | None`.)*
- **`currentPart` is a part FK** → the Step 48 part-cascade pattern applies: a part **rename** rekeys any press's `currentPart`; a part **delete** clears it to `None`. Press rename/delete carry / drop it with the press (it's the press's own field, and `updatePress` doesn't touch `currentPart`, which holds a part name — press renames don't affect it).
- **No scheduler change this step.** The field is stored + entered but **not consumed** by `schedule()` yet — the algorithm is untouched (the `scheduling_scheduler*` checks stay green). Consuming `Press.currentPart` as the die-placement starting point (the actual hysteresis payoff) is the **deferred follow-up**, and is where "don't change the algorithm" gets revisited once the data-entry habit lands and the consumption is designed.
- **Daily upkeep accepted.** The team knows this needs keeping current and has committed to it (Matthew's note — "I don't think they'll like tracking this daily, but they insist they'll do it").

**Shape of the work (Step 79) — a schema slice that *modifies an existing record* (cf. Step 74a's `part_truck`, but a column on `presses`, not a new table).**
- **Schema:** add a nullable `current_part TEXT` column to the `presses` table; **db_version 13 → 14**; add the column in `_createSchedulingTables` (the fresh-schema path: empty / legacy ANIKA / legacy BECKY) **and** an additive idempotent `_migrateV13ToV14` (`ALTER TABLE presses ADD COLUMN current_part TEXT`) wired into the Case-2 chain in [`file_manager/__init__.py`](file_manager/__init__.py). `presses` is **not** in `UNIFIED_TABLES` (a post-v4 scheduling table), so the v4 fingerprint is untouched.
- **Record:** `Press.currentPart : str | None` (default `None`); `getTuple` / `fromTuple` gain the field (a 2-element tuple now). [`records/scheduling.py`](records/scheduling.py)
- **Database:** save/load the column; a `setPressCurrentPart(press, part)` setter (`None` clears); **cascades** — `updatePart` rekeys every press whose `currentPart == old`, `delPart` clears every press whose `currentPart == name` to `None` (mirror the existing `partPressPref` cascades already in those two methods). `addPress` / `updatePress` / `delPress` carry the field with the press. [`records/database.py`](records/database.py)
- **UI:** the Presses tab editor ([`presses_tab.py`](presses_tab.py)) gains a **Current part** combo — a "(none)" entry + every part name (sorted) — prefilled on edit and roundtripped through the setter. `getComboBox` already tolerates a stale stored value (Step 61).
- **fuzz_db:** populate `currentPart` on some presses (a valid part or `None`) so report / migration stress covers it. [`fuzz_db.py`](fuzz_db.py)
- **Smoke:** extend `presses_tab_crud` (set / roundtrip `currentPart` + the part-rename and part-delete cascades) and add `mercy_v13_to_v14_migration` (seed a v13 DB, assert `presses.current_part` created empty, data survives, roundtrip). Rename `mercy_v4_to_v13_end_to_end` → `_v14_`.

**Manual UI gate:** Step 79 — the Current-part combo prefill / roundtrip in the Press editor (smoke can't reach the combo-visibility / prefill path).

**Migration-version-churn upkeep (Step 79):** db_version 13 → 14 forces updating the hardcoded terminal-version literals + docstrings in [`smoke/migrations.py`](smoke/migrations.py), the `mercy_v4_to_v13_end_to_end` → `_v14_` rename, and registering `mercy_v13_to_v14_migration` in both `smoke/__init__.py` and `smoke/__main__.py`. The new column goes in via the migration + fresh-schema path **only** — never into `UNIFIED_TABLES` (fingerprint frozen at the v4 shape), per [`CONVENTIONS.md`](CONVENTIONS.md).

**Landed 2026-07-15 (Step 79).** As planned: `Press.currentPart` (2-element get/fromTuple), `setPressCurrentPart` setter, part **rename** cascade in `updatePart`, `presses.current_part TEXT` on the fresh-schema path + additive `_migrateV13ToV14` (db_version 13→14), save `(?, ?)`, the Press-editor "(none)"+parts combo, fuzz population, extended `presses_tab_crud`, new `mercy_v13_to_v14_migration`, and the `mercy_v4_to_v13_end_to_end`→`_v14_` rename. Real-data drill on `Mercy DB 6-1-26.db` (v12): migrated to v14, `presses.current_part` added, 165 parts / 48 employees / 50 materials untouched. Scheduler still unchanged (`scheduling_scheduler*` green).

**Two changes from the original plan (both from Matthew's manual-test pass, 2026-07-15):**
- **Presses list gains a Current part column** (idle presses read `(none)`) — the die location is daily-tracked, so it needs to be visible at a glance, not only inside each editor (matches the Clients tab showing its value column).
- **Part delete now *blocks* on a mounted die** instead of the originally-planned cascade-to-`None`. `delPart` returns the mounted-die presses as blockers alongside referencing orders (the Parts tab names them in the error popup); the team clears the press first. Rationale: a silent cascade-to-idle would erase a die location they track by hand — a loud, corruption-free stop is the right failure mode (the §dual-mandate call). The rename cascade is unchanged (rename is non-destructive).
- **Surfaced a latent stale-view bug** (the standing FK-refresh family — see the four modes in the Step 48/64 notes): a part rename rekeyed `Press.currentPart` in the model but the Presses tab kept painting the old die name, because `PartsEditWindow` didn't refresh it. **One-off patch applied here** (`PartsEditWindow.readData` now calls `pressesTab.refreshTable()`); the permanent, whole-family fix is **Step 81 (§13.50)**. **[⚠ Superseded 2026-07-16: Step 81 landed and *deleted* that one-off call along with all 45 fan-outs — `PartsEditWindow.readData` now makes a single `refreshAllViews()` call. The sentence above describes code that no longer exists; kept as the record of what Step 79 shipped.]**

**Deferred follow-up — now formalized as Step 80 (§13.49):** the scheduler consumes `Press.currentPart` as its die-placement / hysteresis seed. Held until the data-capture (this step) landed; now scheduled.

### 13.49 Scheduler consumes `Press.currentPart` — die-placement hysteresis seed (planned 2026-07-15) — Step 80

The payoff half of the Step 79 data-capture, and the direct answer to the original problem that started §13.48: a part's die "hops" between presses across shift-days / regenerations because the stateless scheduler has no memory of where a die physically ended up. Step 78 gave the scheduler the one-press-per-part constraint (a die is on one press per `(date, shift)`) plus a die-change-cost seam; Step 79 records where each die *is* (`Press.currentPart`). **Step 80 wires the recorded state into `schedule()`** so a part starts pressing on the press its die is already mounted on — the hysteresis the team wants. This is where the standing "don't change the algorithm" call (§13.48) gets deliberately revisited.

**Design calls to settle at the top of the step — ⚠ HISTORICAL: all settled 2026-07-15 and shipped; see the Landed note below. Do not re-litigate or re-build.** *(original text: "nothing here is final — confirm with Matthew")*
- **Seed, not hard constraint.** When a part has outstanding pressing and some press has `currentPart == part`, the greedy assignment should *prefer* that press. If the die isn't mounted anywhere, assign a press by the existing rules (Step 48 part-press score, then capacity) — that press becomes the part's implied die location for the rest of the run.
- **Input-only vs. write-back.** Simplest v1: `currentPart` is an *input* the team maintains by hand; the schedule shows the *implied* end-state die locations as report output, and does **not** write `Press.currentPart` back to the DB. (A write-back that "learns" the new placement is a bigger, riskier call — hold it.) Confirm before building.
- **Die moves / swaps.** When the seed can't be honored (the press is needed for higher-priority work, or capacity forces a move), the die moves — charge the Step 78 die-change-cost seam. Decide the move/swap priority rule (fewest moves? cheapest? respect due dates first?).
- **Within-run stickiness.** Across shift-days inside one generation, a die stays put unless the algorithm moves it — the per-run analogue of the cross-run hysteresis. Make sure the seed + move rules produce this (no gratuitous hopping).

**Shape of the work (Step 80) — algorithm change, no schema change.**
- Consume `Press.currentPart` in [`scheduling.py`](scheduling.py) `schedule()` as the die-placement seed; extend the assignment to prefer the mounted press and to account die moves against the Step 78 cost seam.
- **Smoke:** the `scheduling_scheduler*` checks change from "unchanged" to "asserts hysteresis" — a part whose die is on press P schedules on P when P has capacity; a die moves only when forced, and the move is costed. Add a focused check that seeding `currentPart` changes the assignment the expected way, and a fuzz check that dies don't hop without cause.
- **Pairs with §13.45** ("validate the greedy scheduler against real order data") — the die-placement seed *is* the real-world starting state that validation needs, so do them together if practical.

**Manual UI / real-data gate:** generate a sample schedule on the real DB with real `currentPart` values entered and eyeball that dies stop hopping — the exact symptom that motivated §13.48. **[⚠ Updated 2026-07-16: this gate is still UNMET, and as written it can't be run. The DB it named (`Mercy DB 6-1-26.db`) is superseded by `Mercy 2.0 DB 7-8-26.db`, and "with real `currentPart` values entered" remains impossible — no real press has a mounted die recorded (Step 81 drill). The closest evidence to date is a manually-entered, team-sanity-checked seed, which is *not* floor state — see the correction in §13.51. Step 80's ✅ means code-landed, not gate-cleared.]**

**Design calls — settled 2026-07-15 (Matthew).** (1) **Scope: costed placement, not just labeling.** Nothing is deployed to the floor yet, so the deeper honest model was chosen over the low-risk "relabel only" option: a die is a physical object that lives on a press and moving it burns setup hours. (2) **Input-only** — `schedule()` reads `currentPart` but never writes it back (subsystem stays stateless, spec §5.1). (3) **Mounted die wins** — the incumbent die keeps its press over a higher-*preference* part; only greater *urgency* (EDF) can displace it (a costed move). (4) **Cost trigger = die-slot contention, not presser scarcity** (Matthew's correction to the design example): a worker switches *presses* rather than swaps a *die*, so a die change is charged only when a part's die must displace a *different* resident die (empty press = free); pointing a present worker at an already-resident die, or deferring non-resident work, is free. (5) **One press per presser/day** — Step 78's `min(pressers, presses)` concurrency stays (~95% real behavior per Matthew); revisit only if the team reports relaying.

**Landed 2026-07-15 (Step 80).** Algorithm change, no schema change; the whole rewrite stays behind the unchanged `schedule(db, today, config)` seam. The greedy was restructured from a **per-order horizon walk to a time-outer walk** (outer loop = shift-days, inner = per-shift-day press assignment) because a persistent, seeded `mount: press→part` map must evolve in time order — a per-order walk can't keep the die map time-consistent. Press identity moved *into* placement (the old end-stage `_assignPresses` is deleted; `_assignPressers` staffing is untouched). Cost rule: free to press on the press holding your die; `dieChangeHours` charged only to mount onto a press holding a *different* die (empty = free); mounting clears the die off its old press (one physical die). Eviction order: empty → idle die → least-urgent incumbent → this part's preference → name. A part with a home press but no free lane **defers** (waits for its press) rather than hop — the no-gratuitous-hopping guarantee. **Key de-risking property: at the default `dieChangeHours = 0.0` the mount map is pure hysteresis with zero effect on completion dates — it only fixes which press each part lands on; capacity/date effects switch on only when the team prices a die change through Step 78's seam.** New per-order bookkeeping lives on a module-level `_OrderState`. Smoke: four new deterministic cases in `scheduling_scheduler` — **L** (seed steers the press over part preference), **M** (evicting a seeded *idle* die costs a die change; empty press mounts free), **N** (within-run stickiness / no hop across a multi-day run), **O** (urgent part takes an empty press rather than evict an incumbent); `scheduling_scheduler_fuzz` already ran over seeded data (fuzz populates `currentPart`) and now also re-runs with the seed cleared to prove robustness both ways. Real-data drill on a v14 copy of `Mercy DB 6-1-26.db`: the real DB has **no scheduling entities yet** (0 presses/orders/pressers — the team hasn't populated them), so hysteresis was validated by synthesizing 3 presses / 3 pressers / 3 orders on **real parts** (real rates + scrap, real employees): each die seeded onto a press *different* from its default placement **moved to its seeded press and ran there for its entire 6–11 shift-day run with zero hopping**, deterministic, no flags. Full smoke green. The floor eyeball (real `currentPart` values in the live app) waits until the team enters real scheduling data.

**Pairs with §13.45** (validate the greedy against real order data) — **still open, but partly unblocked as of 2026-07-16:** real orders and presses now exist (69 orders / 5 presses in `Mercy 2.0 DB 7-8-26.db`), and Matthew has eyeballed a real-order schedule. Three things still gate a genuine verdict: (1) **no real die placement** — `Press.currentPart` is unset on every real press, and the encouraging 2026-07-16 look ran against a *manually entered, team-sanity-checked* seed, not floor state (see the correction in §13.51); (2) **`dieChangeHours` is still 0.0** by deliberate deferral, so die changes are priced at nothing and completion dates are untouched — that number is the input this validation needs; (3) **the team hasn't deployed a schedule yet**, so there's no observed-vs-predicted to compare against. Until (3), any "validation" is a plausibility eyeball, not evidence.

### 13.50 Permanent fix for the stale-view FK-refresh bug family (planned 2026-07-15) — Step 81

Step 79's manual-test miss (a part rename updated `Press.currentPart` in the model but the Presses tab kept painting the old die name) is the latest instance of a **recurring** bug: the **stale-view** mode of the FK rename/delete family. Every FK relationship added so far (Steps 48, 64, 74a, 79) has required the editing window to *manually* call each dependent tab's `refreshTable()`; forgetting one leaves a stale view. It's fragile hand-wiring that grows O(FK-edges), and Step 79 proved it isn't reliably remembered. Step 79 shipped a **one-off patch** (`PartsEditWindow.readData` → `pressesTab.refreshTable()`); **Step 81 is the systemic fix** so no future step has to remember the fan-out.

Scope note: this targets the **stale-view** mode only. The other three modes in the family have their own established patterns and are *not* in scope here — incomplete db cascade (fixed per-method in `db.updateX`/`delX`), stale-window Update crash (Step 60 guards), stale combo prefill (`getComboBox` tolerance). (See the FK rename/refresh notes carried across Steps 48/60/64.)

**Design options that were weighed — ⚠ HISTORICAL, decided 2026-07-16: option _B_ shipped, _not_ the "recommended" A below. Read the Landed note further down before acting on any of this.** (Kept as the record of what was considered and why A was rejected — do *not* "restore" the missing show hooks.)
- **A) Refresh-on-show (recommended).** MERCY shows one tab at a time, so have each tab repaint its table when it becomes visible (`QTabWidget.currentChanged` / a `showEvent` hook). Any view the user switches to self-heals; the entire "forgot to refresh tab Y" class disappears with almost no per-FK wiring. Cheap because only the shown tab refreshes.
- **B) Central `refreshAllTabs()`.** Every edit-window success path calls one MainWindow method that refreshes every tab. Dead simple, robust, but repaints everything on every edit (fine at MERCY's scale) and still needs one call per edit path.
- **C) Dependency/observer registry.** Tabs declare what they depend on (parts, presses, …); a mutation broadcasts an invalidation and only dependents refresh. Most precise, most code — likely over-engineered for MERCY.
- Lean **A**; keep **B** as the low-effort fallback. Either way, once landed, the per-edit `refreshTable()` fan-outs (including Step 79's one-off) can be deleted.

**Shape of the work (Step 81).**
- Implement the chosen mechanism in [`app.py`](app.py) (the `MainWindow` tab container); strip the now-redundant manual `refreshTable()` fan-outs from the `*_tab.py` edit windows.
- **Smoke:** a regression that renames/deletes a record and asserts a *dependent* tab is fresh **without** an explicit refresh call in the test — i.e. the mechanism, not hand-wiring, kept it current. Re-verify the Step 79 symptom (part rename → Presses tab shows the new die name) survives the fan-out removal.

**Landed 2026-07-16 (Step 81) — shipped B, not the recommended A.** The lean toward refresh-on-show didn't survive first contact with the code; **option B** shipped instead, on four findings (Matthew confirmed before building):

1. **B was already 90% built.** `MainWindow._refreshAllTabs()` already existed and was already wired to the DB-load path — including the adapter over the heterogeneous refresh method names (`refreshTable` / `refresh` / `refreshTab`) that *any* uniform mechanism has to absorb.
2. **B's stated downside is a non-issue.** The worry was "repaints everything on every edit". Measured against the real DB (167 parts / 69 orders / 5 presses): **~10 ms**. Imperceptible.
3. **A was worse than the plan credited.** (a) `ScheduleTab.refresh()` is *destructive* — refresh-on-show would wipe a generated schedule every time the user tabbed away and back. (b) Committing an edit fires no show event on the tab *behind* the (non-modal) edit window, so every edit window would keep a self-refresh call anyway — A deletes less wiring than assumed. (c) Edit from a still-open window while a *different* tab is visible → no show event → still stale. A leaves a residual hole; B has none.
4. **Failure modes point at B.** Forget B's call and *the tab you're looking at* is stale — caught in the first manual test. Forget a hand-wired fan-out (or fall in A's hole) and a *distant* tab goes quietly stale — which is exactly how Step 79 slipped through for two steps. **B converts a silent failure into a loud one**, per the standing dual-mandate.

**What shipped.** Two entry points on `MainWindow`: `_refreshAllTabs(hard=True)` (unchanged DB-load repaint: pickers hard-reset, schedule cleared) and the new **`refreshAllViews()`** = `_refreshAllTabs(hard=False)`, called from **all 20** edit/delete success paths across 14 `*_tab.py` files, replacing **45** hand-wired fan-out calls. Step 79's one-off patch is gone with the rest, along with ~30 lines of comments reasoning about which FK reaches which tab — that reasoning is what the step retires.

**Design call — the Schedule tab is excluded from the edit repaint (Matthew, 2026-07-16).** `scheduleTab.refresh()` clears a generated schedule: right on DB load, wrong after an edit (it's a point-in-time report the user asked for, not a live view). So `hard=False` skips it. Validated on real data: generate a real 165-row schedule → edit → schedule intact; DB load → cleared.

**The wrinkle B nearly shipped as a regression (caught by Matthew):** tabs with **dropdown selectors** that all their sub-tabs key off (Employees → Overview) must persist their selection across a repaint. A blanket repaint fires on *every* edit, so a naive rebuild would snap the picker back to "None" mid-read. Inventory of tab-level selectors came to four; the house pattern already existed in **`production_tab._populateEmployeeFilter`** (preserve by stable ID via `itemData` + `blockSignals`, fall back to index 0 only if the record vanished). The two outliers (`employee_detail_tab.employeePicker`, `inventory_tab.datePicker`) were brought up to it; `training_tab.trainingPicker` already preserved and `schedule_tab.shiftCombo` is on the excluded tab. **Preserve by key, never by label** — a rename rewrites the label, and surviving renames is the entire point of Step 81, so label-matching would drop the selection in precisely the scenario being fixed. Because the pickers' rebuild signal is what normally repaints the dependent sub-tabs, and `blockSignals` suppresses it, both now drive `selectEmployee`/`selectDate` explicitly once after the rebuild.

**Smoke: 69 → 71.** `fk_rename_refreshes_dependent_tabs` pins the press-die (Step 79) + order (Step 49) + part-press-pref (Steps 48/64) FK edges onto one part, renames it through the real `PartsEditWindow`, and reads three *other* tabs off their rendered `data` — **with no refresh call anywhere in the test**, so it asserts the mechanism rather than the wiring. `edit_refresh_preserves_picker_selection` covers all three picker behaviours (soft repaint preserves; preserves *across a rename of the selected employee*; hard repaint still resets). Both were **mutation-tested**: no-op'ing `refreshAllViews` fires all six FK assertions (naming the Step 79 symptom verbatim), and disabling the soft-preserve branch fires all eight picker assertions. `employee_delete_cascades_detail_tabs` was re-pointed at `refreshAllViews()` (the flow it claims to mirror) and now also proves the soft preserve *can't resurrect a deleted record*.

**Latent fixture bug surfaced in passing.** The blanket repaint means every tab now renders on every edit, so smoke fixtures must build *valid* databases. Two fixtures inserted mixtures with a raw `db.mixtures[name] = Mixture(...)` instead of `db.addMixture(...)`, leaving the `db` back-reference unset — `Mixture.getCost()` raises without it, so `production_batch_roundtrip` blew up the moment its save repainted the Mixtures tab. Product code was never affected (`file_manager/load.py` sets the back-ref explicitly right after its direct insert; every other path goes through `addX()`), so this was a **fixture artifact, not a product bug** — but it's the general shape of Step 81's cost: fixtures that cut corners now get caught.

**Real-data drill** on a copy of `Mercy 2.0 DB 7-8-26.db` (the current real DB — note this supersedes `Mercy DB 6-1-26.db`): the real file records **no mounted dies yet** (`Press.currentPart` unset on all 5 real presses), so as in the Step 80 drill a die was synthesized onto a **real** press with **real** parts/orders — renaming real part `1046 AS-FS4` (mounted on `Press #1 - 20T`, referenced by order `AC-1A-62474`) propagated to the Presses tab, Orders tab and Part-Press grid with zero hand-wiring. Full smoke green (71 checks), pyright clean.

**A second sweep found three more mutation paths — and one was a live bug (2026-07-16).** The first fan-out sweep grepped for `self.mainApp.<x>Tab.refresh…()` and so missed any call reaching a tab through a *different receiver or an extra level*. A re-sweep over **any** receiver caught three:
**All three were converted to `refreshAllViews()` in this step — the descriptions below are of the *pre-fix* code, which no longer exists:**
- **`PartsMarginsWindow`** (the Margin Calculator's Apply) mutated `part.price` and then hand-called `wind.mainApp.partsTab.refreshTable()`. Not user-visible at the time — `part.price` renders only on the Parts tab — but it was the exact latent shape that recurred four times, and while it existed it falsified CONVENTIONS.md's "*every* edit path" absolute (**that absolute is true again now**). It is also **outside Step 83's `*EditWindow` survey**, so nothing would have swept it up later — worth remembering that the `*EditWindow` naming convention is not the same set as "mutation paths".
- **`MaterialInventoryEditWindow` / `PartInventoryEditWindow`** reached their tab via the nested `mainApp.inventoryTab.materialsTab` path — and these were a **real, shipped, user-visible bug**: they called `<sub>Tab.refreshTable()`, but that tab's `refresh()` is `refreshTable()` **plus `refreshValueLabels()`. So saving an inventory record updated the table while "Current Total Materials Value" kept displaying the pre-edit total.** Verified before/after: pre-fix the label stayed at `0.0000` after a valid save; post-fix it reads `1.3756`. Note the failure mode — not a *forgotten* refresh but a **too-narrow** one, which no amount of remembering-to-refresh prevents, and which is the strongest argument for the blanket call. Covered permanently by the new `inventory_edit_refreshes_value_labels` check.

**⏸ Deferred to Step 83 (§13.52):** the `EditWindow` base class. B leaves one `refreshAllViews()` call per edit path — inherited-instead-of-written is a pure refactor that stacks on B with no rework, so it was split out rather than entangled with a bugfix.

### 13.51 Whole-piece schedule quantities (drift-free) + H:MM press time (planned 2026-07-16) — Step 82

Two findings from Matthew's first look at a **real-order** schedule (2026-07-16, the DB now has actual order data — and the Step 80 die stickiness "looks great"):

> **Correction (2026-07-16, Matthew) — don't over-trust that "looks great".** The **orders are real**, but the **die placement it ran against was not**: Matthew *manually entered* starting die data, and a team member on hand judged the result "appropriate". So it's a **synthetic seed, sanity-checked by someone who knows the floor** — better evidence than a fuzz seed, but *not* the floor's own recorded state. The team **still hasn't deployed a schedule**. Two consequences: (1) §13.45 (validate the greedy against real order data) is **not** half-done — the die half still awaits real deployment; (2) that manual die data isn't persisted in `Mercy 2.0 DB 7-8-26.db` (all 5 real presses have `Press.currentPart` unset as of the Step 81 drill), so a drill still has to synthesize a mount, as Steps 80 and 81 both did.

1. **The schedule prints fractional quantities** — `SII-3 … 1008.24`, `GS8 … 483.253`. You can't press a fraction of a part. `ScheduleRow.quantity` has been a raw `hours * rate` float since the scheduler landed (Steps 52/53) — **pre-existing, not a Step 80 regression**; real rates just made it visible. Matthew: "I guess we just round down, but that might lead to fractional errors accumulating… it'd be nice if there wasn't any drift."
2. **Press-hours print as a fraction** — `7.6303`, `0.369697`. Should read hours:minutes.

**The insight that settles #1: round the running total, not the row.** Rounding each row independently is *exactly* what accumulates error (8h × 126.03/hr = 1008.24 → 1008 loses 0.24 pcs every row, forever). Instead track cumulative press-hours per part and take each row's quantity as the difference between consecutive rounded cumulative totals — `round(cumAfter × rate) − round(cumBefore × rate)`. Every row is whole, and because a part's total hours × rate is *exactly* its integer required-pieces (`requiredPressed` is already a `math.ceil` int and `needHours = required / rate`), the rows **sum exactly to the required total**. Not reduced drift — **zero**: the residue can never accumulate because each row is measured against the true running total, never against the previous rounded row. So we don't trade "round down" against "no drift" — we get both. Expected and correct side effect: two identical 8-hour days can read 1008 then 1009, which is the fractional remainder surfacing exactly when it has genuinely accrued a whole piece.

**Design calls — settled 2026-07-16 (Matthew):**
- **Nearest, on the running total** (not floor): each row hews as close as possible to its true share, and the run total is exact either way.
- **Model, not display.** `ScheduleRow.quantity` becomes an `int` rather than being formatted at render time — drift-free rounding needs the running total, which only the scheduler has, and pieces genuinely are discrete.
- **Flags: whole pieces, decimal hours.** `OrderFlag.piecesShort` → whole pieces; the flag's aggregate `shortHours` stays a decimal (`"76:18 press-hr unplaced by horizon"` reads strangely). `piecesShort` rounds by **ceil**, not nearest — a genuine shortage must never print `"0 pcs short at deadline"` next to `"1 day late"`, and it matches `requiredPressed`'s conservative ceil.
- **H:MM is display-only** — the row keeps float `hours` (the math needs it).

**Shape of the work (Step 82) — no schema change, no `db_version` bump.**
- [`scheduling.py`](scheduling.py): cumulative per-part rounding in the `schedule()` walk; `ScheduleRow.quantity: int`; `OrderFlag.piecesShort: int`; new `formatPressHours()` beside the Step 67 view helpers (`7.6303 → "7:38"`, `0.369697 → "0:22"`, `8.0 → "8:00"`), with minute-carry so `7.999 → "8:00"`, never `"7:60"`.
- [`schedule_tab.py`](schedule_tab.py) + [`report/scheduling.py`](report/scheduling.py): both currently `f"{r.hours:g}"` / `f"{r.quantity:g}"` — swap the press-hours cell to `formatPressHours()`. They share the Step 67 view helpers precisely so the on-screen table and the PDF read identically.
- **Smoke:** a deterministic drift case (a nasty rate over several shift-days: every quantity is a whole number **and** the rows sum exactly to `requiredPressed`), a `formatPressHours` table (carry, zero, sub-hour), and a fuzz invariant that every emitted quantity is integral.

**Note (die-change slivers).** Matthew's screenshot shows Press #4 running GS8 for 7:38 then SII-3.75 for **0:22** — sequential sharing. At the default `dieChangeHours = 0.0` the model prices that die swap at nothing, so it fills a 22-minute tail with a whole die change. Pricing a real die change through the Step 78 seam suppresses such slivers automatically; that knob is the lever, no algorithm change needed. Feeds §13.45.

**⏸ Open, deliberately deferred — setting `dieChangeHours` (Matthew, 2026-07-16):** "I'll set a change cost once I get some proper feedback from the team." **Do not invent a value.** It's a real shop-floor measurement and the seam exists so it's a one-line `ScheduleConfig` change whenever the number arrives. Two paths when it does: a literal (10 min = `10/60`), or `empiricalDieChangeHours(db, today)` deriving it from **Tool Change** production records (needs ≥3 in the trailing window). Until then the scheduler runs at 0.0 = pure hysteresis, completion dates unaffected. This is also the input §13.45 needs to judge the greedy against real orders.

**Landed 2026-07-16 (Step 82).** As planned: per-part `pressedHours` running total in the `schedule()` walk with `_piecesAt` (nearest) differencing, `ScheduleRow.quantity: int`, `OrderFlag.piecesShort: int` via `math.ceil`, `shortHours` left decimal, and `formatPressHours()` added to the Step 67 view helpers + wired into both [`schedule_tab.py`](schedule_tab.py) and [`report/scheduling.py`](report/scheduling.py). **Latent bug found and fixed in passing:** those cells formatted piece counts with `f"{…:g}"`, which flips to *scientific notation* past 6 significant digits (`f"{1234567:g}"` → `'1.23457e+06'`) — a 1.2M-piece order would have printed as garbage. Now that quantities/piecesShort are ints, `:g` is both meaningless and a hazard, so the integer cells moved to `:,` (also gives thousands separators: `1,008`); `shortHours` stays on `:g` since it's a decimal by design. Smoke: new case **P** in `scheduling_scheduler` (5000 pcs @ 126.03/hr over Mon–Fri → quantities `[1008, 1008, 1009, 1008, 967]`, every one an int, summing **exactly** to `requiredPressed`), a `formatPressHours` table in `scheduling_view_slice` (the two real screenshot values, whole shift, zero, half-hour, both minute-carry cases, minute zero-padding), and an integral-quantity invariant in `scheduling_scheduler_fuzz`; hand-built `ScheduleRow`/`OrderFlag` fixtures in `smoke/reports.py` + `scheduling_view_slice` updated to ints (pyright caught them). Real-data drill on the v14 copy: schedule over real parts with genuinely messy **empirical** rates (`AB525` at `20.357142857142858`, `GS5C` at `76.16`) — every quantity whole, press time rendering `8:00`, and each part's rows summing **exactly** to `requiredPressed` (5704 / 5788 / 5808). Full smoke green (69 checks). **Column header renamed `"Press-hours"` → `"Press time"`** (Matthew, 2026-07-16) in both the tab and the PDF, since the cell is now a clock duration rather than a decimal hour count — no smoke asserts the header text, and the Step 66/67 narratives above deliberately keep the old name as the record of what shipped then.

### 13.52 Shared `EditWindow` base class (planned 2026-07-16) — Step 83

Split out of Step 81 (§13.50) as its **option D**, deliberately *not* folded into the bugfix. Step 81 established that every edit path makes one `mainApp.refreshAllViews()` call; D is the same mechanism with that call **inherited rather than written**. Since D is "B plus a refactor", stacking it on top of B costs **zero rework** — which is exactly why it was split: Step 81 stayed a small, reviewable bugfix, and the 20-file refactor gets judged (and reverted) on its own merits.

**The codebase is already shaped for it.** All 20 `*EditWindow` classes derive from `QWidget` directly (no shared base — helpers live in [`utils.py`](utils.py) / [`error.py`](error.py)), yet they were plainly copy-pasted from one template:
- Every `__init__` opens with the identical three lines: `super().__init__(mainApp, Qt.WindowType.Window)` / `setAttribute(WA_DeleteOnClose)` / `self.mainApp = mainApp` (the leading args vary; `mainApp` is always last).
- Every one funnels through `readData(isNew) -> bool`, and the `updateX` / `newX` handler pair is **byte-identical** apart from the method name: `success = self.readData(False)` → `QMessageBox.information(...)` → `self.close()`.

**Shape of the work (Step 83) — pure refactor, no behaviour change, no schema change.**
- A thin `EditWindow(QWidget)` base owning (a) the `__init__` preamble and (b) a `commit(isNew)` that calls the subclass's `readData(isNew)` and on success does `mainApp.refreshAllViews()` + the success message + `close()`.
- Each edit window inherits it, drops the `refreshAllViews()` line from `readData`, and collapses its handler pair onto `commit`. Deletes roughly **80 lines** of duplicated handler boilerplate + **60** of `__init__` preamble.

**Known outliers to handle individually** (found during the Step 81 survey): [`holidays_tab.py`](holidays_tab.py) has a no-arg `readData` wired to a `selectButton`, and [`production_tab.py`](production_tab.py) uses `if self.readData(True):` with its own message text and a separate `ProductionBatchDialog._save()` path.

**Honest limits — worth re-reading before starting.** D is *not* the "impossible to forget" guarantee its pitch implies: a subclass that skips `super().__init__` or wires a button straight to `readData` is silently outside the mechanism again. And Step 81 already made the forgotten-call failure **loud** (your own tab goes stale), so D's real payoff is the boilerplate deletion, not the safety. Weigh that against a 20-window × (update + create) manual sweep — smoke can't reach the message-box commit gate.

---

*This document was prepared with Claude Code (claude-opus-4-6 / claude-sonnet-4-6 / claude-opus-4-7 / claude-opus-4-8) as a planning artifact; §12 is being maintained as implementation proceeds.*
