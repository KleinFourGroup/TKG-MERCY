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

*Last updated 2026-06-24. The original 13-step merge is complete (plus the Step 9.5 polish); Step 13 verified the end-to-end path against real legacy ANIKA + BECKY files — see [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md). Post-release work continues as a running backlog in §13: Steps 14–41 have all landed — per-step status in §12.1, full narratives in [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md). Broadly: UI / report polish (Steps 14–27), a refactor / package-split + code-quality run (28–36 — the `records/`, `file_manager/`, `report/`, and `smoke/` splits plus the vulture and pyright sweeps), and a UI-test + crash-fuzz hardening run (37–41). Each step is one commit on `main` whose message names the step.*

*Step 7 was split into sub-steps 7a–7e to keep each review surface small — see §12.1 for row-by-row status and [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) for the per-substep narrative.*

*2026-06-24: with the Production Scheduling subsystem spec approved by the team, Steps 42–54 were planned as its implementation series — see §13.30 for the roadmap and [`prod-sched-spec.md`](plan_archive/prod-sched-spec.md) for the approved spec. Steps 42 (tab shell), 43 (Press table + first schema/migration to db_version 5), 44 (Pressers table → db_version 6), 45 (Shift Workweek → db_version 7), 46 (Client table → db_version 8, first Sales-group table), 47 (Order table → db_version 9, with the first block-on-delete FK guards) and 48 (Part-Press Preference nested editor → db_version 10, the first nested relational editor) have landed, as has 49 (Order Status nested editor → db_version 11, dated per-order remaining-to-press / remaining-to-ship snapshots); next up is Step 50 (scheduling-algorithm design round — an addendum doc, the second design gate).*

### 12.1 Step status

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
| 50 | ⬜ Planned | Production Scheduling: scheduling-algorithm design round (addendum doc) — see §13.30 |
| 51 | ⬜ Planned | Production Scheduling: scheduling primitives (calendar / capacity / rate / scrap / deadline helpers) — see §13.30 |
| 52 | ⬜ Planned | Production Scheduling: scheduler core (heuristic + infeasibility detection) — see §13.30 |
| 53 | ⬜ Planned | Production Scheduling: Production Schedule Report UI + PDF export — see §13.30 |
| 54 | ⬜ Planned | Production Scheduling: end-to-end verification + migration-chain replay — see §13.30 |
| 55 | ⬜ Planned | UI-test hardening: stale-view invariant in the crash fuzzer (provable downstream-refresh net) — see §13.31 |

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

### 13.31 Step 55 — provable stale-view net: tab-refresh invariant in the UI fuzzer ⬜ Planned

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

**Sequencing.** Independent of the scheduler series (Steps 50–54) — it only touches the smoke/fuzz harness — so it can be pulled forward (e.g. done before Step 50) or taken after the subsystem lands; numbered 55 to keep the Production Scheduling series (42–54) contiguous. A companion **"Lever 1"** (route every edit/delete success path through `_refreshAllTabs()`, collapsing the N×M refresh-wiring obligation to one registration list) is a possible follow-up but is **out of scope** here — this step is detection-only.

---

*This document was prepared with Claude Code (claude-opus-4-6 / claude-sonnet-4-6 / claude-opus-4-7) as a planning artifact; §12 is being maintained as implementation proceeds.*
