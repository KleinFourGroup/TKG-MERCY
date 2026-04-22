"""Repo-wide smoke tests. Run as ``./Scripts/python.exe smoke.py``.

Two baseline checks that MERGE_PLAN steps rely on:

  1. ``compile_all`` — every .py at the repo root compiles (catches syntax
     errors from scripted rewrites like 7c-1 / 7c-2 / 7c-3).
  2. ``empty_roundtrip`` — build ``MainWindow()`` offscreen, save the
     empty DB to a tmp path, reload into a fresh ``MainWindow``, confirm
     no exceptions and the container collections are present and empty.

Step-specific verification still belongs in throwaway ``-c '...'`` scripts
or a new ``smoke_stepN`` function here if broadly useful. This file is the
always-run baseline.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import glob
import py_compile
import sys
import tempfile
from datetime import date as datetime_date


def compile_all() -> list[str]:
    errors = []
    for path in sorted(glob.glob("*.py")):
        if path == "smoke.py":
            continue
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{path}: {e.msg.strip()}")
    return errors


def empty_roundtrip() -> list[str]:
    from PySide6.QtWidgets import QApplication
    from app import MainWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w1 = w2 = None
    try:
        w1 = MainWindow()
        if not w1.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        w1.fileManager.saveFile()
        if w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading saved DB")
            return errors
        w2.fileManager.loadFile()

        db = w2.db
        for name in ("materials", "mixtures", "parts", "packaging",
                     "employees", "reviews", "training", "attendance",
                     "PTO", "notes"):
            coll = getattr(db, name, None)
            if coll is None:
                errors.append(f"db.{name} missing after roundtrip")
            elif len(coll) != 0:
                errors.append(f"db.{name} non-empty ({len(coll)}) after empty roundtrip")
        if not hasattr(db, "holidays"):
            errors.append("db.holidays missing after roundtrip")
    finally:
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        os.unlink(tmp.name)
    return errors


def legacy_anika_migration() -> list[str]:
    """Hand-craft a v1-shape legacy ANIKA DB, open with MERCY, verify v2 state.

    Seeds:
      - 2 mixtures: MixA with 3 materials, MixB with 1 material
      - 3 parts: PartA with 2 pads, PartB with 2 misc, PartC with 1 pad + 1 misc
    Expected post-open state:
      - db_version = 4 (Case 3 stamps MERCY_DB_VERSION after the ANIKA normalization;
        BECKY/production tables are created fresh at current shape)
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
        if version is None or int(version[0]) != 4:
            errors.append(f"db_version expected 4, got {version}")

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
      - db_version = 4
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
        if version is None or int(version[0]) != 4:
            errors.append(f"db_version expected 4, got {version}")

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
    open with MERCY v4, verify the hours column is added and existing data is
    preserved with hours=0."""
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
        if version is None or int(version[0]) != 4:
            errors.append(f"post-migration db_version expected 4, got {version}")
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


def production_roundtrip() -> list[str]:
    """Seed ProductionRecords in-memory, save, reload, assert state is preserved.

    Exercises Step 11 persistence end-to-end without touching the UI:
      - All three actions (Batching -> mix, Pressing -> part, Finishing -> part).
      - scrapQuantity default (0) vs. explicit non-zero.
      - UNIQUE composite-key roundtrip.
      - Delete-then-save sweeps a removed record out of the on-disk table.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import ProductionRecord

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w1 = w2 = None
    try:
        w1 = MainWindow()
        if not w1.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        d = datetime_date(2026, 4, 15)

        # Batching -> mix, default scrap, default hours.
        r1 = ProductionRecord()
        r1.setRecord(101, d, 1, "Batching", "MixA", 7.5)
        if r1.targetType != "mix":
            errors.append(f"r1.targetType: expected 'mix', got {r1.targetType!r}")
        if r1.scrapQuantity != 0:
            errors.append(f"r1.scrapQuantity default: expected 0, got {r1.scrapQuantity!r}")
        if r1.hours != 0:
            errors.append(f"r1.hours default: expected 0, got {r1.hours!r}")
        w1.db.production[r1.key()] = r1

        # Pressing -> part, explicit scrap + hours.
        r2 = ProductionRecord()
        r2.setRecord(102, d, 2, "Pressing", "PartA", 250.0, scrapQuantity=3, hours=7.5)
        if r2.targetType != "part":
            errors.append(f"r2.targetType: expected 'part', got {r2.targetType!r}")
        w1.db.production[r2.key()] = r2

        # Finishing -> part, hours only.
        r3 = ProductionRecord()
        r3.setRecord(102, d, 3, "Finishing", "PartB", 125.5, hours=4.0)
        if r3.targetType != "part":
            errors.append(f"r3.targetType: expected 'part', got {r3.targetType!r}")
        w1.db.production[r3.key()] = r3

        w1.fileManager.saveFile()
        if w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()

        # --- reload and verify ---
        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading production DB")
            return errors
        w2.fileManager.loadFile()

        db = w2.db
        if len(db.production) != 3:
            errors.append(f"expected 3 production records after reload, got {len(db.production)}")

        if r1.key() not in db.production:
            errors.append(f"r1 key missing after reload: {r1.key()}")
        else:
            got = db.production[r1.key()]
            if got.action != "Batching" or got.targetType != "mix" or got.targetName != "MixA":
                errors.append(f"r1 post-reload: action={got.action!r} targetType={got.targetType!r} targetName={got.targetName!r}")
            if got.quantity != 7.5:
                errors.append(f"r1 post-reload quantity: got {got.quantity!r}")
            if got.scrapQuantity != 0:
                errors.append(f"r1 post-reload scrap: got {got.scrapQuantity!r}")
            if got.hours != 0:
                errors.append(f"r1 post-reload hours: got {got.hours!r}")

        if r2.key() not in db.production:
            errors.append(f"r2 key missing after reload: {r2.key()}")
        else:
            got = db.production[r2.key()]
            if got.action != "Pressing" or got.targetType != "part":
                errors.append(f"r2 post-reload: action={got.action!r} targetType={got.targetType!r}")
            if got.scrapQuantity != 3:
                errors.append(f"r2 post-reload scrap: got {got.scrapQuantity!r}")
            if got.hours != 7.5:
                errors.append(f"r2 post-reload hours: got {got.hours!r}")

        if r3.key() not in db.production:
            errors.append(f"r3 key missing after reload: {r3.key()}")
        else:
            got = db.production[r3.key()]
            if got.action != "Finishing" or got.targetType != "part":
                errors.append(f"r3 post-reload: action={got.action!r} targetType={got.targetType!r}")
            if got.hours != 4.0:
                errors.append(f"r3 post-reload hours: got {got.hours!r}")

        # --- delete one, save, reload: confirm sweep removes it ---
        del db.production[r2.key()]
        w2.fileManager.saveFile()
        if w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()

        w3 = MainWindow()
        try:
            if not w3.fileManager.setFile(tmp.name):
                errors.append("setFile returned False when reloading after delete")
            else:
                w3.fileManager.loadFile()
                if len(w3.db.production) != 2:
                    errors.append(f"after delete+save+reload: expected 2 records, got {len(w3.db.production)}")
                if r2.key() in w3.db.production:
                    errors.append("after delete+save+reload: r2 still present")
        finally:
            if w3.fileManager.dbFile is not None:
                w3.fileManager.dbFile.close()
    finally:
        if w1 is not None and w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def production_tool_change_roundtrip() -> list[str]:
    """Step 22: seed a Tool Change record, save, reload, verify empty-state shape.

    Passes deliberately-garbage targetName and scrapQuantity to `setRecord` to
    confirm the `targetType == ""` branch coerces them to the canonical
    empty-state values before the record is stored. Then saves, reloads, and
    checks the canonical shape survives the SQLite roundtrip:

      - targetType  == ""
      - targetName  == ""
      - scrapQuantity == 0
      - quantity + hours are preserved as entered (they vary per shift — one
        row per employee per shift carries the count of changes).
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import ProductionRecord

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w1 = w2 = None
    try:
        w1 = MainWindow()
        if not w1.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        d = datetime_date(2026, 4, 15)

        # Pass garbage targetName and scrapQuantity; setRecord must coerce.
        r = ProductionRecord()
        r.setRecord(101, d, 2, "Tool Change", "stray-part-name",
                    3.0, scrapQuantity=99, hours=0.75)
        if r.targetType != "":
            errors.append(f"targetType: expected '', got {r.targetType!r}")
        if r.targetName != "":
            errors.append(f"targetName coercion failed: got {r.targetName!r}")
        if r.scrapQuantity != 0:
            errors.append(f"scrapQuantity coercion failed: got {r.scrapQuantity!r}")
        if r.quantity != 3.0:
            errors.append(f"quantity should pass through: got {r.quantity!r}")
        if r.hours != 0.75:
            errors.append(f"hours should pass through: got {r.hours!r}")
        w1.db.production[r.key()] = r

        w1.fileManager.saveFile()
        if w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()

        # --- reload and verify ---
        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading tool-change DB")
            return errors
        w2.fileManager.loadFile()

        db = w2.db
        if len(db.production) != 1:
            errors.append(f"expected 1 production record after reload, got {len(db.production)}")
        if r.key() not in db.production:
            errors.append(f"tool-change key missing after reload: {r.key()}")
        else:
            got = db.production[r.key()]
            if got.action != "Tool Change":
                errors.append(f"post-reload action: got {got.action!r}")
            if got.targetType != "":
                errors.append(f"post-reload targetType: got {got.targetType!r}")
            if got.targetName != "":
                errors.append(f"post-reload targetName: got {got.targetName!r}")
            if got.scrapQuantity != 0:
                errors.append(f"post-reload scrapQuantity: got {got.scrapQuantity!r}")
            if got.quantity != 3.0:
                errors.append(f"post-reload quantity: got {got.quantity!r}")
            if got.hours != 0.75:
                errors.append(f"post-reload hours: got {got.hours!r}")
    finally:
        if w1 is not None and w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def production_report() -> list[str]:
    """Step 12: generate each production report and assert files are non-empty.

    Seeds one employee + three records (one per action), then exercises:
      - productionSummaryReport (multi-employee grid path with the totals row)
      - productionActionReport  (single-action filter)
      - productionTargetReport  (single-part filter, both totals + per-action)
      - productionEmployeeReport (single-employee, mixed-action totals)
      - empty-range path (no records in window) — should still render a page.
    Doesn't parse PDF content; success is generation without exception + non-empty file.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import ProductionRecord, Employee
    from report import PDFReport

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    pdfPaths: list[str] = []
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        emp = Employee()
        emp.idNum = 101
        emp.lastName = "Smith"
        emp.firstName = "Alice"
        emp.shift = 1
        emp.fullTime = True
        emp.status = True
        emp.anniversary = datetime_date(2020, 1, 1)
        w.db.employees[emp.idNum] = emp

        d = datetime_date(2026, 4, 15)
        for spec in [(d, 1, "Batching", "MixA", 7.5, 0),
                     (d, 2, "Pressing", "PartA", 250.0, 3),
                     (d, 3, "Finishing", "PartB", 125.5, 0)]:
            r = ProductionRecord()
            r.setRecord(emp.idNum, *spec)
            w.db.production[r.key()] = r

        start = datetime_date(2026, 4, 1)
        end = datetime_date(2026, 4, 30)
        emptyStart = datetime_date(2030, 1, 1)
        emptyEnd = datetime_date(2030, 1, 31)

        reports = [
            ("summary", lambda p: p.productionSummaryReport(start, end)),
            ("action",  lambda p: p.productionActionReport("Pressing", start, end)),
            ("target",  lambda p: p.productionTargetReport("part", "PartA", start, end)),
            ("employee", lambda p: p.productionEmployeeReport(emp.idNum, start, end)),
            ("empty",   lambda p: p.productionSummaryReport(emptyStart, emptyEnd)),
        ]
        for name, fn in reports:
            tmpPdf = tempfile.NamedTemporaryFile(suffix=f"-{name}.pdf", delete=False)
            tmpPdf.close()
            pdfPaths.append(tmpPdf.name)
            try:
                pdf = PDFReport(w.db, tmpPdf.name)
                fn(pdf)
            except Exception as e:
                errors.append(f"report {name} raised: {e!r}")
                continue
            if not os.path.exists(tmpPdf.name) or os.path.getsize(tmpPdf.name) == 0:
                errors.append(f"report {name} produced empty/missing file")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        for p in pdfPaths:
            try:
                os.unlink(p)
            except OSError:
                pass
    return errors


def production_refresh_on_delete() -> list[str]:
    """Step 15: deleting an employee must not leave the production tab stale.

    Seeds one employee + one production record referencing them, calls
    ``db.delEmployee`` (same path the Employees tab hits), then:
      - asserts the orphan production record still exists in-memory (Step 15
        keeps orphans rather than cascading the delete).
      - asserts ``productionTab.refresh()`` does not raise when iterating
        over a record whose ``employeeId`` is no longer a key in
        ``db.employees`` (orphan renders as "(missing #id)").
      - asserts the employee-filter dropdown drops the deleted employee
        after refresh, so the user cannot re-select them.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import (Employee, ProductionRecord,
                         EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB,
                         EmployeePTODB, EmployeeNotesDB)

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        emp = Employee()
        emp.idNum = 101
        emp.lastName = "Smith"
        emp.firstName = "Alice"
        emp.shift = 1
        emp.fullTime = True
        emp.status = True
        emp.anniversary = datetime_date(2020, 1, 1)
        # delEmployee requires all the shadow collections to exist, so mirror
        # the real new-employee path from employees_tab.py.
        w.db.addEmployee(emp)
        w.db.addEmployeeReviews(EmployeeReviewsDB(emp.idNum))
        w.db.addEmployeeTraining(EmployeeTrainingDB(emp.idNum))
        w.db.addEmployeePoints(EmployeePointsDB(emp.idNum))
        w.db.addEmployeePTO(EmployeePTODB(emp.idNum))
        w.db.addEmployeeNotes(EmployeeNotesDB(emp.idNum))

        r = ProductionRecord()
        r.setRecord(emp.idNum, datetime_date(2026, 4, 15), 1, "Batching", "MixA", 7.5)
        w.db.production[r.key()] = r

        # Prime the production tab so the filter reflects the seeded employee.
        w.productionTab.refresh()
        filterIds = [w.productionTab.employeeFilter.itemData(i)
                     for i in range(w.productionTab.employeeFilter.count())]
        if emp.idNum not in filterIds:
            errors.append(f"pre-delete: employee {emp.idNum} missing from filter {filterIds}")

        # Delete via the same entry point the Employees tab uses.
        w.db.delEmployee(emp.idNum)

        if r.key() not in w.db.production:
            errors.append("post-delete: production record was cascaded away (should be kept as orphan)")
        else:
            got = w.db.production[r.key()]
            if got.employeeId != 101:
                errors.append(f"post-delete: orphan employeeId mutated to {got.employeeId!r}")

        # The actual regression: refresh() used to iterate stale data and,
        # separately, the filter kept the deleted employee as a selectable row.
        try:
            w.productionTab.refresh()
        except Exception as e:
            errors.append(f"productionTab.refresh() raised after delete: {e!r}")
            return errors

        filterIds = [w.productionTab.employeeFilter.itemData(i)
                     for i in range(w.productionTab.employeeFilter.count())]
        if emp.idNum in filterIds:
            errors.append(f"post-delete: deleted employee still in filter {filterIds}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def production_batch_roundtrip() -> list[str]:
    """Step 16: drive ProductionBatchDialog headlessly and verify atomic save.

    Seeds an employee + a part + a mix, opens the batch dialog, constructs four
    rows spanning two shifts against a mix (Batching action), saves, asserts:
      - all four records landed in-memory with the correct shared date/action
      - save/reload roundtrip preserves them on disk
    Then re-opens the dialog and attempts a batch containing a duplicate key
    against the already-saved data — expect the save to be refused and the
    in-memory dict to be unchanged.
    """
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app import MainWindow
    from records import (Employee, Mixture,
                         EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB,
                         EmployeePTODB, EmployeeNotesDB)
    from production_tab import ProductionBatchDialog

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    # _save() pops a success/critical QMessageBox; offscreen those would block.
    # Stub them out so we can drive the real save path headlessly.
    origCrit = QMessageBox.critical
    origInfo = QMessageBox.information
    QMessageBox.critical = staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]
    QMessageBox.information = staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w1 = w2 = None
    try:
        w1 = MainWindow()
        if not w1.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        emp = Employee()
        emp.idNum = 101
        emp.lastName = "Smith"
        emp.firstName = "Alice"
        emp.shift = 1
        emp.fullTime = True
        emp.status = True
        emp.anniversary = datetime_date(2020, 1, 1)
        w1.db.addEmployee(emp)
        w1.db.addEmployeeReviews(EmployeeReviewsDB(emp.idNum))
        w1.db.addEmployeeTraining(EmployeeTrainingDB(emp.idNum))
        w1.db.addEmployeePoints(EmployeePointsDB(emp.idNum))
        w1.db.addEmployeePTO(EmployeePTODB(emp.idNum))
        w1.db.addEmployeeNotes(EmployeeNotesDB(emp.idNum))

        w1.db.mixtures["MixA"] = Mixture("MixA")
        w1.db.mixtures["MixB"] = Mixture("MixB")

        # Prime the tab so toolbar state reflects the seeded data.
        w1.productionTab.refresh()

        dialog = ProductionBatchDialog(w1.productionTab, w1)
        # Fresh dialog starts with one row. Add three more for four total.
        dialog._addRow()
        dialog._addRow()
        dialog._addRow()
        if len(dialog.rows) != 4:
            errors.append(f"expected 4 rows after 3x _addRow, got {len(dialog.rows)}")

        # Shared header: Batching against mixes on a fixed date.
        dialog.actionBox.setCurrentText("Batching")
        from utils import toQDate
        batchDate = datetime_date(2026, 4, 18)
        dialog.dateEdit.setDate(toQDate(batchDate))

        # Two on shift 1, two on shift 2, alternating between MixA/MixB so the
        # UNIQUE (employeeId, date, shift, targetType, targetName, action) keys
        # are distinct.
        plan = [
            ("1", "MixA", "10", "0", "8"),
            ("1", "MixB", "12", "1", "7.5"),
            ("2", "MixA", "14", "0", "0"),
            ("2", "MixB", "16", "2", "6"),
        ]
        for row, (shift, target, qty, scrap, hours) in zip(dialog.rows, plan):
            row.shiftBox.setCurrentText(shift)
            idx = row.targetBox.findText(target)
            if idx < 0:
                errors.append(f"target {target!r} missing from row combo")
                return errors
            row.targetBox.setCurrentIndex(idx)
            row.quantityEdit.setText(qty)
            row.scrapEdit.setText(scrap)
            row.hoursEdit.setText(hours)

        dialog._save()

        if len(w1.db.production) != 4:
            errors.append(f"after batch save: expected 4 records in-memory, got {len(w1.db.production)}")
        for shift, target, qty, scrap, hours in plan:
            key = (101, batchDate, int(shift), "mix", target, "Batching")
            if key not in w1.db.production:
                errors.append(f"missing record after save: {key}")
                continue
            rec = w1.db.production[key]
            if rec.quantity != float(qty):
                errors.append(f"{key}: quantity expected {qty}, got {rec.quantity!r}")
            if rec.scrapQuantity != float(scrap):
                errors.append(f"{key}: scrap expected {scrap}, got {rec.scrapQuantity!r}")
            if rec.hours != float(hours):
                errors.append(f"{key}: hours expected {hours}, got {rec.hours!r}")

        w1.fileManager.saveFile()
        if w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()
            w1.fileManager.dbFile = None

        # --- reload and verify on-disk roundtrip ---
        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading batch DB")
            return errors
        w2.fileManager.loadFile()
        if len(w2.db.production) != 4:
            errors.append(f"after reload: expected 4 records, got {len(w2.db.production)}")

        # --- attempt a duplicate-key batch; expect refusal ---
        w2.productionTab.refresh()
        dialog2 = ProductionBatchDialog(w2.productionTab, w2)
        dialog2.actionBox.setCurrentText("Batching")
        dialog2.dateEdit.setDate(toQDate(batchDate))
        # Single row that exactly duplicates an existing key.
        row = dialog2.rows[0]
        row.shiftBox.setCurrentText("1")
        idx = row.targetBox.findText("MixA")
        if idx >= 0:
            row.targetBox.setCurrentIndex(idx)
        row.quantityEdit.setText("99")
        row.scrapEdit.setText("0")

        beforeCount = len(w2.db.production)
        # _save should refuse (QMessageBox.critical pops but doesn't raise offscreen).
        dialog2._save()
        if len(w2.db.production) != beforeCount:
            errors.append(f"duplicate-key batch was not refused: count {beforeCount} -> {len(w2.db.production)}")

        # --- attempt an intra-batch duplicate; expect refusal ---
        dialog3 = ProductionBatchDialog(w2.productionTab, w2)
        dialog3.actionBox.setCurrentText("Batching")
        dialog3.dateEdit.setDate(toQDate(datetime_date(2026, 4, 19)))  # new date, not colliding with saved
        dialog3._addRow()
        for r in dialog3.rows:
            r.shiftBox.setCurrentText("1")
            idx = r.targetBox.findText("MixA")
            if idx >= 0:
                r.targetBox.setCurrentIndex(idx)
            r.quantityEdit.setText("5")
            r.scrapEdit.setText("0")
        beforeCount = len(w2.db.production)
        dialog3._save()
        if len(w2.db.production) != beforeCount:
            errors.append(f"intra-batch duplicate was not refused: count {beforeCount} -> {len(w2.db.production)}")
    finally:
        if w1 is not None and w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        QMessageBox.critical = origCrit  # type: ignore[assignment]
        QMessageBox.information = origInfo  # type: ignore[assignment]
    return errors


def qsettings_reopen() -> list[str]:
    """Step 20: QSettings lastDbPath round-trips through ``_loadPath``.

    Saves an empty DB, stashes its path under ``lastDbPath`` in an isolated
    INI-backed QSettings store, then drives ``MainWindow._loadPath`` on a
    fresh window to simulate the startup auto-reopen hook (bypassing the
    modal). Asserts the DB loads, ``fileManager.filePath`` is set, and
    ``_loadPath`` re-persists ``lastDbPath``. Also checks that a stale
    (missing) path is caught by the caller's ``os.path.isfile`` guard that
    ``main.py`` uses before invoking the helper.
    """
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication
    from app import MainWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    # Isolate QSettings storage so the test never touches the user's real
    # registry/plist. IniFormat + a tmpdir gets torn down cleanly at the end.
    origOrg = QCoreApplication.organizationName()
    origApp = QCoreApplication.applicationName()
    QCoreApplication.setOrganizationName("k4g-mercy-smoke")
    QCoreApplication.setApplicationName("MERCY-smoke")
    settingsDir = tempfile.mkdtemp(prefix="mercy-qsettings-")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settingsDir)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w1 = w2 = None
    try:
        w1 = MainWindow()
        if not w1.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        w1.fileManager.saveFile()
        if w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()
            w1.fileManager.dbFile = None

        # Simulate a previous session having persisted lastDbPath.
        QSettings().setValue("lastDbPath", tmp.name)
        # Force a sync so the value is readable by a fresh QSettings instance.
        QSettings().sync()

        w2 = MainWindow()
        lastPath = QSettings().value("lastDbPath")
        if lastPath != tmp.name:
            errors.append(f"QSettings lastDbPath did not persist: got {lastPath!r}")
            return errors
        if not os.path.isfile(lastPath):
            errors.append(f"lastPath is not a file on disk: {lastPath}")
            return errors

        if not w2._loadPath(lastPath):
            errors.append(f"_loadPath returned False for {lastPath}")
            return errors
        if w2.fileManager.filePath != tmp.name:
            errors.append(f"filePath after _loadPath: expected {tmp.name}, got {w2.fileManager.filePath}")

        post = QSettings().value("lastDbPath")
        if post != tmp.name:
            errors.append(f"_loadPath did not re-persist lastDbPath: got {post!r}")

        # Stale-path guard: main.py checks os.path.isfile before calling
        # _loadPath, so a missing path never reaches the helper. Verify the
        # guard catches a plausible stale path.
        stale = tmp.name + ".missing"
        if os.path.exists(stale):
            errors.append(f"test setup bug: {stale} should not exist")
        elif os.path.isfile(stale):
            errors.append("os.path.isfile true-positive on a path that does not exist")
    finally:
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        if w1 is not None and w1.fileManager.dbFile is not None:
            w1.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        import shutil
        shutil.rmtree(settingsDir, ignore_errors=True)
        QCoreApplication.setOrganizationName(origOrg)
        QCoreApplication.setApplicationName(origApp)
    return errors


def main() -> int:
    failed = False
    for name, fn in [("compile_all", compile_all),
                     ("empty_roundtrip", empty_roundtrip),
                     ("legacy_anika_migration", legacy_anika_migration),
                     ("legacy_becky_migration", legacy_becky_migration),
                     ("legacy_merge", legacy_merge),
                     ("mercy_v3_to_v4_migration", mercy_v3_to_v4_migration),
                     ("production_roundtrip", production_roundtrip),
                     ("production_tool_change_roundtrip", production_tool_change_roundtrip),
                     ("production_report", production_report),
                     ("production_refresh_on_delete", production_refresh_on_delete),
                     ("production_batch_roundtrip", production_batch_roundtrip),
                     ("qsettings_reopen", qsettings_reopen)]:
        errors = fn()
        if errors:
            failed = True
            print(f"FAIL {name}")
            for e in errors:
                print(f"  {e}")
        else:
            print(f"PASS {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
