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
    pressNames = F.populatePresses(db, rng, cfg["presses"])
    F.populatePressers(db, rng, idNums, cfg["pressers"])
    F.populateShiftWorkweek(db, rng)
    F.populatePartPressPref(db, rng, partNames, pressNames)
    clientNames = F.populateClients(db, rng, cfg["clients"])
    orderNums = F.populateOrders(db, rng, clientNames, partNames, cfg["orders"], today)
    F.populateOrderStatus(db, rng, orderNums, today)
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


def inventory_edit_missing_date() -> list[str]:
    """Step 62: the inventory material/part edit windows' readData must surface a
    validation error, not crash, when their date has no inventory snapshot — and
    the part editor's duplicate check must read the .parts collection.

    A 'checked-then-dereferenced-anyway' bug: readData flags a missing date up
    top, but the duplicate-record check below it indexed
    db.inventories[self.date] unconditionally (KeyError on a stale/absent date),
    and the part editor indexed .materials instead of .parts — so it missed real
    duplicate part records and then crashed in addPartRecord. Drives both editors
    headlessly on the error / duplicate paths (QMessageBox stubbed)."""
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from inventory_tab import MaterialInventoryEditWindow, PartInventoryEditWindow
    from records.products import PartInventoryRecord

    errors: list[str] = []
    QApplication.instance() or QApplication(sys.argv)
    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        absentDate = datetime_date(2099, 1, 1)  # guaranteed not in db.inventories

        # 1) Material editor on a date with no inventory: must not KeyError.
        matEd = MaterialInventoryEditWindow(absentDate, None, w)
        matEd.selectedName = "AnyMat"
        matEd.costEntry.setText("5.0")
        matEd.mainLayout[2][1].setText("10")
        try:
            res = matEd.readData(True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"material editor readData raised on absent date: {e!r}")
        else:
            if res is not False:
                errors.append(f"material editor readData returned {res!r}, expected False on absent date")

        # 2) Part editor on a date with no inventory: must not KeyError.
        partEd = PartInventoryEditWindow(absentDate, None, w)
        partEd.selectedName = "AnyPart"
        partEd.costEntry.setText("1.0")
        for row in (2, 3, 4, 5):
            partEd.mainLayout[row][1].setText("1")
        try:
            res = partEd.readData(True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"part editor readData raised on absent date: {e!r}")
        else:
            if res is not False:
                errors.append(f"part editor readData returned {res!r}, expected False on absent date")

        # 3) Part editor duplicate detection must read .parts: seed a part record,
        #    then a NEW editor for the same (date, name) must flag the duplicate
        #    (return False, no raise). Pre-fix it checked .materials, missed the
        #    dup, and crashed in addPartRecord.
        dupDate = datetime_date(2099, 2, 2)
        rec = PartInventoryRecord()
        rec.setName("DupPart")
        rec.setDate(dupDate)
        rec.setInventory(1.0, 1, 1, 1, 1)
        w.db.addPartInventory(rec)
        dupEd = PartInventoryEditWindow(dupDate, None, w)
        dupEd.selectedName = "DupPart"
        dupEd.costEntry.setText("1.0")
        for row in (2, 3, 4, 5):
            dupEd.mainLayout[row][1].setText("1")
        try:
            res = dupEd.readData(True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"part editor readData raised on duplicate part record: {e!r}")
        else:
            if res is not False:
                errors.append(f"part editor readData returned {res!r}, expected False on duplicate part record "
                              f"(the .parts dup check did not fire)")
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


def file_dialog_dir_memory() -> list[str]:
    """§13.45: the Open / Save As / Import dialogs seed from the last-browsed
    directory (``lastDir`` in QSettings) instead of always starting at home.

    Drives ``MainWindow._lastDir`` / ``_rememberDir`` directly (the file
    dialogs themselves are modal and can't be smoke-driven). Asserts: unset →
    home; a remembered real directory is returned verbatim; ``_rememberDir``
    stores the *directory* of a picked file; and a stale (since-deleted)
    remembered directory falls back to home rather than surfacing a bad path.
    """
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication
    from app import MainWindow

    errors = []
    _ = QApplication.instance() or QApplication(sys.argv)

    # Isolate QSettings storage so the test never touches the user's real store.
    origOrg = QCoreApplication.organizationName()
    origApp = QCoreApplication.applicationName()
    QCoreApplication.setOrganizationName("k4g-mercy-smoke")
    QCoreApplication.setApplicationName("MERCY-smoke")
    settingsDir = tempfile.mkdtemp(prefix="mercy-qsettings-")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settingsDir)

    home = os.path.expanduser("~")
    realDir = tempfile.mkdtemp(prefix="mercy-lastdir-")
    w = None
    try:
        QSettings().remove("lastDir")
        QSettings().sync()
        w = MainWindow()

        # Unset → home.
        if w._lastDir() != home:
            errors.append(f"_lastDir() with no stored value: expected home {home!r}, got {w._lastDir()!r}")

        # Remembering a picked file stores its containing directory.
        w._rememberDir(os.path.join(realDir, "somedb.db"))
        stored = QSettings().value("lastDir")
        if stored != realDir:
            errors.append(f"_rememberDir stored {stored!r}, expected {realDir!r}")
        if w._lastDir() != realDir:
            errors.append(f"_lastDir() after remember: expected {realDir!r}, got {w._lastDir()!r}")

        # Stale (deleted) remembered directory → fall back to home, no bad path.
        staleDir = os.path.join(realDir, "gone")
        QSettings().setValue("lastDir", staleDir)
        QSettings().sync()
        if os.path.isdir(staleDir):
            errors.append(f"test setup bug: {staleDir} should not exist")
        elif w._lastDir() != home:
            errors.append(f"_lastDir() with stale dir {staleDir!r}: expected home {home!r}, got {w._lastDir()!r}")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        import shutil
        shutil.rmtree(realDir, ignore_errors=True)
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


def presses_tab_crud() -> list[str]:
    """Step 43: PressesTab CRUD + save/reload roundtrip.

    Seeds tiny fuzz data (which now populates presses), then via
    ``PressEditWindow`` and the tab buttons:
      - opens an Edit window on the first press, confirms ``nameEdit``
        prefills, renames it, clicks ``updateButton``, and confirms
        ``db.presses`` rekeys (new name in, old name out);
      - opens a *new* ``PressEditWindow`` (entry=None), types a novel
        name, clicks ``createButton``, and confirms it appears;
      - selects that new press and calls ``deleteSelection`` (the
        confirm dialog is stubbed to Yes), confirming removal;
      - saves, reloads into a fresh ``MainWindow``, and confirms the
        surviving presses roundtrip through SQLite unchanged.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from presses_tab import PressEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w.pressesTab.refreshTable()

        if len(w.db.presses) == 0:
            errors.append("expected fuzz seed to populate presses, got 0")
            return errors

        # --- Edit: rename an existing press ---
        fixture = sorted(w.db.presses)[0]
        editor = PressEditWindow(fixture, w)
        if editor.nameEdit.text() != fixture:
            errors.append(f"Edit prefill: nameEdit={editor.nameEdit.text()!r}, want {fixture!r}")
        renamed = "Renamed Press"
        editor.nameEdit.setText(renamed)
        editor.updateButton.click()
        if renamed not in w.db.presses:
            errors.append(f"after Update: {renamed!r} missing from db.presses")
        if fixture in w.db.presses:
            errors.append(f"after Update: old key {fixture!r} still present")

        # --- Create a new press ---
        newEditor = PressEditWindow(None, w)
        newName = "SmokeTestPress"
        newEditor.nameEdit.setText(newName)
        newEditor.createButton.click()
        if newName not in w.db.presses:
            errors.append(f"after Create: {newName!r} missing from db.presses")

        # --- Delete that press via the tab (confirm dialog stubbed to Yes) ---
        before = len(w.db.presses)
        w.pressesTab.setSelection([newName])
        w.pressesTab.deleteSelection()
        if newName in w.db.presses:
            errors.append(f"after Delete: {newName!r} still present")
        if len(w.db.presses) != before - 1:
            errors.append(f"after Delete: count {len(w.db.presses)} != {before - 1}")

        # --- save / reload roundtrip ---
        expected = set(w.db.presses)
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading presses DB")
        else:
            w2.fileManager.loadFile()
            got = set(w2.db.presses)
            if got != expected:
                errors.append(f"presses roundtrip mismatch: expected {sorted(expected)}, got {sorted(got)}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def clients_tab_crud() -> list[str]:
    """Step 46: ClientsTab CRUD + save/reload roundtrip (incl. transportDays).

    Seeds tiny fuzz data (which now populates clients), then via
    ``ClientEditWindow`` and the tab buttons:
      - opens an Edit window on the first client, confirms ``nameEdit`` and
        ``transportEdit`` prefill, renames it + changes transportDays, clicks
        ``updateButton``, and confirms ``db.clients`` rekeys (new name in, old
        name out) and the new transportDays sticks;
      - opens a *new* ``ClientEditWindow`` (entry=None), types a novel name +
        transportDays, clicks ``createButton``, and confirms it appears;
      - selects that new client and calls ``deleteSelection`` (confirm dialog
        stubbed to Yes), confirming removal;
      - saves, reloads into a fresh ``MainWindow``, and confirms the surviving
        clients roundtrip through SQLite unchanged — name *and* transportDays.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from clients_tab import ClientEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w.clientsTab.refreshTable()

        if len(w.db.clients) == 0:
            errors.append("expected fuzz seed to populate clients, got 0")
            return errors

        # --- Edit: rename an existing client + change its transportDays ---
        fixture = sorted(w.db.clients)[0]
        editor = ClientEditWindow(fixture, w)
        if editor.nameEdit.text() != fixture:
            errors.append(f"Edit prefill: nameEdit={editor.nameEdit.text()!r}, want {fixture!r}")
        if editor.transportEdit.text() != f"{w.db.clients[fixture].transportDays}":
            errors.append(f"Edit prefill: transportEdit={editor.transportEdit.text()!r}, "
                          f"want {w.db.clients[fixture].transportDays!r}")
        renamed = "Renamed Client"
        editor.nameEdit.setText(renamed)
        editor.transportEdit.setText("4")
        editor.updateButton.click()
        if renamed not in w.db.clients:
            errors.append(f"after Update: {renamed!r} missing from db.clients")
        elif w.db.clients[renamed].transportDays != 4:
            errors.append(f"after Update: transportDays={w.db.clients[renamed].transportDays}, want 4")
        if fixture in w.db.clients:
            errors.append(f"after Update: old key {fixture!r} still present")

        # --- Create a new client ---
        newEditor = ClientEditWindow(None, w)
        newName = "SmokeTestClient"
        newEditor.nameEdit.setText(newName)
        newEditor.transportEdit.setText("0")  # 0 transport days is legal
        newEditor.createButton.click()
        if newName not in w.db.clients:
            errors.append(f"after Create: {newName!r} missing from db.clients")
        elif w.db.clients[newName].transportDays != 0:
            errors.append(f"after Create: transportDays={w.db.clients[newName].transportDays}, want 0")

        # --- Delete that client via the tab (confirm dialog stubbed to Yes) ---
        before = len(w.db.clients)
        w.clientsTab.setSelection([newName])
        w.clientsTab.deleteSelection()
        if newName in w.db.clients:
            errors.append(f"after Delete: {newName!r} still present")
        if len(w.db.clients) != before - 1:
            errors.append(f"after Delete: count {len(w.db.clients)} != {before - 1}")

        # --- save / reload roundtrip (name + transportDays) ---
        expected = {name: w.db.clients[name].transportDays for name in w.db.clients}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading clients DB")
        else:
            w2.fileManager.loadFile()
            got = {name: w2.db.clients[name].transportDays for name in w2.db.clients}
            if got != expected:
                errors.append(f"clients roundtrip mismatch: expected {expected}, got {got}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def orders_tab_crud() -> list[str]:
    """Step 47: OrdersTab CRUD + FK combos + auto-suggest + block-on-delete + roundtrip.

    Seeds tiny fuzz data (now populating clients, parts, and orders), then:
      - confirms deleting a client/part an order references is BLOCKED (the
        client/part and the order both survive);
      - opens an Edit window on an order, confirms the order-number / client /
        part / quantity prefill, changes quantity + price + part + renames the
        order number, and confirms the rekey and field updates land;
      - opens a *new* OrderEditWindow, confirms the order number auto-suggests
        (and re-suggests when the client changes while untouched), then creates
        an order with an explicit number;
      - deletes that order via the tab;
      - saves, reloads into a fresh MainWindow, and confirms every order's
        fields roundtrip through SQLite unchanged.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from orders_tab import OrderEditWindow
    from clients_tab import ClientEditWindow
    from parts_tab import PartsEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()

        if len(w.db.orders) == 0:
            errors.append("expected fuzz seed to populate orders, got 0")
            return errors

        fixtureNum = sorted(w.db.orders)[0]
        fixture = w.db.orders[fixtureNum]
        fixtureClient, fixturePart = fixture.client, fixture.part

        # --- block-on-delete: a client referenced by an order can't be deleted ---
        if fixtureClient in w.db.clients:
            w.clientsTab.setSelection([fixtureClient])
            w.clientsTab.deleteSelection()
            if fixtureClient not in w.db.clients:
                errors.append(f"block-on-delete: client {fixtureClient!r} was deleted despite order {fixtureNum!r}")
            if fixtureNum not in w.db.orders:
                errors.append(f"block-on-delete: order {fixtureNum!r} vanished when its client delete was attempted")

        # --- block-on-delete: a part referenced by an order can't be deleted ---
        if fixturePart in w.db.parts:
            w.partsTab.setSelection([fixturePart])
            w.partsTab.deleteSelection()
            if fixturePart not in w.db.parts:
                errors.append(f"block-on-delete: part {fixturePart!r} was deleted despite order {fixtureNum!r}")
            if fixtureNum not in w.db.orders:
                errors.append(f"block-on-delete: order {fixtureNum!r} vanished when its part delete was attempted")

        # --- rename propagation must refresh the Orders table (Step 47 fix) ---
        # Drive the real client/part edit windows; assert the rename lands in both
        # the order *data* and the Orders *table view* (ordersTab.data). The
        # view-refresh half guards the bug where db.updateClient/updatePart fixed up
        # the order but no one called ordersTab.refreshTable().
        def _orderRow(num):
            return next((r for r in w.ordersTab.data if r[0] == num), None)

        renamedClient = "Renamed Client Co"
        ce = ClientEditWindow(fixtureClient, w)
        ce.nameEdit.setText(renamedClient)
        ce.updateButton.click()
        if w.db.orders[fixtureNum].client != renamedClient:
            errors.append(f"client rename did not propagate to order {fixtureNum!r} data")
        crow = _orderRow(fixtureNum)
        if crow is None or crow[1] != renamedClient:
            errors.append(f"client rename did not refresh the Orders table (row={crow})")
        fixtureClient = renamedClient

        renamedPart = "Renamed Part Z"
        pe = PartsEditWindow(fixturePart, w)
        pe.nameEdit.setText(renamedPart)
        pe.updateButton.click()
        if w.db.orders[fixtureNum].part != renamedPart:
            errors.append(f"part rename did not propagate to order {fixtureNum!r} data")
        prow = _orderRow(fixtureNum)
        if prow is None or prow[2] != renamedPart:
            errors.append(f"part rename did not refresh the Orders table (row={prow})")
        fixturePart = renamedPart

        # --- Edit: rename order + change quantity / price / part ---
        editor = OrderEditWindow(fixtureNum, w)
        if editor.orderNumEdit.text() != fixtureNum:
            errors.append(f"Edit prefill: orderNumEdit={editor.orderNumEdit.text()!r}, want {fixtureNum!r}")
        if editor.clientCombo.currentText() != fixtureClient:
            errors.append(f"Edit prefill: client={editor.clientCombo.currentText()!r}, want {fixtureClient!r}")
        if editor.partCombo.currentText() != fixturePart:
            errors.append(f"Edit prefill: part={editor.partCombo.currentText()!r}, want {fixturePart!r}")
        otherParts = [p for p in sorted(w.db.parts) if p != fixturePart]
        newPart = otherParts[0] if otherParts else fixturePart
        renamed = "RENAMED-ORDER-001"
        editor.orderNumEdit.setText(renamed)
        editor.partCombo.setCurrentText(newPart)
        editor.quantityEdit.setText("777")
        editor.priceEdit.setText("1234.5")
        editor.updateButton.click()
        if renamed not in w.db.orders:
            errors.append(f"after Update: {renamed!r} missing from db.orders")
        else:
            o = w.db.orders[renamed]
            if (o.quantity, o.price, o.part) != (777, 1234.5, newPart):
                errors.append(f"after Update: fields={(o.quantity, o.price, o.part)}, want (777, 1234.5, {newPart!r})")
        if fixtureNum in w.db.orders:
            errors.append(f"after Update: old key {fixtureNum!r} still present")

        # --- Create a new order; confirm the order number auto-suggests ---
        newEditor = OrderEditWindow(None, w)
        suggested = newEditor.orderNumEdit.text()
        if suggested.count("-") != 2 or not suggested.split("-")[-1].isdigit():
            errors.append(f"auto-suggest order number malformed: {suggested!r}")
        # Re-suggest when the client changes while the field is untouched.
        clients = sorted(w.db.clients)
        if len(clients) >= 2:
            other = [c for c in clients if c != newEditor.clientCombo.currentText()][0]
            newEditor.clientCombo.setCurrentText(other)
            if newEditor.orderNumEdit.text() == suggested:
                errors.append("auto-suggest did not refresh when the client changed")
        newName = "SMOKE-NEW-ORDER"
        newEditor.orderNumEdit.setText(newName)
        newEditor.quantityEdit.setText("10")
        newEditor.priceEdit.setText("99.0")
        newEditor.createButton.click()
        if newName not in w.db.orders:
            errors.append(f"after Create: {newName!r} missing from db.orders")

        # --- Delete that order via the tab ---
        before = len(w.db.orders)
        w.ordersTab.setSelection([newName])
        w.ordersTab.deleteSelection()
        if newName in w.db.orders:
            errors.append(f"after Delete: {newName!r} still present")
        if len(w.db.orders) != before - 1:
            errors.append(f"after Delete: count {len(w.db.orders)} != {before - 1}")

        # --- save / reload roundtrip (all fields) ---
        expected = {num: o.getTuple() for num, o in w.db.orders.items()}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading orders DB")
        else:
            w2.fileManager.loadFile()
            got = {num: o.getTuple() for num, o in w2.db.orders.items()}
            if got != expected:
                errors.append(f"orders roundtrip mismatch: expected {expected}, got {got}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def part_press_pref_crud() -> list[str]:
    """Step 64: PartPressPrefTab interactive grid CRUD + cascades + save/reload roundtrip.

    Seeds tiny fuzz data (scoring some part-press pairs), then drives the in-cell
    grid (Step 64 rewrite of the Step 48 modal) through its ScoreDelegate:
      - the delegate prefills a cell's combo from the stored score / "Not set";
      - an in-cell edit sets one press to 5 and clears another to "Not set" (=> no row);
      - renames the part: prefs rekey AND the grid refreshes (FK-rename rule);
      - renames a press: the score map rekeys AND the grid column refreshes;
      - deletes that press: it cascades out of every part's prefs;
      - deletes a part (after clearing its orders): its prefs cascade away;
      - saves, reloads into a fresh MainWindow, confirms prefs roundtrip via getTuples.
    """
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    from app import MainWindow
    from pref_grid import ScoreDelegate, NOT_SET_TEXT
    from presses_tab import PressEditWindow
    from parts_tab import PartsEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()

        parts = sorted(w.db.parts)
        presses = sorted(w.db.presses)
        if len(parts) < 2 or len(presses) < 2:
            errors.append(f"expected >=2 parts and >=2 presses from tiny seed, got {len(parts)}/{len(presses)}")
            return errors
        part = parts[0]

        tab = w.partPressPrefTab
        model = tab.table.dbModel
        delegate = ScoreDelegate()
        opt = QStyleOptionViewItem()

        def idx(part_, press_):
            return model.index(tab.rowKeys.index(part_), 1 + tab.pressNames.index(press_))

        def cell(part_, press_):
            # Current on-screen score for (part, press), read from the live grid matrix.
            t = w.partPressPrefTab
            if part_ not in t.rowKeys or press_ not in t.pressNames:
                return "MISSING"
            return t.data[t.rowKeys.index(part_)][1 + t.pressNames.index(press_)]

        # Clear any seed scores for `part` to a deterministic slate, then a known
        # starting state for the prefill check.
        for pr in presses:
            w.db.setPartPressScore(part, pr, None)
        w.db.setPartPressScore(part, presses[0], 4)
        w.partPressPrefTab.refreshTable()

        # --- in-cell prefill: the delegate opens a combo showing the stored score ---
        scoredCombo = delegate.createEditor(tab.table, opt, idx(part, presses[0]))
        delegate.setEditorData(scoredCombo, idx(part, presses[0]))
        if scoredCombo.currentText() != "4":
            errors.append(f"prefill: {presses[0]} combo={scoredCombo.currentText()!r}, want '4'")
        unsetCombo = delegate.createEditor(tab.table, opt, idx(part, presses[1]))
        delegate.setEditorData(unsetCombo, idx(part, presses[1]))
        if unsetCombo.currentText() != NOT_SET_TEXT:
            errors.append(f"prefill: unscored {presses[1]} combo={unsetCombo.currentText()!r}, want {NOT_SET_TEXT!r}")

        # --- in-cell edit: set presses[1] = 5, clear presses[0] to "Not set" ---
        scoredCombo.setCurrentText("5")
        delegate.setModelData(scoredCombo, model, idx(part, presses[1]))
        scoredCombo.setCurrentText(NOT_SET_TEXT)
        delegate.setModelData(scoredCombo, model, idx(part, presses[0]))
        pref = w.db.partPressPref.get(part)
        if pref is None or pref.scores != {presses[1]: 5}:
            errors.append(f"after in-cell edit: scores={pref and pref.scores}, want {{{presses[1]!r}: 5}}")
        if cell(part, presses[1]) != 5 or cell(part, presses[0]) is not None:
            errors.append(f"grid did not reflect the edit: {presses[1]}={cell(part, presses[1])!r}, "
                          f"{presses[0]}={cell(part, presses[0])!r}")

        # --- part rename: prefs rekey + table refreshes ---
        renamedPart = "Renamed Pref Part"
        pe = PartsEditWindow(part, w)
        pe.nameEdit.setText(renamedPart)
        pe.updateButton.click()
        if part in w.db.partPressPref:
            errors.append(f"part rename: stale key {part!r} still in partPressPref")
        if renamedPart not in w.db.partPressPref:
            errors.append(f"part rename: prefs did not rekey to {renamedPart!r}")
        if not any(r[0] == renamedPart for r in w.partPressPrefTab.data):
            errors.append("part rename: Part-Press Preference table not refreshed")
        part = renamedPart

        # --- press rename: score map rekeys + table refreshes ---
        oldPress = presses[1]
        renamedPress = "Renamed Press X"
        pre = PressEditWindow(oldPress, w)
        pre.nameEdit.setText(renamedPress)
        pre.updateButton.click()
        pref = w.db.partPressPref.get(part)
        if pref is None or oldPress in pref.scores or pref.getScore(renamedPress) != 5:
            errors.append(f"press rename: score map not rekeyed (scores={pref and pref.scores})")
        if cell(part, renamedPress) != 5:
            errors.append(f"press rename: pref grid not refreshed (cell={cell(part, renamedPress)!r})")

        # --- press delete: cascades out of every part's prefs ---
        w.pressesTab.setSelection([renamedPress])
        w.pressesTab.deleteSelection()
        if renamedPress in w.db.presses:
            errors.append(f"press delete: {renamedPress!r} survived")
        for p, pr in w.db.partPressPref.items():
            if renamedPress in pr.scores:
                errors.append(f"press delete: {renamedPress!r} still scored on part {p!r}")
        # `part` scored only renamedPress (all else neutral), so it should drop out entirely.
        if part in w.db.partPressPref:
            errors.append(f"press delete: {part!r} should have no scores left, still present")

        # --- part delete: its prefs cascade away (clear referencing orders first) ---
        survivor = sorted(w.db.parts)[0]
        for onum in [n for n, o in w.db.orders.items() if o.part == survivor]:
            w.db.delOrder(onum)
        livePress = sorted(w.db.presses)[0]
        w.db.setPartPressScore(survivor, livePress, 3)
        w.partPressPrefTab.refreshTable()
        w.partsTab.setSelection([survivor])
        w.partsTab.deleteSelection()
        if survivor in w.db.parts:
            errors.append(f"part delete: {survivor!r} survived (unexpected order ref?)")
        elif survivor in w.db.partPressPref:
            errors.append(f"part delete: prefs for {survivor!r} not cascaded")

        # --- save / reload roundtrip ---
        anyPart = sorted(w.db.parts)[0]
        anyPress = sorted(w.db.presses)[0]
        w.db.setPartPressScore(anyPart, anyPress, 2)
        expected = {p: pr.getTuples() for p, pr in w.db.partPressPref.items()}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading pref DB")
        else:
            w2.fileManager.loadFile()
            got = {p: pr.getTuples() for p, pr in w2.db.partPressPref.items()}
            if got != expected:
                errors.append(f"part-press pref roundtrip mismatch: expected {expected}, got {got}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def part_truck_crud() -> list[str]:
    """Step 74a: PartTruckTab interactive grid CRUD + cascades + save/reload roundtrip.

    Seeds tiny fuzz data, then drives the single-value in-cell grid through its
    TruckValueDelegate (a QLineEdit, not a combo):
      - the delegate prefills a cell from the stored figure / blank (unset);
      - an in-cell edit sets one part's figure and clears another to blank (=> no row);
      - renames the part: the figure rekeys AND the grid refreshes (FK-rename rule);
      - deletes a part (after clearing its orders): its figure cascades away;
      - saves, reloads into a fresh MainWindow, confirms figures roundtrip.
    """
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    from app import MainWindow
    from part_truck_tab import TruckValueDelegate
    from parts_tab import PartsEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()

        parts = sorted(w.db.parts)
        if len(parts) < 2:
            errors.append(f"expected >=2 parts from tiny seed, got {len(parts)}")
            return errors
        partA, partB = parts[0], parts[1]

        tab = w.partTruckTab
        model = tab.table.dbModel
        delegate = TruckValueDelegate()
        opt = QStyleOptionViewItem()

        def idx(part_):
            return model.index(tab.rowKeys.index(part_), 1)

        def cell(part_):
            # Current on-screen figure for `part`, read from the live grid matrix.
            t = w.partTruckTab
            if part_ not in t.rowKeys:
                return "MISSING"
            return t.data[t.rowKeys.index(part_)][1]

        # Deterministic slate: partA has a figure, partB is unset.
        w.db.setPartTruck(partA, None)
        w.db.setPartTruck(partB, None)
        w.db.setPartTruck(partA, 200)
        w.partTruckTab.refreshTable()

        # --- in-cell prefill: the delegate opens a line edit showing the stored figure ---
        setEditor = delegate.createEditor(tab.table, opt, idx(partA))
        delegate.setEditorData(setEditor, idx(partA))
        if setEditor.text() != "200":
            errors.append(f"prefill: {partA} editor={setEditor.text()!r}, want '200'")
        unsetEditor = delegate.createEditor(tab.table, opt, idx(partB))
        delegate.setEditorData(unsetEditor, idx(partB))
        if unsetEditor.text() != "":
            errors.append(f"prefill: unset {partB} editor={unsetEditor.text()!r}, want ''")

        # --- regression guard (Step 74a manual-gate find): an empty field must stay
        # *acceptable* to the editor's validator, or Qt's delegate silently refuses to
        # commit a blank (reverting to the old value) and "clear to unset" is
        # unreachable in the UI — a QIntValidator(min=1) has exactly that defect. ---
        setEditor.setText("")
        if not setEditor.hasAcceptableInput():
            errors.append("empty editor not acceptable — clearing a cell to unset "
                          "would be blocked by Qt's commit gate")

        # --- in-cell edit: set partB = 350, clear partA to blank (=> no row) ---
        unsetEditor.setText("350")
        delegate.setModelData(unsetEditor, model, idx(partB))
        setEditor.setText("")
        delegate.setModelData(setEditor, model, idx(partA))
        if partA in w.db.partTruck:
            errors.append(f"after clear: {partA!r} should be unset, still in partTruck")
        truckB = w.db.partTruck.get(partB)
        if truckB is None or truckB.partsPerTruck != 350:
            errors.append(f"after in-cell edit: {partB} figure={truckB and truckB.partsPerTruck}, want 350")
        if cell(partB) != 350 or cell(partA) is not None:
            errors.append(f"grid did not reflect the edit: {partB}={cell(partB)!r}, {partA}={cell(partA)!r}")

        # --- a non-positive entry clears back to unset (the widget guard) ---
        zeroEditor = delegate.createEditor(tab.table, opt, idx(partB))
        zeroEditor.setText("0")
        delegate.setModelData(zeroEditor, model, idx(partB))
        if partB in w.db.partTruck:
            errors.append(f"'0' entry should clear {partB!r} to unset, still in partTruck")
        # Restore a figure on partB for the rename / roundtrip below.
        w.db.setPartTruck(partB, 350)
        w.partTruckTab.refreshTable()

        # --- part rename: figure rekeys + grid refreshes (FK-rename rule) ---
        renamedPart = "Renamed Truck Part"
        pe = PartsEditWindow(partB, w)
        pe.nameEdit.setText(renamedPart)
        pe.updateButton.click()
        if partB in w.db.partTruck:
            errors.append(f"part rename: stale key {partB!r} still in partTruck")
        renamed = w.db.partTruck.get(renamedPart)
        if renamed is None or renamed.part != renamedPart or renamed.partsPerTruck != 350:
            errors.append(f"part rename: figure did not rekey to {renamedPart!r} ({renamed})")
        if not any(r[0] == renamedPart for r in w.partTruckTab.data):
            errors.append("part rename: Parts per Truck grid not refreshed")

        # --- part delete: its figure cascades away (clear referencing orders first) ---
        for onum in [n for n, o in w.db.orders.items() if o.part == renamedPart]:
            w.db.delOrder(onum)
        w.partsTab.setSelection([renamedPart])
        w.partsTab.deleteSelection()
        if renamedPart in w.db.parts:
            errors.append(f"part delete: {renamedPart!r} survived (unexpected order ref?)")
        elif renamedPart in w.db.partTruck:
            errors.append(f"part delete: figure for {renamedPart!r} not cascaded")

        # --- save / reload roundtrip ---
        anyPart = sorted(w.db.parts)[0]
        w.db.setPartTruck(anyPart, 480)
        expected = {p: t.partsPerTruck for p, t in w.db.partTruck.items()}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading truck DB")
        else:
            w2.fileManager.loadFile()
            got = {p: t.partsPerTruck for p, t in w2.db.partTruck.items()}
            if got != expected:
                errors.append(f"parts-per-truck roundtrip mismatch: expected {expected}, got {got}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def presser_press_pref_crud() -> list[str]:
    """Step 65: PresserPressPrefTab interactive grid CRUD + cascades + save/reload roundtrip.

    The presser twin of ``part_press_pref_crud`` — reuses the same ``PrefGrid`` widget,
    but rows are pressers (keyed by employeeId, labeled by the employee name) instead
    of parts. Seeds tiny fuzz data (which now scores some presser-press pairs), then
    drives the in-cell grid through its ScoreDelegate:
      - the delegate prefills a cell's combo from the stored score / "Not set";
      - an in-cell edit sets one press to 5 and clears another to "Not set" (=> no row);
      - renames the presser's employee: the grid's row LABEL refreshes (the key, an
        employeeId, is unchanged — the label is employee-derived);
      - renames a press: the score map rekeys AND the grid column refreshes;
      - deletes that press: it cascades out of every presser's prefs;
      - deletes the presser: its prefs cascade away;
      - saves, reloads into a fresh MainWindow, confirms prefs roundtrip via getTuples.
    """
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    from app import MainWindow
    from pref_grid import ScoreDelegate, NOT_SET_TEXT
    from presses_tab import PressEditWindow
    from pressers_tab import _presserLabel

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()

        pressers = sorted(w.db.pressers)
        presses = sorted(w.db.presses)
        if len(pressers) < 1 or len(presses) < 2:
            errors.append(f"expected >=1 presser and >=2 presses from tiny seed, got {len(pressers)}/{len(presses)}")
            return errors
        empId = pressers[0]

        tab = w.presserPressPrefTab
        model = tab.table.dbModel
        delegate = ScoreDelegate()
        opt = QStyleOptionViewItem()

        def idx(emp_, press_):
            return model.index(tab.rowKeys.index(emp_), 1 + tab.pressNames.index(press_))

        def cell(emp_, press_):
            # Current on-screen score for (presser, press), read from the live grid matrix.
            t = w.presserPressPrefTab
            if emp_ not in t.rowKeys or press_ not in t.pressNames:
                return "MISSING"
            return t.data[t.rowKeys.index(emp_)][1 + t.pressNames.index(press_)]

        def label(emp_):
            # Current on-screen column-0 label for the presser row.
            t = w.presserPressPrefTab
            return t.data[t.rowKeys.index(emp_)][0]

        # Clear any seed scores for `empId` to a deterministic slate, then a known
        # starting state for the prefill check.
        for pr in presses:
            w.db.setPresserPressScore(empId, pr, None)
        w.db.setPresserPressScore(empId, presses[0], 4)
        w.presserPressPrefTab.refreshTable()

        # --- in-cell prefill: the delegate opens a combo showing the stored score ---
        scoredCombo = delegate.createEditor(tab.table, opt, idx(empId, presses[0]))
        delegate.setEditorData(scoredCombo, idx(empId, presses[0]))
        if scoredCombo.currentText() != "4":
            errors.append(f"prefill: {presses[0]} combo={scoredCombo.currentText()!r}, want '4'")
        unsetCombo = delegate.createEditor(tab.table, opt, idx(empId, presses[1]))
        delegate.setEditorData(unsetCombo, idx(empId, presses[1]))
        if unsetCombo.currentText() != NOT_SET_TEXT:
            errors.append(f"prefill: unscored {presses[1]} combo={unsetCombo.currentText()!r}, want {NOT_SET_TEXT!r}")

        # --- in-cell edit: set presses[1] = 5, clear presses[0] to "Not set" ---
        scoredCombo.setCurrentText("5")
        delegate.setModelData(scoredCombo, model, idx(empId, presses[1]))
        scoredCombo.setCurrentText(NOT_SET_TEXT)
        delegate.setModelData(scoredCombo, model, idx(empId, presses[0]))
        pref = w.db.presserPressPref.get(empId)
        if pref is None or pref.scores != {presses[1]: 5}:
            errors.append(f"after in-cell edit: scores={pref and pref.scores}, want {{{presses[1]!r}: 5}}")
        if cell(empId, presses[1]) != 5 or cell(empId, presses[0]) is not None:
            errors.append(f"grid did not reflect the edit: {presses[1]}={cell(empId, presses[1])!r}, "
                          f"{presses[0]}={cell(empId, presses[0])!r}")

        # --- employee rename: the row label refreshes, the employeeId key is unchanged ---
        emp = w.db.employees[empId]
        emp.lastName = "Zzrenamed"
        emp.firstName = "Presser"
        # Refresh both presser-derived tabs the way the real employee-edit path does,
        # so the Pressers tab's label->id map is current for the delete-by-label below.
        w.presserPressPrefTab.refreshTable()
        w.pressersTab.refreshTable()
        wantLabel = _presserLabel(w.db, empId)
        if empId not in w.db.presserPressPref:
            errors.append(f"employee rename: presser key {empId} unexpectedly changed")
        if label(empId) != wantLabel:
            errors.append(f"employee rename: grid label={label(empId)!r}, want {wantLabel!r}")

        # --- press rename: score map rekeys + grid column refreshes ---
        oldPress = presses[1]
        renamedPress = "Renamed Press Y"
        pre = PressEditWindow(oldPress, w)
        pre.nameEdit.setText(renamedPress)
        pre.updateButton.click()
        pref = w.db.presserPressPref.get(empId)
        if pref is None or oldPress in pref.scores or pref.getScore(renamedPress) != 5:
            errors.append(f"press rename: score map not rekeyed (scores={pref and pref.scores})")
        if cell(empId, renamedPress) != 5:
            errors.append(f"press rename: presser grid not refreshed (cell={cell(empId, renamedPress)!r})")

        # --- press delete: cascades out of every presser's prefs ---
        w.pressesTab.setSelection([renamedPress])
        w.pressesTab.deleteSelection()
        if renamedPress in w.db.presses:
            errors.append(f"press delete: {renamedPress!r} survived")
        for e, pr in w.db.presserPressPref.items():
            if renamedPress in pr.scores:
                errors.append(f"press delete: {renamedPress!r} still scored on presser {e!r}")
        # `empId` scored only renamedPress (all else neutral), so it should drop out entirely.
        if empId in w.db.presserPressPref:
            errors.append(f"press delete: presser {empId!r} should have no scores left, still present")

        # --- presser delete: its prefs cascade away ---
        livePress = sorted(w.db.presses)[0]
        w.db.setPresserPressScore(empId, livePress, 3)
        w.presserPressPrefTab.refreshTable()
        w.pressersTab.setSelection([_presserLabel(w.db, empId)])
        w.pressersTab.deleteSelection()
        if empId in w.db.pressers:
            errors.append(f"presser delete: {empId!r} survived")
        elif empId in w.db.presserPressPref:
            errors.append(f"presser delete: prefs for {empId!r} not cascaded")

        # --- save / reload roundtrip ---
        survivor = sorted(w.db.pressers)[0] if w.db.pressers else None
        if survivor is not None:
            anyPress = sorted(w.db.presses)[0]
            w.db.setPresserPressScore(survivor, anyPress, 2)
        expected = {e: pr.getTuples() for e, pr in w.db.presserPressPref.items()}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading presser pref DB")
        else:
            w2.fileManager.loadFile()
            got = {e: pr.getTuples() for e, pr in w2.db.presserPressPref.items()}
            if got != expected:
                errors.append(f"presser-press pref roundtrip mismatch: expected {expected}, got {got}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def order_status_crud() -> list[str]:
    """Step 49: OrderStatusTab nested editor CRUD + latest-wins + cascade + roundtrip.

    Seeds tiny fuzz data (now laying down dated snapshots per order), then:
      - opens the per-order editor; confirms the snapshot sub-table prefills from
        the order's current snapshots;
      - adds a fresh dated snapshot via the inline editor, confirms it lands in
        db.orderStatus and the sub-table;
      - re-adds the same date with new values, confirms it OVERWRITES (one snapshot
        per date) rather than duplicating;
      - adds a latest-dated snapshot with remaining-to-ship 0 and confirms the order
        reads fulfilled (isFulfilled + the outer table's Fulfilled? column);
      - selects + deletes a snapshot via the editor;
      - renames the order: status snapshots rekey AND the Order Status table
        refreshes (the FK-rename-refresh rule);
      - deletes an order: its status snapshots cascade away;
      - saves, reloads into a fresh MainWindow, confirms snapshots roundtrip via
        getTuples.
    """
    import datetime
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app import MainWindow
    from order_status_tab import OrderStatusEditWindow
    from orders_tab import OrderEditWindow
    from utils import toQDate

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()

        if len(w.db.orderStatus) == 0:
            errors.append("expected fuzz seed to populate order status, got 0")
            return errors

        orderNum = sorted(w.db.orderStatus)[0]
        status = w.db.orderStatus[orderNum]

        # --- editor prefill: sub-table shows the order's current snapshots ---
        editor = OrderStatusEditWindow(orderNum, w)
        if len(editor.snapshotData) != len(status.snapshots):
            errors.append(f"editor sub-table rows {len(editor.snapshotData)} != "
                          f"snapshots {len(status.snapshots)}")

        # --- add a fresh dated snapshot via the inline editor ---
        d1 = datetime.date.today() - datetime.timedelta(days=200)  # outside the seed window
        editor.dateEdit.setDate(toQDate(d1))
        editor.pressEdit.setText("42")
        editor.shipEdit.setText("99")
        editor.addButton.click()
        if w.db.orderStatus[orderNum].snapshots.get(d1) != (42, 99):
            errors.append(f"after add: snapshot[{d1}]={w.db.orderStatus[orderNum].snapshots.get(d1)}, want (42, 99)")
        if not any(r[0] == d1.isoformat() for r in editor.snapshotData):
            errors.append(f"after add: sub-table missing row for {d1}")

        # --- re-add the same date: overwrite, not duplicate ---
        before = len(w.db.orderStatus[orderNum].snapshots)
        editor.dateEdit.setDate(toQDate(d1))
        editor.pressEdit.setText("7")
        editor.shipEdit.setText("8")
        editor.addButton.click()
        if w.db.orderStatus[orderNum].snapshots.get(d1) != (7, 8):
            errors.append(f"after overwrite: snapshot[{d1}]={w.db.orderStatus[orderNum].snapshots.get(d1)}, want (7, 8)")
        if len(w.db.orderStatus[orderNum].snapshots) != before:
            errors.append(f"after overwrite: snapshot count changed {before} -> "
                          f"{len(w.db.orderStatus[orderNum].snapshots)} (should overwrite)")

        # --- latest-by-date wins => fulfilled when remaining-to-ship hits 0 ---
        dLatest = datetime.date.today()
        editor.dateEdit.setDate(toQDate(dLatest))
        editor.pressEdit.setText("0")
        editor.shipEdit.setText("0")
        editor.addButton.click()
        if not w.db.orderStatus[orderNum].isFulfilled():
            errors.append("after 0-to-ship latest snapshot: order not reported fulfilled")
        w.orderStatusTab.refreshTable()
        orow = next((r for r in w.orderStatusTab.data if r[0] == orderNum), None)
        if orow is None or orow[-1] != "Yes":
            errors.append(f"outer table Fulfilled? column not 'Yes' (row={orow})")

        # --- confirmation guard on out-of-order / increasing snapshots ---
        # Latest snapshot is now dLatest (today) = (0, 0). Drive QMessageBox.question
        # with a recorder so we can assert *when* the are-you-sure fires, and that
        # answering No cancels the add. (_silenceMessageBoxes stubbed it to Yes; we
        # restore that stub afterward so the later delete/rename confirms still pass.)
        answer = {"v": QMessageBox.StandardButton.Yes}
        calls = {"n": 0}

        def _recordQ(*_a, **_kw):
            calls["n"] += 1
            return answer["v"]

        savedQ = QMessageBox.question
        QMessageBox.question = staticmethod(_recordQ)  # type: ignore[assignment]
        try:
            # a normal newer, non-increasing snapshot must NOT prompt
            calls["n"] = 0
            editor.dateEdit.setDate(toQDate(dLatest + datetime.timedelta(days=1)))
            editor.pressEdit.setText("0")
            editor.shipEdit.setText("0")
            editor.addButton.click()
            if calls["n"] != 0:
                errors.append("normal decreasing snapshot should not prompt for confirmation")

            # a later snapshot with higher remaining than its predecessor must prompt
            calls["n"] = 0
            editor.dateEdit.setDate(toQDate(dLatest + datetime.timedelta(days=2)))
            editor.pressEdit.setText("5")
            editor.shipEdit.setText("5")
            editor.addButton.click()
            if calls["n"] == 0:
                errors.append("increasing-remaining snapshot did not prompt for confirmation")
            if w.db.orderStatus[orderNum].snapshots.get(dLatest + datetime.timedelta(days=2)) != (5, 5):
                errors.append("increasing snapshot not added after confirming Yes")

            # a back-dated snapshot (earlier than the latest) must prompt
            calls["n"] = 0
            editor.dateEdit.setDate(toQDate(dLatest - datetime.timedelta(days=400)))
            editor.pressEdit.setText("1")
            editor.shipEdit.setText("1")
            editor.addButton.click()
            if calls["n"] == 0:
                errors.append("back-dated snapshot did not prompt for confirmation")

            # answering No must cancel the add
            answer["v"] = QMessageBox.StandardButton.No
            cancelDate = dLatest + datetime.timedelta(days=3)
            editor.dateEdit.setDate(toQDate(cancelDate))
            editor.pressEdit.setText("999")
            editor.shipEdit.setText("999")
            editor.addButton.click()
            if cancelDate in w.db.orderStatus[orderNum].snapshots:
                errors.append("answering No to the confirm still added the snapshot")
        finally:
            QMessageBox.question = savedQ  # type: ignore[assignment]

        # --- select + delete a snapshot via the editor ---
        editor.setSelection([d1.isoformat()])
        editor.deleteButton.click()
        if d1 in w.db.orderStatus[orderNum].snapshots:
            errors.append(f"after delete: snapshot[{d1}] still present")

        # --- order rename: status rekeys + Order Status table refreshes ---
        renamed = "RENAMED-STATUS-ORDER"
        oe = OrderEditWindow(orderNum, w)
        oe.orderNumEdit.setText(renamed)
        oe.updateButton.click()
        if orderNum in w.db.orderStatus:
            errors.append(f"order rename: stale key {orderNum!r} still in orderStatus")
        if renamed not in w.db.orderStatus:
            errors.append(f"order rename: status did not rekey to {renamed!r}")
        elif w.db.orderStatus[renamed].orderNum != renamed:
            errors.append(f"order rename: record orderNum not updated ({w.db.orderStatus[renamed].orderNum!r})")
        if not any(r[0] == renamed for r in w.orderStatusTab.data):
            errors.append("order rename: Order Status table not refreshed")

        # --- order delete: its status cascades away AND the table view refreshes ---
        victim = sorted(w.db.orderStatus)[0]
        w.ordersTab.setSelection([victim])
        w.ordersTab.deleteSelection()
        if victim in w.db.orders:
            errors.append(f"order delete: {victim!r} survived")
        if victim in w.db.orderStatus:
            errors.append(f"order delete: status for {victim!r} not cascaded")
        # The data cascade isn't enough — the Order Status tab must drop the row too,
        # or the deleted order lingers on screen (the bug this guards).
        if any(r[0] == victim for r in w.orderStatusTab.data):
            errors.append(f"order delete: Order Status table still shows {victim!r} (stale view)")

        # --- save / reload roundtrip ---
        expected = {num: st.getTuples() for num, st in w.db.orderStatus.items()}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading order status DB")
        else:
            w2.fileManager.loadFile()
            got = {num: st.getTuples() for num, st in w2.db.orderStatus.items()}
            if got != expected:
                errors.append(f"order status roundtrip mismatch: expected {expected}, got {got}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def order_status_trucks_entry() -> list[str]:
    """Step 74b/76: the "Enter in trucks" toggle on the Order Status snapshot editor.

    Seeds tiny fuzz data, picks an order, and drives OrderStatusEditWindow's trucks
    toggle + press-field conversion (stored + displayed always in pieces):
      - the toggle blocks (reverts) when the part has no parts-per-truck set;
      - with a truck size set, engaging the toggle clears + relabels the PRESS field
        only, leaving the ship field untouched and its label in pieces (Step 76);
      - a 2.5-truck press entry stores 2.5 * partsPerTruck pieces, while ship stays
        pieces (1 -> 1, not 1 * partsPerTruck) (Step 76);
      - a half-truck of an odd count (=> fractional pieces) is rejected, as is a
        non-0.5-step value;
      - selecting a stored snapshot drops back to pieces mode and prefills pieces.
    """
    import datetime
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from order_status_tab import OrderStatusEditWindow
    from utils import toQDate

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
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()
        if len(w.db.orders) == 0:
            errors.append("expected fuzz seed to populate orders, got 0")
            return errors

        orderNum = sorted(w.db.orders)[0]
        part = w.db.orders[orderNum].part
        w.db.setPartTruck(part, None)  # deterministic slate: no truck size

        editor = OrderStatusEditWindow(orderNum, w)

        # --- toggle blocks (reverts) with no parts-per-truck set ---
        editor.trucksCheck.setChecked(True)
        if editor.trucksCheck.isChecked():
            errors.append("trucks toggle engaged with no parts-per-truck set (should revert)")

        # --- with an even truck size, the toggle engages + clears/relabels the PRESS
        #     field only; the ship field + its label are untouched (Step 76) ---
        w.db.setPartTruck(part, 20)
        editor.pressEdit.setText("999")  # stale pieces value that must clear on toggle
        editor.shipEdit.setText("77")    # ship is always pieces; must NOT be cleared
        editor.trucksCheck.setChecked(True)
        if not editor.trucksCheck.isChecked():
            errors.append("trucks toggle did not engage with a truck size set")
        if editor.pressEdit.text() != "":
            errors.append(f"toggle should clear the press field; pressEdit={editor.pressEdit.text()!r}")
        if "trucks" not in editor.pressLabel.text():
            errors.append(f"toggle should relabel press to trucks; label={editor.pressLabel.text()!r}")
        if editor.shipEdit.text() != "77":
            errors.append(f"toggle must not clear the ship field; shipEdit={editor.shipEdit.text()!r}")
        if "pieces" not in editor.shipLabel.text() or "trucks" in editor.shipLabel.text():
            errors.append(f"ship label must stay pieces in trucks mode; label={editor.shipLabel.text()!r}")

        # --- 2.5 trucks x 20 = 50 pieces (press converts); ship stays pieces: 1 -> 1,
        #     NOT 1 x 20 (Step 76) ---
        d1 = datetime.date.today() - datetime.timedelta(days=205)
        editor.dateEdit.setDate(toQDate(d1))
        editor.pressEdit.setText("2.5")
        editor.shipEdit.setText("1")
        editor.addButton.click()
        got = w.db.orderStatus[orderNum].snapshots.get(d1)
        if got != (50, 1):
            errors.append(f"trucks conversion (press only): snapshot[{d1}]={got}, want (50, 1)")

        # --- a half-truck of an ODD count is rejected (fractional pieces) ---
        w.db.setPartTruck(part, 15)
        d2 = datetime.date.today() - datetime.timedelta(days=206)
        editor.dateEdit.setDate(toQDate(d2))
        editor.pressEdit.setText("0.5")  # 0.5 * 15 = 7.5 -> reject
        editor.shipEdit.setText("1")
        editor.addButton.click()
        if d2 in w.db.orderStatus[orderNum].snapshots:
            errors.append("half-truck of an odd count stored (should be blocked)")

        # --- a non-0.5-step value is rejected ---
        editor.pressEdit.setText("0.3")
        editor.shipEdit.setText("1")
        editor.addButton.click()
        if d2 in w.db.orderStatus[orderNum].snapshots:
            errors.append("non-0.5-step trucks value stored (should be blocked)")

        # --- selecting a stored snapshot drops to pieces mode + prefills pieces ---
        editor.setSelection([d1.isoformat()])
        if editor.trucksCheck.isChecked():
            errors.append("selecting a snapshot should drop to pieces mode")
        if editor.pressEdit.text() != "50" or "pieces" not in editor.pressLabel.text():
            errors.append(f"snapshot prefill: press={editor.pressEdit.text()!r} "
                          f"label={editor.pressLabel.text()!r}, want pieces 50")
        if editor.shipEdit.text() != "1":
            errors.append(f"snapshot prefill: ship={editor.shipEdit.text()!r}, want pieces 1")
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


def order_report_window_generates() -> list[str]:
    """Step 77 (§13.47): OrderReportWindow generates the orders PDF report.

    Seeds tiny fuzz data, opens the window (the same one the Report button on both the
    Orders and Order Status tabs opens), and asserts:
      - the client / part combos lead with an "All" sentinel (userData None) and carry
        every client / part;
      - the default due-date range spans the dated orders;
      - Generate writes a real %PDF- file (``startfile`` stubbed so nothing opens),
        with details on and a specific status filter;
      - a From-after-To range is rejected (error path, no export).
    """
    import datetime
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import order_report_window as ORW
    from report.sales import ORDER_STATUS_CLOSED
    from utils import toQDate, fromQDate

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    exported: list[str] = []
    origStartfile = ORW.startfile
    ORW.startfile = lambda path: exported.append(path)  # type: ignore[assignment]
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()
        if len(w.db.orders) == 0:
            errors.append("expected fuzz seed to populate orders, got 0")
            return errors

        win = ORW.OrderReportWindow(w)

        # Client / part combos: an "All" sentinel (None) first, then every name.
        if win.clientBox.itemData(0) is not None:
            errors.append("client combo[0] should be the All sentinel (None)")
        if win.clientBox.count() != len(w.db.clients) + 1:
            errors.append(f"client combo has {win.clientBox.count()} entries, "
                          f"want {len(w.db.clients) + 1}")
        if win.partBox.itemData(0) is not None:
            errors.append("part combo[0] should be the All sentinel (None)")
        if win.partBox.count() != len(w.db.parts) + 1:
            errors.append(f"part combo has {win.partBox.count()} entries, "
                          f"want {len(w.db.parts) + 1}")

        # Default due-date range spans the dated orders.
        dues = [o.dueDate for o in w.db.orders.values() if o.dueDate is not None]
        if dues:
            if fromQDate(win.startDateEdit.date()) != min(dues):
                errors.append("default From != earliest due date")
            if fromQDate(win.endDateEdit.date()) != max(dues):
                errors.append("default To != latest due date")

        # Generate: details on + a specific status -> a real %PDF- (startfile stubbed).
        win.detailsCheck.setChecked(True)
        idx = win.statusBox.findData(ORDER_STATUS_CLOSED)
        if idx >= 0:
            win.statusBox.setCurrentIndex(idx)
        before = len(exported)
        win.generate()
        if len(exported) != before + 1:
            errors.append(f"Generate did not call startfile (exported={exported})")
        else:
            path = exported[-1]
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                errors.append("Generate produced empty/missing PDF")
            else:
                with open(path, "rb") as f:
                    if f.read(5) != b"%PDF-":
                        errors.append("Generated PDF lacks %PDF- magic")
                try:
                    os.unlink(path)
                except OSError:
                    pass

        # From-after-To is rejected: a fresh window (generate() closes on success),
        # an inverted range, and no new export.
        win2 = ORW.OrderReportWindow(w)
        win2.startDateEdit.setDate(toQDate(datetime.date(2100, 1, 1)))
        win2.endDateEdit.setDate(toQDate(datetime.date(2000, 1, 1)))
        before = len(exported)
        win2.generate()
        if len(exported) != before:
            errors.append("From-after-To should be rejected (no export)")
    finally:
        ORW.startfile = origStartfile  # type: ignore[assignment]
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def pressers_tab_crud() -> list[str]:
    """Step 44: PressersTab CRUD + save/reload roundtrip + employee-delete cascade.

    Seeds tiny fuzz data (which now populates pressers against existing
    employees), then via ``PresserEditWindow`` and the tab buttons:
      - opens an Edit window on the first presser, confirms the employee
        combo preselects and ``hoursEdit`` prefills, changes the hours,
        clicks ``updateButton``, and confirms ``hoursPerShift`` updates
        while the employeeId key is unchanged;
      - opens a *new* ``PresserEditWindow`` (entry=None), selects an
        employee who isn't yet a presser, enters hours, clicks
        ``createButton``, and confirms it appears;
      - selects that new presser and calls ``deleteSelection`` (the
        confirm dialog is stubbed to Yes), confirming removal;
      - saves, reloads into a fresh ``MainWindow``, and confirms the
        surviving pressers (employeeId -> hoursPerShift) roundtrip
        through SQLite unchanged;
      - deletes an employee who is a presser and confirms the presser
        record is cascaded away (no orphaned FK).
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from pressers_tab import PresserEditWindow

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w.pressersTab.refreshTable()

        if len(w.db.pressers) == 0:
            errors.append("expected fuzz seed to populate pressers, got 0")
            return errors

        # --- Edit: change an existing presser's hours ---
        fixtureId = sorted(w.db.pressers)[0]
        editor = PresserEditWindow(fixtureId, w)
        if editor.employeeCombo.currentData() != fixtureId:
            errors.append(f"Edit prefill: employeeCombo={editor.employeeCombo.currentData()!r}, want {fixtureId!r}")
        if editor.hoursEdit.text() != f"{w.db.pressers[fixtureId].hoursPerShift}":
            errors.append(f"Edit prefill: hoursEdit={editor.hoursEdit.text()!r}, "
                          f"want {w.db.pressers[fixtureId].hoursPerShift!r}")
        editor.hoursEdit.setText("9.5")
        editor.updateButton.click()
        if fixtureId not in w.db.pressers:
            errors.append(f"after Update: presser {fixtureId!r} vanished")
        elif w.db.pressers[fixtureId].hoursPerShift != 9.5:
            errors.append(f"after Update: hoursPerShift={w.db.pressers[fixtureId].hoursPerShift}, want 9.5")

        # --- Stale-key guard: an Update whose original presser id is gone (deleted
        # / reassigned while an Edit window stayed open) must be a no-op, not a
        # KeyError on self.pressers[newId] (Step 60 class; crash_fuzz-found for
        # updatePresser). ---
        absentId = max(w.db.employees, default=0) + 100000
        while absentId in w.db.pressers:
            absentId += 1
        keysBefore = set(w.db.pressers)
        try:
            w.db.updatePresser(absentId, absentId + 1)
        except Exception as e:  # the whole point is that this must not raise
            errors.append(f"updatePresser on a missing original id raised {type(e).__name__}: {e}")
        if set(w.db.pressers) != keysBefore:
            errors.append(f"updatePresser on a missing original id changed the key set: "
                          f"{sorted(w.db.pressers)} vs {sorted(keysBefore)}")

        # --- Create a new presser on an employee who isn't one yet ---
        freeId = next((e for e in w.db.employees if e not in w.db.pressers), None)
        if freeId is None:
            errors.append("expected at least one non-presser employee in tiny seed")
            return errors
        newEditor = PresserEditWindow(None, w)
        for i in range(newEditor.employeeCombo.count()):
            if newEditor.employeeCombo.itemData(i) == freeId:
                newEditor.employeeCombo.setCurrentIndex(i)
                break
        newEditor.hoursEdit.setText("7.0")
        newEditor.createButton.click()
        if freeId not in w.db.pressers:
            errors.append(f"after Create: presser {freeId!r} missing from db.pressers")
        elif w.db.pressers[freeId].hoursPerShift != 7.0:
            errors.append(f"after Create: hoursPerShift={w.db.pressers[freeId].hoursPerShift}, want 7.0")

        # --- Delete that presser via the tab (confirm dialog stubbed to Yes) ---
        before = len(w.db.pressers)
        w.pressersTab.setSelection([_presserLabelFor(w.db, freeId)])
        w.pressersTab.deleteSelection()
        if freeId in w.db.pressers:
            errors.append(f"after Delete: presser {freeId!r} still present")
        if len(w.db.pressers) != before - 1:
            errors.append(f"after Delete: count {len(w.db.pressers)} != {before - 1}")

        # --- save / reload roundtrip ---
        expected = {e: p.hoursPerShift for e, p in w.db.pressers.items()}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading pressers DB")
        else:
            w2.fileManager.loadFile()
            got = {e: p.hoursPerShift for e, p in w2.db.pressers.items()}
            if got != expected:
                errors.append(f"pressers roundtrip mismatch: expected {expected}, got {got}")

        # --- deleting an employee via the Employee List tab cascades the presser
        #     FK *and* re-renders the Pressers tab (drives the real UI path, not
        #     db.delEmployee directly, so a missing tab refresh is caught here). ---
        if w.db.pressers:
            victim = sorted(w.db.pressers)[0]
            emp = w.db.employees[victim]
            subTab = (w.employeesTab.activeEmployeesTab if emp.status
                      else w.employeesTab.inactiveEmployeesTab)
            subTab.setSelection([victim])
            subTab.deleteSelection()  # confirm dialog stubbed to Yes
            if victim in w.db.pressers:
                errors.append(f"after delete of employee {victim}: presser FK not cascaded")
            if victim in w.pressersTab._idByLabel.values():
                errors.append(f"after delete of employee {victim}: Pressers tab not refreshed (stale row)")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def _presserLabelFor(db, employeeId):
    # Mirror PressersTab's column-0 label so the test can drive setSelection,
    # which maps labels back to employeeIds.
    from pressers_tab import _presserLabel
    return _presserLabel(db, employeeId)


def employee_reid_cascades() -> list[str]:
    """Step 59: changing an employee's idNum cascades to their presser row and
    production records (the FKs follow the re-id instead of orphaning).

    ``db.updateEmployee`` rekeys the HR sub-DBs but historically missed pressers
    (keyed by employeeId, stored as ``Presser.employeeId``) and production (keyed
    by a tuple beginning with employeeId). A re-id keeps the employee alive, so —
    unlike ``delEmployee``, which intentionally leaves production as a
    ``(missing #id)`` tombstone — both must follow or they silently orphan. The
    crash-fuzz stale-view net can't catch this (an orphan reads identically in
    the view and a fresh recompute), so this is its only automated guard.

    Drives the real ``EmployeeEditWindow`` re-id (which also re-exercises the
    Step 56 downstream refresh), then asserts the presser + production moved and
    that the move survives a save/reload roundtrip.
    """
    import datetime
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from employees_tab import EmployeeEditWindow
    from records.production import ProductionRecord

    errors = []
    QApplication.instance() or QApplication(sys.argv)
    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        if not w.db.pressers:
            errors.append("expected fuzz seed to populate pressers, got 0")
            return errors

        oldId = sorted(w.db.pressers)[0]
        emp = w.db.employees[oldId]
        # The tiny seed doesn't populate production, so add a couple rows for the
        # victim to exercise the production half of the cascade.
        for d, tgt in ((datetime.date(2026, 1, 5), "pA"), (datetime.date(2026, 1, 6), "pB")):
            rec = ProductionRecord()
            rec.setRecord(oldId, d, emp.shift or 1, "Pressing", tgt, 100, 5, 8.0)
            w.db.production[rec.key()] = rec
        # Give the victim a presser-press preference too (Step 65) — it's keyed by
        # employeeId just like the presser row, so a re-id must move it or it orphans.
        if not w.db.presses:
            errors.append("expected fuzz seed to populate presses, got 0")
            return errors
        prefPress = sorted(w.db.presses)[0]
        w.db.setPresserPressScore(oldId, prefPress, 5)
        newId = max(w.db.employees) + 1  # strictly greater than all -> guaranteed free

        # Re-id through the real edit dialog (Update on the existing employee).
        editor = EmployeeEditWindow(oldId, w, emp.status)
        editor.idEdit.setText(str(newId))
        editor.updateButton.click()

        # --- in-memory cascade ---
        if oldId in w.db.employees:
            errors.append(f"re-id: old employee {oldId} still present")
        if newId not in w.db.employees:
            errors.append(f"re-id: new employee {newId} missing (re-id didn't happen)")
            return errors
        if oldId in w.db.pressers or newId not in w.db.pressers:
            errors.append(f"presser FK didn't follow re-id: oldIn={oldId in w.db.pressers}, "
                          f"newIn={newId in w.db.pressers}")
        elif w.db.pressers[newId].employeeId != newId:
            errors.append(f"presser.employeeId={w.db.pressers[newId].employeeId}, want {newId}")
        oldProd = sum(1 for r in w.db.production.values() if r.employeeId == oldId)
        newProd = sum(1 for r in w.db.production.values() if r.employeeId == newId)
        if oldProd != 0 or newProd != 2:
            errors.append(f"production didn't follow re-id: old={oldProd}, new={newProd} (want 0, 2)")
        if any(k[0] != r.employeeId for k, r in w.db.production.items()):
            errors.append("production dict key out of sync with rec.employeeId after re-id")
        # presser-press preference must follow the re-id too (Step 65).
        if oldId in w.db.presserPressPref or newId not in w.db.presserPressPref:
            errors.append(f"presser-press pref didn't follow re-id: oldIn={oldId in w.db.presserPressPref}, "
                          f"newIn={newId in w.db.presserPressPref}")
        elif (w.db.presserPressPref[newId].employeeId != newId
              or w.db.presserPressPref[newId].getScore(prefPress) != 5):
            errors.append(f"presser-press pref not intact after re-id: "
                          f"{w.db.presserPressPref[newId].scores}")

        # --- save / reload roundtrip (the rekey must persist) ---
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading re-id DB")
        else:
            w2.fileManager.loadFile()
            if newId not in w2.db.pressers or oldId in w2.db.pressers:
                errors.append(f"roundtrip presser: newIn={newId in w2.db.pressers}, "
                              f"oldIn={oldId in w2.db.pressers}")
            rNew = sum(1 for r in w2.db.production.values() if r.employeeId == newId)
            rOld = sum(1 for r in w2.db.production.values() if r.employeeId == oldId)
            if rNew != 2 or rOld != 0:
                errors.append(f"roundtrip production: new={rNew}, old={rOld} (want 2, 0)")
            got = w2.db.presserPressPref.get(newId)
            if oldId in w2.db.presserPressPref or got is None or got.getScore(prefPress) != 5:
                errors.append(f"roundtrip presser-press pref: newIn={newId in w2.db.presserPressPref}, "
                              f"oldIn={oldId in w2.db.presserPressPref}, scores={got and got.scores}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors


def shift_workweek_roundtrip() -> list[str]:
    """Step 45: WorkweekTab grid toggles + save/reload roundtrip.

    Seeds tiny fuzz data (which now seeds Mon-Fri for all three shifts), then
    drives the WorkweekTab checkbox grid the way a user would:
      - asserts every checkbox state matches db.shiftWorkweek after refresh;
      - unchecks a working day and confirms db.setShiftWorkday cleared it;
      - checks a non-working day (Sunday) and confirms it was added;
      - clears every day of one shift and confirms that shift drops out of
        db.shiftWorkweek entirely (the presence-row invariant — no empty entry);
      - saves, reloads into a fresh MainWindow, and confirms the workweek
        roundtrips through SQLite unchanged (exercises the row-level orphan
        sweep on the cleared days / dropped shift).
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records.scheduling import SHIFTS

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = w2 = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w.workweekTab.refreshTable()

        tab = w.workweekTab
        db = w.db
        if len(db.shiftWorkweek) == 0:
            errors.append("expected fuzz seed to populate shift workweek, got 0 shifts")
            return errors

        # --- grid mirrors db after refresh ---
        for shift in SHIFTS:
            working = db.shiftWorkweek[shift].days if shift in db.shiftWorkweek else set()
            for weekday, chk in tab.checks[shift].items():
                if chk.isChecked() != (weekday in working):
                    errors.append(f"grid/db mismatch shift {shift} weekday {weekday}: "
                                  f"checkbox={chk.isChecked()} db={weekday in working}")

        # Preconditions from the deterministic Mon-Fri seed.
        if 1 not in db.shiftWorkweek or 0 not in db.shiftWorkweek[1].days:
            errors.append("precondition: expected shift 1 to work Monday (weekday 0) after seed")
            return errors

        # --- uncheck Monday (weekday 0) on shift 1 via the checkbox (toggled -> db) ---
        tab.checks[1][0].setChecked(False)
        if 1 in db.shiftWorkweek and 0 in db.shiftWorkweek[1].days:
            errors.append("after uncheck: shift 1 Monday still set in db")

        # --- check Sunday (weekday 6) on shift 2 via the checkbox ---
        tab.checks[2][6].setChecked(True)
        if 2 not in db.shiftWorkweek or 6 not in db.shiftWorkweek[2].days:
            errors.append("after check: shift 2 Sunday not set in db")

        # --- clear every day of shift 3: the whole entry should drop out ---
        for weekday in range(7):
            tab.checks[3][weekday].setChecked(False)
        if 3 in db.shiftWorkweek:
            errors.append(f"after clearing all days: shift 3 still in db.shiftWorkweek "
                          f"(days={db.shiftWorkweek[3].days})")

        # --- save / reload roundtrip ---
        expected = {s: set(ww.days) for s, ww in db.shiftWorkweek.items()}
        w.fileManager.saveFile()
        if w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()

        w2 = MainWindow()
        if not w2.fileManager.setFile(tmp.name):
            errors.append("setFile returned False when reloading workweek DB")
        else:
            w2.fileManager.loadFile()
            got = {s: set(ww.days) for s, ww in w2.db.shiftWorkweek.items()}
            if got != expected:
                errors.append(f"shift workweek roundtrip mismatch: expected {expected}, got {got}")
    finally:
        restore()
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        if w2 is not None and w2.fileManager.dbFile is not None:
            w2.fileManager.dbFile.close()
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


def schedule_tab_generates() -> list[str]:
    """Step 53/66/67/71: ScheduleTab generates, groups, filters, exports, clears.

    Seeds tiny fuzz data, then drives the on-screen Schedule report:
      - Generate makes ``displayed`` equal a direct ``schedule()`` call (the tab
        is a thin view over the stateless seam), enables Export + the filter
        controls, and updates the status line;
      - the grouped render (Step 67) has one mini-table per (date, shift) group,
        and their rows union back to the full displayed schedule with no loss;
      - the unified filter (Step 71) is built into the display: choosing a shift
        live-slices ``displayed`` to match ``filterSchedule()`` while flagged
        orders still show in full (design call), and updates the status line;
      - Export writes exactly what's on screen — both the current (filtered)
        slice and the reset-to-full view produce real %PDF- files (``startfile``
        stubbed so nothing opens);
      - the flags/warnings are condensed to summary labels + detail buttons
        (Step 72): the button is enabled iff there's something to show and
        opening the detail window doesn't crash;
      - ``refresh()`` (the DB-open hook) clears the result/displayed, empties the
        group tables + flag data, and re-disables Export + the filter controls so
        a schedule from a prior file never lingers.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    import schedule_tab as ST
    import scheduling as S

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    restore = _silenceMessageBoxes()
    exported: list[str] = []
    origStartfile = ST.startfile
    ST.startfile = lambda path: exported.append(path)  # type: ignore[assignment]
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors
        _seedTinyFuzzDB(w)
        w._refreshAllTabs()

        tab = w.scheduleTab
        if tab.result is not None or tab.displayed is not None:
            errors.append("expected result/displayed None before first Generate")
        if tab.exportB.isEnabled():
            errors.append("Export should be disabled before first Generate")
        if tab.shiftCombo.isEnabled():
            errors.append("filter controls should be disabled before first Generate")

        # --- Generate: displayed must equal a direct schedule() at full horizon ---
        tab.horizonSpin.setValue(S.MAX_HORIZON_DAYS)
        tab.generate()
        if tab.result is None or tab.displayed is None:
            errors.append("result/displayed is None after Generate")
            return errors
        expected = S.schedule(w.db, None, S.ScheduleConfig(maxHorizonDays=S.MAX_HORIZON_DAYS))
        if tab.displayed.rows != expected.rows:
            errors.append("displayed rows != schedule() rows after Generate")
        if len(tab._flagData) != len(expected.flags):
            errors.append(f"flag data rows={len(tab._flagData)} "
                          f"!= schedule() flags={len(expected.flags)}")
        # Step 72: flags/warnings are condensed to summary labels + detail buttons.
        # The button is enabled iff there's something to show; the summary text
        # leads with the count; opening the detail windows doesn't crash.
        if (len(expected.flags) > 0) != tab.flagsButton.isEnabled():
            errors.append("Flagged Orders button enabled-state doesn't match flag count")
        if not tab.flagsSummary.text().startswith(f"{len(expected.flags)} order"):
            errors.append(f"flags summary text wrong: {tab.flagsSummary.text()!r}")
        tab._openFlags()
        tab._openWarnings()
        if not tab.exportB.isEnabled():
            errors.append("Export should be enabled after Generate")
        if not tab.shiftCombo.isEnabled():
            errors.append("filter controls should be enabled after Generate")
        if not tab.statusLabel.text().startswith("Generated "):
            errors.append(f"status not updated after Generate: {tab.statusLabel.text()!r}")

        # Grouped render: one mini-table per (date, shift) group, and the union of
        # their rows equals the displayed schedule (no rows lost in the regroup).
        groups = S.groupScheduleRows(tab.displayed.rows)
        if len(tab._groupTables) != len(groups):
            errors.append(f"group tables={len(tab._groupTables)} != groups={len(groups)}")
        renderedRows = sum(len(t.dbModel._data) for t in tab._groupTables)
        if renderedRows != len(tab.displayed.rows):
            errors.append(f"rendered group rows={renderedRows} != displayed rows={len(tab.displayed.rows)}")
        # Each rendered row lands on a real press / real part (grouped table is
        # Press/Part/Quantity/Press-hours/Presser -> cols 0/1).
        for t in tab._groupTables:
            for row in t.dbModel._data:
                if row[0] not in w.db.presses:
                    errors.append(f"schedule row on unknown press: {row[0]!r}")
                if row[1] not in w.db.parts:
                    errors.append(f"schedule row on unknown part: {row[1]!r}")

        # --- Filtered view: the date range is built into the display, so choosing
        # a shift live-slices the shown schedule (Step 71) ---
        if expected.rows:
            targetShift = expected.rows[0].shift
            idx = tab.shiftCombo.findData(targetShift)
            if idx >= 0:
                tab.shiftCombo.setCurrentIndex(idx)
            tab._applyFilter()
            shift, start, end = tab._filterArgs()
            wantFiltered = S.filterSchedule(tab.result, shift, start, end)
            if tab.displayed.rows != wantFiltered.rows:
                errors.append("displayed rows != filterSchedule() rows after live filter")
            if not all(r.shift == targetShift for r in tab.displayed.rows):
                errors.append("filtered view contains rows from other shifts")
            if not tab.statusLabel.text().startswith("Filtered view"):
                errors.append(f"status not updated after live filter: {tab.statusLabel.text()!r}")
            # Flags are order-level -> shown in full even when filtered (design call).
            if len(tab._flagData) != len(tab.result.flags):
                errors.append("filtered view dropped flagged orders (should show in full)")

        # --- Export writes exactly what's on screen (Step 71): both the current
        # (filtered, if the block above ran) slice and the reset-to-full view
        # produce real %PDF- files (startfile stubbed so nothing opens) ---
        def _checkExport(label):
            before = len(exported)
            tab.exportPdf()
            if len(exported) != before + 1:
                errors.append(f"{label} export did not call startfile (exported={exported})")
                return
            path = exported[-1]
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                errors.append(f"{label} export produced empty/missing PDF")
                return
            with open(path, "rb") as f:
                if f.read(5) != b"%PDF-":
                    errors.append(f"{label} export PDF lacks %PDF- magic")
            try:
                os.unlink(path)
            except OSError:
                pass

        _checkExport("current view")
        tab.shiftCombo.setCurrentIndex(0)  # back to All shifts / full range
        tab._applyFilter()
        _checkExport("full")

        # --- refresh() (DB-open hook) clears everything ---
        tab.refresh()
        if tab.result is not None or tab.displayed is not None:
            errors.append("refresh did not clear result/displayed")
        if tab._groupTables or tab._flagData:
            errors.append("refresh did not clear the schedule groups / flag data")
        if tab.exportB.isEnabled() or tab.shiftCombo.isEnabled():
            errors.append("refresh did not re-disable Export / filter controls")
    finally:
        ST.startfile = origStartfile  # type: ignore[assignment]
        restore()
        for p in exported:
            try:
                os.unlink(p)
            except OSError:
                pass
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
    return errors
