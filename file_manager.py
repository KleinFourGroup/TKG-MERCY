import sqlite3
import datetime
import glob
import logging
import os
import shutil

from app import MainWindow
from records import (
    Material, Mixture, Package, Part, MaterialInventoryRecord, PartInventoryRecord,
    Employee, EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB, EmployeePTODB, EmployeeNotesDB,
    EmployeeReview, EmployeeTrainingDate, EmployeePoint, EmployeePTORange, EmployeeNote, HolidayObservance
)
from utils import stringToList, stringFromB64

# Bumped whenever the unified schema changes.
#   v1 — Step 4: superset schema with base64-encoded ANIKA compound columns and compound BECKY
#        shift column still in place.
#   v2 — Step 8: ANIKA schema normalized. `mixtures.materials`/`weights` replaced by
#        `mixture_components`; `parts.pad`/`padsPerBox`/`misc` replaced by `part_pads`/`part_misc`;
#        `parts.loading`/`unloading`/`inspection`/`greenScrap` dropped (§3.1, §3.2).
#   v3 — Step 9: BECKY schema normalized. `employees.shift` split into `shift INTEGER` +
#        `fullTime INTEGER`; `reviews.details` and `notes.details` stored as plain TEXT
#        (base64 wrapping removed); orphan rows in training/attendance/PTO swept out (§3.1, §3.3).
MERCY_DB_VERSION = 3

# Table-set fingerprints for format detection (§8.1 of MERGE_PLAN).
ANIKA_TABLES = {"globals", "materials", "mixtures", "packaging", "parts",
                "materialInventory", "partInventory"}
BECKY_TABLES = {"globals", "employees", "reviews", "training", "attendance",
                "PTO", "notes", "holidays", "observances"}
MERCY_EXTRA_TABLES = {"production"}
UNIFIED_TABLES = ANIKA_TABLES | BECKY_TABLES | MERCY_EXTRA_TABLES

class FileManager:
    def __init__(self, mainApp: MainWindow) -> None:
        self.mainApp = mainApp
        self.filePath = None
        self.dbFile = None

    # ---- schema creation helpers -----------------------------------------------------------

    def _createAnikaTables(self):
        # v2 normalized ANIKA schema. Base64-encoded compound columns replaced by child
        # tables (mixture_components, part_pads, part_misc); dead columns dropped from
        # `parts` (§3.1, §3.2).
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS globals(name PRIMARY KEY, value)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS mixtures(name PRIMARY KEY)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS packaging(name PRIMARY KEY, kind, cost)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")

    def _createBeckyTables(self):
        # v3 normalized BECKY schema. `employees.shift` split into separate shift/fullTime
        # INTEGER cols; `reviews.details` / `notes.details` stored as plain TEXT (§3.1).
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS globals(name PRIMARY KEY, value)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS holidays(holiday PRIMARY KEY, month)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS observances(holiday, shift, date, UNIQUE(holiday, shift, date))")

    def _createProductionTable(self):
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        self.dbFile.execute(
            "CREATE TABLE IF NOT EXISTS production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, "
            "date TEXT, "
            "shift INTEGER, "
            "targetType TEXT, "
            "targetName TEXT, "
            "action TEXT, "
            "quantity REAL, "
            "scrapQuantity REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )

    def _setDbVersion(self, version: int):
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        self.dbFile.execute("INSERT OR REPLACE INTO globals VALUES ('db_version', ?)", (version,))

    def _getDbVersion(self):
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        try:
            row = self.dbFile.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        try:
            return int(row[0])
        except (ValueError, TypeError):
            return None

    def _backupDbFile(self):
        # Make a sibling copy before running a destructive migration (§8.2). Timestamp
        # down to the second so same-day re-runs don't overwrite each other.
        # Deliberately not checkpointing the WAL first: (a) a checkpoint with an open
        # write transaction raises "database table is locked", and (b) uncommitted
        # writes are in the WAL, not the main .db file — so copying the main file
        # captures exactly the last-committed state, which is what we want for
        # rollback. If migration later fails, closing without commit leaves the .db
        # file identical to this backup.
        if self.filePath is None:
            raise RuntimeError('self.filePath is None')
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        backupPath = f"{self.filePath}.bak-{stamp}"
        shutil.copy2(self.filePath, backupPath)
        logging.info(f" --> Backup written to {backupPath}")
        return backupPath

    def _migrateAnikaV1ToV2(self):
        # ANIKA schema normalization (§3.1, §3.2). Decode base64 compound columns into
        # mixture_components / part_pads / part_misc; drop dead columns from `parts`.
        # Runs inside the outer initFile transaction, so a failure rolls back cleanly.
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        logging.info(" --> Running ANIKA v1->v2 migration: normalize compound columns")
        self._backupDbFile()

        # --- mixtures ---
        mixRows = self.dbFile.execute("SELECT name, materials, weights FROM mixtures").fetchall()
        self.dbFile.execute(
            "CREATE TABLE IF NOT EXISTS mixture_components("
            "mixture, material, weight REAL, sort_order INTEGER, "
            "UNIQUE(mixture, material))"
        )
        for (mixName, matsEnc, wtsEnc) in mixRows:
            materials = stringToList(matsEnc, str) if matsEnc else []
            weights = stringToList(wtsEnc, float) if wtsEnc else []
            if len(materials) != len(weights):
                raise RuntimeError(
                    f"Mixture {mixName!r}: materials ({len(materials)}) / weights ({len(weights)}) length mismatch"
                )
            for i, (mat, wt) in enumerate(zip(materials, weights)):
                self.dbFile.execute(
                    "INSERT OR REPLACE INTO mixture_components VALUES (?, ?, ?, ?)",
                    (mixName, mat, wt, i)
                )

        self.dbFile.execute("CREATE TABLE mixtures_new(name PRIMARY KEY)")
        self.dbFile.execute("INSERT INTO mixtures_new (name) SELECT name FROM mixtures")
        self.dbFile.execute("DROP TABLE mixtures")
        self.dbFile.execute("ALTER TABLE mixtures_new RENAME TO mixtures")

        # --- parts ---
        partRows = self.dbFile.execute(
            "SELECT name, pad, padsPerBox, misc FROM parts"
        ).fetchall()
        self.dbFile.execute(
            "CREATE TABLE IF NOT EXISTS part_pads("
            "part, pad, padsPerBox INTEGER, sort_order INTEGER, "
            "UNIQUE(part, pad))"
        )
        self.dbFile.execute(
            "CREATE TABLE IF NOT EXISTS part_misc("
            "part, item, sort_order INTEGER, "
            "UNIQUE(part, item))"
        )
        for (partName, padEnc, ppbEnc, miscEnc) in partRows:
            pads = stringToList(padEnc, str) if padEnc else []
            ppbs = stringToList(ppbEnc, int) if ppbEnc else []
            miscs = stringToList(miscEnc, str) if miscEnc else []
            if len(pads) != len(ppbs):
                raise RuntimeError(
                    f"Part {partName!r}: pad ({len(pads)}) / padsPerBox ({len(ppbs)}) length mismatch"
                )
            for i, (pad, ppb) in enumerate(zip(pads, ppbs)):
                self.dbFile.execute(
                    "INSERT OR REPLACE INTO part_pads VALUES (?, ?, ?, ?)",
                    (partName, pad, ppb, i)
                )
            for i, item in enumerate(miscs):
                self.dbFile.execute(
                    "INSERT OR REPLACE INTO part_misc VALUES (?, ?, ?)",
                    (partName, item, i)
                )

        # Recreate `parts` without pad/padsPerBox/misc (now in child tables) and without
        # loading/unloading/inspection/greenScrap (dead per §3.2). Name columns explicitly —
        # SELECT * across a shape change would silently misalign.
        self.dbFile.execute(
            "CREATE TABLE parts_new("
            "name PRIMARY KEY, weight, mix, pressing, turning, "
            "fireScrap, box, piecesPerBox, pallet, boxesPerPallet, "
            "price, sales)"
        )
        self.dbFile.execute(
            "INSERT INTO parts_new "
            "(name, weight, mix, pressing, turning, fireScrap, "
            "box, piecesPerBox, pallet, boxesPerPallet, price, sales) "
            "SELECT name, weight, mix, pressing, turning, fireScrap, "
            "box, piecesPerBox, pallet, boxesPerPallet, price, sales "
            "FROM parts"
        )
        self.dbFile.execute("DROP TABLE parts")
        self.dbFile.execute("ALTER TABLE parts_new RENAME TO parts")

        self._setDbVersion(2)
        logging.info(" --> ANIKA v1->v2 migration complete")

    def _migrateBeckyV2ToV3(self):
        # BECKY schema normalization (§3.1, §3.3). Split `employees.shift` compound string
        # into shift + fullTime INTEGER cols; decode base64-wrapped `reviews.details` /
        # `notes.details` into plain TEXT; sweep orphan rows from training / attendance /
        # PTO whose idNum no longer references a valid employee (§3.3 — `updateEmployee`
        # bug in pre-7a BECKY code could leave dangling references).
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        logging.info(" --> Running BECKY v2->v3 migration: normalize shift / details / orphan sweep")
        self._backupDbFile()

        # --- employees: split compound shift column ---
        empRows = self.dbFile.execute(
            "SELECT idNum, lastName, firstName, anniversary, role, shift, "
            "addressLine1, addressLine2, addressCity, addressState, addressZip, "
            "addressTel, addressEmail, status FROM employees"
        ).fetchall()
        parsedRows = []
        for row in empRows:
            shiftVal = row[5]
            if isinstance(shiftVal, int):
                # Pre-compound legacy format (older than "shift|fullTime" convention):
                # treat as shift only, default fullTime=1.
                shift, fullTime = shiftVal, 1
            elif isinstance(shiftVal, str):
                parts = shiftVal.split("|")
                if len(parts) != 2:
                    raise RuntimeError(f"Employee {row[0]}: malformed shift {shiftVal!r}")
                shift, fullTime = int(parts[0]), int(parts[1])
            else:
                raise RuntimeError(f"Employee {row[0]}: unrecognized shift type {type(shiftVal).__name__}")
            parsedRows.append((row[0], row[1], row[2], row[3], row[4], shift, fullTime, *row[6:]))

        self.dbFile.execute(
            "CREATE TABLE employees_new("
            "idNum PRIMARY KEY, lastName, firstName, anniversary, role, "
            "shift INTEGER, fullTime INTEGER, "
            "addressLine1, addressLine2, addressCity, addressState, addressZip, "
            "addressTel, addressEmail, status)"
        )
        if parsedRows:
            self.dbFile.executemany(
                "INSERT INTO employees_new VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                parsedRows
            )
        self.dbFile.execute("DROP TABLE employees")
        self.dbFile.execute("ALTER TABLE employees_new RENAME TO employees")

        # --- reviews.details: decode base64 in place ---
        reviewRows = self.dbFile.execute("SELECT idNum, date, details FROM reviews").fetchall()
        for (idNum, date, encDetails) in reviewRows:
            plain = stringFromB64(encDetails) if encDetails else ""
            self.dbFile.execute(
                "UPDATE reviews SET details=? WHERE idNum=? AND date=?",
                (plain, idNum, date)
            )

        # --- notes.details: decode base64 in place ---
        noteRows = self.dbFile.execute("SELECT idNum, date, time, details FROM notes").fetchall()
        for (idNum, date, time, encDetails) in noteRows:
            plain = stringFromB64(encDetails) if encDetails else ""
            self.dbFile.execute(
                "UPDATE notes SET details=? WHERE idNum=? AND date=? AND time=?",
                (plain, idNum, date, time)
            )

        # --- orphan sweep on training / attendance / PTO ---
        validIds = set(row[0] for row in self.dbFile.execute("SELECT idNum FROM employees").fetchall())

        def sweepOrphans(table: str, keyCols: tuple[str, ...]):
            if self.dbFile is None:
                raise RuntimeError('self.dbFile is None')
            colList = ", ".join(keyCols)
            rows = self.dbFile.execute(f"SELECT {colList} FROM {table}").fetchall()
            orphans = [r for r in rows if r[0] not in validIds]
            if orphans:
                logging.info(f" --> Removing {len(orphans)} orphan row(s) from {table}: {orphans}")
                whereClause = " AND ".join(f"{c}=?" for c in keyCols)
                self.dbFile.executemany(f"DELETE FROM {table} WHERE {whereClause}", orphans)

        sweepOrphans("training", ("idNum", "training", "date"))
        sweepOrphans("attendance", ("idNum", "date"))
        sweepOrphans("PTO", ("idNum", "start", "end"))

        self._setDbVersion(3)
        logging.info(" --> BECKY v2->v3 migration complete")

    # ---- initFile --------------------------------------------------------------------------

    def _detectDbFormat(self, tables: set[str]) -> str:
        # Classify a .db by its table set. Shared between initFile and the importer so both
        # agree on which of the four recognized shapes a given file is. Returns one of:
        #   "empty"        — no tables; brand-new file.
        #   "mercy"        — already unified MERCY (may still be an older db_version).
        #   "legacy_anika" — ANIKA-only file; no BECKY tables.
        #   "legacy_becky" — BECKY-only file; no ANIKA tables.
        #   "unknown"      — none of the above.
        if len(tables) == 0:
            return "empty"
        if UNIFIED_TABLES.issubset(tables):
            return "mercy"
        if ("materials" in tables and "parts" in tables) and ("employees" not in tables):
            return "legacy_anika"
        if ("employees" in tables and "PTO" in tables) and ("materials" not in tables):
            return "legacy_becky"
        return "unknown"

    def initFile(self):
        if self.filePath is None:
            raise RuntimeError('self.filePath is None')
        try:
            self.dbFile = sqlite3.connect(self.filePath)
            # WAL allows concurrent readers with a single writer; fine for <5 users (§8.6).
            self.dbFile.execute("PRAGMA journal_mode=WAL")

            res = self.dbFile.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = set(row[0] for row in res.fetchall() if not row[0].startswith("sqlite_"))
            logging.info(f"Initialization: found {len(tables)} tables in {self.filePath}: {sorted(tables)}")

            fmt = self._detectDbFormat(tables)

            # Case 1: Brand new (empty) DB -> create the full unified schema.
            if fmt == "empty":
                self._createAnikaTables()
                self._createBeckyTables()
                self._createProductionTable()
                self._setDbVersion(MERCY_DB_VERSION)
                self.dbFile.commit()
                logging.info(f" --> Created unified MERCY schema (db_version={MERCY_DB_VERSION})")
                return True

            # Case 2: Already in unified MERCY format.
            if fmt == "mercy":
                dbVersion = self._getDbVersion()
                # `otherChem` column was added post-v8.0 in ANIKA; ensure it's present.
                cols = [row[1] for row in self.dbFile.execute("PRAGMA table_info(materials)").fetchall()]
                if 'otherChem' not in cols:
                    self.dbFile.execute("ALTER TABLE materials ADD COLUMN otherChem DEFAULT 0")
                if dbVersion is not None and dbVersion < 2:
                    self._migrateAnikaV1ToV2()
                if dbVersion is not None and dbVersion < 3:
                    self._migrateBeckyV2ToV3()
                self.dbFile.commit()
                return True

            # Case 3: Legacy ANIKA DB. Add empty employee + production tables (at v3 shape
            # since they're empty — no BECKY migration needed), then run the ANIKA v1->v2
            # normalization on the existing ANIKA tables, then stamp v3.
            if fmt == "legacy_anika":
                logging.info(f" --> Detected legacy ANIKA format. Adding empty employee + production "
                             f"tables, then normalizing ANIKA schema to v2.")
                cols = [row[1] for row in self.dbFile.execute("PRAGMA table_info(materials)").fetchall()]
                if 'otherChem' not in cols:
                    self.dbFile.execute("ALTER TABLE materials ADD COLUMN otherChem DEFAULT 0")
                self._createBeckyTables()
                self._createProductionTable()
                # Stamp v1 first so _migrateAnikaV1ToV2's version update from 1->2 is meaningful
                # if the migration throws partway; the outer try/except will still close the
                # connection without committing, leaving the original file untouched.
                self._setDbVersion(1)
                self._migrateAnikaV1ToV2()
                # No BECKY data to migrate — the tables we just created are already v3 shape.
                self._setDbVersion(MERCY_DB_VERSION)
                self.dbFile.commit()
                return True

            # Case 4: Legacy BECKY DB. Add empty product + production tables (at v2-equivalent
            # ANIKA shape since Step 8 normalized the create path), then run the BECKY v2->v3
            # normalization on the existing BECKY tables.
            if fmt == "legacy_becky":
                logging.info(f" --> Detected legacy BECKY format. Adding empty product + production "
                             f"tables, then normalizing BECKY schema to v3.")
                # Pre-notes BECKY DBs didn't have a `notes` table. Create with v2 shape (plain
                # `details` column) so the base64 decode pass finds no rows to update.
                if "notes" not in tables:
                    self.dbFile.execute("CREATE TABLE notes(idNum, date, time, details, UNIQUE(idNum, date, time))")
                self._createAnikaTables()
                self._createProductionTable()
                # Stamp v2 so that if the BECKY migration throws partway, the outer try/except
                # closes the connection without committing and leaves the file untouched.
                self._setDbVersion(2)
                self._migrateBeckyV2ToV3()
                self.dbFile.commit()
                return True

            # Unknown format.
            logging.error(f"Initialization error: unrecognized DB format in {self.filePath}")
            logging.info(f" * Found tables: {sorted(tables)}")
            self.dbFile.close()
            return False
        except Exception as e:
            logging.error(f"Initialization error: {repr(e)}")
            if self.dbFile is not None:
                self.dbFile.close()
            return False

    # ---- saveFile --------------------------------------------------------------------------

    def saveFile(self):
        if not ((self.filePath is not None) and (self.dbFile is not None)):
            raise RuntimeError('(self.filePath is not None) and (self.dbFile is not None)')
        # Atomic save: the body below runs as a single SQLite transaction.
        # Any exception rolls the entire save back, leaving the DB file
        # unchanged (§3.4 of MERGE_PLAN.md).
        try:
            self._saveFileBody()
        except Exception:
            self.dbFile.rollback()
            raise
        self.dbFile.commit()

    def _saveFileBody(self):
        db = self.mainApp.db

        # --- globals (ANIKA cost parameters; db_version is preserved separately) ---
        logging.info(f"Saving globals to {self.filePath}")
        for name in db.globals.getGlobals():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO globals VALUES (?, ?)", (name, getattr(db.globals, name)))
                logging.info(f" * Saving {name} = {getattr(db.globals, name)}")
            except Exception as e:
                logging.error(f" * Error saving {name} = {getattr(db.globals, name)}: {repr(e)}")

        def clearOld(dbName, currDict):
            if self.dbFile is None:
                raise RuntimeError('self.dbFile is None')
            res = self.dbFile.execute(f"SELECT name FROM {dbName}")
            deleted = [vals for vals in res.fetchall() if not vals[0] in currDict]
            if len(deleted) > 0:
                try:
                    self.dbFile.executemany(f"DELETE FROM {dbName} WHERE name=?", deleted)
                    logging.info(f" * Deleting old entries {", ".join([f"{name[0]}" for name in deleted])}")
                except Exception as e:
                    logging.error(f" * Error deleting old entries {", ".join([f"{name[0]}" for name in deleted])}: {repr(e)}")

        # --- ANIKA: materials / mixtures / packaging / parts / inventories ---

        logging.info(f"Saving materials to {self.filePath}")
        for name in db.materials:
            vals = db.materials[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO materials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("materials", db.materials)

        logging.info(f"Saving mixtures to {self.filePath}")
        for name in db.mixtures:
            vals = db.mixtures[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO mixtures VALUES (?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("mixtures", db.mixtures)

        logging.info(f"Saving mixture components to {self.filePath}")
        # Strategy: for each in-memory mixture, wipe its child rows and re-insert. Then
        # orphan-clean any child rows whose mixture parent no longer exists.
        for name in db.mixtures:
            self.dbFile.execute("DELETE FROM mixture_components WHERE mixture=?", (name,))
            for vals in db.mixtures[name].getComponentTuples():
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO mixture_components VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")
        res = self.dbFile.execute("SELECT mixture, material FROM mixture_components")
        orphans = [row for row in res.fetchall() if row[0] not in db.mixtures]
        if len(orphans) > 0:
            try:
                self.dbFile.executemany("DELETE FROM mixture_components WHERE (mixture, material)=(?, ?)", orphans)
                logging.info(f" * Deleting orphan components {orphans}")
            except Exception as e:
                logging.error(f" * Error deleting orphan components {orphans}: {repr(e)}")

        logging.info(f"Saving packaging to {self.filePath}")
        for name in db.packaging:
            vals = db.packaging[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO packaging VALUES (?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("packaging", db.packaging)

        logging.info(f"Saving parts to {self.filePath}")
        for name in db.parts:
            vals = db.parts[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("parts", db.parts)

        logging.info(f"Saving part pads to {self.filePath}")
        for name in db.parts:
            self.dbFile.execute("DELETE FROM part_pads WHERE part=?", (name,))
            for vals in db.parts[name].getPadTuples():
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO part_pads VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")
        res = self.dbFile.execute("SELECT part, pad FROM part_pads")
        orphans = [row for row in res.fetchall() if row[0] not in db.parts]
        if len(orphans) > 0:
            try:
                self.dbFile.executemany("DELETE FROM part_pads WHERE (part, pad)=(?, ?)", orphans)
                logging.info(f" * Deleting orphan part pads {orphans}")
            except Exception as e:
                logging.error(f" * Error deleting orphan part pads {orphans}: {repr(e)}")

        logging.info(f"Saving part misc to {self.filePath}")
        for name in db.parts:
            self.dbFile.execute("DELETE FROM part_misc WHERE part=?", (name,))
            for vals in db.parts[name].getMiscTuples():
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO part_misc VALUES (?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")
        res = self.dbFile.execute("SELECT part, item FROM part_misc")
        orphans = [row for row in res.fetchall() if row[0] not in db.parts]
        if len(orphans) > 0:
            try:
                self.dbFile.executemany("DELETE FROM part_misc WHERE (part, item)=(?, ?)", orphans)
                logging.info(f" * Deleting orphan part misc {orphans}")
            except Exception as e:
                logging.error(f" * Error deleting orphan part misc {orphans}: {repr(e)}")

        logging.info(f"Saving materials inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getMaterialTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO materialInventory VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT name, date FROM materialInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].materials]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM materialInventory WHERE (name, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving parts inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getPartTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO partInventory VALUES (?, ?, ?, ?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT name, date FROM partInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].parts]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM partInventory WHERE (name, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        # --- BECKY: employees / reviews / training / attendance / PTO / notes / holidays / observances ---

        logging.info(f"Saving employees to {self.filePath}")
        for idNum in db.employees:
            vals = db.employees[idNum].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum FROM employees")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.employees]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM employees WHERE idNum=?", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"{idNum[0]}" for idNum in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"{idNum[0]}" for idNum in deleted])}: {repr(e)}")

        logging.info(f"Saving reviews to {self.filePath}")
        for idNum in db.reviews:
            valsList = db.reviews[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO reviews VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date FROM reviews")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.reviews or not datetime.date.fromisoformat(vals[1]) in db.reviews[vals[0]].reviews]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM reviews WHERE (idNum, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving training to {self.filePath}")
        for idNum in db.training:
            valsList = db.training[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO training VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, training, date FROM training")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.training or not vals[1] in db.training[vals[0]].training or not datetime.date.fromisoformat(vals[2]) in db.training[vals[0]].training[vals[1]]]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM training WHERE (idNum, training, date)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving attendance to {self.filePath}")
        for idNum in db.attendance:
            valsList = db.attendance[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO attendance VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date FROM attendance")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.attendance or not datetime.date.fromisoformat(vals[1]) in db.attendance[vals[0]].points]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM attendance WHERE (idNum, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving PTO to {self.filePath}")
        for idNum in db.PTO:
            valsList = db.PTO[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO PTO VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, start, end FROM PTO")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.PTO or not (datetime.date.fromisoformat(vals[1]), vals[2] if vals[2] in ["CARRY", "CASH", "DROP"] else datetime.date.fromisoformat(vals[2])) in db.PTO[vals[0]].PTO]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM PTO WHERE (idNum, start, end)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving notes to {self.filePath}")
        for idNum in db.notes:
            valsList = db.notes[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO notes VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date, time FROM notes")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.notes or not (datetime.date.fromisoformat(vals[1]), vals[2]) in db.notes[vals[0]].notes]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM notes WHERE (idNum, date, time)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving holidays to {self.filePath}")
        for vals in db.holidays.getDefaultTuples():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO holidays VALUES (?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT holiday FROM holidays")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.holidays.defaults]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM holidays WHERE holiday=?", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"{holiday[0]}" for holiday in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"{holiday[0]}" for holiday in deleted])}: {repr(e)}")

        logging.info(f"Saving observances to {self.filePath}")
        for vals in db.holidays.getObservanceTuples():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO observances VALUES (?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT holiday, shift, date FROM observances")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[2]).year in db.holidays.observances or
                                                      not vals[0] in db.holidays.observances[datetime.date.fromisoformat(vals[2]).year] or
                                                      not vals[1] in db.holidays.observances[datetime.date.fromisoformat(vals[2]).year][vals[0]] or
                                                      not db.holidays.observances[datetime.date.fromisoformat(vals[2]).year][vals[0]][vals[1]].date.isoformat() == vals[2]]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM observances WHERE (holiday, shift, date)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({observance[0]}, {observance[1]}, {observance[2]})" for observance in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({observance[0]}, {observance[1]}, {observance[2]})" for observance in deleted])}: {repr(e)}")

    # ---- loadFile --------------------------------------------------------------------------

    def loadFile(self):
        if not ((self.filePath is not None) and (self.dbFile is not None)):
            raise RuntimeError('(self.filePath is not None) and (self.dbFile is not None)')
        from records import emptyDB
        self.mainApp.db = emptyDB()
        self._loadIntoDb(self.mainApp.db)

    def _loadIntoDb(self, db):
        # Read every table from self.dbFile into the provided Database. Split out from
        # loadFile so the importer can populate a throwaway `emptyDB()` without
        # clobbering self.mainApp.db.
        if not ((self.filePath is not None) and (self.dbFile is not None)):
            raise RuntimeError('(self.filePath is not None) and (self.dbFile is not None)')

        # --- globals (ANIKA cost parameters; ignore db_version on the load side) ---
        logging.info(f"Loading globals from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM globals")
        for pair in res.fetchall():
            name, val = pair
            if name == "db_version":
                logging.info(f" * (ignored on load) {name} = {val}")
                continue
            setattr(db.globals, name, val)
            logging.info(f" * Loaded {name} = {val}")

        # --- ANIKA data ---

        logging.info(f"Loading materials from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materials")
        for values in res.fetchall():
            material = Material("ERROR")
            material.fromTuple(values)
            db.materials[material.name] = material
            material.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {material}")

        logging.info(f"Loading mixtures from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM mixtures")
        for values in res.fetchall():
            mixture = Mixture("ERROR")
            mixture.fromTuple(values)
            db.mixtures[mixture.name] = mixture
            mixture.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {mixture}")

        logging.info(f"Loading mixture components from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT mixture, material, weight, sort_order FROM mixture_components "
            "ORDER BY mixture, sort_order"
        )
        for (mixtureName, material, weight, _sort) in res.fetchall():
            if mixtureName not in db.mixtures:
                raise RuntimeError(f'mixture_components row references missing mixture {mixtureName!r}')
            db.mixtures[mixtureName].add(material, weight)
            logging.info(f" * Loaded component ({mixtureName}, {material}, {weight})")

        logging.info(f"Loading packaging from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM packaging")
        for values in res.fetchall():
            package = Package("ERROR", None, None)
            package.fromTuple(values)
            db.packaging[package.name] = package
            package.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {package}")

        logging.info(f"Loading parts from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM parts")
        for values in res.fetchall():
            part = Part("ERROR")
            part.fromTuple(values)
            db.parts[part.name] = part
            part.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {part}")

        logging.info(f"Loading part pads from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT part, pad, padsPerBox, sort_order FROM part_pads "
            "ORDER BY part, sort_order"
        )
        for (partName, pad, padsPerBox, _sort) in res.fetchall():
            if partName not in db.parts:
                raise RuntimeError(f'part_pads row references missing part {partName!r}')
            if db.parts[partName].pad is None:
                db.parts[partName].pad = []
            if db.parts[partName].padsPerBox is None:
                db.parts[partName].padsPerBox = []
            db.parts[partName].pad.append(pad)
            db.parts[partName].padsPerBox.append(padsPerBox)
            logging.info(f" * Loaded pad ({partName}, {pad}, {padsPerBox})")

        logging.info(f"Loading part misc from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT part, item, sort_order FROM part_misc "
            "ORDER BY part, sort_order"
        )
        for (partName, item, _sort) in res.fetchall():
            if partName not in db.parts:
                raise RuntimeError(f'part_misc row references missing part {partName!r}')
            db.parts[partName].misc.append(item)
            logging.info(f" * Loaded misc ({partName}, {item})")

        logging.info(f"Loading material inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materialInventory")
        for values in res.fetchall():
            rec = MaterialInventoryRecord()
            rec.fromTuple(values)
            db.addMaterialInventory(rec)
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {rec}")

        logging.info(f"Loading part inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM partInventory")
        for values in res.fetchall():
            rec = PartInventoryRecord()
            rec.fromTuple(values)
            db.addPartInventory(rec)
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {rec}")

        # --- BECKY data ---

        logging.info(f"Loading employees from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM employees")
        for values in res.fetchall():
            employee = Employee()
            employee.fromTuple(values)

            db.addEmployee(employee)
            reviews = EmployeeReviewsDB(employee.idNum)
            db.addEmployeeReviews(reviews)
            training = EmployeeTrainingDB(employee.idNum)
            db.addEmployeeTraining(training)
            points = EmployeePointsDB(employee.idNum)
            db.addEmployeePoints(points)
            PTO = EmployeePTODB(employee.idNum)
            db.addEmployeePTO(PTO)
            notes = EmployeeNotesDB(employee.idNum)
            db.addEmployeeNotes(notes)

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded employee {employee.idNum}")

        logging.info(f"Loading reviews from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM reviews")
        for values in res.fetchall():
            review = EmployeeReview()
            review.fromTuple(values)

            if review.idNum not in db.reviews:
                raise RuntimeError('review.idNum not in db.reviews')
            db.reviews[review.idNum].reviews[review.date] = review

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded review ({review.idNum}, {review.date})")

        logging.info(f"Loading training from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM training")
        for values in res.fetchall():
            training = EmployeeTrainingDate()
            training.fromTuple(values)

            if training.idNum not in db.training:
                raise RuntimeError('training.idNum not in db.training')
            if not training.training in db.training[training.idNum].training:
                db.training[training.idNum].training[training.training] = {}
            db.training[training.idNum].training[training.training][training.date] = training

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded training ({training.idNum}, {training.training}, {training.date})")

        logging.info(f"Loading attendance from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM attendance")
        for values in res.fetchall():
            point = EmployeePoint()
            point.fromTuple(values)

            if point.idNum not in db.attendance:
                raise RuntimeError('point.idNum not in db.attendance')
            db.attendance[point.idNum].points[point.date] = point

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded point ({point.idNum}, {point.date})")

        logging.info(f"Loading PTO from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM PTO")
        for values in res.fetchall():
            pto = EmployeePTORange()
            pto.fromTuple(values)

            if pto.employee not in db.PTO:
                raise RuntimeError('pto.employee not in db.PTO')
            db.PTO[pto.employee].PTO[(pto.start, pto.end)] = pto

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded point ({pto.employee}, {pto.start}, {pto.end})")

        logging.info(f"Loading notes from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM notes")
        for values in res.fetchall():
            note = EmployeeNote()
            note.fromTuple(values)

            if note.idNum not in db.notes:
                raise RuntimeError('note.idNum not in db.notes')
            db.notes[note.idNum].notes[(note.date, note.time)] = note

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded note ({note.idNum}, {note.date}, {note.time})")

        logging.info(f"Loading holidays from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM holidays")
        for values in res.fetchall():
            holiday = values[0]
            month = values[1]

            db.holidays.defaults[holiday] = month

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded holiday {holiday}")

        logging.info(f"Loading observances from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM observances")
        for values in res.fetchall():
            observance = HolidayObservance()
            observance.fromTuple(values)

            db.holidays.setObservance(observance)

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded observance ({observance.holiday}, {observance.date.isoformat()}, {observance.shift})")

    # ---- setFile ---------------------------------------------------------------------------

    def setFile(self, filePath):
        oldPath = self.filePath
        oldConn = self.dbFile
        self.filePath = filePath
        success = self.initFile()
        if success:
            if oldConn is not None:
                oldConn.close()
        else:
            logging.info(f"Failed to initialize {filePath}")
            self.filePath = oldPath
            self.dbFile = oldConn
        return success

    # ---- importOtherDb ---------------------------------------------------------------------

    def importOtherDb(self, srcPath: str):
        # Read a second .db (legacy ANIKA, legacy BECKY, or unified MERCY) into a fresh
        # throwaway Database without touching the currently-open DB or the source file.
        # Returns (otherDb, fmt) on success or (None, "unknown" | "error") on failure.
        #
        # The source file is copied to a temp path first so any migration writes land on
        # the copy; the user's second .db is never mutated (§12.5(c)). The temp copy and
        # its WAL sidecars are cleaned up before returning.
        import tempfile
        from records import emptyDB

        tmpFd, tmpPath = tempfile.mkstemp(suffix=".db")
        os.close(tmpFd)
        try:
            shutil.copy2(srcPath, tmpPath)
        except OSError as e:
            logging.error(f"Import error: could not copy {srcPath} to temp: {repr(e)}")
            try:
                os.unlink(tmpPath)
            except OSError:
                pass
            return None, "error"

        # Use a separate FileManager for the temp copy so its own backup-before-migration
        # logic runs against the copy, and any state on `self` is untouched.
        tmpFM = FileManager(self.mainApp)
        success = tmpFM.setFile(tmpPath)
        if not success:
            logging.error(f"Import error: unrecognized DB format in {srcPath}")
            _cleanupTempDb(tmpPath)
            return None, "unknown"

        otherDb = emptyDB()
        try:
            tmpFM._loadIntoDb(otherDb)
        finally:
            if tmpFM.dbFile is not None:
                tmpFM.dbFile.close()
            _cleanupTempDb(tmpPath)

        return otherDb, "ok"


def _cleanupTempDb(tmpPath: str):
    # Remove the temp DB file plus its WAL/SHM sidecars. Best-effort — a leftover temp
    # file is non-fatal, and Windows may hold the handle briefly after close().
    for suffix in ("", "-wal", "-shm"):
        p = tmpPath + suffix
        if os.path.exists(p):
            try:
                os.unlink(p)
            except OSError as e:
                logging.info(f"Import cleanup: could not remove {p}: {repr(e)}")
    # Also sweep any `.bak-*` sibling files the temp migration produced.
    for p in glob.glob(f"{tmpPath}.bak-*"):
        try:
            os.unlink(p)
        except OSError:
            pass
