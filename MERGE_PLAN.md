# MERCY — Manufacturing and Employee Records: Costing and Yield
## Merge & Implementation Plan

**Date:** 2026-04-16  
**Author:** Matthew Kilgore  
**Status:** Implementation complete — all 13 planned steps landed as of 2026-04-19, plus Step 9.5 (vestigial `Part` attribute cleanup). Step 7 was run as sub-steps (7a correctness → 7b signature → 7c-1 asserts → 7c-2 logging → 7c-3 polish → 7d double-negation → 7e window centering); Step 13 verified the build end-to-end against real legacy ANIKA + BECKY files (see [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md)). Post-release feature backlog requested by the team during Step 13 is tracked in §13.

**See also:** [`CONVENTIONS.md`](CONVENTIONS.md) — live dev conventions and gotchas (smoke.py baseline, `fuzz_db.py` upkeep, headless Qt + `Employee` construction pitfalls).

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
├── employee_overview_tab.py  # renamed from main_tab.py for clarity
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

*Last updated 2026-04-24. All 13 planned steps complete, plus the Step 9.5 polish. Step 13 verified the end-to-end path against real legacy ANIKA + BECKY files (see [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md)). Post-release feature backlog from the team's first look at the release is tracked in §13; Steps 14, 15, 16, 17, 20, 21, and 22 have landed. The second round of team feedback (2026-04-24) added Steps 23 (quantity positive-check) and 24 (per-employee reports, deferred) and finalized the scope of Steps 18 and 19. Each step is committed separately on `main` with a message that names the step.*

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
| 18 | ⏳ Planning | productivity rate reports (tables, feeds costing) — see §13.5 |
| 19 | ⏳ Planning | trend reports (graphs, 30-day rolling averages) — see §13.6 |
| 20 | ✅ Done | Merge plan Step 20: remember last DB, prompt to reopen on startup |
| 21 | ✅ Done | Split MERGE_PLAN.md: move §12.2/§12.4/§12.5 bodies into plan_archive/, extract live conventions into CONVENTIONS.md |
| 22 | ✅ Done | Merge plan Step 22: add Tool Change production action — see §13.10 |
| 23 | ⏳ Planning | production quantity: positive check, not non-negative — see §13.11 |
| 24 | ⏳ Deferred | per-employee reports (pending team confirmation) — see §13.12 |

### 12.2 Decisions / deviations worth knowing before Step 6+

*Step-by-step implementation narratives moved to [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) on 2026-04-22 to keep this doc lean. See that file for what actually shipped for each step, and why.*

### 12.3 Known deferred issues visible in the current build

- Bare `x == None` / `x != None` residuals (not in 7c-3's scope; see [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 7c-3). Small optional follow-up.
- One awkward DeMorgan-able condition at `file_manager.py:176` / `:447` (`if not ((A is not None) and (B is not None)):`) — correct but ugly. Style-only, not blocking.
- Step 5's partial rename: `main_tab.py` → `employee_overview_tab.py` but the class is still `MainTab`. Not in Step 7's scope; see [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 5.

### 12.4 Test conventions used so far

*Historical smoke-check list moved to [`plan_archive/test_conventions.md`](plan_archive/test_conventions.md) on 2026-04-22. Live dev conventions (always-on `smoke.py` baseline, `fuzz_db.py` upkeep, headless-construction gotchas) now live in [`CONVENTIONS.md`](CONVENTIONS.md) at repo root.*

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

### 13.5 Step 18 — productivity rate reports (tables, feeds costing) ⏳ Planning

**Motivation.** Surfaced 2026-04-21 alongside Step 17; detailed spec received in the 2026-04-24 feedback round. Team wants productivity drill-downs — rates per hour by action × target × shift, with per-employee breakdowns inside each target. **Downstream consumer is the costing code, not HR** — they're gathering more precise labor data to refine the per-part cost estimates in the costing globals (the existing `pressing` / `turning` / `finishing` / etc. fields on `parts`). Not bonuses, not quotas, no targets stored on the record.

**Team spec (2026-04-24).**
- **Selection.** Action (required) + target (specific or "all") + shift (specific or "all") + user-picked date range. Same shape as the existing production reports' selector (action/target + date range already present in [production_tab.py:489](production_tab.py:489)'s `ProductionReportWindow`).
- **Output is table-only.** Graphs are Step 19's separate report type. The productivity PDF has no charts.
- **Columns.** Target | Total quantity | Total hours | Rate (qty/hr). Per-employee breakdown rows under each target with the same columns.
- **Layout by selection.**
  - *Specific target + specific shift:* one table — target row (totals + rate) followed by per-employee breakdown.
  - *Specific target + all shifts:* same shape; target row aggregates across shifts.
  - *All targets + specific shift:* summary table first (one row per target + total aggregate row), then per-target tables with per-employee breakdowns.
  - *All targets + all shifts:* summary table, then a second overview table breaking the total aggregate down by shift (*aggregate only — per-shift × per-target matrix is explicitly rejected as too cluttered*), then per-target tables.
- **Tool Change is special.** No rate/hr. No per-employee breakdown. Just total hours spent. Shift selector stays enabled — team joked that specific-shift Tool Change reports collapse to one-row tables; accepted as-is rather than special-casing disable logic.
- **No scrap columns.** Confirmed 2026-04-24. Team will likely want a standalone scrap report later; tracked as pending-feedback, not part of Step 18.

**Resolved design decisions.**
| # | Question | Decision |
|---|----------|----------|
| 1 | Aggregation math | `sum(qty) / sum(hours)` (ratio of sums) over the window. Chosen 2026-04-24 — more honest when shifts are uneven in length or completeness. No alternative mode planned for Step 18; if the team asks later, add a per-report toggle. |
| 2 | Primary cut | `(action, target)` with `(action, target, shift)` and `(action, target, employee)` as drill-downs inside each target section. Action is always a selector (never an "all" option for productivity reports). |
| 3 | Windowing | User-picked date range via the existing selector widgets. |
| 4 | Export | Not in initial scope. Revisit if team wants to paste rates directly into costing globals. |

**Tentative implementation sketch.**
- Add `"Productivity"` as a new entry in [production_tab.py:489](production_tab.py:489)'s `REPORT_TYPES`.
- `ProductionReportWindow` grows target and shift combos with "all" options. Target combo rebuilds when action changes (reuse the action-cascade pattern from Step 16's batch dialog — [production_tab.py:733](production_tab.py:733) region).
- New `PDFReport.productionProductivityReport(action, targetName|None, shift|None, startDate, endDate)` in [report.py](report.py). `None` for target or shift means "all". Internal branching picks the layout from the four cases above.
- Tool Change branch: collapse to total-hours-only table, skip rate/hr and per-employee sections.
- `fuzz_db.py` already produces plausible data for this; no generator changes needed.

**Open question.** Default date range for the selector when the report window opens. Options: last 30 days / last 90 days / year-to-date / blank. Call it during implementation unless the team surfaces a preference first.

**Verification.** Extend `smoke.py` with a productivity-report smoke that exercises all four shape cases (specific/all × specific/all) plus the Tool Change variant. Manual spot-check against the team's DB before shipping.

**Next session pickup.** Scope is clear enough to start coding. Recommend starting with the non-Tool-Change branch (three layout cases), then adding the Tool Change collapse. Mock one layout in `mock_reports.py` first if the all-targets-all-shifts shape feels uncertain — cheap sanity check before wiring into the real pipeline.

### 13.6 Step 19 — trend reports (graphs, 30-day rolling averages) ⏳ Planning

**Motivation.** Second half of the 2026-04-21 feedback; detailed spec received 2026-04-24. Team wants graph-based trend reports that show how rates move over longer windows (quarter to year) — complements Step 18's static-snapshot productivity tables. Distinct report type, not a graph-alongside-table hybrid.

**Team spec (2026-04-24).**
- **Selection.** Same shape as Step 18: action (required) + target (specific or "all") + shift (specific or "all") + user-picked date range. Reuse Step 18's selector once it lands.
- **Range validation.** Reject date ranges shorter than 30 days — the 30-day rolling window can't be computed. Default range: 365 days (quarter-to-year is the expected usage; a sensible default matters here because tiny ranges are a real failure mode).
- **Output is graph-only.** No tables. If the team wants numbers for the same window, they run the Step 18 productivity report.
- **Graph shape.**
  - *One graph per selected target*, y = 30-day rolling average of rate (qty/hr), x = date.
  - *All shifts selected:* each graph shows one line per shift + an aggregate line across all shifts.
  - *Specific shift selected:* each graph has a single line.
  - *All targets selected:* lead with a graph of the total-aggregate rolling average across all targets; then one graph per target below it.
- **Tool Change is special.** 30-day rolling average of *time spent*, not rate/hr. Target selector is moot (Tool Change is targetless per Step 22); shift selector still applies the same way.

**Resolved design decisions.**
| # | Question | Decision |
|---|----------|----------|
| 1 | Rolling average math | **Ratio of sums** over the 30-day window: `sum(qty in window) / sum(hours in window)`. Default. Matches Step 18's aggregation. Per Matthew 2026-04-24: also implement the alternative — mean of per-day rates, *excluding days with zero production* — and pick between them via a module-level flag in [report.py](report.py). Default is ratio-of-sums; flag lets us switch if the team prefers the other shape. |
| 2 | Zero-production days | In per-day-mean mode, skip days where nothing was produced (don't drag the mean to zero). In ratio-of-sums mode this is automatically handled (zeros contribute zero to both numerator and denominator). |
| 3 | Chart library | `reportlab.graphics.charts.lineplots.LinePlot`. Native to the stack, zero new deps, vector into the PDF. Matplotlib stays a latent escape hatch if the output aesthetics fall short. |
| 4 | Chart-per-target layout | One chart per target, laid out sequentially. Leading aggregate chart when target=all. |
| 5 | Deliverable | PDF only. No dashboard pivot. |

**Tentative implementation sketch.**
- Add `"Trend"` as a new entry in [production_tab.py:489](production_tab.py:489)'s `REPORT_TYPES`, after `"Productivity"`.
- Reuse Step 18's selector UI (action/target/shift/range). Factor the selector into a small helper widget if practical — mutual reuse is the point.
- Range-validate on Generate: if `(endDate - startDate).days < 30`, show an error dialog and don't render.
- New `PDFReport.productionTrendReport(action, targetName|None, shift|None, startDate, endDate)` in [report.py](report.py). Branches on `action == "Tool Change"` for the time-spent variant.
- New internal helper `PDFReport._rollingRate(records, windowDays=30, mode="ratioOfSums")` → list of `(date, rate)` points. `mode` is the module-level flag per decision 1. Callers pre-filter records by action/target/shift.
- New chart helper `PDFReport.drawLinePlot(series, title, xLabel, yLabel)` where `series = [(label, [(date, y), ...]), ...]`. Mirrors `drawTable`'s API so a future chart helper can slot in the same way.
- `fuzz_db.py`: add a `quarter` or `year` scale so trend reports have enough data to plot against. Alternative: document `fuzz_db.py --scale large` as the trend-report stress case.

**Open questions.**
- **Rolling-average flag surface.** Module-level constant in [report.py](report.py) vs. keyword arg on the report function. Matthew's "flag in the code" language (2026-04-24) suggests module-level is fine; confirm when writing the code.
- **Chart styling tolerance.** reportlab native charts are frumpy-but-functional. Ship a first cut, get team feedback, then invest in tick customization / legend placement / color schemes. Matplotlib escape hatch stays on the shelf.

**Verification.** Extend `smoke.py` with a trend-report smoke that renders against fuzz data covering at least 60 days. Assert: (a) rolling-average series length matches expected count; (b) both rate modes produce values without crashing; (c) sub-30-day range raises the expected error; (d) Tool Change branch renders time-spent lines. Use `mock_reports.py` for first-cut styling evaluation before wiring into the live pipeline.

**Next session pickup.** Depends on Step 18 landing first (shared selector UI). Once 18 is green, start with `mock_reports.py` trend-graph exemplars; send the team a screenshot for styling sign-off; then wire into `PDFReport`.

### 13.7 Step 20 — remember last DB, prompt to reopen on startup ✅ Done

Landed 2026-04-22. Fifth post-release feature item from Matthew's backlog: MERCY previously booted into an empty DB every session. Quality-of-life add — `QSettings`-backed `lastDbPath` persisted after every successful `open()`/`saveAs()`, loaded on startup via a new `MainWindow._loadPath(path) -> bool` helper, prompted through a `QMessageBox.question` in `main.py` between `window.show()` and `app.exec()`. Zero new deps (`QSettings` is already in the PySide6 stack). See [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md) Step 20 for implementation notes, the decision to keep the prompt modal every time (no "always reopen" checkbox yet), and the stale-path-silent-skip behavior.

**Follow-up still open (not part of Step 20).** Confirm with Matthew whether to also remember the last *import* path for the Import Database dialog, since that currently hard-codes `os.path.expanduser("~")`. Separate feature, separate step.

### 13.8 Dev tooling landed

Not step commits but worth cataloging so a cold pickup knows they exist:

- **`mock_reports.py`** — Step 18 planning artifact, landed 2026-04-21 (commit `5bd3433`). Generates three candidate productivity-rate-report layouts (A/hierarchical, B/flat-with-fleet-comparison, C/action-by-part matrix), each with a reportlab-native grouped bar chart. Output writes to `mock_reports/` (gitignored). Deletable once the team picks a design.
- **`fuzz_db.py`** — fake-data DB generator, landed 2026-04-22 (commit `e4246ee`). Writes a fully-populated MERCY DB through the real `FileManager.saveFile()` pipeline: every record type (materials, mixtures, packaging, parts, inventory, employees, reviews, training, attendance, PTO including CARRY/CASH/DROP, notes, holidays + observances, production) gets plausible random data. Deterministic with `--seed`; scales `tiny|small|medium|large` (medium → ~1.7k production records over 90 days). Verified end-to-end: generated DBs roundtrip through `MainWindow.loadFile()`, the Part → Mix → Material cost chain computes cleanly, `PDFReport.productionSummaryReport` renders against them, and a given seed is byte-equivalent across all 12 populated tables on re-run. Good for stress-testing any report (including Step 18's future output) without needing real team numbers.
- **`version.py` + `main.spec` auto-versioning** — landed 2026-04-22. `app.py`'s `VERSION` constant is no longer hand-edited; `version.py` derives it from `git describe --tags --always --dirty` at import time (leading `v` stripped). Frozen PyInstaller exes can't call git at runtime, so `main.spec` runs the same describe at build time, writes `_version.py` (gitignored, bundled into the exe via normal Analysis pickup) as the fallback, and names the output `mercy-{VERSION}.exe`. Release flow collapses to `git tag vX.Y.Z && pyinstaller main.spec`. `main.spec` is now tracked (was `.gitignore`d by the generic `*.spec` rule; carved out with `!main.spec`) so the build logic rides the repo. See [`CONVENTIONS.md`](CONVENTIONS.md) "Versioning & builds" for day-to-day usage.

### 13.9 Step 21 — split MERGE_PLAN.md into archive files ✅ Done

Landed 2026-04-22. This doc had grown to ~1028 lines / ~51k tokens — `Read` without `offset`/`limit` tripped the 25k-token cap. Most of that bulk was historical narrative not needed at session start.

**What moved.** §12.2 step-by-step implementation narratives → [`plan_archive/implementation_notes.md`](plan_archive/implementation_notes.md); §12.4 historical smoke-check list → [`plan_archive/test_conventions.md`](plan_archive/test_conventions.md); §12.5 Step 13 real-data drill findings → [`plan_archive/real_data_findings.md`](plan_archive/real_data_findings.md). All three moved verbatim — relative `§12.x` pointers and "Step N above" language inside them are intentionally preserved since historical accuracy matters more than polish. Archive files open with a small header naming the split date and pointing back to this doc.

**What was extracted to live docs.** Working notes buried in the old §12.4 — the always-on `smoke.py` baseline, a `fuzz_db.py` upkeep reminder, and two gotchas (headless `Employee` construction, offscreen Qt needing `QApplication`) — moved to [`CONVENTIONS.md`](CONVENTIONS.md) at repo root. Expected to grow organically as more conventions and gotchas surface.

**What stayed live.** §12.1 (step status table), §12.3 (known deferred issues), and all of §13 (post-release backlog). Section numbers §12.2 / §12.4 / §12.5 kept as stub-bodied headers so commit messages and archive-file cross-references don't go stale. Every MERGE_PLAN.md pointer that referenced the moved bodies — line 6, the §12 intro paragraph, §12.3 bullets 1 and 3, and the "See §12.2 Step N" pointers in §13.1 / §13.2 / §13.3 / §13.4 / §13.7 — was redirected to the archive path. The `(Step 7c-3 §12.2)` reference inside the preserved pre-Step-16 draft at the doc tail was deliberately left alone since that whole section is already historical-preservation content.

**Verification.** `wc -l MERGE_PLAN.md` dropped from 1028 to 706; remaining `§12.2` / `§12.4` / `§12.5` hits are all section headers, back-references inside this landed-note, or the preserved pre-Step-16 draft at the doc tail; `Read` end-to-end no longer trips the 25k cap; all four archive/convention files exist and are non-empty. No code touched; `smoke.py` green unchanged.

### 13.10 Step 22 — add Tool Change production action ✅ Done

**Landed 2026-04-22** alongside a VERSION bump to `1.0rc3` (rc2 skipped — internal numbering slip, no rc2 build shipped).

**Motivation.** Surfaced 2026-04-22 in follow-up team feedback (not part of the pending feedback we're still waiting on — this was a sixth request that came in alongside it). Team wants to track an additional production action: `Tool Change`. Unlike the three existing actions, a tool change has no part/mix target — the event itself is the record.

**Team spec, as clarified in session.**
- New action `"Tool Change"` in `PRODUCTION_ACTIONS`.
- `targetType` and `targetName` both stored as `""` (empty strings, consistent with the existing TEXT columns — no schema change).
- `scrapQuantity` fixed at 0 (scrap has no meaning without a target).
- `quantity` is **user-entered**. Original proposal was "always 1", but UNIQUE(employeeId, date, shift, targetType, targetName, action) would then cap tool changes at one per shift per employee. Matthew chose to let quantity vary — one record per employee per shift carries the count of changes that shift. More elegant; "one row per change" is available later as an escape hatch if the team wants finer granularity.
- `hours` is still user-entered. Team wants to track how much time is being spent on tool changes.

**Scope.**
- `defaults.py`: append `"Tool Change"` to `PRODUCTION_ACTIONS`, `"Tool Change": ""` to `PRODUCTION_ACTION_TARGET`, and `"": "changes"` to `PRODUCTION_TARGET_UNIT` so the unit label renders cleanly everywhere.
- `records.py`: `ProductionRecord.setRecord` coerces `targetName=""` and `scrapQuantity=0` when the action's target type is `""`. Keeps the natural UNIQUE key canonical even if callers (fuzz, smoke, batch dialog) pass stale UI text. `fromTuple`'s existing targetType equality check already passes for the new action since both expected and stored values are `""`.
- `production_tab.py`:
  - `ProductionEditWindow`: promote `Target:` / `Scrap:` labels to instance members so `_onActionChanged` can toggle their visibility alongside the combo/edit widgets. Action-cascade block moved to **after** `widgetFromList` so `setVisible` lands on parented widgets (defensive — otherwise visibility sometimes doesn't stick once Qt reparents the children). `readData` skips target + scrap validation when `targetType == ""`, forcing `targetName=""` and `scrap=0.0`.
  - `ProductionBatchDialog`: grab `Target` / `Scrap` column-header `QLabel` references out of the construction loop; `_onActionChanged` toggles their visibility and every row's target/scrap widgets (via a new `_BatchRow.setHasTarget()` helper). `_save` skips target + scrap validation for targetless actions. `_addRow` calls `setHasTarget` on newly added rows so they match the current action's state. Initial state is applied with an explicit `_onActionChanged` call after the first row is seeded. Status label reads `"Tool Change has no target — targets hidden."` while a targetless action is selected.
- `report.py`: `productionActionReport` drops the Target + Scrap columns (headers, data, and the totals row) when `targetType == ""`. The other three reports already handle mixed-action data correctly because the `PRODUCTION_TARGET_UNIT[""] = "changes"` mapping fills in the blanks; no code changes in `productionSummaryReport`, `productionTargetReport`, or `productionEmployeeReport`.
- `fuzz_db.py`: extend `populateProduction` so Tool Change gets picked into the per-employee-per-day rotation with plausible counts (1–4 changes) and short hours (0.1–1.0h).
- **No schema change.** TEXT columns already allow empty strings; the UNIQUE constraint treats `""` like any other value. Old DBs keep loading; new DBs open on older builds too (they just won't show the new action in the dropdown — rows with `action="Tool Change"` would surface the `RuntimeError` in `fromTuple`. Matthew has no pre-Step-22 DBs in the field yet, so this isn't a real concern; flagging in case it becomes one).

**Verification.** `smoke.py` green — twelve checks pass. Added `production_tool_change_roundtrip` alongside the existing eleven: it seeds a Tool Change record with deliberately-garbage `targetName` / `scrapQuantity` args, asserts `setRecord` coerces them to the canonical empty-state, then saves / reloads / verifies the shape survives the SQLite roundtrip (`targetType == ""`, `targetName == ""`, `scrapQuantity == 0`, quantity + hours preserved as entered). Beyond smoke, verified interactively via `fuzz_db.py` (61/232 records were Tool Change with correct empty-state shape) and three inline headless probes against the edit dialog, batch dialog, and per-action report.

**Known unknowns / open follow-ups.**
- ~~Productivity rate reporting (§13.5) will need to think about whether Tool Change rates (changes/hr) belong alongside the production-action rates or get a separate report. Flag for the Step 18 planning session.~~ **Resolved 2026-04-24:** Tool Change reports show total time spent — no rate/hr, no per-employee breakdown. Applies to both Step 18 (productivity tables) and Step 19 (trend graphs). See §13.5 / §13.6 for the specifics.

### 13.11 Step 23 — production quantity: positive, not non-negative ⏳ Planning

**Motivation.** Surfaced 2026-04-24 with the second round of team feedback. Production entry currently accepts `quantity = 0`, which has no meaning — a zero-produced record is just noise in the DB. Validation should reject zero as well as negatives.

**Scope.** Swap the validation mode at both production entry sites:
- [production_tab.py:428](production_tab.py:428) (`ProductionEditWindow.readData`, Quick Entry): `checkInput(..., float, "nonneg", errors, "Quantity")` → `checkInput(..., float, "pos", errors, "Quantity")`.
- [production_tab.py:956](production_tab.py:956) (`ProductionBatchDialog._save`, Batch Entry): same swap for the `quantity` field.
- Scrap stays `"nonneg"` — zero scrap is legitimate and the default.
- `"pos"` mode already exists in [utils.py:42](utils.py:42)'s `checkInput`; no new validator to write.
- `ProductionRecord.setRecord` has no quantity validation today and doesn't need any — the UI is the single validation boundary. If Matthew wants belt-and-suspenders, add `if quantity <= 0: raise ValueError(...)` there too; not doing so by default since it would double-fire the error path and the 7a philosophy prefers one source of truth.

**Verification.** Extend `smoke.py` with a `production_quantity_validation` check: construct a `ProductionEditWindow` headlessly, drive `quantityEdit` with `"0"`, call `readData`, assert the returned errors list contains the Quantity-must-be-positive message. Spot-check Batch Entry via a synthetic row list driven through `_save`'s validation path. Existing Tool Change smoke (Step 22) is unaffected since Tool Change records still carry positive `quantity` (the user-entered count of changes).

**Why tackle this first.** Smallest item in the backlog by a wide margin — two line changes, one smoke assertion. Shippable in one short session, which lets the next session start on the larger Step 18/19 work without stacked uncertainty. Matches §13's "smallest first" ordering principle.

**Known unknowns.** None — specified crisply in the feedback.

### 13.12 Step 24 — per-employee reports ⏳ Deferred

**Status.** Skeleton plan only — **not approved by team yet.** Matthew (2026-04-24) thinks the team will want these once Steps 18/19 land, based on how they talk about the production data. Recorded here so the future work isn't a surprise; waiting on explicit team confirmation before building.

**Motivation.** Step 18/19 reports slice by target/shift with per-employee rows as a drill-down. Per-employee reports invert that: pick an employee, see their whole production picture across all actions and targets. Matthew's read is that once the team sees 18/19 they'll ask for this, but it's better to confirm than to build speculatively.

**Expected scope (Matthew's read, pending confirmation).**
- **Two report types**, mirroring 18 and 19: a table-based *Employee Productivity* report and a graphical *Employee Trend* report.
- **Selection.** Employee (required) + user-picked date range. No action/target/shift filters — the report is always all-action × all-target. *(Explicit exclusion: shift is not a filter here.)*
- **Productivity variant (table).** Lead with one aggregate table per action (rows: action totals across all targets). Follow with per-target breakdown tables within each action. Tool Change gets its time-spent-only treatment (no rate/hr, no target rows since it's targetless per Step 22).
- **Trend variant (graph).** 30-day rolling average per action. One graph per action, y = employee's rate/hr, x = date. Tool Change graph shows time-spent per period instead. Same rolling-average mode flag as Step 19.

**Why deferred.**
- Team hasn't actually asked for these; Matthew's inference. Building them speculatively risks missing what they actually want (which might be subtly different — e.g., the "employee vs. fleet average" comparison floated during earlier Step 18 planning but explicitly dropped from Step 18's 2026-04-24 scope).
- Also: Steps 18 and 19 will exercise enough of the selector / aggregation / chart infrastructure that Step 24 becomes cheap after. No reason to build it out of order.

**Tentative implementation shape (if approved as-sketched).**
- Add `"Employee Productivity"` and `"Employee Trend"` as the 6th and 7th entries in [production_tab.py:489](production_tab.py:489)'s `REPORT_TYPES`.
- Selector collapses to just the employee combo + date range. Hide action/target/shift widgets when these report types are selected.
- `PDFReport.productionEmployeeProductivityReport(employeeId, startDate, endDate)` and `productionEmployeeTrendReport(employeeId, startDate, endDate)`. Both reuse the aggregation helpers and chart helper from Steps 18/19.

**Open questions (to confirm with team before building).**
- Productivity and Trend as two separate report types vs. a single combined PDF per employee?
- Should a "vs. fleet average" column appear in the table variant? (Raised during Step 18 planning, not revisited 2026-04-24.)
- Any Tool Change inclusion at all on per-employee reports, or skip it entirely since the team explicitly said Tool Change doesn't need per-employee data? Likely "skip", but worth asking.

**Next session pickup.** Hold off until Steps 18/19 have shipped and the team has used them for a bit. Bring this skeleton back as a concrete proposal then — ideally with a mock in `mock_reports.py` rather than open-ended questions.

---

Original plan for Step 16 (pre-dated by Step 17) preserved below for reference.



**Motivation.** Team reported that entering production records one at a time via the single-record dialog will be cumbersome when the floor logs dozens per day. Team proposed: shared date + action at the top of a dialog, then N rows of `(employee, target, quantity, scrap)` below, plus an "add row" button.

**Scope.** New `ProductionBatchDialog` in `production_tab.py`, reachable from a new "Batch Entry" button on the `ProductionTab` toolbar alongside whatever triggers `ProductionEntryDialog` today. The existing single-record `ProductionEntryDialog` stays as "Quick Entry" (cheap to keep, still preferable for one-off edits).

**Layout.**
```
┌─────────────────────────────────────────────────┐
│  Date: [____]    Action: [ Pressing     ▾]      │   ← shared header
├─────────────────────────────────────────────────┤
│  Employee ▾   Target ▾   Qty   Scrap   Shift ▾   ✕│  ← row 1
│  Employee ▾   Target ▾   Qty   Scrap   Shift ▾   ✕│  ← row 2
│  ...                                             │
│  [+ Add row]                                     │
├─────────────────────────────────────────────────┤
│                          [ Cancel ]  [ Save ]    │
└─────────────────────────────────────────────────┘
```

**Resolved decisions (from 2026-04-19 session).**
1. **Shift is per-row**, inherited as a default from the previous row. The same batch can span multiple shifts (shift lead entering a full day).
2. **Target dropdown is filtered by the shared action.** Since `action` is at the top of the dialog and target-type is a function of action (`Batching` → mix, `Pressing`/`Finishing` → part), each row's target combo only lists the appropriate type. If the user changes the top-level action mid-edit, all row target-combos must be rebuilt (and any now-invalid selections cleared with a status-line warning).
3. **Atomic per-batch save.** Any validation or UNIQUE failure on any row refuses the entire batch with a per-row error listing. No partial-save semantics — makes the transaction easier to reason about and mirrors Step 7a's atomic-save philosophy for file writes.

**Implementation sketch.**
1. New class `ProductionBatchDialog(QDialog)` (or `QWidget` top-level like the existing windows) in `production_tab.py`. Mirror the `WA_DeleteOnClose` + `setAttribute` pattern used by other edit windows (Step 7c-3 §12.2).
2. Header `QHBoxLayout` with `QDateEdit` + `QComboBox` for action.
3. Scroll area whose inner widget holds a `QVBoxLayout` of row widgets. Each row = small `QWidget` subclass `_BatchRow(QWidget)` holding the 5 input widgets + remove button. Store rows in `self.rows: list[_BatchRow]`.
4. "Add row" button at bottom of scroll area: instantiates a new `_BatchRow`, pre-populates fields from `self.rows[-1]` if it exists (quantity and scrap cleared — safer default than duplicating numerical values).
5. Action-change signal (top-level combo): iterate rows, rebuild each target combo for the new target-type, clear rows whose selected target no longer appears in the new list, show a status label above the rows if any row was invalidated.
6. Save button: iterate rows, build `ProductionRecord` per row, validate each (reusing whatever validation the existing `ProductionEntryDialog` has at `production_tab.py:362`-ish — factor out into a shared module-level helper if it makes the batch code cleaner). UNIQUE-collision check per row against the current in-memory production dict **plus** the rows added earlier in the same batch. On any failure: `QMessageBox` with a per-row error listing, leave the dialog open. On full success: insert all, call `parentTab.refresh()`, close.
7. Wire a "Batch Entry" button into `ProductionTab`'s toolbar (the current quick-entry trigger remains; batch is a peer).

**Verification.** Add `production_batch_roundtrip` to `smoke.py`: construct the dialog headlessly (or bypass the UI and exercise the save-commit logic directly on a synthetic row list), seed 3–4 rows spanning two shifts, commit, save the file, reload in a fresh `MainWindow`, assert all records present. Manual test with real data: enter a batch of 10 rows against the team's file, confirm they all appear in the list and survive a save/reload.

**Known unknowns.**
- `ProductionTab` has a second entry-dialog-ish class starting around `production_tab.py:458` (not fully read during planning — it's about an "EmployeeBox + targetTypeBox + targetNameBox + actionBox" flow, so probably the "Quick Entry" alternative already). Worth skimming before starting: if it already does something batch-like, the new work may be incremental rather than greenfield.

---

*This document was prepared with Claude Code (claude-opus-4-6 / claude-sonnet-4-6 / claude-opus-4-7) as a planning artifact; §12 is being maintained as implementation proceeds.*
