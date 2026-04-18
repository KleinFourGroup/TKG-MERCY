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


def main() -> int:
    failed = False
    for name, fn in [("compile_all", compile_all),
                     ("empty_roundtrip", empty_roundtrip),
                     ("legacy_anika_migration", legacy_anika_migration),
                     ("legacy_becky_migration", legacy_becky_migration)]:
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
