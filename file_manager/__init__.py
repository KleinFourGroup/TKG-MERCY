import logging
import sqlite3

from app import MainWindow
from .schema import (
    SchemaMixin,
    ANIKA_TABLES, BECKY_TABLES, MERCY_EXTRA_TABLES, UNIFIED_TABLES,
)
from .migrate import MigrateMixin
from .save import SaveMixin
from .load import LoadMixin
from .import_db import ImportMixin

# Bumped whenever the unified schema changes.
#   v1 — Step 4: superset schema with base64-encoded ANIKA compound columns and compound BECKY
#        shift column still in place.
#   v2 — Step 8: ANIKA schema normalized. `mixtures.materials`/`weights` replaced by
#        `mixture_components`; `parts.pad`/`padsPerBox`/`misc` replaced by `part_pads`/`part_misc`;
#        `parts.loading`/`unloading`/`inspection`/`greenScrap` dropped (§3.1, §3.2).
#   v3 — Step 9: BECKY schema normalized. `employees.shift` split into `shift INTEGER` +
#        `fullTime INTEGER`; `reviews.details` and `notes.details` stored as plain TEXT
#        (base64 wrapping removed); orphan rows in training/attendance/PTO swept out (§3.1, §3.3).
MERCY_DB_VERSION = 4


class FileManager(SchemaMixin, MigrateMixin, SaveMixin, LoadMixin, ImportMixin):
    # Owns the per-DB connection (`self.dbFile`) and path (`self.filePath`); back-references
    # the MainWindow (`self.mainApp`) so save/load can read and replace `mainApp.db`.
    # Behavior is split across mixins by domain (schema-create, version migrations, save,
    # load, cross-DB import); orchestration (initFile + setFile) lives here so the entry
    # surface is colocated with the class.

    def __init__(self, mainApp: MainWindow) -> None:
        self.mainApp = mainApp
        self.filePath = None
        self.dbFile = None

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
                if dbVersion is not None and dbVersion < 4:
                    self._migrateV3ToV4()
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
                # Production table was created fresh at current shape; bump to match.
                self._setDbVersion(MERCY_DB_VERSION)
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
