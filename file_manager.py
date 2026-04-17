import sqlite3
import datetime

from app import MainWindow
from records import (
    Material, Mixture, Package, Part, MaterialInventoryRecord, PartInventoryRecord,
    Employee, EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB, EmployeePTODB, EmployeeNotesDB,
    EmployeeReview, EmployeeTrainingDate, EmployeePoint, EmployeePTORange, EmployeeNote, HolidayObservance
)

# Bumped whenever the unified schema changes. Step 4 establishes v1:
# the superset of the (still base64-encoded) ANIKA schema + the (still compound-shift) BECKY
# schema + the new production table. Schema normalization (§3.1) happens in Steps 8-9, which
# will bump this accordingly.
MERCY_DB_VERSION = 1

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
        # Pre-normalization ANIKA schema (still uses base64-encoded compound fields). Step 8
        # will migrate these to mixture_components / part_pads / part_misc and drop the dead
        # columns from `parts`.
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS globals(name PRIMARY KEY, value)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS mixtures(name PRIMARY KEY, materials, weights)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS packaging(name PRIMARY KEY, kind, cost)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS parts(name PRIMARY KEY, weight, mix, pressing, turning, loading, unloading, inspection, greenScrap, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, pad, padsPerBox, misc, price, sales)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")

    def _createBeckyTables(self):
        # Pre-normalization BECKY schema (shift still compound, details still base64). Step 9
        # will split `shift` into shift/fullTime and decode the text fields.
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS globals(name PRIMARY KEY, value)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS reviews(idNum, date, nextReview, details, UNIQUE(idNum, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        self.dbFile.execute("CREATE TABLE IF NOT EXISTS notes(idNum, date, time, details, UNIQUE(idNum, date, time))")
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

    # ---- initFile --------------------------------------------------------------------------

    def initFile(self):
        if self.filePath is None:
            raise RuntimeError('self.filePath is None')
        try:
            self.dbFile = sqlite3.connect(self.filePath)
            # WAL allows concurrent readers with a single writer; fine for <5 users (§8.6).
            self.dbFile.execute("PRAGMA journal_mode=WAL")

            res = self.dbFile.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = set(row[0] for row in res.fetchall() if not row[0].startswith("sqlite_"))
            print(f"Initialization: found {len(tables)} tables in {self.filePath}: {sorted(tables)}")

            # Case 1: Brand new (empty) DB -> create the full unified schema.
            if len(tables) == 0:
                self._createAnikaTables()
                self._createBeckyTables()
                self._createProductionTable()
                self._setDbVersion(MERCY_DB_VERSION)
                self.dbFile.commit()
                print(f" --> Created unified MERCY schema (db_version={MERCY_DB_VERSION})")
                return True

            dbVersion = self._getDbVersion()

            # Case 2: Already in unified MERCY format.
            if dbVersion is not None and UNIFIED_TABLES.issubset(tables):
                # `otherChem` column was added post-v8.0 in ANIKA; ensure it's present.
                cols = [row[1] for row in self.dbFile.execute("PRAGMA table_info(materials)").fetchall()]
                if 'otherChem' not in cols:
                    self.dbFile.execute("ALTER TABLE materials ADD COLUMN otherChem DEFAULT 0")
                self.dbFile.commit()
                # Future: add dbVersion < MERCY_DB_VERSION migrations here (Steps 8-11).
                return True

            # Case 3: Legacy ANIKA DB. Add empty employee + production tables, stamp version.
            # Schema normalization (mixture_components, part_pads, etc.) is deferred to Step 8.
            if ("materials" in tables and "parts" in tables) and ("employees" not in tables):
                print(f" --> Detected legacy ANIKA format. Adding empty employee + production "
                      f"tables. Full schema normalization will run in a later migration step.")
                cols = [row[1] for row in self.dbFile.execute("PRAGMA table_info(materials)").fetchall()]
                if 'otherChem' not in cols:
                    self.dbFile.execute("ALTER TABLE materials ADD COLUMN otherChem DEFAULT 0")
                self._createBeckyTables()
                self._createProductionTable()
                self._setDbVersion(MERCY_DB_VERSION)
                self.dbFile.commit()
                return True

            # Case 4: Legacy BECKY DB. Add empty product + production tables, stamp version.
            if ("employees" in tables and "PTO" in tables) and ("materials" not in tables):
                print(f" --> Detected legacy BECKY format. Adding empty product + production "
                      f"tables. Full schema normalization will run in a later migration step.")
                # Pre-notes BECKY DBs didn't have a `notes` table.
                if "notes" not in tables:
                    self.dbFile.execute("CREATE TABLE notes(idNum, date, time, details, UNIQUE(idNum, date, time))")
                self._createAnikaTables()
                self._createProductionTable()
                self._setDbVersion(MERCY_DB_VERSION)
                self.dbFile.commit()
                return True

            # Unknown format.
            print(f"Initialization error: unrecognized DB format in {self.filePath}")
            print(f" * Found tables: {sorted(tables)}")
            self.dbFile.close()
            return False
        except Exception as e:
            print(f"Initialization error: {repr(e)}")
            if self.dbFile is not None:
                self.dbFile.close()
            return False

    # ---- saveFile --------------------------------------------------------------------------

    def saveFile(self):
        if not ((not self.filePath == None) and (not self.dbFile == None)):
            raise RuntimeError('(not self.filePath == None) and (not self.dbFile == None)')
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
        print(f"Saving globals to {self.filePath}")
        for name in db.globals.getGlobals():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO globals VALUES (?, ?)", (name, getattr(db.globals, name)))
                print(f" * Saving {name} = {getattr(db.globals, name)}")
            except Exception as e:
                print(f" * Error saving {name} = {getattr(db.globals, name)}: {repr(e)}")

        def clearOld(dbName, currDict):
            if self.dbFile is None:
                raise RuntimeError('self.dbFile is None')
            res = self.dbFile.execute(f"SELECT name FROM {dbName}")
            deleted = [vals for vals in res.fetchall() if not vals[0] in currDict]
            if len(deleted) > 0:
                try:
                    self.dbFile.executemany(f"DELETE FROM {dbName} WHERE name=?", deleted)
                    print(f" * Deleting old entries {", ".join([f"{name[0]}" for name in deleted])}")
                except Exception as e:
                    print(f" * Error deleting old entries {", ".join([f"{name[0]}" for name in deleted])}: {repr(e)}")

        # --- ANIKA: materials / mixtures / packaging / parts / inventories ---

        print(f"Saving materials to {self.filePath}")
        for name in db.materials:
            vals = db.materials[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO materials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        clearOld("materials", db.materials)

        print(f"Saving mixtures to {self.filePath}")
        for name in db.mixtures:
            vals = db.mixtures[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO mixtures VALUES (?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        clearOld("mixtures", db.mixtures)

        print(f"Saving packaging to {self.filePath}")
        for name in db.packaging:
            vals = db.packaging[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO packaging VALUES (?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        clearOld("packaging", db.packaging)

        print(f"Saving parts to {self.filePath}")
        for name in db.parts:
            vals = db.parts[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        clearOld("parts", db.parts)

        print(f"Saving materials inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getMaterialTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO materialInventory VALUES (?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT name, date FROM materialInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].materials]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM materialInventory WHERE (name, date)=(?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        print(f"Saving parts inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getPartTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO partInventory VALUES (?, ?, ?, ?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT name, date FROM partInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].parts]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM partInventory WHERE (name, date)=(?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        # --- BECKY: employees / reviews / training / attendance / PTO / notes / holidays / observances ---

        print(f"Saving employees to {self.filePath}")
        for idNum in db.employees:
            vals = db.employees[idNum].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum FROM employees")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.employees]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM employees WHERE idNum=?", deleted)
                print(f" * Deleting old entries {", ".join([f"{idNum[0]}" for idNum in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"{idNum[0]}" for idNum in deleted])}: {repr(e)}")

        print(f"Saving reviews to {self.filePath}")
        for idNum in db.reviews:
            valsList = db.reviews[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO reviews VALUES (?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date FROM reviews")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.reviews or not datetime.date.fromisoformat(vals[1]) in db.reviews[vals[0]].reviews]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM reviews WHERE (idNum, date)=(?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        print(f"Saving training to {self.filePath}")
        for idNum in db.training:
            valsList = db.training[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO training VALUES (?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, training, date FROM training")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.training or not vals[1] in db.training[vals[0]].training or not datetime.date.fromisoformat(vals[2]) in db.training[vals[0]].training[vals[1]]]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM training WHERE (idNum, training, date)=(?, ?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        print(f"Saving attendance to {self.filePath}")
        for idNum in db.attendance:
            valsList = db.attendance[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO attendance VALUES (?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date FROM attendance")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.attendance or not datetime.date.fromisoformat(vals[1]) in db.attendance[vals[0]].points]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM attendance WHERE (idNum, date)=(?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        print(f"Saving PTO to {self.filePath}")
        for idNum in db.PTO:
            valsList = db.PTO[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO PTO VALUES (?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, start, end FROM PTO")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.PTO or not (datetime.date.fromisoformat(vals[1]), vals[2] if vals[2] in ["CARRY", "CASH", "DROP"] else datetime.date.fromisoformat(vals[2])) in db.PTO[vals[0]].PTO]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM PTO WHERE (idNum, start, end)=(?, ?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        print(f"Saving notes to {self.filePath}")
        for idNum in db.notes:
            valsList = db.notes[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO notes VALUES (?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date, time FROM notes")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.notes or not (datetime.date.fromisoformat(vals[1]), vals[2]) in db.notes[vals[0]].notes]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM notes WHERE (idNum, date, time)=(?, ?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}: {repr(e)}")

        print(f"Saving holidays to {self.filePath}")
        for vals in db.holidays.getDefaultTuples():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO holidays VALUES (?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT holiday FROM holidays")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.holidays.defaults]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM holidays WHERE holiday=?", deleted)
                print(f" * Deleting old entries {", ".join([f"{holiday[0]}" for holiday in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"{holiday[0]}" for holiday in deleted])}: {repr(e)}")

        print(f"Saving observances to {self.filePath}")
        for vals in db.holidays.getObservanceTuples():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO observances VALUES (?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT holiday, shift, date FROM observances")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[2]).year in db.holidays.observances or
                                                      not vals[0] in db.holidays.observances[datetime.date.fromisoformat(vals[2]).year] or
                                                      not vals[1] in db.holidays.observances[datetime.date.fromisoformat(vals[2]).year][vals[0]] or
                                                      not db.holidays.observances[datetime.date.fromisoformat(vals[2]).year][vals[0]][vals[1]].date.isoformat() == vals[2]]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM observances WHERE (holiday, shift, date)=(?, ?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({observance[0]}, {observance[1]}, {observance[2]})" for observance in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({observance[0]}, {observance[1]}, {observance[2]})" for observance in deleted])}: {repr(e)}")

    # ---- loadFile --------------------------------------------------------------------------

    def loadFile(self):
        if not ((not self.filePath == None) and (not self.dbFile == None)):
            raise RuntimeError('(not self.filePath == None) and (not self.dbFile == None)')
        from records import emptyDB
        self.mainApp.db = emptyDB()
        db = self.mainApp.db

        # --- globals (ANIKA cost parameters; ignore db_version on the load side) ---
        print(f"Loading globals from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM globals")
        for pair in res.fetchall():
            name, val = pair
            if name == "db_version":
                print(f" * (ignored on load) {name} = {val}")
                continue
            setattr(db.globals, name, val)
            print(f" * Loaded {name} = {val}")

        # --- ANIKA data ---

        print(f"Loading materials from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materials")
        for values in res.fetchall():
            material = Material("ERROR")
            material.fromTuple(values)
            db.materials[material.name] = material
            material.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {material}")

        print(f"Loading mixtures from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM mixtures")
        for values in res.fetchall():
            mixture = Mixture("ERROR")
            mixture.fromTuple(values)
            db.mixtures[mixture.name] = mixture
            mixture.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {mixture}")

        print(f"Loading packaging from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM packaging")
        for values in res.fetchall():
            package = Package("ERROR", None, None)
            package.fromTuple(values)
            db.packaging[package.name] = package
            package.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {package}")

        print(f"Loading parts from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM parts")
        for values in res.fetchall():
            part = Part("ERROR")
            part.fromTuple(values)
            db.parts[part.name] = part
            part.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {part}")

        print(f"Loading material inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materialInventory")
        for values in res.fetchall():
            rec = MaterialInventoryRecord()
            rec.fromTuple(values)
            db.addMaterialInventory(rec)
            print(f" * Loaded {values}")
            print(f" --> Loaded {rec}")

        print(f"Loading part inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM partInventory")
        for values in res.fetchall():
            rec = PartInventoryRecord()
            rec.fromTuple(values)
            db.addPartInventory(rec)
            print(f" * Loaded {values}")
            print(f" --> Loaded {rec}")

        # --- BECKY data ---

        print(f"Loading employees from {self.filePath}")
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

            print(f" * Loaded {values}")
            print(f" --> Loaded employee {employee.idNum}")

        print(f"Loading reviews from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM reviews")
        for values in res.fetchall():
            review = EmployeeReview()
            review.fromTuple(values)

            if review.idNum not in db.reviews:
                raise RuntimeError('review.idNum not in db.reviews')
            db.reviews[review.idNum].reviews[review.date] = review

            print(f" * Loaded {values}")
            print(f" --> Loaded review ({review.idNum}, {review.date})")

        print(f"Loading training from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM training")
        for values in res.fetchall():
            training = EmployeeTrainingDate()
            training.fromTuple(values)

            if training.idNum not in db.training:
                raise RuntimeError('training.idNum not in db.training')
            if not training.training in db.training[training.idNum].training:
                db.training[training.idNum].training[training.training] = {}
            db.training[training.idNum].training[training.training][training.date] = training

            print(f" * Loaded {values}")
            print(f" --> Loaded training ({training.idNum}, {training.training}, {training.date})")

        print(f"Loading attendance from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM attendance")
        for values in res.fetchall():
            point = EmployeePoint()
            point.fromTuple(values)

            if point.idNum not in db.attendance:
                raise RuntimeError('point.idNum not in db.attendance')
            db.attendance[point.idNum].points[point.date] = point

            print(f" * Loaded {values}")
            print(f" --> Loaded point ({point.idNum}, {point.date})")

        print(f"Loading PTO from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM PTO")
        for values in res.fetchall():
            pto = EmployeePTORange()
            pto.fromTuple(values)

            if pto.employee not in db.PTO:
                raise RuntimeError('pto.employee not in db.PTO')
            db.PTO[pto.employee].PTO[(pto.start, pto.end)] = pto

            print(f" * Loaded {values}")
            print(f" --> Loaded point ({pto.employee}, {pto.start}, {pto.end})")

        print(f"Loading notes from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM notes")
        for values in res.fetchall():
            note = EmployeeNote()
            note.fromTuple(values)

            if note.idNum not in db.notes:
                raise RuntimeError('note.idNum not in db.notes')
            db.notes[note.idNum].notes[(note.date, note.time)] = note

            print(f" * Loaded {values}")
            print(f" --> Loaded note ({note.idNum}, {note.date}, {note.time})")

        print(f"Loading holidays from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM holidays")
        for values in res.fetchall():
            holiday = values[0]
            month = values[1]

            db.holidays.defaults[holiday] = month

            print(f" * Loaded {values}")
            print(f" --> Loaded holiday {holiday}")

        print(f"Loading observances from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM observances")
        for values in res.fetchall():
            observance = HolidayObservance()
            observance.fromTuple(values)

            db.holidays.setObservance(observance)

            print(f" * Loaded {values}")
            print(f" --> Loaded observance ({observance.holiday}, {observance.date.isoformat()}, {observance.shift})")

    # ---- setFile ---------------------------------------------------------------------------

    def setFile(self, filePath):
        oldPath = self.filePath
        oldConn = self.dbFile
        self.filePath = filePath
        success = self.initFile()
        if success:
            if not oldConn == None:
                oldConn.close()
        else:
            print(f"Failed to initialize {filePath}")
            self.filePath = oldPath
            self.dbFile = oldConn
        return success
