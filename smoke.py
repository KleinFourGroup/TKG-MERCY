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
      - db_version = 2
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
        if version is None or int(version[0]) != 2:
            errors.append(f"db_version expected 2, got {version}")

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


def main() -> int:
    failed = False
    for name, fn in [("compile_all", compile_all),
                     ("empty_roundtrip", empty_roundtrip),
                     ("legacy_anika_migration", legacy_anika_migration)]:
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
