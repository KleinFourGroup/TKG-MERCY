# MERCY — Manufacturing and Employee Records: Costing and Yield
## Merge & Implementation Plan

**Date:** 2026-04-16  
**Author:** Matthew Kilgore  
**Status:** Implementation complete — all 13 planned steps landed as of 2026-04-19, plus Step 9.5 (vestigial `Part` attribute cleanup). Step 7 was run as sub-steps (7a correctness → 7b signature → 7c-1 asserts → 7c-2 logging → 7c-3 polish → 7d double-negation → 7e window centering); Step 13 verified the build end-to-end against real legacy ANIKA + BECKY files (see §12.5 findings). Post-release feature backlog requested by the team during Step 13 is tracked in §13.

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

*Last updated 2026-04-22. All 13 planned steps complete, plus the Step 9.5 polish. Step 13 verified the end-to-end path against real legacy ANIKA + BECKY files (see §12.5 findings). Post-release feature backlog from the team's first look at the release is tracked in §13; Steps 14, 15, 16, 17, and 20 have now landed. Each step was committed separately on `main` with a message that names the step.*

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
| 20 | ✅ Done | Merge plan Step 20: remember last DB, prompt to reopen on startup |

### 12.2 Decisions / deviations worth knowing before Step 6+

**Step 2 — `defaults.py` was copied in Step 2, not Step 5.** The plan's file list puts `defaults.py` under Step 5's BECKY-tab work, but `records.py` imports it (for `POINT_VALS`, `TRAINING`, `HOLIDAYS`), so it had to land before Step 3. No downstream impact; just noting so nobody is surprised that it already exists.

**Step 3 — `Database.__init__` has optional BECKY params.** ANIKA's original positional signature is unchanged; BECKY's collections were appended as `| None = None` kwargs that get replaced with empty containers inside `__init__`. This kept existing call sites working through the merge. Step 7's tech-debt pass is the right time to promote these to required positional args (or equivalent) if desired.

**Step 3 — `Database.toWrite` still only tracks ANIKA tables.** The `toWrite` dict on the unified `Database` lists materials / mixtures / packaging / parts only. The employee tables aren't tracked. `file_manager.saveFile` iterates `db.employees`, `db.reviews`, etc. directly, so `toWrite` isn't load-bearing for the BECKY domain — but the asymmetry is a landmine. Step 7's atomic-save rework should either add the employee tables to `toWrite` or retire `toWrite` in favor of something uniform.

**Step 4 — Unified schema is pre-normalization.** The schema created by `file_manager.initFile()` is the *superset* of ANIKA + BECKY + `production`, but the individual table definitions still have the old shape: ANIKA's `mixtures.materials` / `mixtures.weights` / `parts.pad` / `parts.padsPerBox` / `parts.misc` are still base64-encoded compound columns; `parts` still carries `loading` / `unloading` / `inspection` / `greenScrap`; `employees.shift` is still a compound `"shift|fullTime"` string; `reviews.details` and `notes.details` are still base64. This was deliberate — Steps 8–9 do the normalization and will bump `MERCY_DB_VERSION` from 1 → 2 (or beyond). Don't sneak normalization into intermediate steps.

**Step 4 — Legacy DBs get a "light" on-open migration.** Opening a legacy ANIKA DB adds empty BECKY + production tables and stamps `db_version=1`; opening a legacy BECKY DB adds empty ANIKA + production tables (and adds a `notes` table if the BECKY file predates it) and stamps `db_version=1`. Existing data is untouched. This covers §8.3 items 6–8 and §8.4 items 5–7. The heavy parts of those same sections (base64 decode, column drops, `shift` split) are still for Steps 8 and 9 respectively.

**Step 4 — `MERCY_DB_VERSION` baseline is 1.** Constant lives at the top of `file_manager.py`. Steps 8 and 9 should bump it and add an `if dbVersion < N: migrate()` block inside Case 2 ("Already in unified MERCY format") of `initFile()`.

**Step 4 — Two known bugs are preserved on purpose.** `res.executemany(...)` on a consumed cursor (§3.6) and non-atomic `commit()` per table (§3.4) are both still present in the merged `saveFile`. Leave them alone until Step 7 — don't "helpfully" fix them in Step 6.

**Step 5 — Class rename partial.** `main_tab.py` became `employee_overview_tab.py`, but the class inside is still `MainTab` (not `EmployeeOverviewTab` — that name is already taken by a different class in `employees_tab.py`). Six BECKY sub-tabs had their `from main_tab import MainTab` imports rewritten to `from employee_overview_tab import MainTab`. If Step 7 wants fully consistent naming, pick a different class name (e.g. `EmployeeDetailTab`) and update those six imports in lockstep.

**Step 5 — Layout deviations from §7.1.** (a) No Production tab yet — it's Step 11. Current top-level is 4 tabs, not 5. (b) Settings currently has only Cost Parameters — the "App Info" sub-tab from §7.1 was skipped as trivial polish; add whenever convenient. (c) BECKY's `QLabel("TODO")` "Upcoming Actions" tab was dropped as planned (§4).

**Step 6 — `report.py` is a pure union of the two sources.** ANIKA's existing four reports (`globalsReport`, `mixReport`, `salesReport`, `inventoryReport`) are unchanged; BECKY's three helpers (`drawSubtitle`, `drawParagraph`, `drawSignatureLine`) and five employee reports (`employeePointsReport`, `employeePTOReport`, `employeeNotesReport`, `employeeIncidentReport`, `employeeActiveReport`) were appended. The shared infrastructure (`__init__`, margins, page logic, `_wrapText`, `drawTable`) was byte-identical in both sources, so no reconciliation was needed. `from defaults import PTO_ELIGIBILITY` was added; the tech-debt items in the copied BECKY code (`assert(not x == None)`, `# type: ignore` comments) were left intact for Step 7 to sweep along with the rest of the codebase.

**Step 7a — correctness / data-integrity fixes landed.** Four changes:
1. `Database.updateEmployee()` now handles all six employee-indexed collections (`employees`, `reviews`, `training`, `attendance`, `PTO`, `notes`), updates each sub-DB wrapper's `idNum`, **and propagates the new id down to every child record** — necessary because `EmployeeReviewsDB.getTuples()` (and the analogous methods on training / attendance / notes) assert `self.idNum == child.idNum`, and `EmployeePTODB.getTuples()` asserts `self.idNum == child.employee` (naming diverges: PTO range uses `.employee`, the other four use `.idNum`).
2. All 11 buggy `res.executemany(...)` calls in `file_manager.saveFile`'s save-side code were changed to `self.dbFile.executemany(...)`. §3.6 done.
3. `saveFile()` is now atomic: its body was extracted into a new `_saveFileBody()`, and `saveFile()` wraps it in `try / except: self.dbFile.rollback(); raise / self.dbFile.commit()`. All 26 intermediate `commit()` calls were removed from the body. **Deviation from §3.4:** the plan suggested `with self.dbFile:` (the idiomatic context-manager form); I used the explicit try/rollback/commit wrapper instead because it avoided re-indenting 280 lines of body code and kept the diff reviewable. Functionally identical atomicity — a mid-save exception discards everything; clean exit commits everything. `initFile()`'s four commits at indent 16 were left alone (they finalize schema detection/creation at open time, which is separate from save atomicity).
4. `Database.toWrite` was **retired entirely**. A grep confirmed it was declared once in `records.py` and never read anywhere, so the asymmetry noted in Step 3 was resolved by deletion rather than by extending to employee tables.

Verified offscreen: `updateEmployee(42, 99)` rekeys all six dicts, propagates child ids, and subsequent `getTuples()` passes the id-consistency asserts; save/reload roundtrip preserves the renamed tree; poisoning a second employee's `getTuple` mid-save raised as expected and left the on-disk `employees` table showing only the pre-failure state (atomicity confirmed).

**Step 7b — `Database.__init__` signature tightened.** All 7 BECKY-origin params (`employees`, `reviews`, `training`, `attendance`, `PTO`, `notes`, `holidays`) are now required positional args matching ANIKA's style; the `| None = None` typing and the `X if X is not None else {}` / `ObservancesDB()` scaffolding in the body were both removed in favor of straight `self.X = X` assignments. `emptyDB()` in `records.py` was already passing all 13 containers explicitly so it needed no change. Grep for `Database(` across the repo confirmed it's the only caller. Offscreen smoke test (`MainWindow()` + `emptyDB()`) passes.

**Step 7c-1 — `assert` → explicit `raise` landed.** All 237 `assert(COND)` calls across 17 source files were converted to `if <flipped COND>: raise RuntimeError(<description>)`. Done via a single-pass throwaway script (not committed) that recognized seven common shapes — `X is not None`, `not X == None`, `X is None`, `X == None`, `not X in Y`, `X not in Y`, `X in Y` — and fell back to the generic `if not (COND): raise RuntimeError(COND)` for everything else. **Key subtlety:** the script initially mis-flipped compound `A and B` / `A or B` conditions (treating them as atomic and yielding `A and not B`, which is not equivalent to `not (A and B)`). Caught by spot-checking the diff; fixed by detecting top-level `and`/`or` and forcing the generic fallback for those. A few things to know:

- **Default exception is `RuntimeError` everywhere** — no `ValueError` nuance was applied. The distinction between "internal invariant" and "method-boundary input validation" from §3.7 would require per-site judgment; a mechanical sweep picked one type. If a specific call site would benefit from `ValueError` (e.g. `setID` accepting negative input), that's a targeted follow-up, not a 7c-1 rewrite.
- **Messages are the condition text itself.** `assert(self.db is not None)` became `raise RuntimeError('self.db is None')`. Short, generic, always present. Not "self.db must be set for <method>" — we'd need per-site work for that.
- **The 7c-3 `not x == None` sweep now has fewer targets** because the `assert(not x == None)` variants got rewritten to `if x is None:` in this step. The 194-site count from the original survey is pre-7c-1; 7c-3 will see a reduced number.
- **Line-count growth is real** — most asserts went from one line to two, so the diff is +482/-241 even though logic is unchanged. No functional change beyond the exception type flipping from `AssertionError` (disable-able via `-O`) to `RuntimeError`.
- **Verification:** all 23 source files still compile; `grep -E '^\s*assert[\s(]'` returns zero hits in our source; offscreen `MainWindow()` build passes; smoke test confirmed converted `setID(-1)` / `setID(None)` now raise `RuntimeError` with the expected messages.
- **Known double-negation leftovers (Step 7d).** `assert(not isNone)` at two sites (`employees_tab.py:298`, `parts_tab.py:317`) became `if not (not isNone):` because the script's `not X` pattern only caught `not X == None` and `not X in Y` — a plain `not X` fell through to the generic wrapper. Both should become `if isNone:`. Kept as a separate step since they're cosmetic and isolated.

**Step 7c-2 — `print()` → `logging` landed.** All 136 source-file print calls were reclassified:

- **`file_manager.py` (120 prints → 118 logging.info/error via script + 2 logging.info manual).** Default was `logging.info`; any print whose content began with `Error`/`error` within the first ~40 chars was routed to `logging.error` instead. Two multi-line `print(...)` calls (lines 138/151, `Detected legacy ANIKA/BECKY format` messages that spanned a string-continuation) didn't match the single-line regex and were converted with targeted Edits.
- **`records.py` (4 prints → 3 logging.info + 1 deletion).** The debug print in `EmployeePointsDB.currentPoints` (`"{diff} days from {curr} to {next}, deducting {credit} points from a total of {sumPt}!"`) was **deleted** per §3.8. The three `Database.materialCosts()` / `mixtureCosts()` / `partCosts()` diagnostic dumpers were converted to `logging.info`. The big multi-line `partCosts` format string print was converted with a targeted Edit (didn't match the single-line regex).
- **Tab files — 5 files, 14 prints → `logging.debug`.** `parts_tab.py` (5), `employees_tab.py` (2), `mixtures_tab.py` (2), `materials_tab.py` (2), `packaging_tab.py` (1). These are all dev-leftover diagnostic prints (`print(part)`, `print("Enable")`, `print(self.calendar.selectedDate())` etc.); routing them to `debug` silences them at the default `INFO` level but preserves them for anyone who flips the level.
- **`main.py`.** Added `import logging` and `logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")` near startup. Simple two-field format — log level + message — since the save chatter already includes its own context.

**Subtlety that cost time — and a script bug to know about:** the script's `add_logging_import()` helper that injected `import logging` after existing imports treated `from records import (` at `file_manager.py:5` as a single import line and inserted `import logging` *between* the opening paren and the import body, producing a `SyntaxError`. Caught by the compile check before commit; fixed by moving the import up to be a peer of `import sqlite3` / `import datetime`. If this throwaway pattern is ever reused, the helper needs to detect open-paren continuations and insert after the matching close-paren. For this step it wasn't worth generalizing — fixed manually and moved on.

**Verification:** all 23 source files compile; `grep -E '^\s*print\('` returns zero hits in MERCY source (only deps remain); offscreen `MainWindow()` build passes; end-to-end save of an `emptyDB()` produced the expected `INFO Saving globals to ...` / `INFO  * Saving gasCost = 0.0523` / etc. chatter.

**Step 7c-3 — mechanical + polish sweep landed.** Four items:

1. **`not x == None` → `x is not None` (146 conversions across 18 files).** Regex-based script replace with `not\s+((?:\w+)(?:\.\w+|\[[^\]]*\]|\([^)]*\))*)\s*==\s*None` → `\1 is not None`. The extended LHS grammar handles attribute chains, subscripts (`db.materials[key]`), and empty method calls (`mixture.getCost()`) — the narrower attribute-only regex from the original pick-up notes missed 5 method-call/subscript sites. Compound conditions where `not` applies to a parenthesized expression (`if not (idNum == None or idNum >= 0):` at `records.py:698`) are correctly left alone — the LHS starts with `(`, not `\w`. One awkward residual: `if not ((self.filePath is not None) and (self.dbFile is not None)):` at `file_manager.py:176` / `:447`, outputs of 7c-1's compound-fallback. Correct but DeMorgan-able; left for a future stylistic pass since it's still mechanically correct.

2. **Window-list leak fixed via Qt parent-retention + `WA_DeleteOnClose`.** 21 window classes across 12 tab files (`MaterialsDetailsWindow`, `MaterialsEditWindow`, `MixturesDetailsWindow`, `MixturesEditWindow`, `PartsDetailsWindow`, `PartsMarginsWindow`, `PartsEditWindow`, `PackagingEditWindow`, `InventoryDateEditWindow`, `MaterialInventoryEditWindow`, `PartInventoryEditWindow`, `EmployeeEditWindow`, `YearSelectWindow`, `ObservanceSelectWindow`, `HolidayEditWindow`, `NotesEditWindow`, `PointsEditWindow`, `PTOCarryWindow`, `PTOEditWindow`, `ReviewsEditWindow`, `TrainingEditWindow`). Each window class now calls `super().__init__(mainApp, Qt.WindowType.Window)` and `self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)`. Tab classes drop `self.windows = []` init and the append wrapping (36 active call sites unwrapped; 6 commented-out append lines removed). **Key subtlety verified offscreen:** PySide6 parentless widgets get Python-GC'd once the Python reference drops — `WA_DeleteOnClose` alone does NOT keep them alive (I confirmed this with a bespoke `QWidget.__del__` probe before touching any source). Parenting to `mainApp` (which is itself a long-lived `QWidget`) uses Qt's parent-child tree for retention; the `Qt.WindowType.Window` flag makes the widget render as a top-level window even though it has a parent. Open-without-retention → GC → widget still alive → `.close()` → widget destroyed via `WA_DeleteOnClose` was verified end-to-end on `MaterialsDetailsWindow`. `Qt` import added to `PySide6.QtCore` in 10 files that didn't already have it.

3. **`LBS_PER_TON = 2000` constant** added at the top of `records.py`, referenced in `Material.getCostPerLb()`. Original trailing `#2200?` comment (stale author TODO) dropped; the constant's `# short ton` comment captures the intent.

4. **`requirements.txt`** at repo root: `PySide6` and `reportlab`, unpinned.

**Known follow-up (out of scope for 7c-3):** bare `x == None` / `x != None` → `x is None` / `x is not None` was not in the plan's scope but the sweep highlights it — e.g. `records.py:58` `if self.price == None or self.freight == None:`. Small follow-up if desired; otherwise harmless.

**Verification:** all 23 source files compile; `grep -rE 'not\s+.*==\s*None' *.py` returns one residual (the intentional compound at `records.py:698`); offscreen `MainWindow()` build passes; offscreen open-and-close test on a real window class confirmed parent-retention (survives GC while open) and close-destruction (`WA_DeleteOnClose` fires) both work as intended.

**Step 7d — double-negation cleanup landed.** Two sites (`employees_tab.py:299` and `parts_tab.py:320`) went from `if not (not isNone): raise RuntimeError('not isNone')` to `if isNone: raise RuntimeError('isNone')`. Trivial. `grep -rn 'if not (not' *.py` now returns zero hits in MERCY source.

**Step 7e — window centering restored.** Added `centerOnScreen(widget)` to `utils.py` — sizes the widget (`adjustSize()`), reads `widget.screen().availableGeometry()`, and `move()`s the widget so its size-hint rect is centered on the current screen. Called immediately before `self.show()` in all 21 top-level child window classes touched by 7c-3 (see §12.2 Step 7c-3 item 2 for the full list). `from utils import ... , centerOnScreen` was added to 12 tab files. Offscreen smoke test confirmed `centerOnScreen` positions a parented child widget at reasonable coordinates (e.g. `(190, 382)` on a simulated primary screen). Visual centering was manually verified on the user's machine before commit.

- Chose **center on screen** (not center on parent) because it matches the pre-7c-3 user experience: BECKY/ANIKA's sub-windows were parentless and got their default top-level placement from the WM, which on Windows defaults to near screen-center for freshly-created top-level windows. Screen-centering restores that feel. The parent-center alternative was noted in §12.6 but would have been a UX deviation.
- `adjustSize()` before reading `size()` is important — at `__init__` time the widget hasn't been laid out yet, so `size()` is the default `(640, 480)` or whatever and would mis-center. `adjustSize()` applies the layout's size hint without requiring a `show()` + re-center round-trip.
- `screen is None` early-return guard handles the edge case where the widget has no screen (shouldn't happen after parenting to `mainApp`, but free insurance).

**Step 8 — ANIKA schema migration landed (v1 → v2).** `MERCY_DB_VERSION` bumped from 1 to 2. Four groups of changes:

1. **Schema creation updated to v2 shape.** `_createAnikaTables()` now creates the normalized schema directly: `mixtures(name PRIMARY KEY)` (no more `materials`/`weights`), `parts(name, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)` — 12 cols, the 7 dead/compound cols dropped — plus new child tables `mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))`, `part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))`, `part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))`. Brand-new MERCY DBs (Case 1) are born at v2. Case 4 (legacy BECKY, no ANIKA data) also creates the v2 shape on the ANIKA side — no migration needed there since there's no data to rewrite.

2. **Migration function `_migrateAnikaV1ToV2()`.** Decodes the base64-encoded compound columns with `utils.stringToList(...)`, inserts rows into the new child tables (preserving list order via `sort_order`), then recreates `mixtures` and `parts` without the dropped columns via the create-new / insert-named-cols / drop-old / rename-new pattern. Wired into `initFile()`: Case 2 (unified MERCY, `dbVersion < 2`) runs the migration directly; Case 3 (legacy ANIKA) first adds empty BECKY/production tables, stamps v1, then runs the v1→v2 migration — net result is any legacy ANIKA file lands on v2 in one open. Length-mismatch guards raise on malformed input.

3. **Backup strategy: `.db.bak-YYYY-MM-DD-HHMMSS` sibling file, written before the destructive DDL in the migration function.** **Deviation from §8.2:** originally I tried `PRAGMA wal_checkpoint(TRUNCATE)` before the copy so the backup would include WAL'd pages. That raises `OperationalError: database table is locked` whenever a write transaction is already open (which it always is by the time migration starts — the Case 3 path has already created empty BECKY tables and stamped `db_version=1`). Dropped the checkpoint: uncommitted writes live in the WAL, not the main `.db`, so a plain `shutil.copy2` of the main file captures exactly the last-committed state. This turns out to be **ideal for rollback**: if migration fails and the connection closes without commit, the on-disk file reverts to match the backup. Explicit comment on `_backupDbFile` documents this. No confirmation dialog on backup creation — the `§8.2` mention of a confirm dialog is GUI work for a later step.

4. **Save/load paths updated for the v2 shape.** `Mixture.getTuple()`/`fromTuple()` now handle only `(name,)`; `Mixture.getComponentTuples()` returns `[(mixture, material, weight, sort_order), ...]` for `mixture_components`. `Part.getTuple()`/`fromTuple()` drop to 12 cols (the dropped attrs `loading`/`unloading`/`inspection`/`greenScrap` are set to `None` on load — kept as vestigial instance attributes so `setProduction()` and `__str__` still work, but they no longer round-trip through the DB; see §12.3 for follow-up). `Part.getPadTuples()` / `getMiscTuples()` for the child tables. `file_manager.saveFile`: each child table uses a **per-parent DELETE-then-reinsert** strategy (wipe a mixture's components, insert the current list) plus a final orphan sweep for rows whose parent is no longer in memory. `file_manager.loadFile`: load parents first, then populate children via `ORDER BY parent, sort_order`. `listToString`/`stringToList` imports were removed from `records.py` (no longer used); `stringToB64`/`stringFromB64` remain for Step 9's BECKY details decode.

**Verification.** `smoke.py` gained a `legacy_anika_migration` check that hand-crafts a v1 ANIKA DB with 2 mixtures (one 3-material, one 1-material) and 3 parts (one with 2 pads, one with 2 misc, one with 1 pad + 1 misc), opens it with MERCY, and asserts: `db_version=2`, `mixtures` has just the `name` column, `parts` has the 12 expected cols, each child table has the expected rows in the expected order, the in-memory `Mixture.materials`/`weights` and `Part.pad`/`padsPerBox`/`misc` reconstruct correctly, a sibling `.db.bak-*` file was written, and a full save/reload roundtrip preserves the data. All three smoke checks (`compile_all`, `empty_roundtrip`, `legacy_anika_migration`) pass. Case 1 (brand-new), Case 2 (v1 MERCY → v2), and Case 4 (legacy BECKY) were also spot-checked via throwaway scripts and verified manually in the GUI on the user's machine before commit.

**Step 9 — BECKY schema migration landed (v2 → v3).** `MERCY_DB_VERSION` bumped from 2 to 3. Four groups of changes:

1. **Schema creation updated to v3 shape.** `_createBeckyTables()` now creates the normalized schema directly: `employees(idNum, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)` — 15 cols with the compound `shift` split into two separate int columns; `reviews.details` and `notes.details` declared as `TEXT`. Brand-new MERCY DBs (Case 1) and Case 3's empty BECKY side are born at v3 shape with no migration needed.

2. **Migration function `_migrateBeckyV2ToV3()`.** Three pieces of work: (a) recreate-and-copy on `employees` — `SELECT shift` from the old table, split the `"{shift}|{fullTime}"` string on `|`, `INSERT` into a new 15-col table; (b) decode base64 `reviews.details` / `notes.details` via in-place `UPDATE` statements (no schema change — just content); (c) orphan sweep on `training` / `attendance` / `PTO` for rows whose `idNum` doesn't reference a valid employee (§3.3 — pre-7a `updateEmployee` could leave these dangling). Reviews and notes are not swept because the pre-7a bug already handled those dicts; only training/attendance/PTO were skipped. Wired into `initFile()`:
   - **Case 2 (unified MERCY)** — `if dbVersion < 3: _migrateBeckyV2ToV3()`, chained *after* `if dbVersion < 2: _migrateAnikaV1ToV2()`. Old v1 MERCY files get both migrations in a single open.
   - **Case 3 (legacy ANIKA)** — BECKY side is empty (tables created fresh at v3 shape), so after the ANIKA v1→v2 migration, just `_setDbVersion(MERCY_DB_VERSION)` — no BECKY migration call. Net: one open takes a legacy ANIKA file all the way to v3.
   - **Case 4 (legacy BECKY)** — `_setDbVersion(2)` first (atomicity marker, same pattern as Step 8's v1 stamp), then `_migrateBeckyV2ToV3()` which bumps to v3 at its end. The outer `try/except` closes without commit on failure, leaving the file untouched.

3. **Model + save path updated.** `Employee.getTuple()` now emits a 15-tuple with `shift` and `fullTime` as separate fields (instead of `f"{shift}|{fullTime}"`); `Employee.fromTuple` reads them as two cols and the `isinstance(row[5], int)` / `.split('|')` compatibility branch was removed — by the time `fromTuple` is called, migration has normalized. `EmployeeReview.getTuple`/`fromTuple` and `EmployeeNote.getTuple`/`fromTuple` emit/read `details` as plain strings (no more `stringToB64`/`stringFromB64` wrapping). `saveFile`'s employees INSERT placeholder count bumped 14 → 15. The `from utils import stringToB64, stringFromB64` import at `records.py:3` was dropped.

4. **Shift-type tolerance in migration.** The split-shift code accepts either a compound `"{shift}|{fullTime}"` string (the post-Step-4 BECKY norm) or a bare integer (hypothetical pre-compound legacy format — defaults `fullTime=1`). Anything else raises `RuntimeError` naming the offending employee. In practice only the compound-string form has been observed.

**Verification.** `smoke.py` gained a `legacy_becky_migration` check that hand-crafts a v2 BECKY-shape DB with 3 employees (full-time / part-time / full-time), 2 reviews with b64-wrapped details (one multi-line), 2 notes, and deliberately-orphaned training/attendance/PTO rows (one per table) alongside valid rows. Opens with MERCY (Case 4) and asserts: `db_version=3`, `employees` has 15 cols with `shift INTEGER` + `fullTime INTEGER` split, parsed shift/fullTime values correct per employee, `reviews.details`/`notes.details` are plain text (including newlines preserved), orphan rows removed from all three tables while valid rows are preserved, backup sibling file exists, in-memory `Employee.shift`/`fullTime` reconstruct as `int`/`bool` (not compound), and save/reload roundtrip preserves the migrated data. All four smoke checks (`compile_all`, `empty_roundtrip`, `legacy_anika_migration`, `legacy_becky_migration`) pass. Case 2 (hand-crafted v1 unified MERCY → v3 in one open, chained v1→v2→v3 migrations) was also spot-checked via a throwaway script and confirmed both the ANIKA compound decode and the BECKY shift split in the same open.

**Deviations from plan.** None material. §12.5's aspirational note about removing all four base64 utilities once Step 9 lands turned out to be too ambitious: `_migrateAnikaV1ToV2` still depends on `stringToList`, `_migrateBeckyV2ToV3` depends on `stringFromB64`, and those depend in turn on `stringToB64`/`listToString`. All four remain in `utils.py` indefinitely for legacy-file support. `records.py` and the rest of the main app no longer import them.

**Step 9.5 — vestigial `Part` attributes dropped.** Cleanup follow-up flagged back in §12.3 after Step 8. Three groups of edits:

1. **`records.py` `Part.__init__`.** Removed the four attribute declarations (`self.loading`, `self.unloading`, `self.inspection`, `self.greenScrap`). The `Globals` class's identically-named attributes (`Globals.loading`, `Globals.inspection`, `Globals.greenScrap`) are unrelated — those are the *live* cost-calc inputs and remain untouched.
2. **`records.py` `Part.setProduction` / `Part.fromTuple` / `Part.__str__`.** `setProduction` lost its four dead params (signature went from 10 args to 6: `weight, mix, pressing, turning, fireScrap, price`). `fromTuple` no longer passes four `None`s through to `setProduction` — just the live values. `__str__` format string lost the four `f"UNUSED: {...}"` tokens and their placeholders; the green scrap `%` suffix is gone too since only the fire scrap half of the `{}% + {}%` pair survived.
3. **`parts_tab.py` `PartsEditWindow.readData`.** Dropped the four `X = None` stub locals and the corresponding positional args from the `self.part.setProduction(...)` call.

**Not a schema change.** No `MERCY_DB_VERSION` bump. The on-disk shape already didn't carry these columns (Step 8 handled that). This was purely Python-side cleanup.

**Verification.** All four smoke checks still pass. A `Part.setProduction` call from `Part.fromTuple` initially crashed the `legacy_anika_migration` smoke check with `TypeError: takes 7 positional arguments but 11 were given` — easy fix (update `fromTuple` to match the new signature), caught immediately by the existing test. No other sites needed changes — grep for `part.(loading|unloading|inspection|greenScrap)` across the repo returned zero hits in source.

**Step 10 — DB merge / import landed.** New "Import Database…" button + flow that reads a second legacy or unified `.db` and merges its non-overlapping contents into the currently-open in-memory DB. Four groups of changes:

1. **`file_manager.py` refactor.** Extracted `_detectDbFormat(tables) -> "empty" | "mercy" | "legacy_anika" | "legacy_becky" | "unknown"` from the chained `if`s inside `initFile`; `initFile` now calls it. Extracted `_loadIntoDb(db)` from `loadFile` so any `Database` (not just `self.mainApp.db`) can be populated; `loadFile` became a 3-line wrapper that builds an `emptyDB()` and calls `_loadIntoDb`. Behavior-preserving — all four pre-existing smoke checks still pass.

2. **`FileManager.importOtherDb(srcPath) -> (otherDb, fmt)`.** Copies the source file to a `tempfile.mkstemp(suffix='.db')` path (so any migration writes land on the copy — the user's second `.db` is never mutated per §12.5(c)), instantiates a **second** `FileManager(self.mainApp)` for the temp path, runs `setFile()` (which chains through `initFile` → full v1/v2/v3 migration as needed), builds a fresh `emptyDB()`, and populates it via `tmpFM._loadIntoDb(otherDb)`. Closes the temp connection, removes the temp `.db` + its WAL/SHM sidecars + any `.bak-*` files the migration produced. Returns `(None, "unknown")` on unrecognized format, `(None, "error")` on copy failure, `(otherDb, "ok")` on success. Module-level `_cleanupTempDb(tmpPath)` helper next to the class encapsulates the sweep (best-effort; logs but doesn't raise on `OSError` since Windows sometimes holds handles briefly).

3. **`records.py` — `Database.planMergeFrom(other)` + `Database.mergeFrom(other)`.** Split deliberately so the UI can show a summary before mutating. `planMergeFrom` returns `{"incoming": {...}, "collisions": {...}}` with keys materials / mixtures / packaging / parts / materialInventory / partInventory / employees / holidays / observances. Inventory collisions are checked at the (date, name) grain; observances at (year, holiday, shift); employees at idNum; everything else at name. `mergeFrom` calls `planMergeFrom` internally and **raises `RuntimeError` on any collision** — no silent overwrites. Successful merge reparents each product object's `.db` to the receiving DB, copies all five per-employee sub-DBs for each imported idNum (reviews / training / attendance / PTO / notes), and unions `holidays.defaults` + `holidays.observances`. `globals` and `production` are intentionally skipped per §8.5 (open-file's ANIKA cost params win; production is always empty in legacy files).

4. **`app.py` — new "Import Database…" button.** Added as a 4th peer next to Open / Save / Save As (plan §12.5 said "File → menu action" but the app uses buttons, not menus; stayed consistent with existing UI). Handler flow: picker → `importOtherDb` → on `fmt == "unknown"`/`"error"` show warning + return; otherwise call `planMergeFrom` → if any collision, show a `QMessageBox.warning` listing up to the first 3 entries per colliding type and abort without mutation; otherwise show a `QMessageBox.question` summary ("importing N materials, M employees, …; source file not modified; click Save to persist") and call `mergeFrom` + `_refreshAllTabs()` on confirm. No auto-save — user must explicitly Save (or Save As) per §12.5(d).

**Scope deviations from §12.5.**
- **Button, not menu** (noted above). The app has no menu bar.
- **"Single transaction" framing is in-memory.** §12.5 item 7 suggested "inside a single transaction; any failure rolls back both DBs." The actual implementation mutates only the in-memory `Database` dicts (no writes to the first file on disk until the user clicks Save). Collision detection runs before any mutation, so a partial merge can't happen. Functionally equivalent to a transaction but without the sqlite plumbing — the current-file `saveFile` already has atomic write semantics from Step 7a, so the eventual disk write is already all-or-nothing.
- **Backup of the source file is not run.** §12.5(b) suggested "the second file's `_backupDbFile` should still run before its in-memory migration." Since the migration now runs against a temp copy (not the source), there's nothing for a backup to protect — the source file is never opened for writing. The temp copy's `_backupDbFile` still runs as a side effect of Case 3/4 `initFile` paths, but its `.bak-*` sibling is cleaned up alongside the temp copy.

**Verification.** New `legacy_merge` smoke check seeds a legacy ANIKA + a legacy BECKY file, opens the ANIKA one with MERCY (triggers Case 3 + v1→v3 migration), hashes the BECKY file, runs `importOtherDb` + `mergeFrom`, and asserts: all ANIKA entities still present; all BECKY entities imported with correct shift/fullTime split and decoded review/note details; BECKY source file is byte-identical (sha256 before == after); save/reload roundtrip on the ANIKA file preserves the merged contents. All five smoke checks (`compile_all`, `empty_roundtrip`, `legacy_anika_migration`, `legacy_becky_migration`, `legacy_merge`) pass. Manually verified in the GUI: happy path on a real legacy ANIKA + legacy BECKY pair, import-a-non-DB-file warning path, and double-import collision-abort path.

**Step 11 — production tracking UI landed.** First net-new-functionality step; everything prior was merge/migrate/cleanup. Adds the shift-level production log end-to-end (schema → records → file_manager → tab → app wiring → smoke). Five groups of changes:

1. **Team clarification baked into the design (§6.3 rewrite).** At kickoff the team narrowed the original "any action × any target" model: `Batching` is always against a mix (unit: **drops**), `Pressing` and `Finishing` are always against a part (unit: **parts**). Encoded as two lookup dicts in `defaults.py` — `PRODUCTION_ACTION_TARGET: dict[str, str]` (action → `"mix"`/`"part"`) and `PRODUCTION_TARGET_UNIT: dict[str, str]` (target type → display unit). `ProductionRecord.setRecord(action, targetName, …)` derives `targetType` from the action via the first dict; the second dict drives the UI's unit label. `PRODUCTION_ACTIONS` lives in `defaults.py` per §6.2 / §10-1.

2. **`records.py` — `ProductionRecord` class + `Database.production` container.** Fields: `employeeId`, `date` (`datetime.date`), `shift` (int), `targetType` (`"part"`/`"mix"`, derived — not set directly), `targetName`, `action`, `quantity` (float, unit per §6.3), `scrapQuantity` (float, defaults 0 per §10-2). Methods mirror the other record classes: `setRecord`, `key()` → the 6-tuple UNIQUE composite, `getTuple`/`fromTuple`, `__str__`. `fromTuple` validates the stored `targetType` matches `PRODUCTION_ACTION_TARGET[action]` and raises if not (guards against hand-edited DBs). `Database.__init__` now takes a required `production: dict[tuple, ProductionRecord]` as the final positional arg; `emptyDB()` updated to pass `{}`.

3. **`file_manager.py` — save + load blocks.** Added `ProductionRecord` to the records import. Save block uses a named-column `INSERT OR REPLACE INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity) VALUES (…)` — the AUTOINCREMENT `id` is deliberately omitted so sqlite assigns/keeps it. The delete-sweep converts each on-disk row's date string back to `datetime.date` and checks membership against `db.production`'s tuple keys. Load block selects all eight real columns (ignores `id`), builds a `ProductionRecord`, and stores it at `db.production[rec.key()]`.

4. **`production_tab.py` (new).** Single top-level tab (not nested — §7.1's "Daily Entry | Reports" split is deferred: reports are Step 12, so Daily Entry doesn't need its own sub-tab yet). Filter bar across the top: employee dropdown (with `(All employees)` default) + `QDateEdit` from/to range (default last 30 days). Table below with columns `#` (synthetic row-id, used as the DBTable selection key), Employee, Date, Shift, Action, Target, Quantity, Unit, Scrap; composite 6-tuple keys live in a parallel `self._keyByRowId: dict[str, tuple]` rebuilt on every `genTableData()`. `ProductionEditWindow` follows the 21-window retention pattern (parent = `mainApp`, `Qt.WA_DeleteOnClose`, `centerOnScreen(self)` before `show()`). Action dropdown `currentTextChanged` cascade clears + repopulates the target dropdown (from `db.mixtures` or `db.parts` depending on `PRODUCTION_ACTION_TARGET[action]`) and updates the `Unit:` label. UNIQUE-key collision is caught pre-mutation with a readable `QMessageBox` rather than letting `INSERT OR REPLACE` silently clobber a neighbor.

5. **`app.py` wiring + smoke.** New `Production` top-level tab between `Employees` and `Inventory` per §7.1 (layout now 5 tabs: Products | Employees | Production | Inventory | Settings). `self.productionTab.refresh()` added to `_refreshAllTabs()`. New `production_roundtrip` smoke check seeds three records (one Batching→mix with default scrap, one Pressing→part with explicit scrap=3, one Finishing→part), saves, reloads, verifies all three round-trip with correct `targetType`/`targetName`/`quantity`/`scrapQuantity`, then deletes one and re-roundtrips to confirm the save-side sweep removes the absent key.

**Scope deviations from §12.5.**
- **No nested `Daily Entry | Reports` sub-tabs.** Step 12 (reports) will add the Reports sub-tab; introducing a `QTabWidget` with a single child now would be pure scaffolding. When Step 12 lands, wrap the current `ProductionTab` as the `Daily Entry` child inside a new outer `QTabWidget`.
- **Selection identity via synthetic row-id.** `DBTable.onSelect` reports only column-0 values. Since production records have a 6-tuple composite key, column 0 is a `1..N` row-id (rebuilt per refresh) and `_keyByRowId` maps it back. Cleaner than overloading a composite-string as the visible first column.
- **Edit/delete button enablement.** Initial draft only toggled button state in `__init__`/`refresh`; user-side manual test caught that selection changes didn't re-evaluate. Fix: `setSelection` calls `_setButtonsEnabled()` at the end. Worth remembering for any future DBTable-backed tab — the selection callback is where button state should be kept coherent.

**Verification.** New `production_roundtrip` smoke check (above) plus all five prior checks pass (`compile_all`, `empty_roundtrip`, `legacy_anika_migration`, `legacy_becky_migration`, `legacy_merge`, `production_roundtrip`). Manually verified in the real GUI: create/edit/delete a record of each of the three actions; action-change correctly cascades the target dropdown and unit label; UNIQUE-conflict path shows a readable error; filter by employee and by date range both narrow the table as expected; buttons enable/disable correctly on selection change and when the DB lacks employees-or-products.

**Step 12 — production reports landed.** Team had no concrete asks beyond "per part/mix, per action, per employee, with a date range" so I added all three plus a Summary as a useful fourth. Four groups of changes:

1. **`report.py` — four new `PDFReport` methods + two private helpers.** `productionSummaryReport(start, end)` is an employee-by-action grid (rows = employees with any production in range; cols = the 3 actions with units in the header — `Batching (drops)` / `Pressing (parts)` / `Finishing (parts)`); cells are `"<qty>"` or `"<qty> (scrap: <s>)"` if scrap > 0, or `"—"` if no production for that pair; totals row at the bottom. `productionActionReport(action, start, end)` filters to one action, sorted by `(date, shift, target, employee)`, with single grand-total row. `productionTargetReport(targetType, targetName, start, end)` filters to one part or mix, sorted by `(date, shift, action, employee)`, with **per-action** subtotal rows at the bottom (a part can show up under both Pressing and Finishing — separate totals are more useful than one combined). `productionEmployeeReport(employeeId, start, end)` filters to one employee, sorted by `(date, shift, action, target)`, with per-action subtotals (units shown in the row so the mixed-action totals don't get confusing). All four follow the `salesReport` pagination loop pattern (drawTable returns drawn-count, slice + nextPage, repeat). `_filterProduction(start, end, action=, employeeId=, targetType=, targetName=)` applies all combinable filters in one pass; `_employeeName(id)` returns `"LAST First (id)"` or `"(missing #id)"` for orphans (matches the production tab's existing fallback). Both helpers are private and used 4× across the new reports.

2. **`production_tab.py` — single "Generate Report" button + `ProductionReportWindow`.** Button added as a 4th peer next to New / Edit / Delete (always enabled — the empty-range path renders cleanly rather than throwing). The window is modeled on `ProductionEditWindow` (parent = `mainApp`, `Qt.WA_DeleteOnClose`, `centerOnScreen` before `show`). It has a `Report type` dropdown (the four report names), a from/to date range pre-filled from the tab's filter, plus four conditional input rows that show/hide based on type via `setVisible`: `Action` (only for "Per Action"), `Target type + Target` cascade (only for "Per Target", with `mix → mixtures`/`part → parts` repopulating the name dropdown), and `Employee` (only for "Per Employee", pre-selected from the tab's filter if set). Generate runs pre-validation (start ≤ end; required dropdown for the chosen type non-empty), opens `QFileDialog.getSaveFileName` with a sensible default name (`production-summary.pdf` / `production-pressing.pdf` / `production-<targetName>.pdf` / `production-employee-<id>.pdf`), instantiates `PDFReport`, calls the matching method, and `startfile`s the result.

3. **Empty-range handling.** Each report renders a one-pager with title + subtitle + section + `"No production recorded in this range."` rather than raising or skipping, per §12.5's gotcha note. Verified explicitly in the new smoke check via a 2030 date window.

4. **Smoke check.** `production_report` seeds one employee + three records (one per action — Batching→MixA / Pressing→PartA with scrap=3 / Finishing→PartB) and generates each of the four reports plus the empty-range case. Asserts each PDF file exists and is non-empty; doesn't parse content (per §12.4 convention — generation succeeding is the bar). Uses `Employee()` directly rather than the BECKY tab plumbing — the report code only reads `lastName`/`firstName`/`idNum` so a minimal employee fixture suffices.

**Scope deviations from §12.5.**
- **Single dialog instead of context-aware button.** §12.5 sketched "no employee selected → offers Summary or Target; employee selected → Employee or Summary". I went with one always-visible "Generate Report" button that opens a dialog where the user picks the report type explicitly, with the date range and employee pre-filled from the tab's filter. Cleaner than two enablement codepaths and avoids the question of what to do for the Per Action / Per Target reports under the original sketch (the tab has no action/target filter to read from).
- **No `Daily Entry | Reports` sub-tab nesting.** §12.5 item 3 (and §12.2 Step 11) flagged this as optional; the report surface is a single button so wrapping in a `QTabWidget` would be pure scaffolding. Skipped.
- **Summary report added.** §12.5's three-method sketch didn't include the cross-employee×action grid. Added because the team's "we don't really know what we want yet" framing benefits from a high-level dashboard alongside the deep-dive reports — and it costs almost nothing on top of the existing helpers. Easy to drop later if they don't use it.

**Verification.** New `production_report` smoke check plus all six prior checks pass (`compile_all`, `empty_roundtrip`, `legacy_anika_migration`, `legacy_becky_migration`, `legacy_merge`, `production_roundtrip`, `production_report`). Offscreen sanity check confirms the dialog constructs cleanly, `typeBox` has 4 entries, `actionBox` has 3, and cycling the type dropdown through all four values triggers `_onTypeChanged` without exceptions. Manually verified by Matthew in the real GUI on a real DB before commit.

**Step 14 — reports skip save dialog, open via temp file.** First post-release feature item from §13. Three pieces:

1. **`utils.tempReportPath(prefix)` (new).** Uses `tempfile.mkstemp(suffix=".pdf", prefix=f"{safe}-")`, then `os.close(fd)` and returns the path. The `safe` is the prefix with anything outside `[A-Za-z0-9._-]` replaced by `_`, so each call site can pass a natural human-readable string (`"active-employees"`, `f"employee-{idNum}-notes"`, `f"mixture-{name}"`, `f"{date.isoformat()}-inventory"`) without thinking about path safety. **Deviation from §13.1's sketch:** the sketch suggested `NamedTemporaryFile(... delete=False).name`; switched to `mkstemp` because `NamedTemporaryFile` returns a file object that on Windows holds the OS handle until garbage collection — `mkstemp` returns the fd directly so we can close it immediately and the path is free for `reportlab` to write to.

2. **10 call sites converted across 9 tab files.** Every `QFileDialog.getSaveFileName(...) → if path: → generate → startfile` block became `path = tempReportPath(<prefix>); generate; startfile(path)`. Files: `employees_tab` (active-employee report), `globals_tab`, `inventory_tab`, `mixtures_tab`, `notes_tab` (notes + incident — two sites), `parts_tab` (sales), `points_tab` (attendance), `pto_tab`, `production_tab`. `production_tab.py`'s pre-existing `_defaultName(...)` helper was renamed `_defaultPrefix(...)` and stripped of its `.pdf` suffix; the explicit `targetName.replace("/", "_").replace("\\", "_")` sanitization went away too since `tempReportPath` now centralizes that.

3. **Stale `QFileDialog` and `os` imports swept.** Each affected tab's only `os` use was the `os.path.expanduser("~")` argument to the dialog, so `import os` came out alongside `QFileDialog` in `employees_tab`, `globals_tab`, `mixtures_tab`, `notes_tab`, `points_tab`, `pto_tab`, `parts_tab`, `production_tab`. `inventory_tab.py`'s `import os, datetime` collapsed to `import datetime`; `parts_tab.py`'s `import os, math` collapsed to `import math`. `app.py` still uses `QFileDialog` (open / save / import flows) so its imports were left alone.

**Verification.** All 7 prior smoke checks pass unchanged (`compile_all`, `empty_roundtrip`, `legacy_anika_migration`, `legacy_becky_migration`, `legacy_merge`, `production_roundtrip`, `production_report`); no new smoke check was added because the persistence layer is untouched and §13.1's verification plan explicitly said the existing checks suffice. `grep` for `QFileDialog` / `os.path.expanduser` / `reportFile` returns zero hits in the touched tab files. Manually spot-checked by Matthew in the real GUI before commit — report buttons open the PDF in the OS viewer immediately with no save dialog.

**Step 15 — production tab refresh when an employee is deleted.** Second post-release feature item from §13. One-line fix plus a regression check:

1. **`employees_tab.py::deleteSelection` adds a fourth tab refresh.** After the existing `overviewTab.refresh()` / `activeEmployeesTab.refreshTable()` / `inactiveEmployeesTab.refreshTable()` calls on the delete-confirmed branch, I appended `self.mainApp.productionTab.refresh()`. `MainWindow` already holds `productionTab` as a direct attribute (set at `app.py:66` and referenced from `app.py:133`), so no plumbing was needed. `ProductionTab.refresh` → `_populateEmployeeFilter` already self-corrects when the previously-selected employee is gone (the for/else at `production_tab.py:113–119` falls back to "(All employees)"), so the fix is a single line at the call-site level.

2. **Orphans are kept, not cascaded.** §13.2 was explicit: "deleted employees disappear from selectable pickers, but existing production records referencing them are kept." `records.py::delEmployee` already declines to touch `db.production`; the orphan-display path at `production_tab.py:158` ("`(missing #id)`") handles the render. Both confirmed by the new smoke check — the record's `employeeId` is not mutated post-delete.

3. **New smoke check `production_refresh_on_delete` (8th).** Mirrors the `production_report` fixture style (one `Employee` plus all shadow collections seeded via `addEmployeeReviews` / `addEmployeeTraining` / `addEmployeePoints` / `addEmployeePTO` / `addEmployeeNotes`, because `delEmployee` `raise`s if any of them is absent). Seeds one `ProductionRecord` against the employee, calls `db.delEmployee(emp.idNum)`, then asserts (a) the record still exists with `employeeId` unchanged, (b) `productionTab.refresh()` doesn't raise when iterating over an orphan, and (c) the employee's `idNum` is no longer in `employeeFilter`'s `itemData` after refresh. Gotcha surfaced while writing: the fixture style from `production_report` (bare `db.employees[id] = emp`) is not enough for Step 15's test because it doesn't populate the shadow collections that `delEmployee` asserts on — use the full 6-call sequence from `employees_tab.py::_submit` instead.

**Verification.** All 8 smoke checks pass (the 7 prior plus the new `production_refresh_on_delete`). Nothing else was touched — Step 15 deliberately does not sweep for other cross-tab staleness (per §13.2 resolved decisions). The pre-existing `updateEmployee`-on-rename orphan issue (rekeying an employee's idNum does not rewrite `production.employeeId` rows that reference the old id) is **out of scope** and not fixed — it's a separate latent issue that nobody has reported yet, tracked only implicitly via the "keep orphans visible as `(missing #id)`" fallback. Manually verified by Matthew in the real GUI on a real DB before commit.

**Step 16 — production batch entry dialog.** Third post-release feature item from §13. First new *UI* surface since Step 12 — all of §13.3's pre-planning (shift per-row, target filtered by shared action, atomic per-batch save) carried through unchanged. Four groups of changes:

1. **Toolbar rename + new peer button.** `ProductionTab.newB` was relabeled `"New Production"` → `"Quick Entry"` to match §13.3's naming distinction; a new `batchB` (`"Batch Entry"`) was inserted between `newB` and `editB`. `_setButtonsEnabled` was factored to share `canEnter = hasEmployees and (hasParts or hasMixes)` between both entry buttons rather than duplicating the check. `openBatch()` mirrors `openNew()`'s two early-return guards (no employees / no targets) and then instantiates `ProductionBatchDialog`. Edit and Delete still only light up with a selection, unchanged.

2. **`_BatchRow(QWidget)` — per-row widget.** Employee (min width 200) / target (min width 160) / quantity (max 80) / scrap (max 80) / shift (max 60) / Remove button laid out in a `QHBoxLayout` with zero contentsMargins so rows pack tightly. The employee combo is populated once at row construction (same active-first sort as the single-record dialog at `production_tab.py:263`). The target combo is filled via `_populateTargets(targetType)` which reads from `db.mixtures` or `db.parts` keyed on the targetType argument (not on action — the dialog translates action → targetType before passing it down). `_populateTargets` returns a `bool` flag indicating whether the previously-selected target name is absent from the new list, so the dialog can tally invalidated rows on action-change. When a new row is added with a `prevRow`, it inherits employee / shift / target from it; quantity and scrap stay blank/`"0"` per §16.4 to avoid accidentally duplicating numerical values.

3. **`ProductionBatchDialog(QWidget)` — window.** `Qt.WindowType.Window` + `WA_DeleteOnClose` + `centerOnScreen` like all 21-ish other top-level windows (§12.2 Step 7c-3 item 2 + Step 7e). Header row is `QDateEdit` (today) + `QComboBox(PRODUCTION_ACTIONS)`. A column-header `QHBoxLayout` with matching min/max widths sits above the rows for orientation. Rows live in a `QScrollArea` wrapping a `QWidget(QVBoxLayout)` with a trailing stretch so rows stack at the top rather than expanding. A status `QLabel` (empty by default) surfaces the action-change invalidation count. Auto-resize: `_updateHeight()` runs after every `_addRow` / `_removeRow`, computing `max(480, min(180 + N * 36, 0.9 * screenHeight))` and only calling `resize(self.width(), ...)` when the value differs. The 180 chrome estimate covers header + column header + add button + status + save row + layout margins on Windows; 36 per row is generous for standard combo / line-edit height with padding. User feedback was "I suspect the others will complain about having to resize it vertically" — bumped the ROW_HEIGHT/CHROME constants to err on the side of no scrollbar appearing until the 90% screen-cap kicks in.

4. **Atomic save with per-row error collection.** `_save()` walks each row, collects per-row errors into a `rowErrs: list[str]`, then joins them as `f"Row {i}: {err1}; {err2}; …"`. Errors covered: missing employee / nonexistent employee id / invalid shift / missing target / nonexistent target (with targetType mismatch caught by the mixtures-vs-parts membership check) / blank or negative quantity / negative scrap / UNIQUE collision against `db.production` / UNIQUE collision against an earlier row in the same batch. Only after every row has been validated does the dialog mutate `db.production`; any error anywhere refuses the whole batch with a single `QMessageBox.critical` listing all failing rows. On full success: bulk insert, `parentTab.refresh()`, success `QMessageBox.information` with the count, close. No partial-save semantics, matching Step 7a's atomic-file-write philosophy.

5. **New smoke check `production_batch_roundtrip` (9th).** Seeds an employee + five shadow collections + `Mixture("MixA")` + `Mixture("MixB")`, then drives the real `ProductionBatchDialog._save()` end-to-end against four rows spanning shifts 1+2 and alternating between MixA/MixB (so the composite keys are distinct). Verifies in-memory state, then calls `saveFile` + `loadFile` on a second `MainWindow` to confirm the four rows round-trip on disk. Adds two refusal cases: (a) a single-row batch that exactly duplicates an already-saved key → expect `db.production` count unchanged; (b) an intra-batch duplicate (two rows with identical employee/shift/target/date/action) → same expectation. **Gotcha that cost 10 minutes:** `_save()` pops `QMessageBox.information` on success and `QMessageBox.critical` on failure, both of which **block offscreen** since there's no event pump to dismiss them. Fixed by patching both to no-op lambdas returning `StandardButton.Ok` for the duration of the check and restoring in the `finally` block. Worth remembering for any future UI-path smoke checks — this is the first one that drives a save-button handler rather than the underlying data layer.

**Scope deviations from §13.3.**
- **Button label: `"Quick Entry"`, not `"New Production"`.** §13.3 noted the conceptual framing (`Quick Entry` vs. `Batch Entry`) as a rationale rather than a strict spec, but the rename reads cleaner on the toolbar so both entry modes are equally obvious. The underlying class name (`ProductionEditWindow`) was left alone — it's not user-facing and §13.3 already noted the loose nomenclature in the planning prose.
- **Remove-button label: `"Remove"`, not `"✕"`.** The plan sketch showed a glyph; I used text since the CLI rules here discourage emoji and the text is self-describing. If the floor prefers a narrower glyph we can swap later without changing layout widths.
- **Auto-resize added in response to user ask.** Not in the original §13.3 sketch. Matthew flagged post-implementation that the team would complain about manual vertical resize; `_updateHeight()` was added so the dialog grows with the row count up to a screen cap.

**Known unknown that did not materialize.** §13.3's "Known unknowns" flagged the class starting around `production_tab.py:458` as possibly containing an existing batch-adder flow. That class is `ProductionReportWindow` (the Step 12 report dialog, not an entry flow), so the work was greenfield as the rest of the plan assumed — no increment-vs-rewrite decision to make.

**Verification.** All 9 smoke checks pass (the 8 prior plus the new `production_batch_roundtrip`). Manually verified by Matthew in the real GUI before commit.

**Step 17 — production hours field.** Fourth post-release feature item, surfaced 2026-04-21: the team had omitted a `duration / hours` variable from the production schema. Added as a per-record `hours REAL DEFAULT 0` column, labeled "Hours" in the UI. Five groups of changes:

1. **Schema + migration.** `MERCY_DB_VERSION` bumped 3 → 4. `_createProductionTable` now declares `hours REAL DEFAULT 0`. New `_migrateV3ToV4()` does a guarded `ALTER TABLE production ADD COLUMN hours REAL DEFAULT 0` (the `if 'hours' not in cols` guard is defensive — Case 4 creates the production table fresh at the v4 shape then runs the BECKY v2→v3 migration, so a reopen of a Case-4-opened file would otherwise re-attempt the ALTER on an already-present column). Wired into Case 2 as a third chained `if dbVersion < 4:` clause after the existing ANIKA v1→v2 and BECKY v2→v3 steps.

2. **Case 4 stamping fix.** Case 4 (legacy BECKY) was stamping `db_version=3` at the end instead of `MERCY_DB_VERSION`, a pre-existing inconsistency with Case 3's `self._setDbVersion(MERCY_DB_VERSION)`. Added the stamp at the tail of Case 4 so a freshly-migrated legacy BECKY file lands at the current version rather than triggering a no-op v3→v4 migration on the *next* open. Latent and harmless before this step; only noticeable now that v4 exists. Both `legacy_anika_migration` and `legacy_becky_migration` smoke checks updated `db_version` assertion `3 → 4`.

3. **`ProductionRecord`.** `self.hours: float = 0` added to `__init__`. `setRecord(..., scrapQuantity=0, hours=0)` — keyword arg at the tail so existing call sites that pass `scrapQuantity=...` continue to work. `getTuple` extended to a 9-tuple; `fromTuple` updated with the same `if row[i] is not None else 0` guard used for `scrapQuantity` to tolerate legacy rows where the ALTER-added column is NULL on a few oddball edge cases. `__str__` appends `hours={self.hours}`.

4. **Save / load.** `file_manager.py` INSERT OR REPLACE into production extended from 8 columns to 9 (`hours` added); SELECT on the load side matches. No other persistence path references the tuple shape.

5. **UI surfaces — three paths.**
   - **Table view (`ProductionTab.genTableData`).** New `"Hours"` column at the tail of `headers`; each row appends `f"{rec.hours}"` after scrap. No column-width tuning — `DBTable` auto-sizes, and the existing columns already carry more weight than a single-number hours cell.
   - **Quick Entry (`ProductionEditWindow`).** New `self.hoursEdit = QLineEdit()` inserted below Scrap in `mainLayout`. Defaults to `"0"` on new / mirrors `record.hours` on edit — identical shape to the existing scrap-edit flow. `readData` adds `hours = checkInput(self.hoursEdit.text(), float, "nonneg", errors, "Hours")` and passes it as the 8th positional arg to `setRecord`.
   - **Batch Entry (`_BatchRow` + `ProductionBatchDialog`).** New `self.hoursEdit = QLineEdit("0")` with the same `setMaximumWidth(80)` as scrap, inserted in the HBox between scrap and shift. Column-header tuple extended with `("Hours", 0, 80)` in matching position. `_save()` parses `hoursRaw` with the same blank→0 / else-nonneg-checked pattern as scrap and forwards to `setRecord(..., scrap, hours)`. Inheritance from `prevRow` deliberately does **not** carry hours (same rationale as quantity/scrap per §13.3 decision — safer to leave numeric fields fresh).

6. **Reports.** Hours added to every production report:
   - **Per Action / Per Target / Per Employee** (the three detail reports): new `"Hours"` column at the tail of the headers tuple; each data row appends `f"{r.hours:g}"`; totals rows extended to carry a summed hours cell. `perAction` dict upgraded from `(q, s)` tuples to `(q, s, h)`.
   - **Summary** (the employee×action grid): the cell formatter switched from "`q (scrap: s)` if scrap else `q`" to a unified `_format(q, s, h)` that emits parenthetical annotations only when the corresponding value is `> 0`. Examples: `250` (nothing extra), `250 (scrap: 3)` (scrap only), `250 (8h)` (hours only), `250 (scrap: 3, 8h)` (both). The totals row uses the same formatter. Chosen over a dedicated "Total Hours" column because the grid is already 4 columns wide (Employee + 3 actions) and inlining keeps the report scannable.

7. **Smoke checks.** New `mercy_v3_to_v4_migration` (6th in run order, after `legacy_merge`): hand-crafts a full v3 MERCY DB with one pre-hours production row, opens with MERCY v4, asserts the `ALTER` ran (hours in `PRAGMA table_info(production)`), `db_version=4`, pre-existing row preserved with `hours=0`, and in-memory `loadFile` surfaces `rec.hours == 0`. Existing `production_roundtrip` extended: r1 asserts `hours` defaults to 0, r2 sets `hours=7.5`, r3 sets `hours=4.0`, all three assert round-trip fidelity. Existing `production_batch_roundtrip`'s plan tuple extended from 4-tuple to 5-tuple (adds hours column `"8"`/`"7.5"`/`"0"`/`"6"`), with hours set via `row.hoursEdit.setText(hours)` and asserted against `rec.hours` post-save. Total smoke check count: **10**.

**Decisions / non-decisions worth noting.**
- **Label is "Hours", not "Duration".** Matthew's original prompt said "duration / hours"; picked the shorter / more concrete label for the UI and the DB column. If the team wants "Duration" this is a label-only change (string in the UI labels + headers) — no data rewrites needed.
- **Default is `0`, not blank.** Consistent with scrap. Blank-in-quick-entry would fail validation rather than defaulting, which felt worse. Blank-in-batch-entry parses as 0 to let fast-entry workflows skip the column, same as scrap.
- **Hours is not in the UNIQUE key.** No change to `UNIQUE(employeeId, date, shift, targetType, targetName, action)` — an employee doesn't log two different "hours spent Pressing PartA on shift 1 of date D". The existing semantic of "one record = one action-against-one-target per employee per shift per day" is what we want; hours is just a payload field.
- **Inheritance in batch entry does not carry hours.** Matches the §13.3 decision for quantity and scrap. Easy to add if the team flags it as annoying.
- **Reports show hours as parenthetical in the summary, dedicated column elsewhere.** Flagged explicitly to the team before commit; if they'd rather see a dedicated "Hours" column in the summary (5th column), it's a one-method rewrite.

**Verification.** All 10 smoke checks pass (the 9 prior — with the `db_version` assertion updates in the two legacy tests — plus the new `mercy_v3_to_v4_migration`). Offscreen `MainWindow()` construction confirms `productionTab.headers` ends in `'Hours'`. Manually verified by Matthew in the real GUI on a real DB before commit.

**Step 20 — remember last DB, prompt to reopen on startup.** Fifth post-release feature item, surfaced 2026-04-22: quality-of-life ask so MERCY doesn't boot into an empty DB every session. Pre-planning in §13.7 carried through unchanged. Four groups of changes:

1. **Org/app identity in `main.py`.** `QCoreApplication.setOrganizationName("tkg")` and `setApplicationName("MERCY")` added at the top of the `if __name__ == "__main__":` block, *before* `QApplication([])`. Safe to set before the app is constructed; required before any `QSettings()` call so Qt knows where to read/write (registry on Windows under `HKCU\Software\tkg\MERCY`, `~/.config/tkg/MERCY.conf` on Linux, plist on macOS). The Windows taskbar-grouping `myappid` in `main.py` was also updated from the legacy `k4g.anikaSuite.products` to `tkg.mercySuite.products` in the same commit so the two identities stay in sync.

2. **`MainWindow._loadPath(path: str) -> bool` helper in `app.py`.** Factored out of `open()` so both the File → Open dialog and the startup auto-reopen hook share a single load pipeline. Body: `setFile` → on success `loadFile`, always `setFileLabel` + `_refreshAllTabs`, on success `QSettings().setValue("lastDbPath", self.fileManager.filePath)`. Returns `True` iff `setFile` succeeded. The "always refresh tabs/label" behavior preserves the pre-existing semantics of `open()` (which refreshed even when the dialog was cancelled or `setFile` rolled back the path); a cancel path in `open()` still calls `setFileLabel` + `_refreshAllTabs` directly since it never enters the helper. Persisting inside the helper means the startup auto-reopen also re-writes `lastDbPath` on a successful load — idempotent, and guarantees the key is always pointing at whatever MERCY last successfully read.

3. **Persist on `saveAs` too.** One-liner `QSettings().setValue("lastDbPath", self.fileManager.filePath)` immediately after the successful `saveFile()` inside `saveAs()`. `save()` was deliberately *not* touched — it saves back to an already-persisted path, so re-writing the key would be pure no-op chatter.

4. **Startup hook in `main.py`.** Lives between `window.show()` and `app.exec()`, not in `MainWindow.__init__`. Reads `QSettings().value("lastDbPath")`, guards on `path and os.path.isfile(path)` (stale-path → silent skip; `QSettings.value` returns `None` for a never-set key, which also silently skips), offers a `QMessageBox.question` with the full path in the body so users can tell "which copy" they're about to reopen, and on Yes calls `window._loadPath(lastPath)` inside a `try/except` that logs via `logging.error` and falls through to the empty-DB state on any failure. Matches §13.7's "never block startup" stance.

**Decisions / non-decisions worth noting.**
- **No "always reopen without asking" checkbox on the first pass.** §13.7 flagged this as a latent escape hatch — prompt-every-time keeps the user unstuck if they point MERCY at a busted DB. Add later if the team asks.
- **Full path in the prompt body**, not just the filename. Matthew's floor occasionally has duplicate copies of the same DB in different directories; the path disambiguates without forcing the user to File → Open just to find out.
- **Stale-path path is silent.** Per §13.7 — no "last file missing" dialog. `logging.info` in the logs is enough for diagnostics; users who move their DB don't need a popup on every startup.
- **Refresh semantics in `open()` preserved exactly.** The pre-existing `open()` called `setFileLabel` + `_refreshAllTabs` on every exit path (success / cancel / `setFile` failure). Factoring the load into a helper could have accidentally skipped the refresh on cancel; the `else` branch in the rewritten `open()` keeps parity.
- **`QSettings` has no `initFile` equivalent at the startup hook.** If the file exists but is unreadable or the wrong format, `setFile` returns False inside `_loadPath` and the exception-less fall-through leaves the empty DB. Confirmed by manual test with a truncated 0-byte `.db` — the prompt appears, user clicks Yes, load fails silently in `setFile`, empty DB stays.
- **Only `open()` and `saveAs()` write the key — not `importOther()`.** Import doesn't change the active file path (§12.5(d) — it loads into the in-memory DB and leaves persistence for the user's next Save/Save-As). The key still points at whatever was open before the import; if the user hits Save, nothing needs to change; if they hit Save As, that handler persists the new path.

**Verification.** All 11 smoke checks pass (the 10 prior plus the new `qsettings_reopen`, which round-trips an empty DB through `QSettings.setValue` + `MainWindow._loadPath` in an isolated `IniFormat` store — no touching the user's real registry). `qsettings_reopen` also confirms `_loadPath` re-persists the key on load and exercises the stale-path guard. Manually verified by Matthew in the real GUI on a real DB before commit — fresh launch after opening a file prompts on next startup; Yes reloads; No leaves the empty DB; moving/renaming the last-opened DB silently skips the prompt.

### 12.3 Known deferred issues visible in the current build

- Bare `x == None` / `x != None` residuals (not in 7c-3's scope; see §12.2 Step 7c-3 note). Small optional follow-up.
- One awkward DeMorgan-able condition at `file_manager.py:176` / `:447` (`if not ((A is not None) and (B is not None)):`) — correct but ugly. Style-only, not blocking.
- Step 5's partial rename: `main_tab.py` → `employee_overview_tab.py` but the class is still `MainTab`. Not in Step 7's scope; see Step 5 note above.

### 12.4 Test conventions used so far

Testing has been manual in the real PySide6 GUI on the user's machine. Headless sanity checks are run from the repo-local venv as `./Scripts/python.exe -c '...'`, with `QT_QPA_PLATFORM=offscreen` for anything that instantiates widgets. The Step-5 smoke test that builds a full `MainWindow` offscreen and walks `tab_widget` is a good template for later UI steps.

**Baseline smoke harness** (`smoke.py` at repo root — added after Step 7e, extended in Steps 8, 9, 10, 11, 12, 15, 16, 17, and 20). Run as `./Scripts/python.exe smoke.py`; it sets `QT_QPA_PLATFORM=offscreen` internally. Eleven checks:
- `compile_all` — `py_compile` every `.py` at repo root. Catches syntax errors from scripted rewrites (7c-1 / 7c-2 / 7c-3 patterns). ~1s.
- `empty_roundtrip` — build `MainWindow()`, `setFile` + `saveFile` to a tmp path, reload into a fresh `MainWindow`, `loadFile`, assert the 11 dict-valued collections on `db` are present and empty and `db.holidays` (an `ObservancesDB`, not a dict) exists. Closes sqlite handles before `os.unlink` because Windows file-locks open connections.
- `legacy_anika_migration` (Step 8) — hand-crafts a v1 ANIKA-shape DB with 2 mixtures and 3 parts (covering pads-only, misc-only, and pads+misc combos), opens it with MERCY to trigger Case 3, then asserts v3 schema (`mixtures`=[`name`] only; `parts` = 12 expected cols; `db_version=3` after chained v1→v3 migration), expected child-table row contents, in-memory reconstruction of `Mixture.materials`/`weights` and `Part.pad`/`padsPerBox`/`misc`, presence of a `.db.bak-*` sibling, and save/reload roundtrip fidelity. Updated in Step 9 to assert v3 (the BECKY v2→v3 migration is a no-op version-bump in Case 3 since the employee tables are empty).
- `legacy_becky_migration` (Step 9) — hand-crafts a v2 BECKY-shape DB with 3 employees covering both compound-shift shapes (`"1|1"`, `"2|0"`, `"3|1"`), 2 base64-wrapped reviews (one multi-line), 2 base64-wrapped notes, and deliberately-orphaned `training`/`attendance`/`PTO` rows alongside valid ones. Opens with MERCY to trigger Case 4, then asserts `db_version=3`, the 15-col v3 `employees` shape, correct shift/fullTime split per row, plain-text `reviews.details`/`notes.details` (newlines preserved), orphan sweep removed only the dangling rows, backup sibling file exists, in-memory `Employee.shift`/`fullTime` reconstruct as `int`/`bool`, and save/reload roundtrip fidelity.
- `legacy_merge` (Step 10) — seeds a legacy ANIKA file and a legacy BECKY file, opens the ANIKA one with MERCY (triggers Case 3 + v1→v3 migration), sha256-hashes the BECKY file, calls `FileManager.importOtherDb(beckyPath)` + `Database.mergeFrom(tmpDb)`, then asserts: products from ANIKA + employees + reviews + notes from BECKY are all present in-memory with correct shift/fullTime split; the BECKY source file is byte-identical to what was seeded (hash before == after — the import must never mutate the source); and save/reload roundtrip on the ANIKA file preserves the merged contents.
- `mercy_v3_to_v4_migration` (Step 17) — hand-crafts a unified MERCY-shape DB stamped at `db_version=3` with one pre-hours `production` row (no `hours` column), opens it with MERCY to trigger Case 2's chained v3→v4 migration, then asserts: post-migration `db_version=4`, `hours` present in `PRAGMA table_info(production)`, the pre-existing `production` row preserved with `hours=0` on disk, and `loadFile` surfaces a single in-memory record with `rec.hours == 0`. Closes the sqlite handle before `os.unlink` per the Windows file-lock convention.
- `production_roundtrip` (Step 11) — builds a fresh `MainWindow` against an empty DB, inserts three `ProductionRecord`s directly into `db.production` covering all three actions (`Batching`→mix with default scrap, `Pressing`→part with explicit `scrapQuantity=3`, `Finishing`→part), saves, reloads into a second `MainWindow`, asserts each record round-trips with correct `action` / `targetType` / `targetName` / `quantity` / `scrapQuantity` (including the default-0 case), then deletes one record, re-saves, and reloads into a third `MainWindow` to confirm the save-side sweep in `_saveFileBody` removes the on-disk row when the in-memory key is gone. Does not populate `db.employees` / `db.parts` / `db.mixtures` — the persistence layer doesn't cross-validate those, so keeping the fixture minimal keeps the test focused.
- `production_report` (Step 12) — seeds one `Employee` (id 101, `lastName="Smith"`, `firstName="Alice"`, `fullTime=True`, anniversary 2020-01-01) plus the same three-record fixture as `production_roundtrip` (one record per action, mix and parts), then generates each of the four reports — `productionSummaryReport`, `productionActionReport("Pressing")`, `productionTargetReport("part", "PartA")`, `productionEmployeeReport(101)` — over a 2026-04 window plus an empty 2030 window for the empty-range path. Asserts every PDF file exists and is non-empty; does not parse PDF content (per §12.4 convention — generation succeeding without exception is the bar). Cleans up tmp `.pdf` paths and the `.db`/`-wal`/`-shm` triple in the `finally` block.
- `production_refresh_on_delete` (Step 15) — builds `MainWindow` against an empty DB, seeds one `Employee` plus all five shadow collections (`EmployeeReviewsDB` / `EmployeeTrainingDB` / `EmployeePointsDB` / `EmployeePTODB` / `EmployeeNotesDB` — required because `delEmployee` asserts each is populated), seeds one `ProductionRecord` against the employee, primes `productionTab.refresh()` once and confirms the employee shows up in `employeeFilter`, then calls `db.delEmployee(emp.idNum)`. Asserts (a) the production record still exists in `db.production` with its `employeeId` unchanged (orphan retention — see §13.2), (b) a second `productionTab.refresh()` doesn't raise when the record's `employeeId` is no longer a key in `db.employees`, and (c) the deleted employee's id is gone from `employeeFilter`'s `itemData` after the refresh. Closes the sqlite handle before `os.unlink` in `finally` per the Windows file-lock convention.
- `production_batch_roundtrip` (Step 16) — builds `MainWindow` against an empty DB, seeds one `Employee` plus all five shadow collections plus `Mixture("MixA")` + `Mixture("MixB")`, then drives the real `ProductionBatchDialog._save()` against four rows spanning shifts 1+2 and alternating MixA/MixB (so the 6-tuple keys are all distinct). Verifies in-memory state, then save/reload roundtrip on a fresh `MainWindow`. Adds two refusal cases: a single-row batch that exactly duplicates an already-saved key, and an intra-batch duplicate (two rows with identical key fields) — both expected to leave `db.production` untouched. **First smoke check that drives a UI save-button handler**, so it patches `QMessageBox.critical` + `QMessageBox.information` to no-op lambdas returning `StandardButton.Ok` for the duration of the check and restores in `finally` — offscreen, those dialogs' `exec()` nests an event loop without an input path to dismiss it, so without the patch the check would hang.
- `qsettings_reopen` (Step 20) — saves an empty DB through the real `FileManager.saveFile()` pipeline, stashes its path under the `lastDbPath` key of an isolated `QSettings` store (IniFormat + `setPath(UserScope, tmpdir)` + a throwaway org/app name so the check never touches the user's real registry/plist), constructs a fresh `MainWindow`, then drives `MainWindow._loadPath(lastPath)` to simulate the startup auto-reopen hook *without* invoking the modal. Asserts (a) `QSettings.value("lastDbPath")` survives a fresh `QSettings()` after `sync()`, (b) `_loadPath` returns `True` and sets `fileManager.filePath`, (c) `_loadPath` re-persists the key on success, and (d) `os.path.isfile` correctly rejects a plausible stale-path sentinel (the guard `main.py` uses before calling `_loadPath`). Restores the original org/app name and rmtree's the settings tmpdir in `finally` so subsequent checks run clean.

Run `smoke.py` as the always-on baseline at the start and end of any invasive step. Step-specific assertions still go in throwaway `-c '...'` scripts or a new function in `smoke.py` if broadly reusable.

Gotcha when constructing test `Employee` objects headlessly: `Employee.shift` is an `int` and `Employee.fullTime` is a separate `bool` — setting `e.shift = "1|1"` (trying to pre-format the compound string) produces a triple-piped `"1|1|1"` out of `getTuple()` because `getTuple` itself re-appends `|{fullTime}`. Set `e.shift = 1; e.fullTime = True` instead, or use the `setJob(role, shift, fullTime)` method.

### 12.5 Step 13 — end-to-end verification on real data (findings)

**What ran.** A throwaway driver (`step13_real_data.py`, not committed) executed five drills offscreen against copies of two real legacy files the team handed over — `legancyanika.db` (v1 ANIKA, no `db_version` stamp, detected via table shape) and `legacybecky.db` (v2 BECKY). Sources were hashed before and after; both were byte-identical afterward. All five drills passed; the summary below is retained so future regressions can be compared against known-good numbers.

**Check 1a — legacy ANIKA migration.**
- Pre: 7 tables, version `None`, counts `{materials:49, mixtures:10, parts:141, packaging:51, materialInventory:31, partInventory:57, globals:8}`.
- Post: 19 tables, `db_version=3`, all MERCY tables present. Base64 compound decode produced `mixture_components=71, part_pads=148, part_misc=281`. Row counts for `mixtures` and `parts` unchanged (10/10, 141/141). One `.db.bak-*` sibling written, matching §8 expectation. Save/reload roundtrip preserved counts.

**Check 1b — legacy BECKY migration.**
- Pre: 9 tables, `db_version=2`, counts `{employees:29, training:188, attendance:135, PTO:85, reviews:1, notes:3, holidays:10, observances:30}`.
- Post: 19 tables, `db_version=3`. `employees` columns split into `shift` + `fullTime` per §3.3. Base64 decode applied to `reviews.details` / `notes.details`. **Orphan sweep found zero orphans** in this file — the `updateEmployee` pre-7a bug evidently never corrupted it. Good for the release, bad for code coverage: the orphan-sweep code path is exercised only by synthetic fixtures in `smoke.py::legacy_becky_migration`. If a later BECKY file does have orphans, watch for the correct count drop and the info-level log line.
- One `.bak` sibling written. Save/reload roundtrip preserved employee count (29/29). Source byte-identical.

**Check 1c — merge.**
- ANIKA copy opened first (141 parts), then BECKY copy imported via `importOtherDb`. Merge plan reported **zero collisions** (the two real files share no keys — ANIKA identifies by string name, BECKY by `idNum`). Post-merge: 141 parts + 29 employees + 29 review-collections carried through. Save/reload preserved everything. BECKY temp copy SHA-256 identical before and after `importOtherDb` — **Step 10's "source file untouched" guarantee holds on real data**.

**Check 2a — backup/restore drill.**
- Migrated a real ANIKA copy to MERCY format, truncated the live file to 0 bytes, copied the `.bak-*` sibling back into place, reopened in a fresh `MainWindow`. The restored file is pre-migration, so MERCY re-ran the ANIKA v1→v3 migration on it (creating a second `.bak`), and loaded successfully with `parts=141` intact. Recovery path works end-to-end.

**Check 2b — atomic-save drill.**
- Opened a fully-migrated file, deleted an in-memory part (`1046-FS4`), monkey-patched `_saveFileBody` to run the real body and then raise `RuntimeError` before `saveFile`'s outer `commit()`. On-disk row counts (`parts`, `mixtures`, `materials`, `mixture_components`, `part_pads`) were byte-identical before and after the attempted save — Step 7a's try/rollback/commit wrapper is rolling back correctly against a real-file connection, not just the hand-crafted fixtures.

**What Step 13 did NOT cover.** Three items from the original Step 13 pick-up notes didn't fire and are left for future steps or dropped as low priority:
- **Production tracking + reports against real production data** (original check 3). Deferred — the team hasn't started logging production yet. Covered in practice once they do; no code work needed now.
- **Report sanity-check loop with the team** (original check 4). The team's first-look feedback instead surfaced three feature asks, now tracked as §13.
- **Cross-platform sanity** (original check 5). Windows-only shop; dropped.

**Performance notes.** The v2→v3 BECKY migration's per-row `UPDATE` on `reviews.details` / `notes.details` ran instantaneously on the real 29-employee file (1 review, 3 notes). The §12.5-original-hypothesis about large-file slowness did not materialize at this file size — but the drill didn't push into hundreds of reviews/notes either, so the "swap to a `CASE`-expression single `UPDATE`" fallback remains a live option if the team's next snapshot is substantially bigger.

**Regression hooks for future sessions.** The synthetic `smoke.py` checks (`legacy_anika_migration`, `legacy_becky_migration`, `legacy_merge`, production roundtrip + report) cover the same code paths as the drills above on fixture data — they are the durable safety net. The throwaway driver was deliberately not promoted to `smoke.py` because it depends on files that are gitignored and specific to Matthew's machine; committing it would either break for anyone else running `smoke.py` or force those files into the tree.

---

## 13. Post-release feature backlog

Requests from the team after their first look at MERCY. Each item is small enough to be one step and one commit in the §12 style; open questions resolved in-session on 2026-04-19 are recorded inline. Order is deliberate: smallest / lowest-risk first, so tomorrow's session can ship increments rather than gating the whole backlog behind the biggest item.

### 13.1 Step 14 — reports: skip save dialog, open via temp file ✅ Done

Landed 2026-04-20. See §12.2 Step 14 for implementation notes and deviations.

### 13.2 Step 15 — production tab refresh when an employee is deleted ✅ Done

Landed 2026-04-20. See §12.2 Step 15 for implementation notes and the scope decisions.

### 13.3 Step 16 — production tab: batch entry ✅ Done

Landed 2026-04-20. See §12.2 Step 16 for implementation notes and the scope decisions.

### 13.4 Step 17 — production hours field ✅ Done

Landed 2026-04-21. Surfaced in Matthew's first post-release feedback session: the team had forgotten to include duration/hours in the production schema. One-session add — new `hours REAL DEFAULT 0` column on `production`, wired through records / save / load / table / Quick Entry / Batch Entry / all four reports. See §12.2 Step 17 for implementation notes, the Case-4 stamping fix it piggybacked, and the report-formatting decisions.

### 13.5 Step 18 — productivity rate reports (feeds costing) ⏳ Planning

**Motivation.** Surfaced 2026-04-21 alongside Step 17. Team wants productivity drill-downs — rates per hour by part × action × employee × shift, with the ability to compare individuals to the fleet average. **Downstream consumer is the costing code, not HR.** They're gathering more precise labor data so they can refine the per-part cost estimates in the costing globals (the existing `pressing` / `turning` / `finishing` / etc. fields on `parts`). Not bonuses, not quotas, no targets stored on the record. This reframing matters: report shape should mirror the *inputs costing needs*, not a generic performance dashboard.

**Confirmed scope (from 2026-04-21 session).**
- Rate = `quantity / hours`, aggregated across arbitrary slices.
- Comparisons are individual-vs-average (per part, per employee). Nice-to-have, not required.
- No target-rate column or threshold storage. If "vs. expected" ever becomes desirable, the expected rate is already in costing globals.
- PDF deliverable, same `PDFReport` pipeline as the other production reports.

**Open questions — need team input before coding starts.**
1. **Aggregation math.** `sum(qty) / sum(hours)` over the window, vs. mean of per-shift rates, vs. median. These diverge whenever shifts are uneven in length or in completeness. Pick wrong and the rates mislead.
2. **Primary cut.** Probably per `(part, action)` since that's the costing-input granularity. But `(employee, part, action)` would let them see which employees are skewing the average — worth clarifying whether that's a separate report or a drill-down from the primary.
3. **Windowing.** Rolling 30 days, user-picked range, or both? Filter UI can handle either.
4. **Scrap rate.** `scrap / quantity` alongside the production rate in the same table, or a separate report?
5. **Export.** Does the team want a CSV alongside the PDF so they can paste rates into the costing globals, or is reading-and-typing fine for the first iteration?

**Tentative direction (subject to team answers).** New report type "Production Rates" as a fifth entry in `ProductionReportWindow.REPORT_TYPES`. Shape: grouped table (one row per `(part, action)`) with columns Quantity / Hours / Rate (qty/hr) / Scrap / Scrap-rate. When an employee is selected, add a "vs. average" column comparing the selected employee's rate to the fleet average for that `(part, action)`. Fleet average row at the bottom. Integrates with Step 19 (graphs) — this is the natural first customer.

**Next session pickup.** Draft two or three example reports (mocked numbers) to send the team a concrete "pick one" doc — that unsticks scope faster than open-ended questions.

### 13.6 Step 19 — graphs in reports (reportlab native) ⏳ Planning

**Motivation.** Second half of the 2026-04-21 feedback: team wants graphs alongside (or instead of) tables in the production reports.

**Confirmed decisions (2026-04-21 session).**
- **PDF only.** No dashboard pivot — the app's deliverable stays a file you can email and archive.
- **`reportlab.graphics.charts` first.** Native to the stack, zero new deps, vector into the PDF, keeps the PyInstaller binary lean. Matplotlib stays a latent escape hatch if the aesthetics fall short after seeing the first pass — decision deferred until we have team eyes on real output.

**Open questions.**
1. **Which charts, for which reports?** Bar-per-employee-per-action in Summary? Line-over-time for a per-part report? Both? Team hasn't been specific — mock examples will help.
2. **Replace tables or sit alongside?** Default: alongside, since the numbers themselves are the costing-input deliverable (§13.5). Losing them loses half the point.
3. **Styling tolerance.** `reportlab.graphics.charts` gives frumpy-but-functional output. Before we over-invest in tick customization / legend placement / color schemes, see what the team says about the first pass.

**Tentative direction.** Add chart helpers to `report.py` mirroring the existing `drawTable(data, headers)` API — e.g., `drawBarChart(groups, labels, values, title)`. Most plausible first charts:
- **Grouped bar** — one group per employee, three bars (Batching / Pressing / Finishing rate). Companions the Summary report.
- **Line over time** — one line per part, x = date, y = rate. Companions a per-part rate report.

Ship those two as exemplars inside §13.5's new "Production Rates" report, hand to the team, iterate.

**Next session pickup.** Draft one report using mock rate data with both a table and a grouped-bar chart rendered side-by-side. That's the concrete deliverable to validate the approach before scaling to the other report types.

### 13.7 Step 20 — remember last DB, prompt to reopen on startup ✅ Done

Landed 2026-04-22. Fifth post-release feature item from Matthew's backlog: MERCY previously booted into an empty DB every session. Quality-of-life add — `QSettings`-backed `lastDbPath` persisted after every successful `open()`/`saveAs()`, loaded on startup via a new `MainWindow._loadPath(path) -> bool` helper, prompted through a `QMessageBox.question` in `main.py` between `window.show()` and `app.exec()`. Zero new deps (`QSettings` is already in the PySide6 stack). See §12.2 Step 20 for implementation notes, the decision to keep the prompt modal every time (no "always reopen" checkbox yet), and the stale-path-silent-skip behavior.

**Follow-up still open (not part of Step 20).** Confirm with Matthew whether to also remember the last *import* path for the Import Database dialog, since that currently hard-codes `os.path.expanduser("~")`. Separate feature, separate step.

### 13.8 Dev tooling landed

Not step commits but worth cataloging so a cold pickup knows they exist:

- **`mock_reports.py`** — Step 18 planning artifact, landed 2026-04-21 (commit `5bd3433`). Generates three candidate productivity-rate-report layouts (A/hierarchical, B/flat-with-fleet-comparison, C/action-by-part matrix), each with a reportlab-native grouped bar chart. Output writes to `mock_reports/` (gitignored). Deletable once the team picks a design.
- **`fuzz_db.py`** — fake-data DB generator, landed 2026-04-22 (commit `e4246ee`). Writes a fully-populated MERCY DB through the real `FileManager.saveFile()` pipeline: every record type (materials, mixtures, packaging, parts, inventory, employees, reviews, training, attendance, PTO including CARRY/CASH/DROP, notes, holidays + observances, production) gets plausible random data. Deterministic with `--seed`; scales `tiny|small|medium|large` (medium → ~1.7k production records over 90 days). Verified end-to-end: generated DBs roundtrip through `MainWindow.loadFile()`, the Part → Mix → Material cost chain computes cleanly, `PDFReport.productionSummaryReport` renders against them, and a given seed is byte-equivalent across all 12 populated tables on re-run. Good for stress-testing any report (including Step 18's future output) without needing real team numbers.

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
