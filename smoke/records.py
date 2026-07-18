"""Schema + roundtrip checks: compile-everything, empty-DB roundtrip,
production-record roundtrip (incl. Tool Change shape), and the Step 23
quantity-positive validation. The cheap baseline tier."""
import glob
import os
import py_compile
import sys
import tempfile
from datetime import date as datetime_date


def compile_all() -> list[str]:
    """py_compile every .py at repo root. Catches syntax errors from
    mechanical rewrites (e.g. the Step 7c-1 / 7c-2 / 7c-3 sweeps and the
    Step 29 hygiene sweep) before the heavier checks try to import them.
    ~1s. Note: the `records/` and `smoke/` packages aren't walked here; they
    get covered transitively by the heavier checks importing from them."""
    errors = []
    for path in sorted(glob.glob("*.py")):
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{path}: {e.msg.strip()}")
    return errors


def empty_roundtrip() -> list[str]:
    """Build a fresh MainWindow against an empty DB, save to a tmp path, reload
    into a second MainWindow, and assert all expected collections survive as
    empty containers. Catches regressions in setFile / saveFile / loadFile for
    the no-data case. Closes sqlite handles before os.unlink because Windows
    file-locks open connections."""
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
                     "PTO", "notes", "presses", "pressers", "shiftWorkweek",
                     "partPressPref", "partTruck", "clients", "orders"):
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


def production_quantity_validation() -> list[str]:
    """Step 23: quantity=0 must be rejected at both production entry points.

    Drives ProductionEditWindow (Quick Entry) and ProductionBatchDialog (Batch
    Entry) with a quantity of ``0`` and asserts that validation fires — the
    user-facing error mentions Quantity must be positive, and no record gets
    stored. Guards against regression to ``"nonneg"``; scrap and hours stay
    ``"nonneg"`` and are unaffected.
    """
    import production_tab
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app import MainWindow
    from records import (Employee, Mixture,
                         EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB,
                         EmployeePTODB, EmployeeNotesDB)
    from production_tab import ProductionEditWindow, ProductionBatchDialog
    from utils import toQDate

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    # Capture everything the UI would have surfaced through errorMessage; stub
    # the batch dialog's QMessageBox calls for parity with production_batch_*.
    captured: list[list[str]] = []
    origErrorMessage = production_tab.errorMessage
    production_tab.errorMessage = lambda parent, errs: captured.append(list(errs))  # type: ignore[assignment]
    origCrit = QMessageBox.critical
    origInfo = QMessageBox.information
    QMessageBox.critical = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]
    QMessageBox.information = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]

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
        w.db.addEmployee(emp)
        w.db.addEmployeeReviews(EmployeeReviewsDB(emp.idNum))
        w.db.addEmployeeTraining(EmployeeTrainingDB(emp.idNum))
        w.db.addEmployeePoints(EmployeePointsDB(emp.idNum))
        w.db.addEmployeePTO(EmployeePTODB(emp.idNum))
        w.db.addEmployeeNotes(EmployeeNotesDB(emp.idNum))
        # addMixture, not a raw dict insert — see the note in smoke/ui.py's
        # production_batch_roundtrip: without the db back-reference getCost raises.
        w.db.addMixture(Mixture("MixA"))
        w.productionTab.refresh()

        # --- Quick Entry: quantity=0 must fail with a Quantity-positive error ---
        edit = ProductionEditWindow(w.productionTab, None, w)
        edit.actionBox.setCurrentText("Batching")
        tIdx = edit.targetBox.findText("MixA")
        if tIdx >= 0:
            edit.targetBox.setCurrentIndex(tIdx)
        edit.quantityEdit.setText("0")
        edit.scrapEdit.setText("0")  # nonneg still accepted
        edit.hoursEdit.setText("1")

        captured.clear()
        ok = edit.readData(isNew=True)
        if ok:
            errors.append("Quick Entry: readData returned True for quantity=0 (expected rejection)")
        joined = " | ".join(m for batch in captured for m in batch)
        if "Quantity" not in joined or "positive" not in joined:
            errors.append(
                f"Quick Entry: expected a 'Quantity ... positive' error for quantity=0, "
                f"got: {joined!r}"
            )
        if len(w.db.production) != 0:
            errors.append(
                f"Quick Entry: record was stored despite rejection (len={len(w.db.production)})"
            )
        edit.close()

        # --- Batch Entry: a row with quantity=0 must block the whole batch ---
        dialog = ProductionBatchDialog(w.productionTab, w)
        dialog.actionBox.setCurrentText("Batching")
        dialog.dateEdit.setDate(toQDate(datetime_date(2026, 4, 24)))
        row = dialog.rows[0]
        row.shiftBox.setCurrentText("1")
        rIdx = row.targetBox.findText("MixA")
        if rIdx >= 0:
            row.targetBox.setCurrentIndex(rIdx)
        row.quantityEdit.setText("0")
        row.scrapEdit.setText("0")
        row.hoursEdit.setText("1")

        captured.clear()
        before = len(w.db.production)
        dialog._save()
        after = len(w.db.production)
        if after != before:
            errors.append(
                f"Batch Entry: quantity=0 should have blocked the batch; "
                f"production went {before} -> {after}"
            )
        joined = " | ".join(m for batch in captured for m in batch)
        if "quantity" not in joined or "positive" not in joined:
            errors.append(
                f"Batch Entry: expected a 'quantity ... positive' error for quantity=0, "
                f"got: {joined!r}"
            )
        dialog.close()
    finally:
        production_tab.errorMessage = origErrorMessage  # type: ignore[assignment]
        QMessageBox.critical = origCrit  # type: ignore[assignment]
        QMessageBox.information = origInfo  # type: ignore[assignment]
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def mixture_full_loi_material() -> list[str]:
    """Step 84-post-triage: a mixture containing a 100 %-LOI material must not
    divide by zero.

    A fully-combustible organic binder (PVA, lard oil) legitimately has
    LOI = 100 % — it leaves no calcined residue — so ``Mixture.getProp`` on the
    ignited (LOI) basis hit ``matVal / (1 - 100/100)`` = a 0/0 singularity.
    Because the Mixtures tab renders oxide columns on every open/edit
    (``_refreshAllTabs`` -> ``mixturesTab.refreshTable`` -> ``getProp('Al2O3')``),
    the uncaught ZeroDivisionError blew straight out of the File->Open flow,
    leaving an empty window that the team read as a *wiped database*. The data
    on disk was intact; the app just never finished rendering. Real trigger:
    the "Mold Mend P" mixtures with "PVA - Dry" in the shop DB.

    The fix clamps the LOI fraction below 1 (mirroring
    ``scheduling.requiredPressed``'s scrap clamp). This check pins:
      1. ``getProp`` returns a finite value (no crash) for every oxide when a
         100 %-LOI binder with all-zero oxides is present — and equals what the
         non-volatile material alone contributes (the binder adds 0).
      2. The Mixtures tab refresh and the Mix Report both render, not raise
         (the two user-facing surfaces that showed the "wipe").
      3. A material with LOI just under the clamp (99.0 %) is left *exactly*
         unclamped, so the fix perturbs no good data.
      4. The impossible case (oxides present *and* LOI = 100 %) yields a finite,
         absurd-but-visible number rather than crashing (dual-mandate: surface
         bad data loudly, never corrupt or silently swallow).
    """
    import math
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records.products import Material, Mixture
    from report import PDFReport

    errors: list[str] = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    pdfPath = None
    w = None

    def _mat(name, si, loi):
        # A materially-complete Material: every oxide + size + otherChem set
        # non-None so getProp never short-circuits on None and the Mix Report's
        # f"{...:.1f}" formatting has real numbers to render.
        m = Material(name)
        m.setChems(si, 10.0, 1.0, 0.5, 0.0, 0.0, 0.1, 0.1, 0.1, 0.1, loi)
        m.setSizes(20.0, 20.0, 20.0, 20.0, 20.0)
        m.otherChem = 0.0
        m.setCost(100.0, 10.0)
        return m

    OXIDES = ("SiO2", "Al2O3", "Fe2O3", "TiO2", "Li2O",
              "P2O5", "Na2O", "CaO", "K2O", "MgO", "otherChem")
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        # A refractory (real oxides, ordinary LOI) + a fully-volatile binder
        # (all-zero oxides, LOI = 100). addMaterial/addMixture wire the db
        # back-reference getProp needs.
        refractory = _mat("Refractory", 45.0, 13.8)
        binder = Material("PVA Binder")
        binder.setChems(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0)
        binder.setSizes(0.0, 0.0, 0.0, 0.0, 0.0)
        binder.otherChem = 0.0
        binder.setCost(100.0, 10.0)
        w.db.addMaterial(refractory)
        w.db.addMaterial(binder)

        mix = Mixture("Mold Mend")
        mix.add("Refractory", 90.0)
        mix.add("PVA Binder", 10.0)
        w.db.addMixture(mix)

        # (1) getProp is finite for every oxide, and the binder contributes 0.
        for ox in OXIDES:
            try:
                val = mix.getProp(ox)
            except ZeroDivisionError:
                errors.append(f"getProp({ox!r}) still divides by zero on a 100%-LOI binder")
                continue
            except Exception as e:  # noqa: BLE001
                errors.append(f"getProp({ox!r}) raised {e!r}")
                continue
            if val is None or not math.isfinite(val):
                errors.append(f"getProp({ox!r}) returned non-finite {val!r}")
        # Correctness: with the binder adding nothing, SiO2 == refractory's own
        # calcined contribution at its 90 % weight share. Guarded so a regression
        # that reintroduces the crash reports a clean FAIL, not an aborted battery.
        expectedSiO2 = 0.9 * 45.0 / (1 - 13.8 / 100)
        try:
            gotSiO2 = mix.getProp("SiO2")
        except Exception as e:  # noqa: BLE001
            gotSiO2 = None
            errors.append(f"getProp('SiO2') raised: {e!r}")
        if gotSiO2 is None or not math.isclose(gotSiO2, expectedSiO2, rel_tol=1e-9):
            errors.append(f"getProp('SiO2')={gotSiO2!r}, expected ~{expectedSiO2!r} "
                          f"(binder should contribute 0)")

        # (2) The two user-facing surfaces that showed the "wipe" must render.
        try:
            w.mixturesTab.refreshTable()
        except Exception as e:  # noqa: BLE001
            errors.append(f"mixturesTab.refreshTable() raised on a 100%-LOI mix: {e!r}")
        tmpPdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmpPdf.close()
        pdfPath = tmpPdf.name
        try:
            PDFReport(w.db, pdfPath).mixReport("Mold Mend")
        except Exception as e:  # noqa: BLE001
            errors.append(f"mixReport raised on a 100%-LOI mix: {e!r}")
        else:
            if not os.path.exists(pdfPath) or os.path.getsize(pdfPath) == 0:
                errors.append("mixReport produced an empty/missing file")

        # (3) LOI just under the clamp (99.0 %) is left exactly unclamped, so no
        # good data shifts. A clamp at 99.9 would give 20/0.001; unclamped is
        # 20/0.01 — a 10x gap this pins shut.
        justUnder = _mat("JustUnder", 20.0, 99.0)
        w.db.addMaterial(justUnder)
        plain = Mixture("Plain")
        plain.add("JustUnder", 100.0)
        w.db.addMixture(plain)
        expectedPlain = 1.0 * 20.0 / (1 - 99.0 / 100)  # == 2000.0
        try:
            gotPlain = plain.getProp("SiO2")
        except Exception as e:  # noqa: BLE001
            gotPlain = None
            errors.append(f"getProp on LOI=99.0 material raised: {e!r}")
        if gotPlain is None or not math.isclose(gotPlain, expectedPlain, rel_tol=1e-9):
            errors.append(f"getProp on LOI=99.0 material = {gotPlain!r}, expected "
                          f"{expectedPlain!r}: the clamp must not perturb LOI <= 99.9")

        # (4) Impossible data (oxides present AND LOI = 100) -> finite + absurd,
        # not a crash. Visibly wrong beats silently swallowed.
        bogus = _mat("BogusBinder", 50.0, 100.0)  # 50% SiO2 yet 100% burns off
        w.db.addMaterial(bogus)
        bad = Mixture("Bad")
        bad.add("BogusBinder", 100.0)
        w.db.addMixture(bad)
        try:
            badVal = bad.getProp("SiO2")
        except Exception as e:  # noqa: BLE001
            errors.append(f"getProp on impossible (oxide+100%LOI) data raised {e!r}")
        else:
            if badVal is None or not math.isfinite(badVal):
                errors.append(f"impossible-data getProp returned non-finite {badVal!r}")
            elif badVal <= 50.0:
                errors.append(f"impossible-data getProp={badVal!r} should be absurdly "
                              f"large (visibly wrong), not a plausible {50.0}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        if pdfPath is not None:
            try:
                os.unlink(pdfPath)
            except OSError:
                pass
    return errors
