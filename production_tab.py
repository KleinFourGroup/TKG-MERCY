import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QMessageBox, QCalendarWidget, QComboBox, QDateEdit,
)
from PySide6.QtCore import Qt

from table import DBTable
from app import MainWindow
from records import ProductionRecord
from defaults import (
    PRODUCTION_ACTIONS, PRODUCTION_ACTION_TARGET, PRODUCTION_TARGET_UNIT,
)
from error import errorMessage
from utils import (
    widgetFromList, checkInput, toQDate, fromQDate, centerOnScreen,
)


def _employeeLabel(emp):
    return f"{emp.lastName.upper()} {emp.firstName} ({emp.idNum})"


class ProductionTab(QWidget):
    # Full-width tab listing shift-level production records with filter-by-employee +
    # date range. Reports live in Step 12, so this is edit/browse only.
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp

        today = datetime.date.today()
        # Default range: last 30 days through today — matches how the floor would
        # normally scan "recent" entries.
        self.filterStart: datetime.date = today - datetime.timedelta(days=30)
        self.filterEnd: datetime.date = today
        self.filterEmployeeId: int | None = None  # None == all employees

        self.employeeFilter = QComboBox()
        self.employeeFilter.setEditable(False)
        self.employeeFilter.currentIndexChanged.connect(self._onEmployeeFilterChanged)

        self.startDateEdit = QDateEdit()
        self.startDateEdit.setCalendarPopup(True)
        self.startDateEdit.setDisplayFormat("yyyy-MM-dd")
        self.startDateEdit.setDate(toQDate(self.filterStart))
        self.startDateEdit.dateChanged.connect(self._onDateFilterChanged)

        self.endDateEdit = QDateEdit()
        self.endDateEdit.setCalendarPopup(True)
        self.endDateEdit.setDisplayFormat("yyyy-MM-dd")
        self.endDateEdit.setDate(toQDate(self.filterEnd))
        self.endDateEdit.dateChanged.connect(self._onDateFilterChanged)

        filterLayout = QHBoxLayout()
        filterLayout.addWidget(QLabel("Employee:"))
        filterLayout.addWidget(self.employeeFilter)
        filterLayout.addWidget(QLabel("From:"))
        filterLayout.addWidget(self.startDateEdit)
        filterLayout.addWidget(QLabel("To:"))
        filterLayout.addWidget(self.endDateEdit)

        # Synthetic "#" column at index 0 holds a row-id string that DBTable reports
        # via setSelection. The composite 6-tuple key lives in self._keyByRowId,
        # rebuilt in genTableData.
        self._keyByRowId: dict[str, tuple] = {}
        self._populateEmployeeFilter()
        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection: list[tuple] = []  # list of 6-tuple keys
        self.selectLabel = QLabel("Selection: N/A")

        self.newB = QPushButton("New Production")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Production")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Production")
        self.deleteB.clicked.connect(self.deleteProduction)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)

        layout = QVBoxLayout()
        layout.addLayout(filterLayout)
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(barLayout)
        self.setLayout(layout)

        self._setButtonsEnabled()

    def _populateEmployeeFilter(self):
        # Build (All employees) + one entry per employee (active first, then inactive).
        self.employeeFilter.blockSignals(True)
        self.employeeFilter.clear()
        self.employeeFilter.addItem("(All employees)", userData=None)
        emps = list(self.mainApp.db.employees.values())
        emps.sort(key=lambda e: (0 if e.status else 1,
                                 (e.lastName or "").lower(),
                                 (e.firstName or "").lower()))
        for emp in emps:
            suffix = "" if emp.status else " [inactive]"
            self.employeeFilter.addItem(_employeeLabel(emp) + suffix, userData=emp.idNum)
        # Re-select the previously filtered employee if it still exists.
        if self.filterEmployeeId is not None:
            for i in range(self.employeeFilter.count()):
                if self.employeeFilter.itemData(i) == self.filterEmployeeId:
                    self.employeeFilter.setCurrentIndex(i)
                    break
            else:
                self.filterEmployeeId = None
                self.employeeFilter.setCurrentIndex(0)
        self.employeeFilter.blockSignals(False)

    def _onEmployeeFilterChanged(self, _idx: int):
        self.filterEmployeeId = self.employeeFilter.currentData()
        self.refresh()

    def _onDateFilterChanged(self, _qd):
        self.filterStart = fromQDate(self.startDateEdit.date())
        self.filterEnd = fromQDate(self.endDateEdit.date())
        self.refresh()

    def genTableData(self):
        self.headers = ["#", "Employee", "Date", "Shift", "Action",
                        "Target", "Quantity", "Unit", "Scrap"]
        self._keyByRowId = {}
        rows = []
        recs = list(self.mainApp.db.production.values())

        def _include(rec: ProductionRecord) -> bool:
            if rec.date is None:
                return False
            if rec.date < self.filterStart or rec.date > self.filterEnd:
                return False
            if self.filterEmployeeId is not None and rec.employeeId != self.filterEmployeeId:
                return False
            return True

        recs = [r for r in recs if _include(r)]
        recs.sort(key=lambda r: (r.date, r.shift if r.shift is not None else 0,
                                 r.employeeId if r.employeeId is not None else 0,
                                 r.action or "", r.targetName or ""))

        for i, rec in enumerate(recs):
            rowId = str(i + 1)
            if rec.employeeId in self.mainApp.db.employees:
                empStr = _employeeLabel(self.mainApp.db.employees[rec.employeeId])
            else:
                empStr = f"(missing #{rec.employeeId})"
            unit = PRODUCTION_TARGET_UNIT.get(rec.targetType or "", "")
            rows.append([
                rowId,
                empStr,
                rec.date.isoformat() if rec.date else "",
                str(rec.shift) if rec.shift is not None else "",
                rec.action or "",
                rec.targetName or "",
                f"{rec.quantity}" if rec.quantity is not None else "",
                unit,
                f"{rec.scrapQuantity}",
            ])
            self._keyByRowId[rowId] = rec.key()
        self.tableData = rows

    def setSelection(self, selection):
        # DBTable hands back the row-id strings from column 0. Map them to record keys
        # so subsequent edit/delete calls don't have to reinterpret the table rows.
        self.selection = [self._keyByRowId[rid] for rid in selection if rid in self._keyByRowId]
        if self.selection:
            self.selectLabel.setText(f"Selection: {len(self.selection)} record(s)")
        else:
            self.selectLabel.setText("Selection: N/A")
        self._setButtonsEnabled()

    def _setButtonsEnabled(self):
        hasEmployees = len(self.mainApp.db.employees) > 0
        hasParts = len(self.mainApp.db.parts) > 0
        hasMixes = len(self.mainApp.db.mixtures) > 0
        self.newB.setEnabled(hasEmployees and (hasParts or hasMixes))
        self.editB.setEnabled(len(self.selection) > 0)
        self.deleteB.setEnabled(len(self.selection) > 0)

    def openNew(self):
        if len(self.mainApp.db.employees) == 0:
            errorMessage(self.mainApp, ["Cannot record production: no employees in the database."])
            return
        if len(self.mainApp.db.parts) == 0 and len(self.mainApp.db.mixtures) == 0:
            errorMessage(self.mainApp, ["Cannot record production: no parts or mixtures in the database."])
            return
        ProductionEditWindow(self, None, self.mainApp)

    def openEdits(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No production records selected."])
            return
        for key in self.selection:
            if key not in self.mainApp.db.production:
                errorMessage(self.mainApp, [f"Production record {key} no longer exists."])
                continue
            ProductionEditWindow(self, self.mainApp.db.production[key], self.mainApp)

    def deleteProduction(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No production records selected."])
            return
        confirm = QMessageBox.question(
            self, "Delete production?",
            f"Are you sure you want to delete {len(self.selection)} production record(s)?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for key in self.selection:
            if key in self.mainApp.db.production:
                del self.mainApp.db.production[key]
        QMessageBox.information(self.mainApp, "Success", "Production record(s) deleted.")
        self.refresh()

    def refresh(self):
        self._populateEmployeeFilter()
        self.genTableData()
        self.table.setData(self.tableData)
        self.selection = [k for k in self.selection if k in self.mainApp.db.production]
        self.setSelection([rid for rid, key in self._keyByRowId.items() if key in self.selection])
        self._setButtonsEnabled()


class ProductionEditWindow(QWidget):
    # Edit window for a single ProductionRecord. Action drives targetType (via
    # defaults.PRODUCTION_ACTION_TARGET), which in turn drives the target dropdown
    # and unit label.
    def __init__(self, parentTab: ProductionTab, record: ProductionRecord | None,
                 mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.parentTab = parentTab
        self.record = record
        self.isNew = record is None

        if self.isNew:
            self.setWindowTitle("Production: New")
        else:
            self.setWindowTitle(
                f"Production: {record.date.isoformat()} "  # type: ignore[union-attr]
                f"s{record.shift} {record.action} {record.targetName}"  # type: ignore[union-attr]
            )

        # --- employee dropdown ---
        self.employeeBox = QComboBox()
        self.employeeBox.setEditable(False)
        emps = list(self.mainApp.db.employees.values())
        emps.sort(key=lambda e: (0 if e.status else 1,
                                 (e.lastName or "").lower(),
                                 (e.firstName or "").lower()))
        for emp in emps:
            suffix = "" if emp.status else " [inactive]"
            self.employeeBox.addItem(_employeeLabel(emp) + suffix, userData=emp.idNum)
        if not self.isNew and record is not None:
            for i in range(self.employeeBox.count()):
                if self.employeeBox.itemData(i) == record.employeeId:
                    self.employeeBox.setCurrentIndex(i)
                    break

        # --- date ---
        self.calendar = QCalendarWidget()
        if not self.isNew and record is not None and record.date is not None:
            self.calendar.setSelectedDate(toQDate(record.date))

        # --- shift ---
        self.shiftBox = QComboBox()
        self.shiftBox.setEditable(False)
        self.shiftBox.addItems(["1", "2", "3"])
        if not self.isNew and record is not None and record.shift is not None:
            self.shiftBox.setCurrentText(str(record.shift))

        # --- action -> cascades target dropdown and unit label ---
        self.actionBox = QComboBox()
        self.actionBox.setEditable(False)
        self.actionBox.addItems(PRODUCTION_ACTIONS)
        self.actionBox.currentTextChanged.connect(self._onActionChanged)

        self.targetBox = QComboBox()
        self.targetBox.setEditable(False)

        self.unitLabel = QLabel("Unit: —")

        # --- quantities ---
        self.quantityEdit = QLineEdit()
        if not self.isNew and record is not None and record.quantity is not None:
            self.quantityEdit.setText(f"{record.quantity}")

        self.scrapEdit = QLineEdit()
        # Default scrap to 0 on new entries (§12.5(b)); preserve stored value on edit.
        if not self.isNew and record is not None:
            self.scrapEdit.setText(f"{record.scrapQuantity}")
        else:
            self.scrapEdit.setText("0")

        # Seed the action dropdown — this also populates targetBox + unitLabel via the
        # cascade. On edit we want the record's saved action/target, so set action
        # explicitly and then override the target selection.
        if not self.isNew and record is not None and record.action in PRODUCTION_ACTIONS:
            self.actionBox.setCurrentText(record.action)
        else:
            self.actionBox.setCurrentIndex(0)
        self._onActionChanged(self.actionBox.currentText())
        if not self.isNew and record is not None and record.targetName:
            idx = self.targetBox.findText(record.targetName)
            if idx >= 0:
                self.targetBox.setCurrentIndex(idx)

        self.mainLayout = [
            [QLabel("Employee:"), self.employeeBox],
            [QLabel("Date:"), self.calendar],
            [QLabel("Shift:"), self.shiftBox],
            [QLabel("Action:"), self.actionBox],
            [QLabel("Target:"), self.targetBox],
            [self.unitLabel],
            [QLabel("Quantity:"), self.quantityEdit],
            [QLabel("Scrap:"), self.scrapEdit],
            [QPushButton("Update"), QPushButton("Create")],
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.mainLayout[-1][0].clicked.connect(self.updateRecord)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newRecord)
        centerOnScreen(self)
        self.show()

    def _onActionChanged(self, actionText: str):
        targetType = PRODUCTION_ACTION_TARGET.get(actionText)
        self.targetBox.clear()
        if targetType == "mix":
            names = sorted(self.mainApp.db.mixtures.keys())
        elif targetType == "part":
            names = sorted(self.mainApp.db.parts.keys())
        else:
            names = []
        self.targetBox.addItems(names)
        unit = PRODUCTION_TARGET_UNIT.get(targetType or "", "")
        self.unitLabel.setText(f"Unit: {unit}" if unit else "Unit: —")

    def readData(self, isNew: bool) -> bool:
        errors: list[str] = []

        empId = self.employeeBox.currentData()
        if empId is None:
            errors.append("No employee selected.")
        elif empId not in self.mainApp.db.employees:
            errors.append(f"Employee {empId} no longer exists.")

        date = fromQDate(self.calendar.selectedDate())

        shiftText = self.shiftBox.currentText()
        try:
            shift = int(shiftText)
        except ValueError:
            errors.append(f"Invalid shift: {shiftText!r}")
            shift = 0

        action = self.actionBox.currentText()
        if action not in PRODUCTION_ACTIONS:
            errors.append(f"Unknown action: {action!r}")
        targetType = PRODUCTION_ACTION_TARGET.get(action, "")
        targetName = self.targetBox.currentText()
        if not targetName:
            errors.append("No target selected.")
        else:
            if targetType == "mix" and targetName not in self.mainApp.db.mixtures:
                errors.append(f"Mixture {targetName!r} no longer exists.")
            if targetType == "part" and targetName not in self.mainApp.db.parts:
                errors.append(f"Part {targetName!r} no longer exists.")

        quantity = checkInput(self.quantityEdit.text(), float, "nonneg", errors, "Quantity")
        scrap = checkInput(self.scrapEdit.text(), float, "nonneg", errors, "Scrap")

        if errors:
            errorMessage(self, errors)
            return False

        newKey = (empId, date, shift, targetType, targetName, action)

        # UNIQUE(employeeId, date, shift, targetType, targetName, action): block
        # conflicts up front so the user gets a readable message rather than an
        # INSERT OR REPLACE that silently clobbers a neighbor.
        if isNew:
            if newKey in self.mainApp.db.production:
                errorMessage(self, [
                    "A production record with these employee/date/shift/action/target "
                    "values already exists."
                ])
                return False
        else:
            if self.record is None:
                raise RuntimeError('self.record is None on edit')
            oldKey = self.record.key()
            if newKey != oldKey and newKey in self.mainApp.db.production:
                errorMessage(self, [
                    "Another production record already has these employee/date/shift/"
                    "action/target values."
                ])
                return False

        if isNew:
            rec = ProductionRecord()
            rec.setRecord(empId, date, shift, action, targetName, quantity, scrap)
            self.mainApp.db.production[rec.key()] = rec
        else:
            if self.record is None:
                raise RuntimeError('self.record is None on edit')
            oldKey = self.record.key()
            if oldKey in self.mainApp.db.production:
                del self.mainApp.db.production[oldKey]
            self.record.setRecord(empId, date, shift, action, targetName, quantity, scrap)
            self.mainApp.db.production[self.record.key()] = self.record

        self.parentTab.refresh()
        return True

    def newRecord(self):
        if self.readData(True):
            QMessageBox.information(self, "Success", "Production record added!")
            self.close()

    def updateRecord(self):
        if self.readData(False):
            QMessageBox.information(self, "Success", "Production record updated!")
            self.close()
