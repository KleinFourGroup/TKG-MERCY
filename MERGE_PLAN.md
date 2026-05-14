# MERCY — Manufacturing and Employee Records: Costing and Yield
## Merge & Implementation Plan

**Date:** 2026-04-16  
**Author:** Matthew Kilgore  
**Status:** Implementation complete — all 13 planned steps landed as of 2026-04-19, plus Step 9.5 (vestigial `Part` attribute cleanup). Step 7 was run as sub-steps (7a correctness → 7b signature → 7c-1 asserts → 7c-2 logging → 7c-3 polish → 7d double-negation → 7e window centering); Step 13 verified the build end-to-end against real legacy ANIKA + BECKY files (see [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md)). Post-release feature backlog requested by the team during Step 13 is tracked in §13.

**See also:** [`CONVENTIONS.md`](CONVENTIONS.md) — live dev conventions and gotchas (smoke baseline, `fuzz_db.py` upkeep, headless Qt + `Employee` construction pitfalls).

---

## 1. Background and Motivation

Two internal desktop applications currently exist:

| App | Codename | Purpose | Version |
|-----|----------|---------|---------|
| Algorithmic Nexus for Information and Knowledge Analysis | **ANIKA** | Product/material inventory and part costing | 8.0 |
| Benefits of Employment Calendar for Knowledge Yield | **BECKY** | Employee HR tracking (reviews, training, PTO, attendance, notes) | 3.1 |

A third application has been requested: a **per-employee production tracker** that records how much of each part (or batch mix) an employee produces per shift per day. Because this feature inherently references data from both ANIKA (parts/mixes) and BECKY (employees), building it as a standalone third app would require either duplicating data or coupling three separate files. The right solution is to **merge all three into a single unified application and database.**

The merged application is named **MERCY** — *Manufacturing and Employee Records: Costing and Yield* — a name that captures the full scope of the unified system, echoes "Knowledge Yield" from BECKY's full title, and carries the double meaning of production yield that is central to the new tracking feature.

Both existing apps are built on the same stack — PySide6, SQLite, reportlab — and share near-identical utility modules (`table.py`, `utils.py`, `error.py`). The architectural lift of merging is moderate, and the merge is also a good opportunity to fix known technical debt.

---

## 2. Technical Inventory

### 2.1 Shared Stack

Both apps use:
- **UI:** PySide6 (Qt6 for Python)
- **Database:** SQLite (single `.db` file, loaded fully into memory)
- **Reports:** reportlab (PDF generation via canvas API)
- **Python stdlib:** `sqlite3`, `datetime`, `base64`, `os`, `sys`

Neither app has a `requirements.txt`. External dependencies are: `PySide6`, `reportlab`. *(The Excel importer in ANIKA used `openpyxl` but has been retired — see §4.)*

### 2.2 ANIKA — File Inventory

| File | Purpose |
|------|---------|
| `main.py` | Entry point |
| `app.py` | `MainWindow`; 6-tab layout |
| `records.py` | Data models: `Material`, `Mixture`, `Package`, `Part`, `ImportedPart`, `Globals`, `Inventory`, `Database` |
| `file_manager.py` | SQLite init/load/save; schema migration |
| `utils.py` | UI helpers, `listToString`/`stringToList` (base64 encoding) |
| `table.py` | `DBTable`/`DBTableModel` — generic `QTableView` wrapper |
| `report.py` | `PDFReport`: globals, mix, sales, and inventory reports |
| `materials_tab.py` | Materials CRUD |
| `mixtures_tab.py` | Mixtures CRUD + PDF report |
| `packaging_tab.py` | Packaging CRUD |
| `parts_tab.py` | Parts CRUD, margin calculator |
| `inventory_tab.py` | Dual-nested material + part inventory tabs |
| `globals_tab.py` | Global cost parameters |
| `error.py` | Error dialog |
| `converter.py` | **Retired** — was a one-time Excel import tool; to be deleted |

**ANIKA Database Tables:** `globals`, `materials`, `mixtures`, `packaging`, `parts`, `materialInventory`, `partInventory`

### 2.3 BECKY — File Inventory

| File | Purpose |
|------|---------|
| `main.py` | Entry point |
| `app.py` | `MainWindow`; 4-tab layout |
| `records.py` | Data models: `Employee`, `EmployeeReview`, `EmployeeTrainingDate`, `EmployeePoint`, `EmployeePTORange`, `EmployeeNote`, `HolidayObservance`, `Database` |
| `file_manager.py` | SQLite init/load/save; version-based migration |
| `defaults.py` | Static configuration: training types, review intervals, point values, holidays, PTO eligibility |
| `utils.py` | UI helpers, `stringToB64`/`stringFromB64`, `listToString`/`stringToList` |
| `table.py` | Identical to ANIKA |
| `report.py` | `PDFReport`: employee points, PTO, notes, incident, and active-employee reports |
| `main_tab.py` | Employee picker + sub-tab container |
| `employees_tab.py` | Employee CRUD, active/inactive, PDF report |
| `reviews_tab.py` | Review tracking |
| `training_tab.py` | Safety training tracking |
| `points_tab.py` | Attendance/disciplinary points |
| `pto_tab.py` | PTO hours: tenure base, quarterly bonuses, carryover |
| `notes_tab.py` | Incident notes |
| `holidays_tab.py` | Holiday defaults + shift-specific observances |
| `error.py` | Identical to ANIKA |

**BECKY Database Tables:** `globals`, `employees`, `reviews`, `training`, `attendance`, `PTO`, `notes`, `holidays`, `observances`

---

## 3. Current Schema — Issues to Fix

This merge is the right time to correct several accumulated technical shortcuts. The issues below are organized by severity.

### 3.1 Base64-Encoded Compound Fields (HIGH — schema change)

Both apps use a workaround of encoding lists as base64-delimited strings inside single SQLite columns. This is fragile (no referential integrity, hard to query directly, opaque if the DB is ever opened externally) and should be replaced with proper relational tables.

**ANIKA — `mixtures` table:**
```
-- Current (bad):
mixtures(name PRIMARY KEY, materials, weights)
  where materials = base64("MatA#MatB#MatC")
  and   weights   = base64("100.0#50.0#25.0")

-- Correct:
mixtures(name PRIMARY KEY)
mixture_components(mixture, material, weight, sort_order,
                   UNIQUE(mixture, material))
```

**ANIKA — `parts` table (pad and misc packaging):**
```
-- Current (bad):
parts(..., pad, padsPerBox, misc, ...)
  where pad        = base64("PadA#PadB")
  and   padsPerBox = base64("2#1")
  and   misc       = base64("MiscA")

-- Correct:
part_pads(part, pad, padsPerBox, sort_order, UNIQUE(part, pad))
part_misc(part, item, sort_order, UNIQUE(part, item))
-- then drop pad, padsPerBox, misc columns from parts
```

**BECKY — `reviews.details` and `notes.details`:**
These store plain freeform text wrapped in base64. SQLite TEXT handles newlines natively; the encoding serves no purpose. Migration: decode in-place to plain TEXT.

**BECKY — `employees.shift`:**
Currently stores `"{shift}|{fullTime}"` (e.g. `"2|1"`) as a single string.
```
-- Current (bad):
employees(..., shift, ...)   -- stores "2|1"

-- Correct:
employees(..., shift INTEGER, fullTime INTEGER, ...)
```

### 3.2 Dead / Inconsistent Fields in ANIKA `parts` Table (MEDIUM — schema change)

**Unused columns:** `Part.loading`, `Part.unloading`, `Part.inspection` are stored in the DB but explicitly marked "UNUSED" in the codebase's own `__str__` method. The global `loading` and `inspection` values (in the `globals` table) are what the cost calculations actually use. These per-part columns should be dropped.

**greenScrap — Decision: use global rate only; drop per-part column.** `Part.setProduction()` stores a per-part `greenScrap` value, but `Part.getScrap()` ignores it and uses `globals.greenScrap` instead. Per-part override adds complexity with no current benefit. The `greenScrap` column will be dropped from `parts`; the global value remains the single source of truth.

### 3.3 Incomplete `updateEmployee()` in BECKY (HIGH — logic bug)

`Database.updateEmployee()` in BECKY's `records.py` has a `# TODO` comment and only updates the keys in `employees`, `reviews`, and `notes` dicts when an employee's ID changes. The `training`, `attendance`, and `PTO` dicts are not updated, leaving dangling references. This must be fixed before the production table is added (which will also key on employee ID).

### 3.4 Non-Atomic Saves (HIGH — data integrity)

Both `file_manager.py` implementations save each table independently with individual `commit()` calls. If the app crashes mid-save, the database is left in a partially-written state with no way to roll back. The fix is to wrap the entire save in a single transaction using SQLite's context manager (`with conn:`).

### 3.5 Schema Migration by Table Count (MEDIUM — fragility)

ANIKA's `file_manager.initFile()` detects schema version by counting tables (e.g., `if len(tables) == 10`). Adding any new table breaks this logic. BECKY's approach (using `globals.db_version`) is better and should be adopted uniformly.

### 3.6 `res.executemany()` on a Consumed Cursor (MEDIUM — silent failure risk)

In both `file_manager.py` files, code like:
```python
res = self.dbFile.execute("SELECT ...")
deleted = [...]
res.executemany("DELETE ...", deleted)  # BUG: res is exhausted
```
The `executemany` call here operates on the result cursor object, not a fresh cursor. This can silently fail to delete stale rows. Fix: use `self.dbFile.executemany(...)`.

### 3.7 Assertions as Error Handling (MEDIUM — crash risk)

Both codebases use `assert` statements extensively to validate internal state (100+ occurrences). Python assertions are disabled when running with the `-O` (optimize) flag, and even when enabled they produce ugly `AssertionError` tracebacks rather than user-facing messages. Replace with explicit `raise ValueError(...)` or `raise RuntimeError(...)`.

### 3.8 Minor Issues

| Issue | Location | Fix |
|-------|----------|-----|
| `print()` instead of logging | Both, throughout | Replace with `logging` module (`logging.info`, `logging.error`) |
| Window list memory leak | `*_tab.py` in both apps | Add `Qt.WA_DeleteOnClose` attribute; stop accumulating window references |
| `not x == None` pattern | Both, throughout | Replace with `x is not None` (more Pythonic and marginally faster) |
| Magic number `2000` | ANIKA `records.py:56` | Extract as named constant `LBS_PER_TON = 2000` with explanatory comment (short ton) |
| Magic numbers `18`, `8` (ImportedPart) | ANIKA `records.py` | Moot once `ImportedPart` is removed |
| Debug `print()` in points logic | BECKY `records.py:345` | Remove |
| No `requirements.txt` | Both | Create one listing `PySide6` and `reportlab` |

---

## 4. What Gets Dropped

- **`converter.py`** (ANIKA): The Excel import was a one-time migration tool. It references `ImportedPart`, a legacy class that uses different unit conventions than the current `Part` class. Both `converter.py` and `ImportedPart` (and its `convert()` method) should be deleted. This simplifies `records.py` considerably.
- **BECKY's "Upcoming Actions" tab**: Currently a `QLabel("TODO")` placeholder. It has been evaluated and is not planned for the foreseeable future. The placeholder will be removed entirely from the merged app.
- **`base64`** serialization utilities: Once the schema normalization in §3.1 is complete, `listToString`, `stringToList`, `stringToB64`, and `stringFromB64` in `utils.py` can all be removed.

---

## 5. Proposed Unified Schema

### 5.1 Complete Table List (19 tables)

**From ANIKA (modified):**

```sql
-- Unchanged
CREATE TABLE globals(name PRIMARY KEY, value);
CREATE TABLE materials(
    name PRIMARY KEY, cost, freight,
    SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, otherChem,
    Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325
);
CREATE TABLE packaging(name PRIMARY KEY, kind, cost);
CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date));
CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date));

-- Replaced: mixtures flat → normalized
CREATE TABLE mixtures(name PRIMARY KEY);
CREATE TABLE mixture_components(
    mixture, material, weight REAL, sort_order INTEGER,
    UNIQUE(mixture, material)
);

-- Modified: drop pad/padsPerBox/misc/loading/unloading/inspection/greenScrap
CREATE TABLE parts(
    name PRIMARY KEY, weight, mix,
    pressing, turning,
    fireScrap,
    box, piecesPerBox, pallet, boxesPerPallet,
    price, sales
);

-- New: replaces parts.pad / parts.padsPerBox
CREATE TABLE part_pads(
    part, pad, padsPerBox INTEGER, sort_order INTEGER,
    UNIQUE(part, pad)
);

-- New: replaces parts.misc
CREATE TABLE part_misc(
    part, item, sort_order INTEGER,
    UNIQUE(part, item)
);
```

**From BECKY (modified):**

```sql
-- Modified: split shift column, remove base64 from details
CREATE TABLE employees(
    idNum PRIMARY KEY, lastName, firstName, anniversary,
    role, shift INTEGER, fullTime INTEGER,
    addressLine1, addressLine2, addressCity, addressState,
    addressZip, addressTel, addressEmail,
    status INTEGER
);
CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date));
CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date));
CREATE TABLE attendance(idNum, date, reason, value REAL, UNIQUE(idNum, date));
CREATE TABLE PTO(idNum, start, end, hours REAL, UNIQUE(idNum, start, end));
CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time));
CREATE TABLE holidays(holiday PRIMARY KEY, month INTEGER);
CREATE TABLE observances(holiday, shift INTEGER, date, UNIQUE(holiday, shift, date));
```

**New — production tracking:**

```sql
CREATE TABLE production(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employeeId INTEGER,              -- FK to employees.idNum
    date TEXT,                       -- ISO date (YYYY-MM-DD)
    shift INTEGER,                   -- 1, 2, or 3
    targetType TEXT,                 -- "part" or "mix"
    targetName TEXT,                 -- name in parts or mixtures table respectively
    action TEXT,                     -- "Batching", "Pressing", or "Finishing"
    quantity REAL,                   -- pieces for parts; lbs for mixes
    scrapQuantity REAL DEFAULT 0,    -- pieces/lbs scrapped (0 if not applicable)
    UNIQUE(employeeId, date, shift, targetType, targetName, action)
);
```

### 5.2 Globals Table Keys (unified)

```
gasCost               (from ANIKA)
batchingFactor        (from ANIKA)
laborCost             (from ANIKA)
greenScrap            (from ANIKA — single global rate; per-part override removed)
loading               (from ANIKA)
inspection            (from ANIKA)
manufacturingOverhead (from ANIKA)
SGA                   (from ANIKA)
db_version            (from BECKY — integer, incremented on each schema migration)
```

---

## 6. Production Tracking Design

The production tracking schema is based on the model:
**(employee, date, shift, part-or-mix, action, quantity)**

All design questions have been resolved; decisions are documented in §10.

### 6.1 "Part or Mix" — polymorphic reference

A production record can reference either a **part** (e.g., "pressed 200 of Part X") or a **mix** (e.g., "batched 1400 lbs of Mix Y"). The schema uses a discriminator pattern:
- `targetType TEXT` — `"part"` or `"mix"`
- `targetName TEXT` — the name in the `parts` or `mixtures` table respectively

This keeps the table flat and queryable without nullable FK columns.

### 6.2 Action values — fixed list

`action` is constrained to a fixed list stored in `defaults.py` (alongside `TRAINING`), preventing typos and enabling reliable report grouping:

```python
PRODUCTION_ACTIONS: list[str] = [
    "Batching",
    "Pressing",
    "Finishing",
]
```

The UI will present these as a dropdown, not a free-text field.

### 6.3 Quantity units

Per team clarification at Step 11 kickoff (2026-04-19), actions map 1:1 to target types, and units are expressed in terms of the action's natural work unit rather than the generic part/mix unit originally sketched:

- `Batching` is always against a **mix**; unit is **drops** (pressing drops).
- `Pressing` is always against a **part**; unit is **parts**.
- `Finishing` is always against a **part**; unit is **parts**.

The mapping lives in `defaults.py` as `PRODUCTION_ACTION_TARGET: dict[str, str]` (action → `"mix"`/`"part"`) and `PRODUCTION_TARGET_UNIT: dict[str, str]` (`"mix"` → `"drops"`, `"part"` → `"parts"`). `ProductionRecord.setRecord(action, targetName, …)` takes the action and derives `targetType` from the first dict; the UI uses the second dict to label the quantity field. No separate units column is needed on disk.

### 6.4 Scrap tracking

`scrapQuantity REAL DEFAULT 0` is included in the schema. It defaults to 0 so it need not be entered when not applicable, and is available for quality analysis when it is.

### 6.5 Inventory integration

Production records are **independent** of the inventory tables. The `partInventory` and `materialInventory` WIP staging values in ANIKA are not tied to production scheduling and will not be automatically updated by production entries. The two systems remain separate.

---

## 7. Proposed File Structure

```
TKG-MERCY/
│
├── main.py                  # Entry point (trivial merge)
├── app.py                   # Merged MainWindow with new tab layout
├── records.py               # All data model classes (ANIKA + BECKY + Production)
├── file_manager.py          # Unified DB init/load/save + migration logic
├── utils.py                 # BECKY's superset version (minus base64 utilities)
├── table.py                 # Shared table widget (identical in both; keep one)
├── error.py                 # Error dialog (identical in both; keep one)
├── defaults.py              # From BECKY: training types, review intervals, etc.
│                            #   + PRODUCTION_ACTIONS list (new)
├── report.py                # Merged PDFReport class
│
├── # Products domain (from ANIKA)
├── parts_tab.py
├── mixtures_tab.py
├── materials_tab.py
├── packaging_tab.py
├── inventory_tab.py
├── globals_tab.py
│
├── # Employees domain (from BECKY)
├── employee_detail_tab.py    # renamed from main_tab.py → employee_overview_tab.py → final name (Steps 5, 29)
├── employees_tab.py
├── reviews_tab.py
├── training_tab.py
├── points_tab.py
├── pto_tab.py
├── notes_tab.py
├── holidays_tab.py
│
└── # Production domain (new)
    └── production_tab.py
```

### 7.1 Merged Tab Layout

```
┌──────────────────────────────────────────────────────────────┐
│  MERCY v1.0                                                  │
│  File: path/to/database.db        [Open] [Save] [Save As]    │
├────────────┬────────────┬─────────────┬────────────┬─────────┤
│  Products  │  Employees │  Production │  Inventory │ Settings│
└────────────┴────────────┴─────────────┴────────────┴─────────┘
```

- **Products** → nested: Parts | Mixtures | Materials | Packaging
- **Employees** → nested: Overview | Employee List | Holiday Observances
- **Production** → nested: Daily Entry | Reports
- **Inventory** → nested: Materials | Parts  *(same as current ANIKA Inventory tab)*
- **Settings** → nested: Cost Parameters *(current Globals tab)* | App Info

---

## 8. Migration Plan for Existing Users

### 8.1 Overview

The merged app will be able to open three kinds of `.db` files:
1. An ANIKA-format database (no employee tables)
2. A BECKY-format database (no material tables)
3. A MERCY-format database (both + production table)

Detection logic in `file_manager.initFile()`:
- Has `materials` + `parts` but no `employees` → **ANIKA DB**, run ANIKA migration
- Has `employees` + `PTO` but no `materials` → **BECKY DB**, run BECKY migration
- Has `production` table + `globals.db_version` → **MERCY DB**, check version number

### 8.2 Safety: Always Back Up First

Before any migration, the app will:
1. Copy `database.db` → `database.db.bak-YYYY-MM-DD`
2. Show the user a confirmation dialog naming the backup file
3. Run the migration in a single SQLite transaction (if anything fails, roll back entirely — the original file is untouched)

### 8.3 ANIKA Migration Steps

1. Decode `mixtures.materials` and `mixtures.weights` base64 fields
2. Create `mixture_components` table; insert decoded rows; drop `materials` and `weights` columns from `mixtures`
3. Decode `parts.pad`, `parts.padsPerBox`, `parts.misc` base64 fields
4. Create `part_pads` and `part_misc` tables; insert decoded rows
5. Recreate `parts` table without `pad`, `padsPerBox`, `misc`, `loading`, `unloading`, `inspection`, and `greenScrap` columns (SQLite requires table recreation to drop columns)
6. Create all BECKY-origin tables (empty): `employees`, `reviews`, `training`, `attendance`, `PTO`, `notes`, `holidays`, `observances`
7. Create `production` table
8. Set `globals.db_version = 1`

### 8.4 BECKY Migration Steps

1. Read `employees.shift` compound field, split into `shift` and `fullTime`
2. Recreate `employees` table with split columns; copy data
3. Decode base64 in `reviews.details` and `notes.details` → plain TEXT; update in place
4. Fix any rows where `updateEmployee()` left dangling keys in `training`, `attendance`, or `PTO` (validate FK consistency; log any orphaned rows)
5. Create all ANIKA-origin tables (empty): `materials`, `mixtures`, `mixture_components`, `packaging`, `parts`, `part_pads`, `part_misc`, `materialInventory`, `partInventory`
6. Create `production` table
7. Set `globals.db_version = 1`

### 8.5 Merging Two Existing Databases

If a user has both an ANIKA `.db` and a BECKY `.db` file with real data, the app should support a one-time merge:

1. File → *Import from BECKY database...* (or vice versa)
2. User selects the second file
3. App migrates both to MERCY format in memory
4. Imports the employee tables from the BECKY file into the already-open MERCY DB
5. The only conflict is `globals`: use ANIKA's cost parameters; the unified DB's `db_version` takes precedence
6. Save the merged result

### 8.6 Concurrency

The app will have fewer than five concurrent users. SQLite in **WAL (Write-Ahead Logging) mode** is sufficient for this — WAL allows multiple simultaneous readers and one writer without locking contention. Enable at DB creation time:

```python
conn.execute("PRAGMA journal_mode=WAL")
```

No other infrastructure changes are needed.

---

## 9. Implementation Order

Each step leaves the app in a working state so the team can test incrementally.

| Step | Description | Risk | Testable Milestone |
|------|-------------|------|-------------------|
| **1** | Create new repo (`TKG-MERCY`). Copy ANIKA as base. Delete `converter.py` and `ImportedPart`. | Low | App works identically to ANIKA |
| **2** | Merge shared files: adopt BECKY's `utils.py` (superset); both `table.py` and `error.py` are identical | Low | No change in behavior |
| **3** | Merge `records.py`: add all BECKY model classes; unify `Database` class | Medium | Compiles; ANIKA features work |
| **4** | Merge `file_manager.py`: unified schema creation with `db_version` tracking; add WAL pragma | Medium | Can create new empty unified DB file |
| **5** | Add all BECKY tab files; wire into new tab layout in `app.py` | Medium | Both domains visible; both load/save correctly |
| **6** | Merge `report.py` | Low | All existing reports generate correctly |
| **7** | Apply tech debt fixes: assertions → exceptions, atomic saves, fix `executemany` bug, fix `updateEmployee`, replace `print` with logging, fix window cleanup | Medium | Cleaner, more robust app |
| **8** | Implement ANIKA migration (base64 normalization, column drops, table recreation) | High | Old ANIKA `.db` files open and migrate correctly |
| **9** | Implement BECKY migration (shift split, base64 decode, FK consistency check) | High | Old BECKY `.db` files open and migrate correctly |
| **10** | Implement DB merge (import second `.db` into first) | Medium | Both old databases can be combined into one |
| **11** | Implement production tracking: `ProductionRecord` in `records.py`, `PRODUCTION_ACTIONS` in `defaults.py`, `file_manager.py` additions, `production_tab.py` | Medium | New feature works end-to-end |
| **12** | Implement production reports in `report.py` | Low | Reports generate correctly |
| **13** | End-to-end testing with real data; backup/restore verification | — | Ready to ship |

---

## 10. Resolved Design Decisions

All production tracking design questions have been answered by the team lead.

| # | Question | Decision |
|---|----------|----------|
| **1** | Should `action` be free-text or a fixed list? | **Fixed list.** Values: `Batching`, `Pressing`, `Finishing`. Stored in `defaults.py` as `PRODUCTION_ACTIONS`; presented as a dropdown in the UI. |
| **2** | Should the `production` table include a `scrapQuantity` field? | **Yes**, included as `scrapQuantity REAL DEFAULT 0`. Defaults to 0 so entry is not required when not applicable. |
| **3** | Should saving a production record automatically update part WIP inventory? | **No.** The inventory staging values in ANIKA are not tied to production scheduling. The two systems remain independent. |
| **4** | Should individual parts be able to override the global green scrap rate? | **No.** All parts use `globals.greenScrap`. The unused per-part `greenScrap` column will be dropped from the `parts` table during migration. |
| **5** | Should "Upcoming Actions" (upcoming reviews, expiring training, etc.) be included? | **No.** This feature is not planned for the foreseeable future and the existing placeholder will be removed. |

---

## 11. Summary of Changes vs. Current Code

| Category | ANIKA change | BECKY change |
|----------|-------------|-------------|
| New tables | `mixture_components`, `part_pads`, `part_misc`, `production`, all BECKY tables | all ANIKA tables, `production` |
| Modified tables | `mixtures` (drop encoded cols), `parts` (drop 7 cols), `globals` (add `db_version`) | `employees` (split `shift`), `reviews` (decode `details`), `notes` (decode `details`) |
| Deleted files | `converter.py` | — |
| Deleted classes | `ImportedPart` | — |
| Deleted utility functions | `listToString`, `stringToList` (after migration complete) | `listToString`, `stringToList`, `stringToB64`, `stringFromB64` |
| Logic fixes | `getScrap()` confirmed global-only; drop `greenScrap` from `parts` | `updateEmployee()` incomplete key updates |
| Infrastructure | Atomic saves, `db_version` migration, WAL mode | Atomic saves (already has `db_version`) |

---

## 12. Implementation Progress

*Last updated 2026-05-13. All 13 planned steps complete, plus the Step 9.5 polish. Step 13 verified the end-to-end path against real legacy ANIKA + BECKY files (see [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md)). Post-release feature backlog from the team's first look at the release is tracked in §13; Steps 14–23 and 25–27 have landed, plus Step 24 (the previously-deferred per-employee productivity report, landed 2026-05-08 once the team confirmed scope). The second round of team feedback (2026-04-24) added Step 23 (quantity positive-check, landed same day) and Step 24 (per-employee reports, initially deferred), finalized the scope of Steps 18 and 19 (both landed 2026-04-24), and surfaced Step 25 (confirm-on-close dialog, also landed 2026-04-24). The third round (2026-05-08) added Step 26 (rate columns on the production-family reports) to address persistent team confusion between the production and productivity reports, confirmed the spec for Step 24, and — after Matthew's manual test of Step 24 — surfaced Step 27 (Employee Productivity polish). All four landed same-day. With team feedback running slow, Steps 28-32 were sketched 2026-05-09 as a code-quality / refactor backlog (records.py split, code hygiene sweep, selector helper, smoke.py split, file_manager.py split) — all gated on the team blessing the recent reports. Team blessing came in 2026-05-10; Step 29 (code hygiene sweep) landed same day as the first of the refactor steps. 2026-05-11 archival sweep collapsed the §13.6/§13.12/§13.13/§13.14/§13.15/§13.17 done-step bodies and the tail-of-doc legacy Step 16 sketch into pointer-stubs to keep this doc under the single-read budget; full narratives are in [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md). Step 28 (the `records.py` → `records/` package split) landed 2026-05-11 — smoke 17 PASS on the first try since the backwards-compat re-export shim kept every existing `from records import ...` line working unchanged. Step 30 (selector helper widget) landed same day, factoring the five-combo cluster out of `ProductionReportWindow` into a new `production_report_selector.py`. Step 31 (smoke.py split) followed the same day, slicing the 2068-line `smoke.py` into a `smoke/` package along the records/migrations/reports/ui domain split called out in §13.19; CLI shifted to `./Scripts/python.exe -m smoke`. Step 32 (file_manager.py split) closed out the refactor backlog the same day — 1123-line `file_manager.py` carved into a six-file `file_manager/` package using mixin composition (schema / migrate / save / load / import_db, with the `FileManager` class itself orchestrating in `__init__.py`); smoke 17 PASS first try and a fuzz-DB load → save → reload roundtrip across 19 populated tables (3522 production records) compared row-for-row identical post-save. 2026-05-13 session closed the Step 28.1 follow-up (`file_manager/load.py` and `fuzz_db.py` switched to per-module records imports), renamed `EmployeeOverviewTab` → `EmployeeListTab` to close the §12.3 follow-up, added `TYPE_CHECKING` attribute-stub blocks to all five `file_manager/` mixins so Pylance can resolve `self.dbFile`/etc., and landed Step 33 — the `report.py` → `report/` package split using the same mixin composition as Step 32 (PDFReportCore base + Product/Employee/Production reports mixins; smoke 17 PASS first try). Each step is committed separately on `main` with a message that names the step.*

Step 7 was split into sub-steps to keep each review surface small. The hygiene sweep (7c) turned out to be large enough that it was further split into three; 7e was added when 7c-3's window-retention fix surfaced a centering regression:

- **7a** — correctness / data-integrity fixes (done).
- **7b** — promote `Database.__init__`'s optional BECKY kwargs to required args (done).
- **7c-1** — `assert` → `raise` (237 sites across the repo; judgment calls between `RuntimeError` for internal invariants vs `ValueError` for method-boundary input).
- **7c-2** — `print()` → `logging` (136 sites; 120 of them in `file_manager.py` save chatter) + drop the BECKY debug `print` in points logic.
- **7c-3** — mechanical + polish: `not x == None` → `x is not None`, window-close leak (`Qt.WA_DeleteOnClose` + parent-retention), `LBS_PER_TON` constant, `requirements.txt`.
- **7d** — clean up 2 double-negation leftovers from 7c-1.
- **7e** — restore window centering regressed by 7c-3's parent-retention change.

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

Landed 2026-05-13. Same composition pattern as Step 32: a `PDFReportCore` base owns `__init__` + the canvas/text/table primitives (`drawTitle` / `drawTable` / `_wrapText` / etc.); three domain mixins (`ProductReportsMixin`, `EmployeeReportsMixin`, `ProductionReportsMixin`) own the per-domain reports; `report/__init__.py` composes them into a single `PDFReport` class. External imports (`from report import PDFReport`) keep working unchanged — the 13 import sites across the tabs and `smoke/reports.py` needed no edits.

Four-file shape: `core.py` (191 lines), `products.py` (272), `employees.py` (242), `production.py` (1148). Production stays bundled for now.

**Eventual goal (Matthew, 2026-05-13):** as each report's layout is finalized in the field, peel them off into one-report-per-mixin files for human readability — the unit of "smallest readable file" is a single report, not a domain. No urgency: it's a nuisance to do incrementally and there's no value until layouts are stable. Tracked here as the running follow-up.

Each mixin carries a small `if TYPE_CHECKING:` stub block declaring the `PDFReportCore` attributes/helpers it reads off `self` (`db`, `pdf`, `setupPage`, `drawTable`, etc.) — same pattern landed in `file_manager/` earlier this session. Pylance resolves cross-mixin references; zero runtime cost.

One smoke-side touch: `TREND_MODE` is a module-level feature flag that the trend-report smoke check mutates to swap algorithms mid-test. After the split it lives in `report/production.py`, so `smoke/reports.py` was updated from `import report as R` to `import report.production as R` (one line). Re-exporting `TREND_MODE` from `report/__init__.py` would have made the read work but not the mutation, since re-exports copy the binding rather than reference it — so the mutation has to address the submodule directly.

Verification: smoke 17 PASS first try (covers all four production reports automatically). Manual sweep of one product report and one employee report (which smoke doesn't cover) confirmed identical PDF rendering.

---

*This document was prepared with Claude Code (claude-opus-4-6 / claude-sonnet-4-6 / claude-opus-4-7) as a planning artifact; §12 is being maintained as implementation proceeds.*
