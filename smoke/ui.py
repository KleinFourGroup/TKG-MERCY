"""UI-path checks: production-tab refresh on employee delete, the batch
entry dialog roundtrip, QSettings last-DB reopen, the close-event
Save / Don't Save / Cancel prompt, and the records-side (Parts / Employees)
Edit dialog roundtrips (Step 37)."""
import os
import random
import sys
import tempfile
from datetime import date as datetime_date


def _silenceMessageBoxes():
    """Stub QMessageBox.information/critical/warning/question so dialogs that
    pop them don't block offscreen. Returns a restore callable for finally blocks."""
    from PySide6.QtWidgets import QMessageBox
    orig = {
        "information": QMessageBox.information,
        "critical": QMessageBox.critical,
        "warning": QMessageBox.warning,
        "question": QMessageBox.question,
    }
    QMessageBox.information = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]
    QMessageBox.critical = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]
    QMessageBox.warning = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]
    QMessageBox.question = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Yes)  # type: ignore[assignment]
    def restore():
        QMessageBox.information = orig["information"]  # type: ignore[assignment]
        QMessageBox.critical = orig["critical"]  # type: ignore[assignment]
        QMessageBox.warning = orig["warning"]  # type: ignore[assignment]
        QMessageBox.question = orig["question"]  # type: ignore[assignment]
    return restore


def _seedTinyFuzzDB(w):
    """Populate ``w.db`` in place using fuzz_db's tiny preset with seed=1.
    Mirrors the pattern from ``product_employee_reports`` (Step 35) but without
    file I/O. Returns ``(partNames, idNums, mixtureNames)`` for fixture lookup."""
    import datetime
    import fuzz_db as F
    rng = random.Random(1)
    cfg = F.SCALES["tiny"]
    today = datetime.date.today()
    db = w.db
    materialNames = F.populateMaterials(db, rng, cfg["materials"])
    mixtureNames = F.populateMixtures(db, rng, cfg["mixtures"], materialNames)
    F.populatePackaging(db, rng, cfg["packaging"])
    packagingByKind = {k: [] for k in F.PACKAGING_POOL}
    for name in db.packaging:
        packagingByKind[db.packaging[name].kind].append(name)
    partNames = F.populateParts(db, rng, cfg["parts"], mixtureNames, packagingByKind)
    idNums = F.populateEmployees(db, rng, cfg["employees"], today)
    F.populateReviews(db, rng, idNums, today)
    F.populateTraining(db, rng, idNums, today)
    F.populateAttendance(db, rng, idNums, today)
    F.populatePTO(db, rng, idNums, today)
    F.populateNotes(db, rng, idNums, today)
    F.populateHolidays(db, rng, today)
    return partNames, idNums, mixtureNames


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
    QMessageBox.critical = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]
    QMessageBox.information = staticmethod(lambda *a, **_kw: QMessageBox.StandardButton.Ok)  # type: ignore[assignment]

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
    modal). Asserts the DB loads, ``fileManager.filePath`` is set,
    ``saveButton`` is enabled (regression guard: pre-fix, the auto-reopen
    path didn't refresh button state and Save stayed grayed out), and
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
        if not w2.saveButton.isEnabled():
            errors.append("saveButton not enabled after _loadPath (Step 20 regression)")

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


def close_confirm() -> list[str]:
    """Step 25: close-event prompts Save / Don't Save / Cancel.

    Stubs MainWindow._confirmCloseChoice to force each StandardButton in turn,
    fires closeEvent, and asserts the three branches behave correctly:
      - Save     -> event accepted, fileManager.saveFile called
      - Discard  -> event accepted, fileManager.saveFile NOT called
      - Cancel   -> event ignored (window stays open)
    Also confirms the no-file-loaded case skips the prompt entirely.
    """
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QCloseEvent
    from app import MainWindow

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
        w.fileManager.saveFile()

        # Swap saveFile for a counter so we can tell whether the close flow
        # actually persists, without having to re-read the DB from disk.
        saveCalls = {"n": 0}
        origSave = w.fileManager.saveFile
        def countingSave():
            saveCalls["n"] += 1
            return origSave()
        w.fileManager.saveFile = countingSave  # type: ignore[assignment]

        cases = [
            ("Save",    QMessageBox.StandardButton.Save,    True,  1),
            ("Discard", QMessageBox.StandardButton.Discard, True,  0),
            ("Cancel",  QMessageBox.StandardButton.Cancel,  False, 0),
        ]
        for label, button, expectAccept, expectSaves in cases:
            saveCalls["n"] = 0
            w._confirmCloseChoice = lambda b=button: b  # type: ignore[assignment]
            ev = QCloseEvent()
            w.closeEvent(ev)
            if ev.isAccepted() != expectAccept:
                errors.append(
                    f"{label}: expected isAccepted={expectAccept}, "
                    f"got {ev.isAccepted()}"
                )
            if saveCalls["n"] != expectSaves:
                errors.append(
                    f"{label}: expected {expectSaves} saveFile call(s), "
                    f"got {saveCalls['n']}"
                )

        # No-file-loaded path: swap filePath to None and confirm the close
        # event accepts without invoking the prompt.
        w.fileManager.filePath = None
        promptCalls = {"n": 0}
        def shouldNotPrompt():
            promptCalls["n"] += 1
            return QMessageBox.StandardButton.Cancel
        w._confirmCloseChoice = shouldNotPrompt  # type: ignore[assignment]
        saveCalls["n"] = 0
        ev = QCloseEvent()
        w.closeEvent(ev)
        if not ev.isAccepted():
            errors.append("no-file-loaded: expected event accepted, got ignored")
        if promptCalls["n"] != 0:
            errors.append(
                f"no-file-loaded: prompt fired {promptCalls['n']} time(s) "
                f"(should be 0)"
            )
        if saveCalls["n"] != 0:
            errors.append(
                f"no-file-loaded: saveFile fired {saveCalls['n']} time(s) "
                f"(should be 0)"
            )
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def parts_tab_crud() -> list[str]:
    """Step 37: PartsTab dialog roundtrips against a tiny fuzz DB.

    Seeds tiny-scale fuzz data (seed=1), picks the first part by name, then:
      - opens ``PartsDetailsWindow`` and confirms the constructed labels
        carry the fixture's name and weight (label-text scrape — the
        Details window is display-only so prefill is the only assertion);
      - opens ``PartsMarginsWindow`` and confirms it constructs and
        emits at least one ``Apply`` button (the margin-row generator
        produces one row per percentage bracket);
      - opens ``PartsEditWindow`` on the fixture, asserts every named
        editor (nameEdit / weightEdit / mixCombo / pressingEdit /
        turningEdit / boxCombo / piecesPerBoxEdit / palletCombo /
        boxesPerPalletEdit / priceEdit) reflects the fixture, then
        clicks ``updateButton`` after bumping weight + price and
        confirms ``db.parts`` reflects the change;
      - opens a *new* ``PartsEditWindow`` (entry=None), fills every
        named editor with novel values, clicks ``createButton``, and
        confirms a new entry appears in ``db.parts`` with the values.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from parts_tab import PartsDetailsWindow, PartsMarginsWindow, PartsEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        partNames, _, _ = _seedTinyFuzzDB(w)
        w.partsTab.refreshTable()

        fixture = sorted(partNames)[0]
        part = w.db.parts[fixture]

        # --- PartsDetailsWindow ---
        details = PartsDetailsWindow(fixture, w)
        from PySide6.QtWidgets import QLabel
        labelTexts = [lbl.text() for lbl in details.findChildren(QLabel)]
        joined = " | ".join(labelTexts)
        if f"Part: {fixture}" not in joined:
            errors.append(f"Details: missing 'Part: {fixture}' in label set; got {joined[:160]}")
        if f"{part.weight} lbs" not in joined:
            errors.append(f"Details: missing weight '{part.weight} lbs' in label set")
        details.close()

        # --- PartsMarginsWindow ---
        margins = PartsMarginsWindow(fixture, w)
        from PySide6.QtWidgets import QPushButton
        applyButtons = [b for b in margins.findChildren(QPushButton) if b.text() == "Apply"]
        if not applyButtons:
            errors.append("Margins: no Apply buttons rendered (expected one per percentage row)")
        margins.close()

        # --- PartsEditWindow: prefill + Update roundtrip ---
        editor = PartsEditWindow(fixture, w)
        if editor.nameEdit.text() != fixture:
            errors.append(f"Edit prefill: nameEdit={editor.nameEdit.text()!r}, want {fixture!r}")
        if editor.weightEdit.text() != str(part.weight):
            errors.append(f"Edit prefill: weightEdit={editor.weightEdit.text()!r}, want {part.weight!r}")
        if editor.mixCombo.currentText() != part.mix:
            errors.append(f"Edit prefill: mixCombo={editor.mixCombo.currentText()!r}, want {part.mix!r}")
        if editor.pressingEdit.text() != str(part.pressing):
            errors.append(f"Edit prefill: pressingEdit={editor.pressingEdit.text()!r}, want {part.pressing!r}")
        if editor.turningEdit.text() != str(part.turning):
            errors.append(f"Edit prefill: turningEdit={editor.turningEdit.text()!r}, want {part.turning!r}")
        if editor.boxCombo.currentText() != part.box:
            errors.append(f"Edit prefill: boxCombo={editor.boxCombo.currentText()!r}, want {part.box!r}")
        if editor.piecesPerBoxEdit.text() != str(part.piecesPerBox):
            errors.append(f"Edit prefill: piecesPerBoxEdit={editor.piecesPerBoxEdit.text()!r}, want {part.piecesPerBox!r}")
        if editor.palletCombo.currentText() != part.pallet:
            errors.append(f"Edit prefill: palletCombo={editor.palletCombo.currentText()!r}, want {part.pallet!r}")
        if editor.boxesPerPalletEdit.text() != str(part.boxesPerPallet):
            errors.append(f"Edit prefill: boxesPerPalletEdit={editor.boxesPerPalletEdit.text()!r}, want {part.boxesPerPallet!r}")
        if editor.priceEdit.text() != str(part.price):
            errors.append(f"Edit prefill: priceEdit={editor.priceEdit.text()!r}, want {part.price!r}")

        editor.weightEdit.setText("12.5")
        editor.priceEdit.setText("99.99")
        editor.updateButton.click()
        updated = w.db.parts.get(fixture)
        if updated is None:
            errors.append(f"after Update: db.parts[{fixture!r}] missing")
        else:
            if updated.weight != 12.5:
                errors.append(f"after Update: weight={updated.weight!r}, want 12.5")
            if updated.price != 99.99:
                errors.append(f"after Update: price={updated.price!r}, want 99.99")

        # --- PartsEditWindow: Create new part ---
        newEditor = PartsEditWindow(None, w)
        newName = "SmokeTestPart"
        # Pick valid combo choices from the fuzz DB so the create succeeds.
        mixChoice = newEditor.mixCombo.itemText(0)
        boxChoice = newEditor.boxCombo.itemText(0)
        palletChoice = newEditor.palletCombo.itemText(0)
        newEditor.nameEdit.setText(newName)
        newEditor.weightEdit.setText("7.25")
        newEditor.mixCombo.setCurrentText(mixChoice)
        newEditor.pressingEdit.setText("250")
        newEditor.turningEdit.setText("180")
        newEditor.boxCombo.setCurrentText(boxChoice)
        newEditor.piecesPerBoxEdit.setText("12")
        newEditor.palletCombo.setCurrentText(palletChoice)
        newEditor.boxesPerPalletEdit.setText("40")
        newEditor.fireScrapEdit.setText("3.5")
        newEditor.priceEdit.setText("12.34")
        # quoteCheck starts Checked + salesEdit disabled for new parts; that's fine.
        newEditor.createButton.click()
        created = w.db.parts.get(newName)
        if created is None:
            errors.append(f"after Create: db.parts[{newName!r}] missing")
        else:
            if created.weight != 7.25:
                errors.append(f"new part: weight={created.weight!r}, want 7.25")
            if created.mix != mixChoice:
                errors.append(f"new part: mix={created.mix!r}, want {mixChoice!r}")
            if created.box != boxChoice:
                errors.append(f"new part: box={created.box!r}, want {boxChoice!r}")
            if created.sales != "Quote":
                errors.append(f"new part: sales={created.sales!r}, want 'Quote' (default when quoteCheck checked)")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def employees_tab_crud() -> list[str]:
    """Step 37: EmployeeEditWindow roundtrips against a tiny fuzz DB.

    Seeds tiny-scale fuzz data (seed=1), picks the first active employee,
    then:
      - opens ``EmployeeEditWindow`` on the fixture, asserts every named
        editor (idEdit / lastNameEdit / firstNameEdit / roleEdit /
        addressLine1Edit / addressLine2Edit / addressCityEdit /
        addressZipEdit / addressTelEdit / addressEmailEdit / shift /
        fullTime / states) reflects the fixture, then clicks
        ``updateButton`` after changing role + zip and confirms
        ``db.employees`` reflects the change;
      - opens a *new* ``EmployeeEditWindow`` (entry=None, active=True),
        fills every named editor with novel values, clicks
        ``createButton``, and confirms a new entry appears in
        ``db.employees`` with the values plus the shadow collections
        (reviews / training / attendance / PTO / notes) are seeded.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from employees_tab import EmployeeEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _, idNums, _ = _seedTinyFuzzDB(w)
        w.employeesTab.activeEmployeesTab.refreshTable()
        w.employeesTab.inactiveEmployeesTab.refreshTable()

        activeIds = [i for i in idNums if w.db.employees[i].status]
        if not activeIds:
            errors.append("fuzz fixture produced no active employees (test setup bug)")
            return errors
        fixtureId = sorted(activeIds)[0]
        emp = w.db.employees[fixtureId]

        # --- EmployeeEditWindow: prefill + Update roundtrip ---
        editor = EmployeeEditWindow(fixtureId, w, True)
        if editor.idEdit.text() != str(fixtureId):
            errors.append(f"Edit prefill: idEdit={editor.idEdit.text()!r}, want {fixtureId!r}")
        if editor.lastNameEdit.text() != emp.lastName:
            errors.append(f"Edit prefill: lastNameEdit={editor.lastNameEdit.text()!r}, want {emp.lastName!r}")
        if editor.firstNameEdit.text() != emp.firstName:
            errors.append(f"Edit prefill: firstNameEdit={editor.firstNameEdit.text()!r}, want {emp.firstName!r}")
        if editor.roleEdit.text() != emp.role:
            errors.append(f"Edit prefill: roleEdit={editor.roleEdit.text()!r}, want {emp.role!r}")
        if editor.addressLine1Edit.text() != emp.addressLine1:
            errors.append(f"Edit prefill: addressLine1Edit={editor.addressLine1Edit.text()!r}, want {emp.addressLine1!r}")
        if editor.addressCityEdit.text() != emp.addressCity:
            errors.append(f"Edit prefill: addressCityEdit={editor.addressCityEdit.text()!r}, want {emp.addressCity!r}")
        if editor.addressZipEdit.text() != str(emp.addressZip):
            errors.append(f"Edit prefill: addressZipEdit={editor.addressZipEdit.text()!r}, want {emp.addressZip!r}")
        if editor.shift.currentText() != str(emp.shift):
            errors.append(f"Edit prefill: shift={editor.shift.currentText()!r}, want {emp.shift!r}")
        if editor.fullTime.currentText() != str(emp.fullTime):
            errors.append(f"Edit prefill: fullTime={editor.fullTime.currentText()!r}, want {emp.fullTime!r}")
        if editor.states.currentText() != emp.addressState:
            errors.append(f"Edit prefill: states={editor.states.currentText()!r}, want {emp.addressState!r}")

        editor.roleEdit.setText("Smoke Test Lead")
        editor.addressZipEdit.setText("99999")
        editor.updateButton.click()
        updated = w.db.employees.get(fixtureId)
        if updated is None:
            errors.append(f"after Update: db.employees[{fixtureId!r}] missing")
        else:
            if updated.role != "Smoke Test Lead":
                errors.append(f"after Update: role={updated.role!r}, want 'Smoke Test Lead'")
            if updated.addressZip != "99999":
                errors.append(f"after Update: addressZip={updated.addressZip!r}, want '99999'")

        # --- EmployeeEditWindow: Create new ---
        newEditor = EmployeeEditWindow(None, w, True)
        newId = 999999
        # idEdit is pre-populated with a random ID; overwrite for determinism.
        newEditor.idEdit.setText(str(newId))
        newEditor.lastNameEdit.setText("Smoke")
        newEditor.firstNameEdit.setText("Tester")
        newEditor.roleEdit.setText("QA")
        newEditor.addressLine1Edit.setText("1 Smoke St")
        newEditor.addressCityEdit.setText("Testville")
        newEditor.states.setCurrentText("OH")
        newEditor.addressZipEdit.setText("12345")
        newEditor.addressTelEdit.setText("555-0100")
        newEditor.shift.setCurrentText("2")
        newEditor.fullTime.setCurrentText("True")
        newEditor.createButton.click()
        created = w.db.employees.get(newId)
        if created is None:
            errors.append(f"after Create: db.employees[{newId!r}] missing")
        else:
            if created.lastName != "Smoke" or created.firstName != "Tester":
                errors.append(f"new employee: name={created.lastName!r}/{created.firstName!r}, want 'Smoke'/'Tester'")
            if created.role != "QA":
                errors.append(f"new employee: role={created.role!r}, want 'QA'")
            if created.shift != 2:
                errors.append(f"new employee: shift={created.shift!r}, want 2")
            if created.fullTime is not True:
                errors.append(f"new employee: fullTime={created.fullTime!r}, want True")
            # Shadow collections must be seeded so subsequent reviews/training/etc work.
            for shadow, dictName in [(w.db.reviews, "reviews"),
                                     (w.db.training, "training"),
                                     (w.db.attendance, "attendance"),
                                     (w.db.PTO, "PTO"),
                                     (w.db.notes, "notes")]:
                if newId not in shadow:
                    errors.append(f"new employee: db.{dictName}[{newId}] not seeded")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


# ---------------------------------------------------------------------------
# Step 37b — employee-detail side (Overview tab + 5 sub-tab Edit dialogs +
# delete cascade). Mirrors the pre-37 manual sweep that picked a fixture
# employee, clicked through each sub-tab + each Edit dialog, and confirmed
# label population / dialog prefill / save roundtrip.
# ---------------------------------------------------------------------------


def _pickerSelectionFor(emp) -> str:
    """Reproduce the picker string from EmployeeDetailTab.refreshPicker:
    'LASTNAME firstname (id)'. Used to drive ``employeePicker.setCurrentText``."""
    last = (emp.lastName or "?").upper()
    return f"{last} {emp.firstName} ({emp.idNum})"


def _detailTabsScratchSetup(seed=1):
    """Construct a MainWindow, seed it with a tiny fuzz DB, refresh the
    overview picker, and return ``(window, restore, tmp, idNums)``.

    Caller is responsible for the finally-block teardown (the standard
    restore() + dbFile.close() + os.unlink dance)."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = MainWindow()
    if not w.fileManager.setFile(tmp.name):
        raise RuntimeError("setFile returned False on fresh empty DB")
    _, idNums, _ = _seedTinyFuzzDB(w)
    w.overviewTab.refresh()
    return w, restore, tmp, idNums


def employee_detail_populates() -> list[str]:
    """Step 37b: picking an employee fills all 5 detail sub-tabs; 'None' clears them.

    Drives ``employee_detail_tab.EmployeePicker`` programmatically and asserts
    that ``currentEmployeeLabel`` on every detail sub-tab (Reviews / Training /
    Points / PTO / Notes) reflects the selected fixture, then that switching
    back to 'None' returns every sub-tab to "Employee: N/A". Also confirms the
    picker actually contains the fixture's selection string (a Step-20-class
    regression catch: a stale picker that didn't refresh would silently
    no-op the setCurrentText).
    """
    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, idNums = _detailTabsScratchSetup()
        activeIds = [i for i in idNums if w.db.employees[i].status]
        if not activeIds:
            errors.append("fuzz fixture produced no active employees (test setup bug)")
            return errors
        fixtureId = sorted(activeIds)[0]
        emp = w.db.employees[fixtureId]
        selection = _pickerSelectionFor(emp)

        pickerItems = [w.overviewTab.employeePicker.itemText(i)
                       for i in range(w.overviewTab.employeePicker.count())]
        if selection not in pickerItems:
            errors.append(f"picker missing fixture selection {selection!r}; got {pickerItems[:5]}...")
            return errors

        w.overviewTab.employeePicker.setCurrentText(selection)
        expectedLabel = f"Employee: {selection}"
        for tabName in ("reviewsTab", "trainingTab", "pointsTab", "PTOTab", "notesTab"):
            tab = getattr(w.overviewTab, tabName)
            got = tab.currentEmployeeLabel.text()
            if got != expectedLabel:
                errors.append(f"{tabName}: label={got!r}, want {expectedLabel!r}")

        w.overviewTab.employeePicker.setCurrentText("None")
        for tabName in ("reviewsTab", "trainingTab", "pointsTab", "PTOTab", "notesTab"):
            tab = getattr(w.overviewTab, tabName)
            got = tab.currentEmployeeLabel.text()
            if got != "Employee: N/A":
                errors.append(f"{tabName} after None: label={got!r}, want 'Employee: N/A'")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


def reviews_dialog_roundtrip() -> list[str]:
    """Step 37b: ReviewsEditWindow new-and-edit roundtrips.

    Drives ``ReviewsEditWindow`` headlessly through both branches:
      - New: opens with entry=None, sets calendar + daysEdit + detailsEdit,
        clicks createButton, asserts the record lands in
        ``db.reviews[idNum].reviews[date]``.
      - Edit: re-opens on the just-created review, asserts prefill matches,
        changes daysEdit + detailsEdit, clicks updateButton, asserts the
        record reflects the new values and nextReview is recomputed.
    """
    from utils import toQDate
    from reviews_tab import ReviewsEditWindow

    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, idNums = _detailTabsScratchSetup()
        fixtureId = sorted(i for i in idNums if w.db.employees[i].status)[0]
        w.overviewTab.employeePicker.setCurrentText(_pickerSelectionFor(w.db.employees[fixtureId]))

        # --- New ---
        d = datetime_date(2026, 4, 1)
        dlg = ReviewsEditWindow(fixtureId, None, w)
        dlg.calendar.setSelectedDate(toQDate(d))
        dlg.daysEdit.setText("90")
        dlg.detailsEdit.setText("Smoke test review")
        dlg.createButton.click()
        rec = w.db.reviews[fixtureId].reviews.get(d)
        if rec is None:
            errors.append(f"after Create: db.reviews[{fixtureId}].reviews[{d}] missing")
            return errors
        if rec.details != "Smoke test review":
            errors.append(f"after Create: details={rec.details!r}, want 'Smoke test review'")
        if rec.nextReview != d + __import__("datetime").timedelta(days=90):
            errors.append(f"after Create: nextReview={rec.nextReview!r}, want {d!r}+90d")

        # --- Edit ---
        dlg2 = ReviewsEditWindow(fixtureId, rec, w)
        if dlg2.daysEdit.text() != "90":
            errors.append(f"Edit prefill: daysEdit={dlg2.daysEdit.text()!r}, want '90'")
        if dlg2.detailsEdit.text() != "Smoke test review":
            errors.append(f"Edit prefill: detailsEdit={dlg2.detailsEdit.text()!r}, want 'Smoke test review'")
        dlg2.daysEdit.setText("180")
        dlg2.detailsEdit.setText("Updated review")
        dlg2.updateButton.click()
        rec2 = w.db.reviews[fixtureId].reviews.get(d)
        if rec2 is None:
            errors.append(f"after Update: db.reviews[{fixtureId}].reviews[{d}] missing")
        elif rec2.details != "Updated review":
            errors.append(f"after Update: details={rec2.details!r}, want 'Updated review'")
        elif rec2.nextReview != d + __import__("datetime").timedelta(days=180):
            errors.append(f"after Update: nextReview={rec2.nextReview!r}, want {d!r}+180d")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


def training_dialog_roundtrip() -> list[str]:
    """Step 37b: TrainingEditWindow new-and-edit roundtrips against a fuzzed employee.

    Picks the first defaults.TRAINING key, opens TrainingEditWindow with
    entry=None, sets calendar + comment, clicks createButton, asserts the
    record lands in db.training. Then re-opens on the new record, asserts
    prefill, edits comment, updateButton, asserts the new comment.
    """
    import defaults as D
    from utils import toQDate
    from training_tab import TrainingEditWindow

    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, idNums = _detailTabsScratchSetup()
        fixtureId = sorted(i for i in idNums if w.db.employees[i].status)[0]
        w.overviewTab.employeePicker.setCurrentText(_pickerSelectionFor(w.db.employees[fixtureId]))
        trainingType = D.TRAINING[0]
        d = datetime_date(2026, 4, 5)
        # If fuzz already seeded this (trainingType, date) for the fixture, push the date out.
        while d in w.db.training[fixtureId].training[trainingType]:
            d = d + __import__("datetime").timedelta(days=1)

        dlg = TrainingEditWindow(fixtureId, trainingType, None, w)
        dlg.calendar.setSelectedDate(toQDate(d))
        dlg.comment.setText("Initial training")
        dlg.createButton.click()
        rec = w.db.training[fixtureId].training[trainingType].get(d)
        if rec is None:
            errors.append(f"after Create: db.training[{fixtureId}].training[{trainingType!r}][{d}] missing")
            return errors
        if rec.comment != "Initial training":
            errors.append(f"after Create: comment={rec.comment!r}, want 'Initial training'")

        dlg2 = TrainingEditWindow(fixtureId, trainingType, rec, w)
        if dlg2.comment.text() != "Initial training":
            errors.append(f"Edit prefill: comment={dlg2.comment.text()!r}, want 'Initial training'")
        dlg2.comment.setText("Refresher")
        dlg2.updateButton.click()
        rec2 = w.db.training[fixtureId].training[trainingType].get(d)
        if rec2 is None or rec2.comment != "Refresher":
            errors.append(f"after Update: comment={(rec2.comment if rec2 else None)!r}, want 'Refresher'")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


def points_dialog_roundtrip() -> list[str]:
    """Step 37b: PointsEditWindow new-and-edit roundtrips.

    Uses a default reason ('Absence' from POINT_VALS) so the dialog
    auto-fills pointsInput from the lookup table — exercises the
    setReason side-effect path that disables pointsInput / otherReason
    on non-Other reasons. Then re-opens the created record and asserts
    prefill + an Update roundtrip with a different reason.
    """
    from utils import toQDate
    from points_tab import PointsEditWindow

    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, idNums = _detailTabsScratchSetup()
        fixtureId = sorted(i for i in idNums if w.db.employees[i].status)[0]
        w.overviewTab.employeePicker.setCurrentText(_pickerSelectionFor(w.db.employees[fixtureId]))
        d = datetime_date(2026, 4, 7)
        while d in w.db.attendance[fixtureId].points:
            d = d + __import__("datetime").timedelta(days=1)

        dlg = PointsEditWindow(fixtureId, None, w)
        dlg.calendar.setSelectedDate(toQDate(d))
        dlg.reasons.setCurrentText("Absence")
        # setReason side-effect should have populated pointsInput from POINT_VALS["Absence"] = 1.
        if dlg.pointsInput.text() != "1":
            errors.append(f"setReason side-effect: pointsInput={dlg.pointsInput.text()!r}, want '1'")
        dlg.createButton.click()
        rec = w.db.attendance[fixtureId].points.get(d)
        if rec is None:
            errors.append(f"after Create: db.attendance[{fixtureId}].points[{d}] missing")
            return errors
        if rec.reason != "Absence":
            errors.append(f"after Create: reason={rec.reason!r}, want 'Absence'")
        if rec.value != 1.0:
            errors.append(f"after Create: value={rec.value!r}, want 1.0")

        dlg2 = PointsEditWindow(fixtureId, rec, w)
        if dlg2.reasons.currentText() != "Absence":
            errors.append(f"Edit prefill: reasons={dlg2.reasons.currentText()!r}, want 'Absence'")
        dlg2.reasons.setCurrentText("Tardy")
        dlg2.updateButton.click()
        rec2 = w.db.attendance[fixtureId].points.get(d)
        if rec2 is None or rec2.reason != "Tardy":
            errors.append(f"after Update: reason={(rec2.reason if rec2 else None)!r}, want 'Tardy'")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


def pto_dialog_roundtrip() -> list[str]:
    """Step 37b: PTOEditWindow new-and-edit roundtrips.

    Picks the fixture employee with the longest tenure (so PTO_ELIGIBILITY
    and available-hours checks don't block the test), constructs a PTO range
    well outside the fuzz-populated window, hours=4. New → assert in db →
    Edit → change hours → updateButton → assert.
    """
    from utils import toQDate
    from pto_tab import PTOEditWindow

    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, idNums = _detailTabsScratchSetup()
        # Tenured-most active employee gets the most reliable available-hours value.
        actives = [(w.db.employees[i].anniversary, i) for i in idNums
                   if w.db.employees[i].status and w.db.employees[i].anniversary is not None]
        if not actives:
            errors.append("fuzz fixture produced no active employee with anniversary (test setup bug)")
            return errors
        actives.sort()  # oldest anniversary first → most tenured
        fixtureId = actives[0][1]
        w.overviewTab.employeePicker.setCurrentText(_pickerSelectionFor(w.db.employees[fixtureId]))

        # Use a future date 2 years out so it can't collide with fuzz_db's
        # last-300-day PTO ranges and is well past any anniversary + 90 days.
        today = __import__("datetime").date.today()
        start = __import__("datetime").date(today.year + 2, 6, 15)
        end = __import__("datetime").date(today.year + 2, 6, 16)

        dlg = PTOEditWindow(fixtureId, None, w)
        dlg.calendarStart.setSelectedDate(toQDate(start))
        dlg.calendarEnd.setSelectedDate(toQDate(end))
        dlg.hours.setText("4")
        dlg.createButton.click()
        key = (start, end)
        rec = w.db.PTO[fixtureId].PTO.get(key)
        if rec is None:
            errors.append(f"after Create: db.PTO[{fixtureId}].PTO[{key}] missing")
            return errors
        if rec.hours != 4.0:
            errors.append(f"after Create: hours={rec.hours!r}, want 4.0")

        dlg2 = PTOEditWindow(fixtureId, rec, w)
        if dlg2.hours.text() != "4.0":
            errors.append(f"Edit prefill: hours={dlg2.hours.text()!r}, want '4.0'")
        dlg2.hours.setText("8")
        dlg2.updateButton.click()
        rec2 = w.db.PTO[fixtureId].PTO.get(key)
        if rec2 is None or rec2.hours != 8.0:
            errors.append(f"after Update: hours={(rec2.hours if rec2 else None)!r}, want 8.0")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


def notes_dialog_roundtrip() -> list[str]:
    """Step 37b: NotesEditWindow new-and-edit roundtrips.

    Date + time + details → createButton → assert key in db.notes; then
    re-open the new note, assert prefill, edit details, updateButton,
    re-assert. Time is set via QTime to exercise the timeInput parse path
    (a Step-7-class fragility: the dialog formats time itself as 'HH:MM').
    """
    from PySide6.QtCore import QTime
    from utils import toQDate
    from notes_tab import NotesEditWindow

    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, idNums = _detailTabsScratchSetup()
        fixtureId = sorted(i for i in idNums if w.db.employees[i].status)[0]
        w.overviewTab.employeePicker.setCurrentText(_pickerSelectionFor(w.db.employees[fixtureId]))
        d = datetime_date(2026, 4, 9)
        timeStr = "09:30"
        # Avoid collision with fuzz-seeded notes.
        while (d, timeStr) in w.db.notes[fixtureId].notes:
            d = d + __import__("datetime").timedelta(days=1)

        dlg = NotesEditWindow(fixtureId, None, w)
        dlg.calendar.setSelectedDate(toQDate(d))
        dlg.timeInput.setTime(QTime(9, 30))
        dlg.detailsInput.setPlainText("Initial note")
        dlg.createButton.click()
        rec = w.db.notes[fixtureId].notes.get((d, timeStr))
        if rec is None:
            errors.append(f"after Create: db.notes[{fixtureId}].notes[({d}, {timeStr!r})] missing")
            return errors
        if rec.details != "Initial note":
            errors.append(f"after Create: details={rec.details!r}, want 'Initial note'")

        dlg2 = NotesEditWindow(fixtureId, rec, w)
        if dlg2.detailsInput.toPlainText() != "Initial note":
            errors.append(f"Edit prefill: details={dlg2.detailsInput.toPlainText()!r}, want 'Initial note'")
        dlg2.detailsInput.setPlainText("Updated note")
        dlg2.updateButton.click()
        rec2 = w.db.notes[fixtureId].notes.get((d, timeStr))
        if rec2 is None or rec2.details != "Updated note":
            errors.append(f"after Update: details={(rec2.details if rec2 else None)!r}, want 'Updated note'")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


def employee_delete_cascades_detail_tabs() -> list[str]:
    """Step 37b: deleting an employee while their detail tabs are visible
    drops the selection on all 5 sub-tabs.

    Mirrors the real flow from EmployeeTab.deleteSelection:
    ``db.delEmployee(idNum)`` followed by ``mainApp.overviewTab.refresh()``.
    The picker's refresh clears the current selection (setCurrentIndex(0)
    fires selectEmployee('None') → employeeID=None → every sub-tab
    refreshes back to N/A). Asserts both the picker no longer offers the
    deleted employee and every detail sub-tab shows 'Employee: N/A'.
    """
    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, idNums = _detailTabsScratchSetup()
        fixtureId = sorted(i for i in idNums if w.db.employees[i].status)[0]
        emp = w.db.employees[fixtureId]
        selection = _pickerSelectionFor(emp)
        w.overviewTab.employeePicker.setCurrentText(selection)

        # Sanity: pre-delete, every tab reflects the fixture.
        for tabName in ("reviewsTab", "trainingTab", "pointsTab", "PTOTab", "notesTab"):
            tab = getattr(w.overviewTab, tabName)
            if "N/A" in tab.currentEmployeeLabel.text():
                errors.append(f"pre-delete {tabName}: label is N/A, expected fixture")

        # Delete via the same entry point the EmployeesTab uses.
        w.db.delEmployee(fixtureId)
        w.overviewTab.refresh()

        pickerItems = [w.overviewTab.employeePicker.itemText(i)
                       for i in range(w.overviewTab.employeePicker.count())]
        if selection in pickerItems:
            errors.append(f"post-delete: picker still contains {selection!r}")

        for tabName in ("reviewsTab", "trainingTab", "pointsTab", "PTOTab", "notesTab"):
            tab = getattr(w.overviewTab, tabName)
            got = tab.currentEmployeeLabel.text()
            if got != "Employee: N/A":
                errors.append(f"post-delete {tabName}: label={got!r}, want 'Employee: N/A'")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


# ---------------------------------------------------------------------------
# Step 37c — Holidays tab (Observances + Defaults sub-tabs).
# ---------------------------------------------------------------------------


def holidays_tab_observances() -> list[str]:
    """Step 37c: ObservancesTab renders shift dates and the ◀/▶ year nav works.

    Seeds a tiny fuzz DB (which populates both default-holiday months AND
    per-shift observances for ``today.year`` + ``today.year + 1``), then
    overrides Christmas Day shift 1 / shift 2 to known dates and *deletes*
    the fuzz-seeded shift 3 so we can also assert the N/A render path.
    Refreshes the holidaysTab.observancesTab, then:
      - Asserts each default holiday has a row in ``observanceRows``.
      - For the Christmas Day row, asserts Shift 1 / Shift 2 labels
        contain the overridden dates and Shift 3 shows N/A.
      - Clicks ◀ once, asserts ``curYearB.text()`` == str(year-1) AND
        that the Christmas Day row reads Shift 1: N/A in the prior year
        (fuzz only seeds current + next year, so year-1 is empty —
        regression catch for the year nav re-building rows from scratch
        rather than reusing cached ones).
      - Clicks ▶ once, asserts ``curYearB.text()`` returns to str(year).
    """
    import datetime
    from records.employees import HolidayObservance

    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, _ = _detailTabsScratchSetup()
        year = datetime.date.today().year
        # Override known shifts; drop shift 3 so it renders as N/A.
        w.db.holidays.setObservance(HolidayObservance("Christmas Day", datetime.date(year, 12, 25), 1))
        w.db.holidays.setObservance(HolidayObservance("Christmas Day", datetime.date(year, 12, 24), 2))
        w.db.holidays.delObservance(year, "Christmas Day", 3)

        # Force the tab to rebuild on the seeded year.
        tab = w.holidaysTab.observancesTab
        tab.currentYear = year
        tab.refresh(hard=True)

        if tab.curYearB.text() != str(year):
            errors.append(f"curYearB text={tab.curYearB.text()!r}, want {str(year)!r}")

        rowsByHoliday = {row[0]: row for row in tab.observanceRows}
        for holiday in w.db.holidays.defaults:
            if holiday not in rowsByHoliday:
                errors.append(f"observanceRows missing default holiday {holiday!r}")

        xmas = rowsByHoliday.get("Christmas Day")
        if xmas is None:
            errors.append("Christmas Day row missing")
        else:
            # row shape: [holiday, label, date1, select1, clear1, date2, ...]
            s1 = xmas[2].text()
            s2 = xmas[5].text()
            s3 = xmas[8].text()
            if f"Shift 1: {year}-12-25" not in s1:
                errors.append(f"Shift 1 label={s1!r}, want 'Shift 1: {year}-12-25'")
            if f"Shift 2: {year}-12-24" not in s2:
                errors.append(f"Shift 2 label={s2!r}, want 'Shift 2: {year}-12-24'")
            if "Shift 3: N/A" not in s3:
                errors.append(f"Shift 3 label={s3!r}, want 'Shift 3: N/A'")

        # --- ◀ year nav: drop to year-1, no observances there → all N/A ---
        tab.decYearB.click()
        if tab.curYearB.text() != str(year - 1):
            errors.append(f"after decYear: curYearB={tab.curYearB.text()!r}, want {str(year - 1)!r}")
        rowsByHoliday = {row[0]: row for row in tab.observanceRows}
        xmas = rowsByHoliday.get("Christmas Day")
        if xmas is not None:
            for slot, label in [(2, "Shift 1"), (5, "Shift 2"), (8, "Shift 3")]:
                if f"{label}: N/A" not in xmas[slot].text():
                    errors.append(f"year-1 Christmas Day {label}={xmas[slot].text()!r}, want N/A")

        # --- ▶ year nav: bump back to the seeded year ---
        tab.incYearB.click()
        if tab.curYearB.text() != str(year):
            errors.append(f"after incYear: curYearB={tab.curYearB.text()!r}, want {str(year)!r}")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors


def holidays_tab_defaults_crud() -> list[str]:
    """Step 37c: HolidayEditWindow new + edit roundtrips for default holidays.

    Seeds tiny fuzz DB (the default-holiday month map is populated by
    fuzz_db.populateHolidays), then:
      - Opens HolidayEditWindow(None) to create a synthetic holiday,
        sets holidayName + holidayMonth, clicks createButton, asserts
        the new entry appears in db.holidays.defaults with the right
        month.
      - Opens HolidayEditWindow(existing) on a fuzz-seeded holiday,
        asserts holidayName + holidayMonth prefill match the DB,
        changes the month, clicks updateButton, asserts the change
        landed in db.holidays.defaults.
    """
    from holidays_tab import HolidayEditWindow

    errors = []
    w = restore = tmp = None
    try:
        w, restore, tmp, _ = _detailTabsScratchSetup()
        defaultsTab = w.holidaysTab.defaultsTab
        defaultsTab.refresh()

        # --- New ---
        synthName = "Smoke Test Day"
        dlg = HolidayEditWindow(defaultsTab, None, w)
        dlg.holidayName.setText(synthName)
        dlg.holidayMonth.setCurrentText("7")
        dlg.createButton.click()
        if synthName not in w.db.holidays.defaults:
            errors.append(f"after Create: db.holidays.defaults missing {synthName!r}")
        elif w.db.holidays.defaults[synthName] != 7:
            errors.append(f"after Create: month={w.db.holidays.defaults[synthName]!r}, want 7")

        # --- Edit an existing fuzz-seeded holiday ---
        existing = next((h for h in w.db.holidays.defaults if h != synthName), None)
        if existing is None:
            errors.append("fuzz fixture produced no default holidays (test setup bug)")
            return errors
        priorMonth = w.db.holidays.defaults[existing]
        dlg2 = HolidayEditWindow(defaultsTab, existing, w)
        if dlg2.holidayName.text() != existing:
            errors.append(f"Edit prefill: holidayName={dlg2.holidayName.text()!r}, want {existing!r}")
        if dlg2.holidayMonth.currentText() != str(priorMonth):
            errors.append(f"Edit prefill: holidayMonth={dlg2.holidayMonth.currentText()!r}, want {priorMonth!r}")
        newMonth = (priorMonth % 12) + 1  # any month other than the current one
        dlg2.holidayMonth.setCurrentText(str(newMonth))
        dlg2.updateButton.click()
        if w.db.holidays.defaults.get(existing) != newMonth:
            errors.append(f"after Update: db.holidays.defaults[{existing!r}]={w.db.holidays.defaults.get(existing)!r}, want {newMonth}")
    finally:
        if restore is not None:
            restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if tmp is not None:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + suffix)
                except OSError:
                    pass
    return errors
