# MERCY — Manufacturing and Employee Records: Costing and Yield
## Merge & Implementation Plan

**Date:** 2026-04-16  
**Author:** Matthew Kilgore  
**Status:** Implementation in progress — Steps 1–11 of 13 complete as of 2026-04-19, plus Step 9.5 (vestigial `Part` attribute cleanup). Step 7 was run as sub-steps (7a correctness → 7b signature → 7c-1 asserts → 7c-2 logging → 7c-3 polish → 7d double-negation → 7e window centering); see §12 for current state, deviations, and deferred items before picking up **Step 12** (production reports).

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

*Last updated 2026-04-19. Steps 1–12 complete plus the Step 9.5 polish; **Step 13 (end-to-end testing on real data) is the only remaining step**. Each step was committed separately on `main` with a message that names the step.*

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
| 13 | ⏳ Pending | Per §9. |

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

### 12.3 Known deferred issues visible in the current build

- Bare `x == None` / `x != None` residuals (not in 7c-3's scope; see §12.2 Step 7c-3 note). Small optional follow-up.
- One awkward DeMorgan-able condition at `file_manager.py:176` / `:447` (`if not ((A is not None) and (B is not None)):`) — correct but ugly. Style-only, not blocking.
- Step 5's partial rename: `main_tab.py` → `employee_overview_tab.py` but the class is still `MainTab`. Not in Step 7's scope; see Step 5 note above.

### 12.4 Test conventions used so far

Testing has been manual in the real PySide6 GUI on the user's machine. Headless sanity checks are run from the repo-local venv as `./Scripts/python.exe -c '...'`, with `QT_QPA_PLATFORM=offscreen` for anything that instantiates widgets. The Step-5 smoke test that builds a full `MainWindow` offscreen and walks `tab_widget` is a good template for later UI steps.

**Baseline smoke harness** (`smoke.py` at repo root — added after Step 7e, extended in Steps 8, 9, 10, 11, and 12). Run as `./Scripts/python.exe smoke.py`; it sets `QT_QPA_PLATFORM=offscreen` internally. Seven checks:
- `compile_all` — `py_compile` every `.py` at repo root. Catches syntax errors from scripted rewrites (7c-1 / 7c-2 / 7c-3 patterns). ~1s.
- `empty_roundtrip` — build `MainWindow()`, `setFile` + `saveFile` to a tmp path, reload into a fresh `MainWindow`, `loadFile`, assert the 11 dict-valued collections on `db` are present and empty and `db.holidays` (an `ObservancesDB`, not a dict) exists. Closes sqlite handles before `os.unlink` because Windows file-locks open connections.
- `legacy_anika_migration` (Step 8) — hand-crafts a v1 ANIKA-shape DB with 2 mixtures and 3 parts (covering pads-only, misc-only, and pads+misc combos), opens it with MERCY to trigger Case 3, then asserts v3 schema (`mixtures`=[`name`] only; `parts` = 12 expected cols; `db_version=3` after chained v1→v3 migration), expected child-table row contents, in-memory reconstruction of `Mixture.materials`/`weights` and `Part.pad`/`padsPerBox`/`misc`, presence of a `.db.bak-*` sibling, and save/reload roundtrip fidelity. Updated in Step 9 to assert v3 (the BECKY v2→v3 migration is a no-op version-bump in Case 3 since the employee tables are empty).
- `legacy_becky_migration` (Step 9) — hand-crafts a v2 BECKY-shape DB with 3 employees covering both compound-shift shapes (`"1|1"`, `"2|0"`, `"3|1"`), 2 base64-wrapped reviews (one multi-line), 2 base64-wrapped notes, and deliberately-orphaned `training`/`attendance`/`PTO` rows alongside valid ones. Opens with MERCY to trigger Case 4, then asserts `db_version=3`, the 15-col v3 `employees` shape, correct shift/fullTime split per row, plain-text `reviews.details`/`notes.details` (newlines preserved), orphan sweep removed only the dangling rows, backup sibling file exists, in-memory `Employee.shift`/`fullTime` reconstruct as `int`/`bool`, and save/reload roundtrip fidelity.
- `legacy_merge` (Step 10) — seeds a legacy ANIKA file and a legacy BECKY file, opens the ANIKA one with MERCY (triggers Case 3 + v1→v3 migration), sha256-hashes the BECKY file, calls `FileManager.importOtherDb(beckyPath)` + `Database.mergeFrom(tmpDb)`, then asserts: products from ANIKA + employees + reviews + notes from BECKY are all present in-memory with correct shift/fullTime split; the BECKY source file is byte-identical to what was seeded (hash before == after — the import must never mutate the source); and save/reload roundtrip on the ANIKA file preserves the merged contents.
- `production_roundtrip` (Step 11) — builds a fresh `MainWindow` against an empty DB, inserts three `ProductionRecord`s directly into `db.production` covering all three actions (`Batching`→mix with default scrap, `Pressing`→part with explicit `scrapQuantity=3`, `Finishing`→part), saves, reloads into a second `MainWindow`, asserts each record round-trips with correct `action` / `targetType` / `targetName` / `quantity` / `scrapQuantity` (including the default-0 case), then deletes one record, re-saves, and reloads into a third `MainWindow` to confirm the save-side sweep in `_saveFileBody` removes the on-disk row when the in-memory key is gone. Does not populate `db.employees` / `db.parts` / `db.mixtures` — the persistence layer doesn't cross-validate those, so keeping the fixture minimal keeps the test focused.
- `production_report` (Step 12) — seeds one `Employee` (id 101, `lastName="Smith"`, `firstName="Alice"`, `fullTime=True`, anniversary 2020-01-01) plus the same three-record fixture as `production_roundtrip` (one record per action, mix and parts), then generates each of the four reports — `productionSummaryReport`, `productionActionReport("Pressing")`, `productionTargetReport("part", "PartA")`, `productionEmployeeReport(101)` — over a 2026-04 window plus an empty 2030 window for the empty-range path. Asserts every PDF file exists and is non-empty; does not parse PDF content (per §12.4 convention — generation succeeding without exception is the bar). Cleans up tmp `.pdf` paths and the `.db`/`-wal`/`-shm` triple in the `finally` block.

Run `smoke.py` as the always-on baseline at the start and end of any invasive step. Step-specific assertions still go in throwaway `-c '...'` scripts or a new function in `smoke.py` if broadly reusable.

Gotcha when constructing test `Employee` objects headlessly: `Employee.shift` is an `int` and `Employee.fullTime` is a separate `bool` — setting `e.shift = "1|1"` (trying to pre-format the compound string) produces a triple-piped `"1|1|1"` out of `getTuple()` because `getTuple` itself re-appends `|{fullTime}`. Set `e.shift = 1; e.fullTime = True` instead, or use the `setJob(role, shift, fullTime)` method.

### 12.5 Pick-up notes for Step 13 (end-to-end testing on real data)

**Step 13 — end-to-end testing with real data + backup/restore verification.** Last step on the plan. Per §9 this is process-heavy rather than code-heavy — the bar is "ready to ship" rather than "feature complete." All Steps 1–12 functionality is in place; the goal is to find and fix anything that the synthetic smoke fixtures or developer-machine manual testing missed when run against the actual production ANIKA + BECKY databases on the team's hardware.

**Scope.** No fixed code deliverable; the deliverable is *confidence*. Concrete checks to run, in roughly the order they should fail least → most expensively:

1. **Migrate the team's actual ANIKA `.db` and BECKY `.db` files** — separately first, then the merge — and compare migrated output against a hand-spot-check of representative records (a few employees, a few mixtures with multi-material recipes, a few parts with pads + misc). The `_backupDbFile` sibling-file should appear in each case (Steps 8, 9, 10). Note that the import path runs migrations against a temp copy (Step 10's deviation), so the team's real second file should be byte-identical before/after — worth diffing with `sha256sum` to confirm.

2. **Backup/restore drill.** Per §9 step 13's "backup/restore verification" line: rename the live MERCY `.db` to simulate corruption, restore from the most recent `.db.bak-*` sibling, confirm the app reopens it cleanly. Then deliberately interrupt a save (Ctrl+C mid-`saveFile`) and confirm the atomic-save guarantee from Step 7a holds — the on-disk file should reflect either the pre-save state or the post-save state, never a partial.

3. **Production tracking + reports against real production data** once the team's been logging shifts for a few days. Watch for: large date-range Per Target reports paginating correctly across many pages; the "(missing #id)" fallback firing if anyone deletes an employee with existing production records; UNIQUE-conflict messages being intelligible to the floor when they hit one.

4. **Report sanity-check loop with the team.** §12.2 Step 12's framing was "they don't know what they want yet — give them four reports and see what sticks." Step 13 is when they tell us which ones they actually use and what's missing. Likely candidates for Step 14+ if asked: charts (currently flagged as out-of-scope in §12.5 follow-ups), cross-referencing production with `parts.price` for revenue, or shift-lead signoff lines via `drawSignatureLine` (helper exists, unused so far).

5. **Cross-platform sanity** if anyone ever runs MERCY on macOS/Linux — `os.startfile` is Windows-only; the `utils.startfile` shim handles other platforms but it hasn't been exercised. Low priority unless the team needs it.

**Likely findings to expect.** Not predictions, just things experience says to watch for:
- **Performance on large legacy DBs.** All migrations have been tested on hand-crafted 2-3 record fixtures. Real BECKY files probably have hundreds of employees with years of attendance/PTO/notes; the v2→v3 migration's per-row UPDATE on `reviews.details`/`notes.details` could be slow. If it is, batching into a single `UPDATE` with a `CASE` expression is a faster swap.
- **Report column widths on real part/mixture names.** `drawTable` handles text wrapping via `_wrapText`, but if the team's part names are unusually long (>40 chars) the auto-computed equal column widths in the Summary report could look unbalanced. Custom `widths` lists are easy to add per-report if needed.
- **Date-range default of 30 days** on the production tab might not match the team's actual usage pattern (e.g. they may want to default to "current week" or "current pay period"). Trivial to change in `ProductionTab.__init__`.
- **`Database.toWrite` was retired in Step 7a** but `file_manager.saveFile` still iterates the dicts directly. Save performance on a fully-populated unified DB hasn't been measured against the original ANIKA/BECKY split-file performance — worth a back-of-envelope check.

**What's NOT in Step 13.** (a) Any new features — those are Step 14+ if the team requests them. (b) Style polish on existing reports unless the team flags something as unreadable. (c) The deferred items in §12.3 (bare `x == None` residuals, the DeMorgan-able compound at `file_manager.py:176`/`:447`, the `MainTab` class rename) — all explicitly out of scope and noted there.

**Touchpoints from prior steps worth remembering.**
- **Atomic save semantics** (Step 7a): `saveFile()` wraps `_saveFileBody()` in try/rollback/commit. Mid-save crash = on-disk file unchanged. Tested offscreen but not in anger against a real corruption scenario — Step 13's drill above is the place.
- **Migration backup files** (Step 8): `.db.bak-YYYY-MM-DD-HHMMSS` siblings are written before destructive DDL in `_migrateAnikaV1ToV2` / `_migrateBeckyV2ToV3`. They accumulate; nothing prunes them. If Step 13 surfaces concern about `.bak` clutter, an "older than N days" cleanup at startup is a reasonable Step 14 follow-up but explicitly not Step 13's job.
- **Import-merge keeps the source file untouched** (Step 10): `importOtherDb` runs migrations against a temp copy, then cleans up. The team's second `.db` is byte-identical before/after — confirm this against their real files via `sha256sum` as part of Step 13's check 1 above.
- **Smoke harness is the regression net.** All 7 checks pass at Step 12 commit. If Step 13 surfaces a fix, add a regression check to `smoke.py` (or extend an existing one) so future sessions can't regress it. The checks compose well — they all use the same `tempfile` / `MainWindow` / cleanup pattern.

---

*This document was prepared with Claude Code (claude-opus-4-6 / claude-sonnet-4-6) as a planning artifact; §12 is being maintained as implementation proceeds.*
