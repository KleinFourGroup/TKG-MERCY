"""UI-path checks: production-tab refresh on employee delete, the batch
entry dialog roundtrip, QSettings last-DB reopen, and the close-event
Save / Don't Save / Cancel prompt."""
import os
import sys
import tempfile
from datetime import date as datetime_date


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
