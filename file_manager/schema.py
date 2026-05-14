import sqlite3
from typing import TYPE_CHECKING

# Table-set fingerprints for format detection (§8.1 of MERGE_PLAN).
ANIKA_TABLES = {"globals", "materials", "mixtures", "packaging", "parts",
                "materialInventory", "partInventory"}
BECKY_TABLES = {"globals", "employees", "reviews", "training", "attendance",
                "PTO", "notes", "holidays", "observances"}
MERCY_EXTRA_TABLES = {"production"}
UNIFIED_TABLES = ANIKA_TABLES | BECKY_TABLES | MERCY_EXTRA_TABLES


class SchemaMixin:
    # Table-creation, version-stamp, and format-detect helpers shared by FileManager.
    # Operates on `self.dbFile` set up by the composed FileManager.

    if TYPE_CHECKING:
        # Attribute provided by the composed FileManager (see file_manager/__init__.py).
        dbFile: sqlite3.Connection | None

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
            "hours REAL DEFAULT 0, "
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
