# MERCY — Manufacturing and Employee Records: Costing and Yield
## Merge & Implementation Plan

**Date:** 2026-04-16  
**Author:** Matthew Kilgore  
**Status:** Implementation in progress — Steps 1–6 + 7a + 7b of 13 complete as of 2026-04-17. Step 7 is being run as three sub-steps (7a correctness → 7b signature → 7c hygiene); see §12 for current state, deviations, and deferred items before picking up **Step 7c**.

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

- For parts (`targetType = "part"`): **pieces** (can be fractional for partial batches if needed)
- For mixes (`targetType = "mix"`): **lbs**

Units are implied by `targetType` and documented in code. No separate units column is needed.

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

*Last updated 2026-04-17. Steps 1–6 + 7a + 7b complete; **Step 7c is next**. Each step was committed separately on `main` with a message that names the step.*

Step 7 has been split into three sub-steps to keep each review surface small:

- **7a** — correctness / data-integrity fixes (done).
- **7b** — promote `Database.__init__`'s optional BECKY kwargs to required args (next).
- **7c** — hygiene sweep (`assert` → `raise`, `print` → `logging`, `not x == None` → `x is not None`, window-close leak, `LBS_PER_TON` constant, drop BECKY debug `print`, add `requirements.txt`).

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
| 7c | ⏳ Next | Hygiene sweep (see §12.2 Step 7 notes for full list). |
| 8–13 | ⏳ Pending | Per §9. |

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

### 12.3 Known deferred issues visible in the current build

- `assert` for internal validation (100+ occurrences), `print()` for logging, window-list leak, `not x == None` idiom, magic `2000` in `Part` costing, debug `print` in BECKY `records.py` points logic, no `requirements.txt` — all Step 7c.
- Base64 everywhere, compound `employees.shift`, dead `parts` columns (`loading`, `unloading`, `inspection`, `greenScrap`, plus the base64 compound columns `pad`/`padsPerBox`/`misc`) — Steps 8–9.
- Step 5's partial rename: `main_tab.py` → `employee_overview_tab.py` but the class is still `MainTab`. Not in Step 7's scope unless we want to pick it up in 7c; see Step 5 note above.

### 12.4 Test conventions used so far

Testing has been manual in the real PySide6 GUI on the user's machine. Headless sanity checks are run from the repo-local venv as `./Scripts/python.exe -c '...'`, with `QT_QPA_PLATFORM=offscreen` for anything that instantiates widgets. The Step-5 smoke test that builds a full `MainWindow` offscreen and walks `tab_widget` is a good template for later UI steps.

Gotcha when constructing test `Employee` objects headlessly: `Employee.shift` is an `int` and `Employee.fullTime` is a separate `bool` — setting `e.shift = "1|1"` (trying to pre-format the compound string) produces a triple-piped `"1|1|1"` out of `getTuple()` because `getTuple` itself re-appends `|{fullTime}`. Set `e.shift = 1; e.fullTime = True` instead, or use the `setJob(role, shift, fullTime)` method.

### 12.5 Pick-up notes for Step 7c

Hygiene sweep. Items (all from §3.7, §3.8, §12.2):

1. **`assert` → explicit exceptions.** 100+ occurrences across `records.py`, `file_manager.py`, `report.py`, and the tab files. For internal invariants that should never fire in correct code, use `raise RuntimeError(...)`; for invalid-input validation at method boundaries, use `raise ValueError(...)`. A few asserts inside short-lived helpers (e.g. `assert(self.dbFile is not None)` right after opening) can stay as sanity checks if switching them to `if` / `raise` would add noise without clarity.
2. **`print()` → `logging`.** `print(f"Saving ...")` / `print(f" * Error ...")` chatter all over `file_manager.py` should become `logging.info(...)` / `logging.error(...)`. Add a simple `logging.basicConfig(level=logging.INFO)` call in `main.py` near startup.
3. **`not x == None` → `x is not None`** across both `records.py` and `file_manager.py`. Safe replace_all candidates. Watch for the inverted form `if not x == None:` which becomes `if x is not None:`.
4. **Window-list leak in `*_tab.py` files.** All the "edit" sub-windows (e.g. `parts_tab`'s edit dialog) are appended to a list on the parent tab and never removed. Fix: set `Qt.WA_DeleteOnClose` on each window and stop retaining references — or move to modal `QDialog.exec()` if the interaction model allows.
5. **`LBS_PER_TON = 2000` constant** in `records.py` (§3.8). One magic `2000` in `Material.getCostPerLb()` / wherever; extract with a short comment noting "short ton".
6. **Remove the debug `print()` in BECKY's points logic** at `records.py:345` (BECKY's line; may be offset in the merged `records.py` — grep for the `print` inside `EmployeePointsDB.currentPoints`).
7. **Add `requirements.txt`** listing `PySide6` and `reportlab`.

Split 7c further if it grows — e.g. separate "`assert` → `raise`" as its own step since it's the largest line-count item and carries the most review surface.

---

*This document was prepared with Claude Code (claude-opus-4-6 / claude-sonnet-4-6) as a planning artifact; §12 is being maintained as implementation proceeds.*
