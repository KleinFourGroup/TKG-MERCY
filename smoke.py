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
      - db_version = 3 (legacy ANIKA takes the full v1->v3 path; BECKY side is empty
        so the v2->v3 step is a no-op version bump)
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
        if version is None or int(version[0]) != 3:
            errors.append(f"db_version expected 3, got {version}")

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
      - db_version = 3
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
        if version is None or int(version[0]) != 3:
            errors.append(f"db_version expected 3, got {version}")

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

        # Batching -> mix, default scrap.
        r1 = ProductionRecord()
        r1.setRecord(101, d, 1, "Batching", "MixA", 7.5)
        if r1.targetType != "mix":
            errors.append(f"r1.targetType: expected 'mix', got {r1.targetType!r}")
        if r1.scrapQuantity != 0:
            errors.append(f"r1.scrapQuantity default: expected 0, got {r1.scrapQuantity!r}")
        w1.db.production[r1.key()] = r1

        # Pressing -> part, explicit scrap.
        r2 = ProductionRecord()
        r2.setRecord(102, d, 2, "Pressing", "PartA", 250.0, scrapQuantity=3)
        if r2.targetType != "part":
            errors.append(f"r2.targetType: expected 'part', got {r2.targetType!r}")
        w1.db.production[r2.key()] = r2

        # Finishing -> part, different shift/date/target to avoid UNIQUE overlap with r2.
        r3 = ProductionRecord()
        r3.setRecord(102, d, 3, "Finishing", "PartB", 125.5)
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

        if r2.key() not in db.production:
            errors.append(f"r2 key missing after reload: {r2.key()}")
        else:
            got = db.production[r2.key()]
            if got.action != "Pressing" or got.targetType != "part":
                errors.append(f"r2 post-reload: action={got.action!r} targetType={got.targetType!r}")
            if got.scrapQuantity != 3:
                errors.append(f"r2 post-reload scrap: got {got.scrapQuantity!r}")

        if r3.key() not in db.production:
            errors.append(f"r3 key missing after reload: {r3.key()}")
        else:
            got = db.production[r3.key()]
            if got.action != "Finishing" or got.targetType != "part":
                errors.append(f"r3 post-reload: action={got.action!r} targetType={got.targetType!r}")

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


def main() -> int:
    failed = False
    for name, fn in [("compile_all", compile_all),
                     ("empty_roundtrip", empty_roundtrip),
                     ("legacy_anika_migration", legacy_anika_migration),
                     ("legacy_becky_migration", legacy_becky_migration),
                     ("legacy_merge", legacy_merge),
                     ("production_roundtrip", production_roundtrip),
                     ("production_report", production_report)]:
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
