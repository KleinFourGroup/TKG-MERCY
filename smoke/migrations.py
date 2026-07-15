"""Legacy DB migration checks: ANIKA v1, BECKY v2, the merge path,
the unified-MERCY v3->v4 (hours column), v4->v5 (presses table),
v5->v6 (pressers table), v6->v7 (shift_workweek table), v7->v8
(clients table), v8->v9 (orders table), v9->v10 (part_press_pref
table), v10->v11 (order_status table), v11->v12 (presser_press_pref
table), v12->v13 (part_truck table) and v13->v14 (presses.current_part
column) migrations."""
import glob
import os
import sys
import tempfile
from datetime import date as datetime_date


def legacy_anika_migration() -> list[str]:
    """Hand-craft a v1-shape legacy ANIKA DB, open with MERCY, verify v2 state.

    Seeds:
      - 2 mixtures: MixA with 3 materials, MixB with 1 material
      - 3 parts: PartA with 2 pads, PartB with 2 misc, PartC with 1 pad + 1 misc
    Expected post-open state:
      - db_version = 12 (Case 3 stamps MERCY_DB_VERSION after the ANIKA normalization;
        BECKY/production/scheduling/sales tables are created fresh at current shape)
      - mixture_components has 4 rows
      - part_pads has 3 rows, part_misc has 3 rows
      - parts table has exactly 12 columns (dead cols dropped)
      - mixtures table has exactly 1 column (materials/weights dropped)
      - loadFile() reconstructs the in-memory Mixture/Part objects correctly
      - a backup sibling file exists
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3
    import glob

    from utils import listToString

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    backup_glob = f"{tmp.name}.bak-*"
    w = None
    try:
        # --- seed legacy ANIKA v1-shape DB ---
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY, materials, weights)")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, loading, unloading, inspection, greenScrap, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, pad, padsPerBox, misc, price, sales)")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")

        # Materials referenced by mixtures need to exist for loadFile's Mixture sanity,
        # though mixture_components has no FK enforcement. Add them anyway.
        for m in ("MatA", "MatB", "MatC", "MatD"):
            conn.execute("INSERT INTO materials(name) VALUES (?)", (m,))
        for p in ("BoxA", "PadA", "PadB", "MiscA", "MiscB", "MiscC", "PalletA"):
            conn.execute("INSERT INTO packaging VALUES (?, ?, ?)", (p, "kind", 1.0))

        conn.execute(
            "INSERT INTO mixtures VALUES (?, ?, ?)",
            ("MixA", listToString(["MatA", "MatB", "MatC"], str),
             listToString([100.0, 50.0, 25.0], float))
        )
        conn.execute(
            "INSERT INTO mixtures VALUES (?, ?, ?)",
            ("MixB", listToString(["MatD"], str), listToString([200.0], float))
        )

        # Parts: 19 columns. Use consistent simple values.
        conn.execute(
            "INSERT INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("PartA", 1.0, "MixA", 100.0, 100.0, 1.0, 1.0, 1.0, 1.0, 0.05,
             "BoxA", 10, "PalletA", 40,
             listToString(["PadA", "PadB"], str), listToString([2, 1], int),
             listToString([], str),
             9.99, 0)
        )
        conn.execute(
            "INSERT INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("PartB", 2.0, "MixB", 100.0, 100.0, 1.0, 1.0, 1.0, 1.0, 0.05,
             "BoxA", 10, "PalletA", 40,
             listToString([], str), listToString([], int),
             listToString(["MiscA", "MiscB"], str),
             9.99, 0)
        )
        conn.execute(
            "INSERT INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("PartC", 3.0, "MixA", 100.0, 100.0, 1.0, 1.0, 1.0, 1.0, 0.05,
             "BoxA", 10, "PalletA", 40,
             listToString(["PadA"], str), listToString([3], int),
             listToString(["MiscC"], str),
             9.99, 0)
        )
        conn.commit()
        conn.close()

        # --- open with MERCY (triggers Case 3 legacy ANIKA migration) ---
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on legacy ANIKA DB")
            return errors
        w.fileManager.loadFile()

        # --- schema assertions ---
        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"db_version expected 14, got {version}")

        mix_cols = [r[1] for r in conn.execute("PRAGMA table_info(mixtures)").fetchall()]
        if mix_cols != ["name"]:
            errors.append(f"mixtures columns expected ['name'], got {mix_cols}")

        part_cols = [r[1] for r in conn.execute("PRAGMA table_info(parts)").fetchall()]
        expected_parts = ["name", "weight", "mix", "pressing", "turning", "fireScrap",
                          "box", "piecesPerBox", "pallet", "boxesPerPallet", "price", "sales"]
        if part_cols != expected_parts:
            errors.append(f"parts columns expected {expected_parts}, got {part_cols}")

        mc_rows = conn.execute(
            "SELECT mixture, material, weight, sort_order FROM mixture_components ORDER BY mixture, sort_order"
        ).fetchall()
        expected_mc = [
            ("MixA", "MatA", 100.0, 0),
            ("MixA", "MatB", 50.0, 1),
            ("MixA", "MatC", 25.0, 2),
            ("MixB", "MatD", 200.0, 0),
        ]
        if mc_rows != expected_mc:
            errors.append(f"mixture_components rows: expected {expected_mc}, got {mc_rows}")

        pp_rows = conn.execute(
            "SELECT part, pad, padsPerBox, sort_order FROM part_pads ORDER BY part, sort_order"
        ).fetchall()
        expected_pp = [
            ("PartA", "PadA", 2, 0),
            ("PartA", "PadB", 1, 1),
            ("PartC", "PadA", 3, 0),
        ]
        if pp_rows != expected_pp:
            errors.append(f"part_pads rows: expected {expected_pp}, got {pp_rows}")

        pm_rows = conn.execute(
            "SELECT part, item, sort_order FROM part_misc ORDER BY part, sort_order"
        ).fetchall()
        expected_pm = [
            ("PartB", "MiscA", 0),
            ("PartB", "MiscB", 1),
            ("PartC", "MiscC", 0),
        ]
        if pm_rows != expected_pm:
            errors.append(f"part_misc rows: expected {expected_pm}, got {pm_rows}")
        conn.close()

        # --- in-memory roundtrip assertions ---
        db = w.db
        if "MixA" not in db.mixtures or db.mixtures["MixA"].materials != ["MatA", "MatB", "MatC"]:
            errors.append(f"MixA.materials: got {db.mixtures.get('MixA') and db.mixtures['MixA'].materials}")
        if "MixA" in db.mixtures and db.mixtures["MixA"].weights != [100.0, 50.0, 25.0]:
            errors.append(f"MixA.weights: got {db.mixtures['MixA'].weights}")
        if "PartA" in db.parts:
            if db.parts["PartA"].pad != ["PadA", "PadB"]:
                errors.append(f"PartA.pad: got {db.parts['PartA'].pad}")
            if db.parts["PartA"].padsPerBox != [2, 1]:
                errors.append(f"PartA.padsPerBox: got {db.parts['PartA'].padsPerBox}")
        if "PartB" in db.parts and db.parts["PartB"].misc != ["MiscA", "MiscB"]:
            errors.append(f"PartB.misc: got {db.parts['PartB'].misc}")

        # --- backup assertion ---
        backups = glob.glob(backup_glob)
        if len(backups) != 1:
            errors.append(f"expected exactly 1 backup file matching {backup_glob}, found {backups}")

        # --- save/reload roundtrip on the migrated file ---
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading migrated DB")
        else:
            w2.fileManager.loadFile()
            db2 = w2.db
            if "MixA" in db2.mixtures and db2.mixtures["MixA"].materials != ["MatA", "MatB", "MatC"]:
                errors.append(f"post-roundtrip MixA.materials: got {db2.mixtures['MixA'].materials}")
            if "PartA" in db2.parts and db2.parts["PartA"].pad != ["PadA", "PadB"]:
                errors.append(f"post-roundtrip PartA.pad: got {db2.parts['PartA'].pad}")
            if w2.fileManager.dbFile is not None:
                w2.fileManager.dbFile.close()
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for p in glob.glob(backup_glob):
            try:
                os.unlink(p)
            except OSError:
                pass
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def legacy_becky_migration() -> list[str]:
    """Hand-craft a v2-shape legacy BECKY DB, open with MERCY, verify v3 state.

    Seeds:
      - 3 employees: shift="1|1", shift="2|0" (part-time), shift="3|1"
      - 2 reviews with base64-wrapped details (including newlines)
      - 2 notes with base64-wrapped details
      - 1 orphan training row (idNum not in employees)
      - 1 orphan attendance row
      - 1 orphan PTO row
      - 1 valid training / attendance / PTO row each to confirm sweep is selective
    Expected post-open state:
      - db_version = 12
      - employees table has `shift INTEGER, fullTime INTEGER` as separate cols (15 total)
      - shift/fullTime split correctly for each seeded employee
      - reviews.details and notes.details are plain text (not b64)
      - orphan rows removed from training / attendance / PTO; valid rows preserved
      - backup sibling file exists
      - save/reload roundtrip preserves the migrated data
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3
    import glob

    from utils import stringToB64

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    backup_glob = f"{tmp.name}.bak-*"
    w = None
    w2 = None
    try:
        # --- seed legacy BECKY v2-shape DB ---
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 2)")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")

        # Employees: shift encoded as "{shift}|{fullTime}" per pre-Step-9 convention.
        conn.execute("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (1, "Smith", "Alice", "2020-01-15", "Operator", "1|1",
                      "123 Main", "", "Townsville", "OH", "44000", "555-1234", "a@x.com", 1))
        conn.execute("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (2, "Jones", "Bob", "2021-06-01", "Presser", "2|0",
                      "456 Oak", "Apt 3", "Townsville", "OH", "44000", "555-5678", "b@x.com", 1))
        conn.execute("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (3, "Kim", "Carol", "2019-03-22", "Finisher", "3|1",
                      "789 Pine", "", "Townsville", "OH", "44000", "555-9999", "c@x.com", 1))

        # Reviews with b64-wrapped details (including a newline to exercise the round-trip).
        conn.execute("INSERT INTO reviews VALUES (?, ?, ?, ?)",
                     (1, "2024-01-10", "2025-01-10", stringToB64("First review.\nGood work.")))
        conn.execute("INSERT INTO reviews VALUES (?, ?, ?, ?)",
                     (2, "2024-07-15", "2025-07-15", stringToB64("Second review.")))

        # Notes with b64-wrapped details.
        conn.execute("INSERT INTO notes VALUES (?, ?, ?, ?)",
                     (1, "2024-03-05", "14:30", stringToB64("Late arrival.")))
        conn.execute("INSERT INTO notes VALUES (?, ?, ?, ?)",
                     (3, "2024-04-12", "09:00", stringToB64("Perfect attendance.\nKudos.")))

        # Valid + orphan rows in training / attendance / PTO.
        conn.execute("INSERT INTO training VALUES (?, ?, ?, ?)", (1, "Forklift", "2023-05-01", ""))
        conn.execute("INSERT INTO training VALUES (?, ?, ?, ?)", (99, "Forklift", "2023-05-01", ""))  # orphan
        conn.execute("INSERT INTO attendance VALUES (?, ?, ?, ?)", (2, "2024-02-14", "Late", 0.5))
        conn.execute("INSERT INTO attendance VALUES (?, ?, ?, ?)", (99, "2024-02-14", "Late", 0.5))  # orphan
        conn.execute("INSERT INTO PTO VALUES (?, ?, ?, ?)", (3, "2024-06-01", "2024-06-05", 40.0))
        conn.execute("INSERT INTO PTO VALUES (?, ?, ?, ?)", (99, "2024-06-01", "2024-06-05", 40.0))  # orphan
        conn.commit()
        conn.close()

        # --- open with MERCY (triggers Case 4 legacy BECKY migration) ---
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on legacy BECKY DB")
            return errors
        w.fileManager.loadFile()

        # --- schema assertions ---
        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"db_version expected 14, got {version}")

        emp_cols = [r[1] for r in conn.execute("PRAGMA table_info(employees)").fetchall()]
        expected_emp = ["idNum", "lastName", "firstName", "anniversary", "role",
                        "shift", "fullTime",
                        "addressLine1", "addressLine2", "addressCity", "addressState",
                        "addressZip", "addressTel", "addressEmail", "status"]
        if emp_cols != expected_emp:
            errors.append(f"employees columns expected {expected_emp}, got {emp_cols}")

        emp_rows = conn.execute("SELECT idNum, shift, fullTime FROM employees ORDER BY idNum").fetchall()
        expected_emp_rows = [(1, 1, 1), (2, 2, 0), (3, 3, 1)]
        if emp_rows != expected_emp_rows:
            errors.append(f"employees shift/fullTime: expected {expected_emp_rows}, got {emp_rows}")

        # reviews / notes: details should be plain text, not b64
        rev_details = conn.execute("SELECT details FROM reviews WHERE idNum=1 AND date='2024-01-10'").fetchone()
        if rev_details is None or rev_details[0] != "First review.\nGood work.":
            errors.append(f"reviews.details decode: got {rev_details}")

        note_details = conn.execute("SELECT details FROM notes WHERE idNum=3 AND date='2024-04-12'").fetchone()
        if note_details is None or note_details[0] != "Perfect attendance.\nKudos.":
            errors.append(f"notes.details decode: got {note_details}")

        # orphan sweep
        training_ids = sorted(r[0] for r in conn.execute("SELECT idNum FROM training").fetchall())
        if training_ids != [1]:
            errors.append(f"training orphan sweep: expected [1], got {training_ids}")
        attendance_ids = sorted(r[0] for r in conn.execute("SELECT idNum FROM attendance").fetchall())
        if attendance_ids != [2]:
            errors.append(f"attendance orphan sweep: expected [2], got {attendance_ids}")
        pto_ids = sorted(r[0] for r in conn.execute("SELECT idNum FROM PTO").fetchall())
        if pto_ids != [3]:
            errors.append(f"PTO orphan sweep: expected [3], got {pto_ids}")
        conn.close()

        # --- in-memory roundtrip assertions ---
        db = w.db
        if 1 not in db.employees or db.employees[1].shift != 1 or db.employees[1].fullTime is not True:
            e = db.employees.get(1)
            errors.append(f"Employee 1: shift={e and e.shift} fullTime={e and e.fullTime}")
        if 2 not in db.employees or db.employees[2].shift != 2 or db.employees[2].fullTime is not False:
            e = db.employees.get(2)
            errors.append(f"Employee 2: shift={e and e.shift} fullTime={e and e.fullTime}")
        if 1 in db.reviews:
            rev = db.reviews[1].reviews.get(datetime_date(2024, 1, 10))
            if rev is None or rev.details != "First review.\nGood work.":
                errors.append(f"in-memory review details: got {rev and rev.details}")
        if 3 in db.notes:
            note = db.notes[3].notes.get((datetime_date(2024, 4, 12), "09:00"))
            if note is None or note.details != "Perfect attendance.\nKudos.":
                errors.append(f"in-memory note details: got {note and note.details}")

        # --- backup assertion ---
        backups = glob.glob(backup_glob)
        if len(backups) != 1:
            errors.append(f"expected exactly 1 backup file matching {backup_glob}, found {backups}")

        # --- save/reload roundtrip ---
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading migrated BECKY DB")
        else:
            w2.fileManager.loadFile()
            db2 = w2.db
            if 2 in db2.employees:
                e = db2.employees[2]
                if e.shift != 2 or e.fullTime is not False:
                    errors.append(f"post-roundtrip employee 2: shift={e.shift} fullTime={e.fullTime}")
            if 1 in db2.reviews:
                rev = db2.reviews[1].reviews.get(datetime_date(2024, 1, 10))
                if rev is None or rev.details != "First review.\nGood work.":
                    errors.append(f"post-roundtrip review details: got {rev and rev.details}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for p in glob.glob(backup_glob):
            try:
                os.unlink(p)
            except OSError:
                pass
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def legacy_merge() -> list[str]:
    """Open a legacy ANIKA DB with MERCY, import a legacy BECKY DB on top.

    Exercises the Step-10 import path end-to-end:
      - Seeds one legacy ANIKA file (materials / mixtures / parts / inventory bits)
        and one legacy BECKY file (employees + per-employee collections).
      - Opens the ANIKA file with MERCY (triggers Case 3, v1->v3 migration).
      - Calls FileManager.importOtherDb(beckyPath), then Database.mergeFrom(tmpDb).
      - Asserts the merged in-memory state contains both sides' data.
      - Asserts the BECKY source file is byte-identical to what was seeded
        (hash before vs. after the import).
      - Save/reload roundtrip on the ANIKA file preserves the merged data.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import hashlib
    import sqlite3
    import glob

    from utils import listToString, stringToB64

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    anikaFd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    anikaFd.close()
    beckyFd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    beckyFd.close()
    anikaBackupGlob = f"{anikaFd.name}.bak-*"
    beckyBackupGlob = f"{beckyFd.name}.bak-*"
    w = None
    w2 = None
    try:
        # --- seed legacy ANIKA DB ---
        conn = sqlite3.connect(anikaFd.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY, materials, weights)")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, loading, unloading, inspection, greenScrap, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, pad, padsPerBox, misc, price, sales)")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        for m in ("MatA", "MatB"):
            conn.execute("INSERT INTO materials(name) VALUES (?)", (m,))
        for p in ("BoxA", "PadA", "PalletA"):
            conn.execute("INSERT INTO packaging VALUES (?, ?, ?)", (p, "kind", 1.0))
        conn.execute(
            "INSERT INTO mixtures VALUES (?, ?, ?)",
            ("MixA", listToString(["MatA", "MatB"], str), listToString([100.0, 50.0], float))
        )
        conn.execute(
            "INSERT INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("PartA", 1.0, "MixA", 100.0, 100.0, 1.0, 1.0, 1.0, 1.0, 0.05,
             "BoxA", 10, "PalletA", 40,
             listToString(["PadA"], str), listToString([2], int),
             listToString([], str),
             9.99, 0)
        )
        conn.commit()
        conn.close()

        # --- seed legacy BECKY DB ---
        conn = sqlite3.connect(beckyFd.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 2)")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (1, "Smith", "Alice", "2020-01-15", "Operator", "1|1",
                      "123 Main", "", "Townsville", "OH", "44000", "555-1234", "a@x.com", 1))
        conn.execute("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (2, "Jones", "Bob", "2021-06-01", "Presser", "2|0",
                      "456 Oak", "Apt 3", "Townsville", "OH", "44000", "555-5678", "b@x.com", 1))
        conn.execute("INSERT INTO reviews VALUES (?, ?, ?, ?)",
                     (1, "2024-01-10", "2025-01-10", stringToB64("Good review.")))
        conn.execute("INSERT INTO notes VALUES (?, ?, ?, ?)",
                     (1, "2024-03-05", "14:30", stringToB64("Late arrival.")))
        conn.execute("INSERT INTO training VALUES (?, ?, ?, ?)", (1, "Forklift", "2023-05-01", ""))
        conn.commit()
        conn.close()

        # Hash the BECKY file *after* WAL is released so it reflects the steady on-disk state.
        def fileHash(path: str) -> str:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()

        beckyHashBefore = fileHash(beckyFd.name)

        # --- open ANIKA with MERCY (Case 3 migration) ---
        w = MainWindow()
        if not w.fileManager.setFile(anikaFd.name):
            errors.append("setFile returned False on legacy ANIKA DB")
            return errors
        w.fileManager.loadFile()

        if "PartA" not in w.db.parts:
            errors.append(f"pre-import: expected PartA in db.parts, got {sorted(w.db.parts.keys())}")
        if len(w.db.employees) != 0:
            errors.append(f"pre-import: expected 0 employees, got {len(w.db.employees)}")

        # --- import BECKY ---
        otherDb, fmt = w.fileManager.importOtherDb(beckyFd.name)
        if fmt != "ok" or otherDb is None:
            errors.append(f"importOtherDb failed: fmt={fmt}")
            return errors

        plan = w.db.planMergeFrom(otherDb)
        for key, vals in plan["collisions"].items():
            if vals:
                errors.append(f"unexpected collision on {key}: {vals}")
        if plan["incoming"]["employees"] != [1, 2]:
            errors.append(f"expected employees [1, 2], got {plan['incoming']['employees']}")

        w.db.mergeFrom(otherDb)

        # --- post-merge in-memory assertions ---
        db = w.db
        if "PartA" not in db.parts:
            errors.append("post-merge: PartA missing from db.parts")
        if "MixA" not in db.mixtures or db.mixtures["MixA"].materials != ["MatA", "MatB"]:
            errors.append(f"post-merge: MixA.materials={db.mixtures.get('MixA') and db.mixtures['MixA'].materials}")
        if 1 not in db.employees or db.employees[1].shift != 1 or db.employees[1].fullTime is not True:
            e = db.employees.get(1)
            errors.append(f"post-merge: employee 1 shift={e and e.shift} fullTime={e and e.fullTime}")
        if 2 not in db.employees or db.employees[2].shift != 2 or db.employees[2].fullTime is not False:
            e = db.employees.get(2)
            errors.append(f"post-merge: employee 2 shift={e and e.shift} fullTime={e and e.fullTime}")
        if 1 not in db.reviews or datetime_date(2024, 1, 10) not in db.reviews[1].reviews:
            errors.append("post-merge: employee 1's review missing")
        if 1 not in db.notes or (datetime_date(2024, 3, 5), "14:30") not in db.notes[1].notes:
            errors.append("post-merge: employee 1's note missing")

        # --- BECKY source file untouched ---
        beckyHashAfter = fileHash(beckyFd.name)
        if beckyHashBefore != beckyHashAfter:
            errors.append(f"BECKY source file was mutated: {beckyHashBefore} -> {beckyHashAfter}")

        # --- save+reload roundtrip of the merged ANIKA file ---
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(anikaFd.name):
            errors.append("setFile returned False when reloading merged DB")
        else:
            w2.fileManager.loadFile()
            db2 = w2.db
            if "PartA" not in db2.parts:
                errors.append("post-roundtrip: PartA missing")
            if 1 not in db2.employees or db2.employees[1].shift != 1:
                e = db2.employees.get(1)
                errors.append(f"post-roundtrip: employee 1 shift={e and e.shift}")
            if 1 in db2.reviews:
                rev = db2.reviews[1].reviews.get(datetime_date(2024, 1, 10))
                if rev is None or rev.details != "Good review.":
                    errors.append(f"post-roundtrip: review details={rev and rev.details}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for bglob in (anikaBackupGlob, beckyBackupGlob):
            for p in glob.glob(bglob):
                try:
                    os.unlink(p)
                except OSError:
                    pass
        for base in (anikaFd.name, beckyFd.name):
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(base + suffix)
                except OSError:
                    pass
    return errors


def mercy_v3_to_v4_migration() -> list[str]:
    """Seed a unified MERCY DB stamped at v3 with a pre-hours production row,
    open with current MERCY, verify the v3->v4 hours column is added and existing
    data is preserved with hours=0. (The chain continues to v14; terminal
    db_version is asserted as 14, and the v4->v5 presses / v5->v6 pressers /
    v6->v7 shift_workweek / v7->v8 clients / v8->v9 orders / v9->v10
    part_press_pref / v10->v11 order_status / v11->v12 presser_press_pref /
    v12->v13 part_truck tables land too, plus the v13->v14 presses.current_part
    column.)"""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v3-shape MERCY DB by hand: full unified schema except production
        # has no `hours` column, and db_version=3.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 3)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        # Pre-v4 production table: no hours column.
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0)
        )
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v3 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        prod_cols = [r[1] for r in conn.execute("PRAGMA table_info(production)").fetchall()]
        if "hours" not in prod_cols:
            errors.append(f"production.hours missing after migration: cols={prod_cols}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row is None:
            errors.append("pre-existing production row lost during migration")
        elif row != (7.5, 0, 0):
            errors.append(f"production row after migration: expected (7.5, 0, 0), got {row}")
        conn.close()

        # loadFile should surface hours=0 on the in-memory record.
        w.fileManager.loadFile()
        recs = list(w.db.production.values())
        if len(recs) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(recs)}")
        elif recs[0].hours != 0:
            errors.append(f"in-memory hours after migration: got {recs[0].hours!r}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v4_to_v5_migration() -> list[str]:
    """Step 43: seed a unified MERCY DB stamped at v4 (no presses table),
    open with current MERCY, verify the v4->v5 presses table is created and
    existing production data survives untouched. (The chain continues to v14;
    terminal db_version is asserted as 14, and the v5->v6 pressers / v6->v7
    shift_workweek / v7->v8 clients / v8->v9 orders / v9->v10 part_press_pref /
    v10->v11 order_status / v11->v12 presser_press_pref / v12->v13 part_truck
    tables land too, plus the v13->v14 presses.current_part column.)"""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v4-shape MERCY DB by hand: full unified schema (production has the
        # hours column), db_version=4, and NO presses table — exactly what a pre-Step-43
        # MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 4)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v4 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "presses" not in tables:
            errors.append(f"presses table missing after migration: tables={sorted(tables)}")
        else:
            press_count = conn.execute("SELECT COUNT(*) FROM presses").fetchone()[0]
            if press_count != 0:
                errors.append(f"presses table should be empty after migration, has {press_count} rows")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty presses collection and keep production.
        w.fileManager.loadFile()
        if len(w.db.presses) != 0:
            errors.append(f"expected 0 in-memory presses after migration, got {len(w.db.presses)}")
        if len(w.db.production) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(w.db.production)}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v5_to_v6_migration() -> list[str]:
    """Step 44: seed a unified MERCY DB stamped at v5 (presses table present,
    no pressers table), open with current MERCY, verify the pressers table is
    created and db_version reaches 14 (the chain continues through v6->v7 / v7->v8 /
    v8->v9 / v9->v10 / v10->v11 / v11->v12 / v12->v13 / v13->v14), with existing presses / production data surviving
    untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v5-shape MERCY DB by hand: full unified schema with the presses
        # table populated, db_version=5, and NO pressers table — exactly what a
        # pre-Step-44 MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 5)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v5 presses table (with a row) but deliberately no pressers table.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v5 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "pressers" not in tables:
            errors.append(f"pressers table missing after migration: tables={sorted(tables)}")
        else:
            presser_count = conn.execute("SELECT COUNT(*) FROM pressers").fetchone()[0]
            if presser_count != 0:
                errors.append(f"pressers table should be empty after migration, has {presser_count} rows")
        press_row = conn.execute("SELECT name FROM presses").fetchone()
        if press_row != ("Press 1",):
            errors.append(f"presses row not preserved after migration: got {press_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty pressers collection and keep the
        # existing press + production records.
        w.fileManager.loadFile()
        if len(w.db.pressers) != 0:
            errors.append(f"expected 0 in-memory pressers after migration, got {len(w.db.pressers)}")
        if len(w.db.presses) != 1:
            errors.append(f"expected 1 press in-memory, got {len(w.db.presses)}")
        if len(w.db.production) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(w.db.production)}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v6_to_v7_migration() -> list[str]:
    """Step 45: seed a unified MERCY DB stamped at v6 (presses + pressers tables
    present, no shift_workweek table), open with current MERCY, verify the
    shift_workweek table is created and db_version reaches 14 (the chain continues
    through v7->v8 / v8->v9 / v9->v10 / v10->v11 / v11->v12 / v12->v13 / v13->v14), with existing presses / pressers /
    production data surviving untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v6-shape MERCY DB by hand: full unified schema with presses +
        # pressers populated, db_version=6, and NO shift_workweek table — exactly
        # what a pre-Step-45 MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 6)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v6 presses + pressers tables (each with a row) but deliberately no
        # shift_workweek table.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v6 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "shift_workweek" not in tables:
            errors.append(f"shift_workweek table missing after migration: tables={sorted(tables)}")
        else:
            ww_count = conn.execute("SELECT COUNT(*) FROM shift_workweek").fetchone()[0]
            if ww_count != 0:
                errors.append(f"shift_workweek table should be empty after migration, has {ww_count} rows")
        press_row = conn.execute("SELECT name FROM presses").fetchone()
        if press_row != ("Press 1",):
            errors.append(f"presses row not preserved after migration: got {press_row}")
        presser_row = conn.execute("SELECT employeeId, hoursPerShift FROM pressers").fetchone()
        if presser_row != (101, 8.0):
            errors.append(f"pressers row not preserved after migration: got {presser_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty shiftWorkweek collection and keep
        # the existing press / presser / production records.
        w.fileManager.loadFile()
        if len(w.db.shiftWorkweek) != 0:
            errors.append(f"expected 0 in-memory shift workweeks after migration, got {len(w.db.shiftWorkweek)}")
        if len(w.db.presses) != 1:
            errors.append(f"expected 1 press in-memory, got {len(w.db.presses)}")
        if len(w.db.pressers) != 1:
            errors.append(f"expected 1 presser in-memory, got {len(w.db.pressers)}")
        if len(w.db.production) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(w.db.production)}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v7_to_v8_migration() -> list[str]:
    """Step 46: seed a unified MERCY DB stamped at v7 (presses + pressers +
    shift_workweek tables present, no clients table), open with current MERCY,
    verify the clients table is created and db_version reaches 14 (the chain
    continues through v8->v9 / v9->v10 / v10->v11 / v11->v12 / v12->v13 / v13->v14), with existing presses / pressers /
    shift_workweek / production data surviving untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v7-shape MERCY DB by hand: full unified schema with presses +
        # pressers + shift_workweek populated, db_version=7, and NO clients table —
        # exactly what a pre-Step-46 MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 7)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v7 scheduling tables (each with data) but deliberately no clients table.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.execute("CREATE TABLE shift_workweek(shift INTEGER, weekday INTEGER, UNIQUE(shift, weekday))")
        conn.execute("INSERT INTO shift_workweek VALUES (1, 0)")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v7 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "clients" not in tables:
            errors.append(f"clients table missing after migration: tables={sorted(tables)}")
        else:
            client_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            if client_count != 0:
                errors.append(f"clients table should be empty after migration, has {client_count} rows")
        press_row = conn.execute("SELECT name FROM presses").fetchone()
        if press_row != ("Press 1",):
            errors.append(f"presses row not preserved after migration: got {press_row}")
        presser_row = conn.execute("SELECT employeeId, hoursPerShift FROM pressers").fetchone()
        if presser_row != (101, 8.0):
            errors.append(f"pressers row not preserved after migration: got {presser_row}")
        ww_row = conn.execute("SELECT shift, weekday FROM shift_workweek").fetchone()
        if ww_row != (1, 0):
            errors.append(f"shift_workweek row not preserved after migration: got {ww_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty clients collection and keep the
        # existing press / presser / workweek / production records.
        w.fileManager.loadFile()
        if len(w.db.clients) != 0:
            errors.append(f"expected 0 in-memory clients after migration, got {len(w.db.clients)}")
        if len(w.db.presses) != 1:
            errors.append(f"expected 1 press in-memory, got {len(w.db.presses)}")
        if len(w.db.pressers) != 1:
            errors.append(f"expected 1 presser in-memory, got {len(w.db.pressers)}")
        if len(w.db.shiftWorkweek) != 1:
            errors.append(f"expected 1 shift workweek in-memory, got {len(w.db.shiftWorkweek)}")
        if len(w.db.production) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(w.db.production)}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v8_to_v9_migration() -> list[str]:
    """Step 47: seed a unified MERCY DB stamped at v8 (clients + scheduling tables
    present, no orders table), open with current MERCY, verify the orders table is
    created, db_version reaches 14 (the chain runs on through v9->v10 / v10->v11 /
    v11->v12 / v12->v13 / v13->v14), and
    existing clients / presses / pressers / shift_workweek / production data survive
    untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v8-shape MERCY DB by hand: full unified schema with the scheduling
        # tables + clients populated, db_version=8, and NO orders table — exactly
        # what a pre-Step-47 MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 8)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v8 scheduling + clients tables (each with data) but deliberately no orders table.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.execute("CREATE TABLE shift_workweek(shift INTEGER, weekday INTEGER, UNIQUE(shift, weekday))")
        conn.execute("INSERT INTO shift_workweek VALUES (1, 0)")
        conn.execute("CREATE TABLE clients(name PRIMARY KEY, transportDays INTEGER)")
        conn.execute("INSERT INTO clients VALUES ('Acme Ceramics', 5)")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v8 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "orders" not in tables:
            errors.append(f"orders table missing after migration: tables={sorted(tables)}")
        else:
            order_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            if order_count != 0:
                errors.append(f"orders table should be empty after migration, has {order_count} rows")
        client_row = conn.execute("SELECT name, transportDays FROM clients").fetchone()
        if client_row != ("Acme Ceramics", 5):
            errors.append(f"clients row not preserved after migration: got {client_row}")
        press_row = conn.execute("SELECT name FROM presses").fetchone()
        if press_row != ("Press 1",):
            errors.append(f"presses row not preserved after migration: got {press_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty orders collection and keep the
        # existing client / scheduling / production records.
        w.fileManager.loadFile()
        if len(w.db.orders) != 0:
            errors.append(f"expected 0 in-memory orders after migration, got {len(w.db.orders)}")
        if len(w.db.clients) != 1:
            errors.append(f"expected 1 client in-memory, got {len(w.db.clients)}")
        if len(w.db.presses) != 1:
            errors.append(f"expected 1 press in-memory, got {len(w.db.presses)}")
        if len(w.db.production) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(w.db.production)}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v9_to_v10_migration() -> list[str]:
    """Step 48: seed a unified MERCY DB stamped at v9 (scheduling + sales tables
    present, no part_press_pref table), open with current MERCY, verify the
    part_press_pref table is created, db_version is bumped to 10 (the chain runs on
    through v10->v11 / v11->v12 / v12->v13 / v13->v14), and existing parts / presses / orders / production data survive
    untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v9-shape MERCY DB by hand: full unified schema with the scheduling
        # + sales tables populated, db_version=9, and NO part_press_pref table —
        # exactly what a pre-Step-48 MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 9)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v9 scheduling + sales tables (each with data) but deliberately no part_press_pref.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.execute("CREATE TABLE shift_workweek(shift INTEGER, weekday INTEGER, UNIQUE(shift, weekday))")
        conn.execute("INSERT INTO shift_workweek VALUES (1, 0)")
        conn.execute("CREATE TABLE clients(name PRIMARY KEY, transportDays INTEGER)")
        conn.execute("INSERT INTO clients VALUES ('Acme Ceramics', 5)")
        conn.execute("CREATE TABLE orders(orderNum PRIMARY KEY, client, part, quantity INTEGER, price REAL, dueDate)")
        conn.execute("INSERT INTO orders VALUES ('AC-PA-000001', 'Acme Ceramics', 'PartA', 100, 500.0, '2026-07-01')")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v9 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "part_press_pref" not in tables:
            errors.append(f"part_press_pref table missing after migration: tables={sorted(tables)}")
        else:
            pref_count = conn.execute("SELECT COUNT(*) FROM part_press_pref").fetchone()[0]
            if pref_count != 0:
                errors.append(f"part_press_pref table should be empty after migration, has {pref_count} rows")
        order_row = conn.execute("SELECT orderNum, client, part FROM orders").fetchone()
        if order_row != ("AC-PA-000001", "Acme Ceramics", "PartA"):
            errors.append(f"orders row not preserved after migration: got {order_row}")
        press_row = conn.execute("SELECT name FROM presses").fetchone()
        if press_row != ("Press 1",):
            errors.append(f"presses row not preserved after migration: got {press_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty partPressPref collection and keep the
        # existing part / press / order / production records.
        w.fileManager.loadFile()
        if len(w.db.partPressPref) != 0:
            errors.append(f"expected 0 in-memory part-press prefs after migration, got {len(w.db.partPressPref)}")
        if len(w.db.orders) != 1:
            errors.append(f"expected 1 order in-memory, got {len(w.db.orders)}")
        if len(w.db.presses) != 1:
            errors.append(f"expected 1 press in-memory, got {len(w.db.presses)}")
        if len(w.db.production) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(w.db.production)}")

        # A fresh part-press preference should now save + reload cleanly on the migrated DB.
        from records import PartPressPref
        pref = PartPressPref("PartA")
        pref.setScore("Press 1", 4)
        w.db.partPressPref["PartA"] = pref
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        w.fileManager.setFile(tmp.name)
        w.fileManager.loadFile()
        got = w.db.partPressPref.get("PartA")
        if got is None or got.getScore("Press 1") != 4:
            errors.append(f"post-migration pref roundtrip failed: {got and got.scores}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v10_to_v11_migration() -> list[str]:
    """Step 49: seed a unified MERCY DB stamped at v10 (scheduling + sales tables
    present, no order_status table), open with current MERCY, verify the
    order_status table is created, db_version reaches 14 (the chain runs on through
    v11->v12 / v12->v13 / v13->v14), and existing parts / presses / orders / part_press_pref / production
    data survive untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v10-shape MERCY DB by hand: full unified schema with the scheduling
        # + sales tables populated (including part_press_pref), db_version=10, and NO
        # order_status table — exactly what a pre-Step-49 MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 10)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v10 scheduling + sales tables (each with data) but deliberately no order_status.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.execute("CREATE TABLE shift_workweek(shift INTEGER, weekday INTEGER, UNIQUE(shift, weekday))")
        conn.execute("INSERT INTO shift_workweek VALUES (1, 0)")
        conn.execute("CREATE TABLE part_press_pref(part, press, score INTEGER, UNIQUE(part, press))")
        conn.execute("INSERT INTO part_press_pref VALUES ('PartA', 'Press 1', 4)")
        conn.execute("CREATE TABLE clients(name PRIMARY KEY, transportDays INTEGER)")
        conn.execute("INSERT INTO clients VALUES ('Acme Ceramics', 5)")
        conn.execute("CREATE TABLE orders(orderNum PRIMARY KEY, client, part, quantity INTEGER, price REAL, dueDate)")
        conn.execute("INSERT INTO orders VALUES ('AC-PA-000001', 'Acme Ceramics', 'PartA', 100, 500.0, '2026-07-01')")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v10 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "order_status" not in tables:
            errors.append(f"order_status table missing after migration: tables={sorted(tables)}")
        else:
            status_count = conn.execute("SELECT COUNT(*) FROM order_status").fetchone()[0]
            if status_count != 0:
                errors.append(f"order_status table should be empty after migration, has {status_count} rows")
        order_row = conn.execute("SELECT orderNum, client, part FROM orders").fetchone()
        if order_row != ("AC-PA-000001", "Acme Ceramics", "PartA"):
            errors.append(f"orders row not preserved after migration: got {order_row}")
        pref_row = conn.execute("SELECT part, press, score FROM part_press_pref").fetchone()
        if pref_row != ("PartA", "Press 1", 4):
            errors.append(f"part_press_pref row not preserved after migration: got {pref_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty orderStatus collection and keep the
        # existing order / pref / production records.
        w.fileManager.loadFile()
        if len(w.db.orderStatus) != 0:
            errors.append(f"expected 0 in-memory order statuses after migration, got {len(w.db.orderStatus)}")
        if len(w.db.orders) != 1:
            errors.append(f"expected 1 order in-memory, got {len(w.db.orders)}")
        if len(w.db.partPressPref) != 1:
            errors.append(f"expected 1 part-press pref in-memory, got {len(w.db.partPressPref)}")
        if len(w.db.production) != 1:
            errors.append(f"expected 1 production record in-memory, got {len(w.db.production)}")

        # A fresh order status snapshot should now save + reload cleanly on the migrated DB.
        w.db.setOrderSnapshot("AC-PA-000001", datetime_date(2026, 5, 1), 60, 100)
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        w.fileManager.setFile(tmp.name)
        w.fileManager.loadFile()
        got = w.db.orderStatus.get("AC-PA-000001")
        if got is None or got.snapshots.get(datetime_date(2026, 5, 1)) != (60, 100):
            errors.append(f"post-migration order status roundtrip failed: {got and got.snapshots}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v11_to_v12_migration() -> list[str]:
    """Step 65: seed a unified MERCY DB stamped at v11 (all scheduling + sales tables
    present, no presser_press_pref table), open with current MERCY, verify the
    presser_press_pref table is created, the chain runs on to db_version 14 (the
    v12->v13 part_truck and v13->v14 presses.current_part migrations also fire), and
    existing parts / presses / pressers / part_press_pref / order_status / production
    data survive untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v11-shape MERCY DB by hand: full unified schema with every scheduling
        # + sales table populated (including part_press_pref + order_status),
        # db_version=11, and NO presser_press_pref table — exactly what a pre-Step-65
        # MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 11)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("INSERT INTO employees VALUES (101, 'Doe', 'Jane', '2020-01-01', 'Presser', 1, 1, '', '', '', 'PA', '', '', '', 1)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v11 scheduling + sales tables (each with data) but deliberately no presser_press_pref.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.execute("CREATE TABLE shift_workweek(shift INTEGER, weekday INTEGER, UNIQUE(shift, weekday))")
        conn.execute("INSERT INTO shift_workweek VALUES (1, 0)")
        conn.execute("CREATE TABLE part_press_pref(part, press, score INTEGER, UNIQUE(part, press))")
        conn.execute("INSERT INTO part_press_pref VALUES ('PartA', 'Press 1', 4)")
        conn.execute("CREATE TABLE clients(name PRIMARY KEY, transportDays INTEGER)")
        conn.execute("INSERT INTO clients VALUES ('Acme Ceramics', 5)")
        conn.execute("CREATE TABLE orders(orderNum PRIMARY KEY, client, part, quantity INTEGER, price REAL, dueDate)")
        conn.execute("INSERT INTO orders VALUES ('AC-PA-000001', 'Acme Ceramics', 'PartA', 100, 500.0, '2026-07-01')")
        conn.execute("CREATE TABLE order_status(orderNum, date, remainingToPress INTEGER, remainingToShip INTEGER, UNIQUE(orderNum, date))")
        conn.execute("INSERT INTO order_status VALUES ('AC-PA-000001', '2026-05-01', 60, 100)")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v11 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "presser_press_pref" not in tables:
            errors.append(f"presser_press_pref table missing after migration: tables={sorted(tables)}")
        else:
            pref_count = conn.execute("SELECT COUNT(*) FROM presser_press_pref").fetchone()[0]
            if pref_count != 0:
                errors.append(f"presser_press_pref table should be empty after migration, has {pref_count} rows")
        # Pre-existing data untouched.
        presser_row = conn.execute("SELECT employeeId, hoursPerShift FROM pressers").fetchone()
        if presser_row != (101, 8.0):
            errors.append(f"pressers row not preserved after migration: got {presser_row}")
        part_pref_row = conn.execute("SELECT part, press, score FROM part_press_pref").fetchone()
        if part_pref_row != ("PartA", "Press 1", 4):
            errors.append(f"part_press_pref row not preserved after migration: got {part_pref_row}")
        status_row = conn.execute("SELECT orderNum, remainingToPress, remainingToShip FROM order_status").fetchone()
        if status_row != ("AC-PA-000001", 60, 100):
            errors.append(f"order_status row not preserved after migration: got {status_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty presserPressPref collection and keep the
        # existing presser / part-pref / order-status / production records.
        w.fileManager.loadFile()
        if len(w.db.presserPressPref) != 0:
            errors.append(f"expected 0 in-memory presser-press prefs after migration, got {len(w.db.presserPressPref)}")
        if len(w.db.pressers) != 1:
            errors.append(f"expected 1 presser in-memory, got {len(w.db.pressers)}")
        if len(w.db.partPressPref) != 1:
            errors.append(f"expected 1 part-press pref in-memory, got {len(w.db.partPressPref)}")

        # A fresh presser-press preference should now save + reload cleanly on the migrated DB.
        w.db.setPresserPressScore(101, "Press 1", 5)
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        w.fileManager.setFile(tmp.name)
        w.fileManager.loadFile()
        got = w.db.presserPressPref.get(101)
        if got is None or got.getScore("Press 1") != 5:
            errors.append(f"post-migration presser-press pref roundtrip failed: {got and got.scores}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v12_to_v13_migration() -> list[str]:
    """Step 74a: seed a unified MERCY DB stamped at v12 (all scheduling + sales tables
    present, no part_truck table), open with current MERCY, verify the part_truck
    table is created, the chain runs on to db_version 14 (the v13->v14
    presses.current_part migration also fires), and existing parts / presses /
    pressers / part_press_pref / presser_press_pref / order_status / production data
    survive untouched."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v12-shape MERCY DB by hand: full unified schema with every scheduling
        # + sales table populated (including presser_press_pref), db_version=12, and NO
        # part_truck — exactly what a pre-Step-74a MERCY file looks like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 12)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("INSERT INTO parts VALUES ('PartA', 1.0, 'MixA', 10, 0, 0.05, 'BoxA', 20, 'PalletA', 40, 5.0, 0)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("INSERT INTO employees VALUES (101, 'Doe', 'Jane', '2020-01-01', 'Presser', 1, 1, '', '', '', 'PA', '', '', '', 1)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v12 scheduling + sales tables (each with data) but deliberately no part_truck.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.execute("CREATE TABLE shift_workweek(shift INTEGER, weekday INTEGER, UNIQUE(shift, weekday))")
        conn.execute("INSERT INTO shift_workweek VALUES (1, 0)")
        conn.execute("CREATE TABLE part_press_pref(part, press, score INTEGER, UNIQUE(part, press))")
        conn.execute("INSERT INTO part_press_pref VALUES ('PartA', 'Press 1', 4)")
        conn.execute("CREATE TABLE presser_press_pref(employeeId, press, score INTEGER, UNIQUE(employeeId, press))")
        conn.execute("INSERT INTO presser_press_pref VALUES (101, 'Press 1', 5)")
        conn.execute("CREATE TABLE clients(name PRIMARY KEY, transportDays INTEGER)")
        conn.execute("INSERT INTO clients VALUES ('Acme Ceramics', 5)")
        conn.execute("CREATE TABLE orders(orderNum PRIMARY KEY, client, part, quantity INTEGER, price REAL, dueDate)")
        conn.execute("INSERT INTO orders VALUES ('AC-PA-000001', 'Acme Ceramics', 'PartA', 100, 500.0, '2026-07-01')")
        conn.execute("CREATE TABLE order_status(orderNum, date, remainingToPress INTEGER, remainingToShip INTEGER, UNIQUE(orderNum, date))")
        conn.execute("INSERT INTO order_status VALUES ('AC-PA-000001', '2026-05-01', 60, 100)")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v12 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        if "part_truck" not in tables:
            errors.append(f"part_truck table missing after migration: tables={sorted(tables)}")
        else:
            truck_count = conn.execute("SELECT COUNT(*) FROM part_truck").fetchone()[0]
            if truck_count != 0:
                errors.append(f"part_truck table should be empty after migration, has {truck_count} rows")
        # Pre-existing data untouched.
        presser_row = conn.execute("SELECT employeeId, hoursPerShift FROM pressers").fetchone()
        if presser_row != (101, 8.0):
            errors.append(f"pressers row not preserved after migration: got {presser_row}")
        part_pref_row = conn.execute("SELECT part, press, score FROM part_press_pref").fetchone()
        if part_pref_row != ("PartA", "Press 1", 4):
            errors.append(f"part_press_pref row not preserved after migration: got {part_pref_row}")
        presser_pref_row = conn.execute("SELECT employeeId, press, score FROM presser_press_pref").fetchone()
        if presser_pref_row != (101, "Press 1", 5):
            errors.append(f"presser_press_pref row not preserved after migration: got {presser_pref_row}")
        status_row = conn.execute("SELECT orderNum, remainingToPress, remainingToShip FROM order_status").fetchone()
        if status_row != ("AC-PA-000001", 60, 100):
            errors.append(f"order_status row not preserved after migration: got {status_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct an empty partTruck collection and keep the
        # existing part-pref / presser-pref / order-status / production records.
        w.fileManager.loadFile()
        if len(w.db.partTruck) != 0:
            errors.append(f"expected 0 in-memory parts-per-truck after migration, got {len(w.db.partTruck)}")
        if len(w.db.partPressPref) != 1:
            errors.append(f"expected 1 part-press pref in-memory, got {len(w.db.partPressPref)}")
        if len(w.db.presserPressPref) != 1:
            errors.append(f"expected 1 presser-press pref in-memory, got {len(w.db.presserPressPref)}")

        # A fresh parts-per-truck figure should now save + reload cleanly on the migrated DB.
        w.db.setPartTruck("PartA", 500)
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        w.fileManager.setFile(tmp.name)
        w.fileManager.loadFile()
        got = w.db.partTruck.get("PartA")
        if got is None or got.partsPerTruck != 500:
            errors.append(f"post-migration parts-per-truck roundtrip failed: {got and got.partsPerTruck}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mercy_v13_to_v14_migration() -> list[str]:
    """Step 79: seed a unified MERCY DB stamped at v13 (all scheduling + sales tables
    present, `presses` with the old single-column shape — no current_part), open with
    current MERCY, verify the presses.current_part column is added (nullable, empty for
    the existing row), db_version is bumped to 14, existing data survives untouched, and
    a fresh mounted-die value saves + reloads cleanly on the migrated DB.

    Unlike the v5..v13 checks (each asserts a whole new table appears), v14 alters an
    existing table, so this asserts the column via PRAGMA table_info and roundtrips a
    value through db.setPressCurrentPart."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        # Build a v13-shape MERCY DB by hand: full unified schema with every scheduling
        # + sales table populated (including part_truck), db_version=13, and `presses`
        # in its pre-Step-79 one-column shape — exactly what a pre-v14 MERCY file looks
        # like.
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
        conn.execute("INSERT INTO globals VALUES ('db_version', 13)")
        conn.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
        conn.execute("CREATE TABLE mixtures(name PRIMARY KEY)")
        conn.execute("CREATE TABLE mixture_components(mixture, material, weight REAL, sort_order INTEGER, UNIQUE(mixture, material))")
        conn.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
        conn.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, price, sales)")
        conn.execute("INSERT INTO parts VALUES ('PartA', 1.0, 'MixA', 10, 0, 0.05, 'BoxA', 20, 'PalletA', 40, 5.0, 0)")
        conn.execute("CREATE TABLE part_pads(part, pad, padsPerBox INTEGER, sort_order INTEGER, UNIQUE(part, pad))")
        conn.execute("CREATE TABLE part_misc(part, item, sort_order INTEGER, UNIQUE(part, item))")
        conn.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
        conn.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
        conn.execute("CREATE TABLE employees(idNum PRIMARY KEY, lastName, firstName, anniversary, role, shift INTEGER, fullTime INTEGER, addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail, status)")
        conn.execute("INSERT INTO employees VALUES (101, 'Doe', 'Jane', '2020-01-01', 'Presser', 1, 1, '', '', '', 'PA', '', '', '', 1)")
        conn.execute("CREATE TABLE reviews(idNum, date, nextReview, details TEXT, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE training(idNum, training, date, comment, UNIQUE(idNum, training, date))")
        conn.execute("CREATE TABLE attendance(idNum, date, reason, value, UNIQUE(idNum, date))")
        conn.execute("CREATE TABLE PTO(idNum, start, end, hours, UNIQUE(idNum, start, end))")
        conn.execute("CREATE TABLE notes(idNum, date, time, details TEXT, UNIQUE(idNum, date, time))")
        conn.execute("CREATE TABLE holidays(holiday PRIMARY KEY, month)")
        conn.execute("CREATE TABLE observances(holiday, shift, date, UNIQUE(holiday, shift, date))")
        conn.execute(
            "CREATE TABLE production("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "employeeId INTEGER, date TEXT, shift INTEGER, "
            "targetType TEXT, targetName TEXT, action TEXT, "
            "quantity REAL, scrapQuantity REAL DEFAULT 0, hours REAL DEFAULT 0, "
            "UNIQUE(employeeId, date, shift, targetType, targetName, action))"
        )
        conn.execute(
            "INSERT INTO production(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (101, "2026-04-15", 1, "mix", "MixA", "Batching", 7.5, 0, 2.0)
        )
        # v13 scheduling + sales tables (each with data). `presses` is deliberately the
        # old single-column shape — the pre-Step-79 state the v13->v14 migration upgrades.
        conn.execute("CREATE TABLE presses(name PRIMARY KEY)")
        conn.execute("INSERT INTO presses VALUES ('Press 1')")
        conn.execute("CREATE TABLE pressers(employeeId PRIMARY KEY, hoursPerShift REAL)")
        conn.execute("INSERT INTO pressers VALUES (101, 8.0)")
        conn.execute("CREATE TABLE shift_workweek(shift INTEGER, weekday INTEGER, UNIQUE(shift, weekday))")
        conn.execute("INSERT INTO shift_workweek VALUES (1, 0)")
        conn.execute("CREATE TABLE part_press_pref(part, press, score INTEGER, UNIQUE(part, press))")
        conn.execute("INSERT INTO part_press_pref VALUES ('PartA', 'Press 1', 4)")
        conn.execute("CREATE TABLE presser_press_pref(employeeId, press, score INTEGER, UNIQUE(employeeId, press))")
        conn.execute("INSERT INTO presser_press_pref VALUES (101, 'Press 1', 5)")
        conn.execute("CREATE TABLE part_truck(part PRIMARY KEY, partsPerTruck INTEGER)")
        conn.execute("INSERT INTO part_truck VALUES ('PartA', 500)")
        conn.execute("CREATE TABLE clients(name PRIMARY KEY, transportDays INTEGER)")
        conn.execute("INSERT INTO clients VALUES ('Acme Ceramics', 5)")
        conn.execute("CREATE TABLE orders(orderNum PRIMARY KEY, client, part, quantity INTEGER, price REAL, dueDate)")
        conn.execute("INSERT INTO orders VALUES ('AC-PA-000001', 'Acme Ceramics', 'PartA', 100, 500.0, '2026-07-01')")
        conn.execute("CREATE TABLE order_status(orderNum, date, remainingToPress INTEGER, remainingToShip INTEGER, UNIQUE(orderNum, date))")
        conn.execute("INSERT INTO order_status VALUES ('AC-PA-000001', '2026-05-01', 60, 100)")
        conn.commit()
        conn.close()

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on v13 MERCY DB")
            return errors

        conn = sqlite3.connect(tmp.name)
        version = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if version is None or int(version[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {version}")
        press_cols = [r[1] for r in conn.execute("PRAGMA table_info(presses)").fetchall()]
        if "current_part" not in press_cols:
            errors.append(f"presses.current_part column missing after migration: cols={press_cols}")
        else:
            # Existing row's die is NULL (idle) — the additive column default.
            cur = conn.execute("SELECT current_part FROM presses WHERE name='Press 1'").fetchone()
            if cur is None or cur[0] is not None:
                errors.append(f"existing press current_part should be NULL after migration, got {cur}")
        # Pre-existing data untouched.
        presser_row = conn.execute("SELECT employeeId, hoursPerShift FROM pressers").fetchone()
        if presser_row != (101, 8.0):
            errors.append(f"pressers row not preserved after migration: got {presser_row}")
        truck_row = conn.execute("SELECT part, partsPerTruck FROM part_truck").fetchone()
        if truck_row != ("PartA", 500):
            errors.append(f"part_truck row not preserved after migration: got {truck_row}")
        status_row = conn.execute("SELECT orderNum, remainingToPress, remainingToShip FROM order_status").fetchone()
        if status_row != ("AC-PA-000001", 60, 100):
            errors.append(f"order_status row not preserved after migration: got {status_row}")
        row = conn.execute(
            "SELECT quantity, scrapQuantity, hours FROM production WHERE employeeId=101"
        ).fetchone()
        if row != (7.5, 0, 2.0):
            errors.append(f"production row after migration: expected (7.5, 0, 2.0), got {row}")
        conn.close()

        # loadFile should reconstruct the press with currentPart None (idle).
        w.fileManager.loadFile()
        press = w.db.presses.get("Press 1")
        if press is None:
            errors.append("Press 1 missing from in-memory presses after migration")
        elif press.currentPart is not None:
            errors.append(f"expected in-memory currentPart None after migration, got {press.currentPart!r}")

        # A fresh mounted-die value should now save + reload cleanly on the migrated DB.
        w.db.setPressCurrentPart("Press 1", "PartA")
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        w.fileManager.setFile(tmp.name)
        w.fileManager.loadFile()
        got = w.db.presses.get("Press 1")
        if got is None or got.currentPart != "PartA":
            errors.append(f"post-migration current_part roundtrip failed: {got and got.currentPart!r}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


# The nine additive Production Scheduling / Sales tables (db_version 5..13; v14 adds
# the presses.current_part column, not a new table).
_SCHED_SALES_TABLES = ["presses", "pressers", "shift_workweek", "part_press_pref",
                       "clients", "orders", "order_status", "presser_press_pref",
                       "part_truck"]


def mercy_v4_to_v14_end_to_end() -> list[str]:
    """Step 54: full migration-chain replay on a *realistically populated* v4 DB,
    then the Production Scheduling subsystem end-to-end on the migrated data.

    Where the per-version checks (v3->v4 .. v13->v14) migrate a 1-row fixture and
    only assert the tables appear, this is the "subsystem ready to ship" drill —
    the automated twin of the real-data drill run on Matthew's `Mercy DB 6-1-26.db`:

      - build a realistic v14 DB (fuzz_db: materials/mixtures/parts/employees/
        production), then *downgrade it on disk* — drop the 9 scheduling/sales
        tables and stamp db_version=4 — so it's byte-for-byte a pre-Step-43 file
        carrying real costing/HR/production data;
      - reopen with MERCY: the v4->v14 additive chain runs. Assert it reaches v14,
        creates all 9 tables empty, adds the presses.current_part column, leaves the
        pre-existing data untouched, and — the additive-chain invariant the
        migrate.py comments claim but nothing asserts — writes NO `.bak` sibling;
      - populate scheduling/sales on the migrated DB, save -> reload, and confirm
        every collection roundtrips (and production survives);
      - run schedule() + scheduleReport against the migrated+reloaded DB: rows land
        on real working shift-days / presses / parts, every eligible order is
        scheduled or flagged (never dropped), and the PDF renders.
    """
    import datetime
    import glob
    import random
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from report import PDFReport
    import scheduling as S
    import fuzz_db as F
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    backup_glob = f"{tmp.name}.bak-*"
    pdfPath = None
    w0 = w = w2 = None
    try:
        rng = random.Random(54)
        cfg = F.SCALES["tiny"]
        today = datetime.date(2026, 6, 25)

        # --- 1. Build a realistic v14 DB, then downgrade it to v4 shape on disk. ---
        w0 = MainWindow()
        if not w0.fileManager.setFile(tmp.name):
            errors.append("setFile returned False creating base DB")
            return errors
        db0 = w0.db
        materialNames = F.populateMaterials(db0, rng, cfg["materials"])
        mixtureNames = F.populateMixtures(db0, rng, cfg["mixtures"], materialNames)
        F.populatePackaging(db0, rng, cfg["packaging"])
        packagingByKind = {k: [] for k in F.PACKAGING_POOL}
        for name in db0.packaging:
            packagingByKind[db0.packaging[name].kind].append(name)
        partNames = F.populateParts(db0, rng, cfg["parts"], mixtureNames, packagingByKind)
        idNums = F.populateEmployees(db0, rng, cfg["employees"], today)
        F.populateProduction(db0, rng, idNums, partNames, mixtureNames,
                             cfg["productionDays"], today)
        w0.fileManager.saveFile()
        if w0.fileManager.dbFile is not None:
            w0.fileManager.dbFile.close()

        conn = sqlite3.connect(tmp.name)
        for t in _SCHED_SALES_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.execute("INSERT OR REPLACE INTO globals VALUES ('db_version', 4)")
        conn.commit()
        preserved = ["materials", "mixtures", "parts", "employees", "production"]
        preCounts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in preserved}
        conn.close()
        if any(v == 0 for v in preCounts.values()):
            errors.append(f"fuzz fixture under-populated the base DB: {preCounts}")

        backupsBefore = set(glob.glob(backup_glob))

        # --- 2. Reopen with MERCY -> the v4..v14 additive chain runs. ---
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on downgraded v4 DB")
            return errors
        w.fileManager.loadFile()

        conn = sqlite3.connect(tmp.name)
        ver = conn.execute("SELECT value FROM globals WHERE name='db_version'").fetchone()
        if ver is None or int(ver[0]) != 14:
            errors.append(f"post-migration db_version expected 14, got {ver}")
        tables = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        for t in _SCHED_SALES_TABLES:
            if t not in tables:
                errors.append(f"{t} missing after v4->v14 migration")
            else:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                if n != 0:
                    errors.append(f"{t} should be empty after additive migration, got {n}")
        # v13->v14 alters presses (a column, not a table) — assert it fired within the chain.
        press_cols = [r[1] for r in conn.execute("PRAGMA table_info(presses)").fetchall()]
        if "current_part" not in press_cols:
            errors.append(f"presses.current_part missing after v4->v14 migration: cols={press_cols}")
        postCounts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in preserved}
        conn.close()
        if postCounts != preCounts:
            errors.append(f"pre-existing data changed by migration: {preCounts} -> {postCounts}")
        if set(glob.glob(backup_glob)) != backupsBefore:
            errors.append("additive v4->v14 migration wrote a backup (should not — additive chain)")

        # --- 3. Populate scheduling/sales on the migrated DB, then roundtrip. ---
        db = w.db
        rng2 = random.Random(99)
        pressNames = F.populatePresses(db, rng2, cfg["presses"])
        presserIds = F.populatePressers(db, rng2, list(db.employees.keys()), cfg["pressers"])
        F.populateShiftWorkweek(db, rng2)
        F.populatePartPressPref(db, rng2, list(db.parts.keys()), pressNames)
        F.populatePresserPressPref(db, rng2, presserIds, pressNames)
        F.populatePartTruck(db, rng2, list(db.parts.keys()))
        clientNames = F.populateClients(db, rng2, cfg["clients"])
        orderNums = F.populateOrders(db, rng2, clientNames, list(db.parts.keys()),
                                     cfg["orders"], today)
        F.populateOrderStatus(db, rng2, orderNums, today)

        before = (len(db.presses), len(db.pressers), len(db.shiftWorkweek),
                  len(db.partPressPref), len(db.presserPressPref), len(db.partTruck),
                  len(db.clients), len(db.orders), len(db.orderStatus), len(db.production))
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False reloading migrated+populated DB")
            return errors
        w2.fileManager.loadFile()
        db2 = w2.db
        after = (len(db2.presses), len(db2.pressers), len(db2.shiftWorkweek),
                 len(db2.partPressPref), len(db2.presserPressPref), len(db2.partTruck),
                 len(db2.clients), len(db2.orders), len(db2.orderStatus), len(db2.production))
        if before != after:
            errors.append(f"scheduling/sales roundtrip mismatch: {before} -> {after}")

        # --- 4. Scheduler + report end-to-end on the migrated+reloaded DB. ---
        result = S.schedule(db2, today)
        for r in result.rows:
            if not S.shiftWorksOn(db2, r.shift, r.date):
                errors.append(f"schedule row on non-working shift-day: {r.date} shift={r.shift}")
            if r.press not in db2.presses:
                errors.append(f"schedule row on unknown press: {r.press}")
            if r.part not in db2.parts:
                errors.append(f"schedule row on unknown part: {r.part}")
        eligible = set()
        for num, order in db2.orders.items():
            st = db2.orderStatus.get(num)
            if st is not None and st.isFulfilled():
                continue
            if S.outstandingToPress(db2, order) <= 0:
                continue
            eligible.add(num)
        scheduledParts = {r.part for r in result.rows}
        flaggedOrders = {f.orderNum for f in result.flags}
        for num in eligible:
            if num not in flaggedOrders and db2.orders[num].part not in scheduledParts:
                errors.append(f"eligible order {num} neither scheduled nor flagged")

        pdfPath = tmp.name + ".sched.pdf"
        PDFReport(db2, pdfPath).scheduleReport(result, 365)
        if not os.path.exists(pdfPath) or os.path.getsize(pdfPath) == 0:
            errors.append("schedule report produced empty/missing file on migrated DB")
        else:
            with open(pdfPath, "rb") as f:
                if f.read(5) != b"%PDF-":
                    errors.append("schedule report on migrated DB lacks %PDF- magic")
        if w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
    finally:
        for handle in (w0, w, w2):
            if handle is not None and handle.fileManager.dbFile is not None:
                handle.fileManager.dbFile.close()
        if pdfPath is not None:
            try:
                os.unlink(pdfPath)
            except OSError:
                pass
        for p in glob.glob(backup_glob):
            try:
                os.unlink(p)
            except OSError:
                pass
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def scheduling_save_rollback() -> list[str]:
    """Step 54: a save that fails mid-body rolls back, leaving the on-disk
    scheduling/sales tables byte-identical — Step 13's atomic-save drill (check
    2b), re-run now that `_saveFileBody` writes the 7 new tables.

    Populates a full fuzz DB (incl. scheduling/sales), saves it cleanly, then
    injects a `RuntimeError` after `_saveFileBody` runs but before saveFile's
    outer commit (the exact failure shape Step 13 used). A sentinel press added
    in memory must NOT survive on disk, and every scheduling/sales table's row
    count must be unchanged — proving the try/rollback/commit wrapper reverts a
    failed save across the new tables, not just the original ones.
    """
    import datetime
    import random
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records.scheduling import Press
    import fuzz_db as F
    import sqlite3

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        rng = random.Random(7)
        cfg = F.SCALES["tiny"]
        today = datetime.date(2026, 6, 25)

        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh DB")
            return errors
        db = w.db
        materialNames = F.populateMaterials(db, rng, cfg["materials"])
        mixtureNames = F.populateMixtures(db, rng, cfg["mixtures"], materialNames)
        F.populatePackaging(db, rng, cfg["packaging"])
        packagingByKind = {k: [] for k in F.PACKAGING_POOL}
        for name in db.packaging:
            packagingByKind[db.packaging[name].kind].append(name)
        partNames = F.populateParts(db, rng, cfg["parts"], mixtureNames, packagingByKind)
        idNums = F.populateEmployees(db, rng, cfg["employees"], today)
        F.populateProduction(db, rng, idNums, partNames, mixtureNames,
                             cfg["productionDays"], today)
        pressNames = F.populatePresses(db, rng, cfg["presses"])
        F.populatePressers(db, rng, idNums, cfg["pressers"])
        F.populateShiftWorkweek(db, rng)
        F.populatePartPressPref(db, rng, partNames, pressNames)
        clientNames = F.populateClients(db, rng, cfg["clients"])
        orderNums = F.populateOrders(db, rng, clientNames, partNames, cfg["orders"], today)
        F.populateOrderStatus(db, rng, orderNums, today)

        w.fileManager.saveFile()  # clean baseline save

        def snapshot():
            conn = sqlite3.connect(tmp.name)
            snap = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in _SCHED_SALES_TABLES}
            snap["_presses"] = sorted(r[0] for r in conn.execute("SELECT name FROM presses"))
            conn.close()
            return snap

        before = snapshot()

        # Mutate in memory: a sentinel press that must be rolled back, never persisted.
        sentinel = "ROLLBACK_SENTINEL_PRESS"
        db.addPress(Press(sentinel))

        fm = w.fileManager
        origBody = fm._saveFileBody

        def failing_body():
            origBody()  # writes everything (incl. the sentinel) into the transaction
            raise RuntimeError("injected failure after _saveFileBody, before commit")

        fm._saveFileBody = failing_body  # type: ignore[method-assign]
        raised = False
        try:
            fm.saveFile()
        except RuntimeError:
            raised = True
        finally:
            del fm._saveFileBody  # restore the class method
        if not raised:
            errors.append("injected save failure did not propagate out of saveFile")

        after = snapshot()
        if after != before:
            errors.append(f"rollback failed: on-disk scheduling/sales state changed "
                          f"{before} -> {after}")
        if sentinel in after["_presses"]:
            errors.append("rolled-back sentinel press leaked onto disk (no rollback)")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors
