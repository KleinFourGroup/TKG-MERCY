import datetime
import logging
import shutil

from utils import stringToList, stringFromB64


class MigrateMixin:
    # Per-version schema migrations + the pre-migration backup helper. Each migration
    # runs inside the outer initFile transaction, so a failure rolls back cleanly.
    # Version targets are literal integers (`_setDbVersion(2)`/`(3)`/`(4)`); MERCY_DB_VERSION
    # is owned by the package root and isn't referenced here.

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

    def _migrateV3ToV4(self):
        # Add `hours` column to the production table. Existing records get 0 via the
        # column default; no data transform needed.
        if self.dbFile is None:
            raise RuntimeError('self.dbFile is None')
        logging.info(" --> Running v3->v4 migration: add production.hours")
        cols = [row[1] for row in self.dbFile.execute("PRAGMA table_info(production)").fetchall()]
        if 'hours' not in cols:
            self.dbFile.execute("ALTER TABLE production ADD COLUMN hours REAL DEFAULT 0")
        self._setDbVersion(4)
        logging.info(" --> v3->v4 migration complete")
