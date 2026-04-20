import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QMessageBox, QCalendarWidget, QComboBox, QDateEdit, QScrollArea,
)
from PySide6.QtCore import Qt

from table import DBTable
from app import MainWindow
from records import ProductionRecord
from defaults import (
    PRODUCTION_ACTIONS, PRODUCTION_ACTION_TARGET, PRODUCTION_TARGET_UNIT,
)
from error import errorMessage
from report import PDFReport
from utils import (
    widgetFromList, checkInput, toQDate, fromQDate, startfile, tempReportPath, centerOnScreen,
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

        self.newB = QPushButton("Quick Entry")
        self.newB.clicked.connect(self.openNew)
        self.batchB = QPushButton("Batch Entry")
        self.batchB.clicked.connect(self.openBatch)
        self.editB = QPushButton("Edit Production")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Production")
        self.deleteB.clicked.connect(self.deleteProduction)
        self.reportB = QPushButton("Generate Report")
        self.reportB.clicked.connect(self.openReport)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.batchB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)
        barLayout.addWidget(self.reportB)

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
        canEnter = hasEmployees and (hasParts or hasMixes)
        self.newB.setEnabled(canEnter)
        self.batchB.setEnabled(canEnter)
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

    def openBatch(self):
        if len(self.mainApp.db.employees) == 0:
            errorMessage(self.mainApp, ["Cannot record production: no employees in the database."])
            return
        if len(self.mainApp.db.parts) == 0 and len(self.mainApp.db.mixtures) == 0:
            errorMessage(self.mainApp, ["Cannot record production: no parts or mixtures in the database."])
            return
        ProductionBatchDialog(self, self.mainApp)

    def openEdits(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No production records selected."])
            return
        for key in self.selection:
            if key not in self.mainApp.db.production:
                errorMessage(self.mainApp, [f"Production record {key} no longer exists."])
                continue
            ProductionEditWindow(self, self.mainApp.db.production[key], self.mainApp)

    def openReport(self):
        ProductionReportWindow(self, self.mainApp,
                               self.filterEmployeeId, self.filterStart, self.filterEnd)

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


class ProductionReportWindow(QWidget):
    # Single dialog for all four production reports. Conditional fields are
    # shown/hidden based on the selected report type so the user only sees the
    # inputs that report needs.
    REPORT_TYPES = [
        "Production Summary",
        "Per Action",
        "Per Target",
        "Per Employee",
    ]

    def __init__(self, parentTab: ProductionTab, mainApp: MainWindow,
                 initialEmployeeId: int | None,
                 initialStart: datetime.date, initialEnd: datetime.date):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.parentTab = parentTab
        self.setWindowTitle("Production Report")

        self.typeBox = QComboBox()
        self.typeBox.setEditable(False)
        self.typeBox.addItems(self.REPORT_TYPES)
        self.typeBox.currentTextChanged.connect(self._onTypeChanged)

        self.startDateEdit = QDateEdit()
        self.startDateEdit.setCalendarPopup(True)
        self.startDateEdit.setDisplayFormat("yyyy-MM-dd")
        self.startDateEdit.setDate(toQDate(initialStart))

        self.endDateEdit = QDateEdit()
        self.endDateEdit.setCalendarPopup(True)
        self.endDateEdit.setDisplayFormat("yyyy-MM-dd")
        self.endDateEdit.setDate(toQDate(initialEnd))

        self.actionBox = QComboBox()
        self.actionBox.setEditable(False)
        self.actionBox.addItems(PRODUCTION_ACTIONS)

        self.targetTypeBox = QComboBox()
        self.targetTypeBox.setEditable(False)
        self.targetTypeBox.addItem("Mixture", userData="mix")
        self.targetTypeBox.addItem("Part", userData="part")
        self.targetTypeBox.currentIndexChanged.connect(self._onTargetTypeChanged)

        self.targetNameBox = QComboBox()
        self.targetNameBox.setEditable(False)

        self.employeeBox = QComboBox()
        self.employeeBox.setEditable(False)
        emps = list(self.mainApp.db.employees.values())
        emps.sort(key=lambda e: (0 if e.status else 1,
                                 (e.lastName or "").lower(),
                                 (e.firstName or "").lower()))
        for emp in emps:
            suffix = "" if emp.status else " [inactive]"
            self.employeeBox.addItem(_employeeLabel(emp) + suffix, userData=emp.idNum)
        if initialEmployeeId is not None:
            for i in range(self.employeeBox.count()):
                if self.employeeBox.itemData(i) == initialEmployeeId:
                    self.employeeBox.setCurrentIndex(i)
                    break

        self.actionLabel = QLabel("Action:")
        self.targetTypeLabel = QLabel("Target type:")
        self.targetNameLabel = QLabel("Target:")
        self.employeeLabel = QLabel("Employee:")

        self.generateB = QPushButton("Generate")
        self.generateB.clicked.connect(self.generate)

        self.mainLayout = [
            [QLabel("Report type:"), self.typeBox],
            [QLabel("From:"), self.startDateEdit],
            [QLabel("To:"), self.endDateEdit],
            [self.actionLabel, self.actionBox],
            [self.targetTypeLabel, self.targetTypeBox],
            [self.targetNameLabel, self.targetNameBox],
            [self.employeeLabel, self.employeeBox],
            [self.generateB],
        ]
        widgetFromList(self, self.mainLayout)

        self._onTargetTypeChanged(self.targetTypeBox.currentIndex())
        self._onTypeChanged(self.typeBox.currentText())

        centerOnScreen(self)
        self.show()

    def _onTargetTypeChanged(self, _idx: int):
        targetType = self.targetTypeBox.currentData()
        self.targetNameBox.clear()
        if targetType == "mix":
            self.targetNameBox.addItems(sorted(self.mainApp.db.mixtures.keys()))
        elif targetType == "part":
            self.targetNameBox.addItems(sorted(self.mainApp.db.parts.keys()))

    def _onTypeChanged(self, t: str):
        showAction = (t == "Per Action")
        showTarget = (t == "Per Target")
        showEmployee = (t == "Per Employee")
        for w in (self.actionLabel, self.actionBox):
            w.setVisible(showAction)
        for w in (self.targetTypeLabel, self.targetTypeBox,
                  self.targetNameLabel, self.targetNameBox):
            w.setVisible(showTarget)
        for w in (self.employeeLabel, self.employeeBox):
            w.setVisible(showEmployee)

    def generate(self):
        startDate = fromQDate(self.startDateEdit.date())
        endDate = fromQDate(self.endDateEdit.date())
        if startDate > endDate:
            errorMessage(self, ["Start date must be on or before end date."])
            return

        reportType = self.typeBox.currentText()
        action = self.actionBox.currentText()
        targetType = self.targetTypeBox.currentData()
        targetName = self.targetNameBox.currentText()
        employeeId = self.employeeBox.currentData()

        if reportType == "Per Target" and not targetName:
            label = "mixtures" if targetType == "mix" else "parts"
            errorMessage(self, [f"No {label} available to report on."])
            return
        if reportType == "Per Employee" and employeeId is None:
            errorMessage(self, ["No employee selected."])
            return

        savePath = tempReportPath(self._defaultPrefix(reportType, action, targetName, employeeId))

        pdf = PDFReport(self.mainApp.db, savePath)
        if reportType == "Production Summary":
            pdf.productionSummaryReport(startDate, endDate)
        elif reportType == "Per Action":
            pdf.productionActionReport(action, startDate, endDate)
        elif reportType == "Per Target":
            pdf.productionTargetReport(targetType, targetName, startDate, endDate)
        elif reportType == "Per Employee":
            pdf.productionEmployeeReport(employeeId, startDate, endDate)
        else:
            raise RuntimeError(f'unknown reportType {reportType!r}')

        startfile(savePath)
        self.close()

    def _defaultPrefix(self, reportType, action, targetName, employeeId) -> str:
        if reportType == "Production Summary":
            return "production-summary"
        if reportType == "Per Action":
            return f"production-{action.lower()}"
        if reportType == "Per Target":
            return f"production-{targetName or 'target'}"
        if reportType == "Per Employee":
            return f"production-employee-{employeeId}"
        return "production-report"


class _BatchRow(QWidget):
    # One row inside ProductionBatchDialog. Holds employee / target / quantity /
    # scrap / shift widgets plus a Remove button. Date and action are shared and
    # live on the parent dialog.
    def __init__(self, mainApp: MainWindow, parentDialog: "ProductionBatchDialog",
                 targetType: str, prevRow: "_BatchRow | None"):
        super().__init__(parentDialog)
        self.mainApp = mainApp
        self.parentDialog = parentDialog

        self.employeeBox = QComboBox()
        self.employeeBox.setEditable(False)
        self.employeeBox.setMinimumWidth(200)
        self.employeeBox.setMaximumWidth(200)
        emps = list(self.mainApp.db.employees.values())
        emps.sort(key=lambda e: (0 if e.status else 1,
                                 (e.lastName or "").lower(),
                                 (e.firstName or "").lower()))
        for emp in emps:
            suffix = "" if emp.status else " [inactive]"
            self.employeeBox.addItem(_employeeLabel(emp) + suffix, userData=emp.idNum)

        self.targetBox = QComboBox()
        self.targetBox.setEditable(False)
        self.targetBox.setMinimumWidth(160)
        self.targetBox.setMaximumWidth(160)
        self._populateTargets(targetType)

        self.quantityEdit = QLineEdit()
        self.quantityEdit.setMaximumWidth(80)
        self.scrapEdit = QLineEdit("0")
        self.scrapEdit.setMaximumWidth(80)

        self.shiftBox = QComboBox()
        self.shiftBox.setEditable(False)
        self.shiftBox.addItems(["1", "2", "3"])
        self.shiftBox.setMaximumWidth(60)

        self.removeB = QPushButton("Remove")
        self.removeB.clicked.connect(lambda: self.parentDialog._removeRow(self))

        if prevRow is not None:
            # Inherit defaults from the previous row per §16 decision — quantity and
            # scrap stay blank/zero so the user doesn't accidentally duplicate numbers.
            self.employeeBox.setCurrentIndex(prevRow.employeeBox.currentIndex())
            self.shiftBox.setCurrentText(prevRow.shiftBox.currentText())
            prevTarget = prevRow.targetBox.currentText()
            if prevTarget:
                idx = self.targetBox.findText(prevTarget)
                if idx >= 0:
                    self.targetBox.setCurrentIndex(idx)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.employeeBox)
        layout.addWidget(self.targetBox)
        layout.addWidget(self.quantityEdit)
        layout.addWidget(self.scrapEdit)
        layout.addWidget(self.shiftBox)
        layout.addWidget(self.removeB)
        self.setLayout(layout)

    def _populateTargets(self, targetType: str) -> bool:
        # Refill the target combo for the current action's targetType. Returns True
        # if the previously-selected target no longer appears in the new list (so
        # the batch dialog can tally invalidated rows for the status label).
        prev = self.targetBox.currentText()
        self.targetBox.blockSignals(True)
        self.targetBox.clear()
        if targetType == "mix":
            names = sorted(self.mainApp.db.mixtures.keys())
        elif targetType == "part":
            names = sorted(self.mainApp.db.parts.keys())
        else:
            names = []
        self.targetBox.addItems(names)
        invalidated = False
        if prev:
            if prev in names:
                self.targetBox.setCurrentText(prev)
            else:
                invalidated = True
        self.targetBox.blockSignals(False)
        return invalidated


class ProductionBatchDialog(QWidget):
    # Batch-entry dialog: shared date + action at the top, a scrollable list of
    # _BatchRow widgets below, atomic save. See MERGE_PLAN §13.3 (Step 16).
    def __init__(self, parentTab: ProductionTab, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.parentTab = parentTab
        self.setWindowTitle("Production: Batch Entry")

        today = datetime.date.today()
        self.dateEdit = QDateEdit()
        self.dateEdit.setCalendarPopup(True)
        self.dateEdit.setDisplayFormat("yyyy-MM-dd")
        self.dateEdit.setDate(toQDate(today))

        self.actionBox = QComboBox()
        self.actionBox.setEditable(False)
        self.actionBox.addItems(PRODUCTION_ACTIONS)
        self.actionBox.currentTextChanged.connect(self._onActionChanged)

        headerLayout = QHBoxLayout()
        headerLayout.addWidget(QLabel("Date:"))
        headerLayout.addWidget(self.dateEdit)
        headerLayout.addSpacing(24)
        headerLayout.addWidget(QLabel("Action:"))
        headerLayout.addWidget(self.actionBox)
        headerLayout.addStretch()

        colHeaderLayout = QHBoxLayout()
        colHeaderLayout.setContentsMargins(0, 0, 0, 0)
        for text, minW, maxW in (
            ("Employee", 200, 200),
            ("Target",   160, 160),
            ("Quantity",   0, 80),
            ("Scrap",      0, 80),
            ("Shift",      0, 60),
            ("",           0, 0),
        ):
            lbl = QLabel(text)
            if minW:
                lbl.setMinimumWidth(minW)
            if maxW:
                lbl.setMaximumWidth(maxW)
            colHeaderLayout.addWidget(lbl)

        self.statusLabel = QLabel("")

        self.rows: list[_BatchRow] = []
        self.rowsLayout = QVBoxLayout()
        self.rowsLayout.setContentsMargins(0, 0, 0, 0)
        self.rowsLayout.addStretch()

        rowsContainer = QWidget()
        rowsContainer.setLayout(self.rowsLayout)
        self.scrollB = QScrollArea()
        self.scrollB.setWidget(rowsContainer)
        self.scrollB.setWidgetResizable(True)

        self.addRowB = QPushButton("Add row")
        self.addRowB.clicked.connect(self._addRow)

        self.saveB = QPushButton("Save")
        self.saveB.clicked.connect(self._save)
        self.cancelB = QPushButton("Cancel")
        self.cancelB.clicked.connect(self.close)

        buttonRow = QHBoxLayout()
        buttonRow.addStretch()
        buttonRow.addWidget(self.cancelB)
        buttonRow.addWidget(self.saveB)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(headerLayout)
        mainLayout.addLayout(colHeaderLayout)
        mainLayout.addWidget(self.scrollB)
        mainLayout.addWidget(self.addRowB)
        mainLayout.addWidget(self.statusLabel)
        mainLayout.addLayout(buttonRow)
        self.setLayout(mainLayout)

        self.resize(900, 480)
        self._addRow()  # also updates height for the initial row

        centerOnScreen(self, False)
        self.show()

    def _currentTargetType(self) -> str:
        return PRODUCTION_ACTION_TARGET.get(self.actionBox.currentText(), "")

    def _addRow(self):
        prev = self.rows[-1] if self.rows else None
        row = _BatchRow(self.mainApp, self, self._currentTargetType(), prev)
        self.rows.append(row)
        # Insert before the trailing stretch so rows stack at the top of the scroll area.
        insertAt = self.rowsLayout.count() - 1
        self.rowsLayout.insertWidget(insertAt, row)
        self._updateHeight()

    def _removeRow(self, row: _BatchRow):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rowsLayout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._updateHeight()

    def _updateHeight(self):
        # Grow/shrink the dialog with the row count so the user doesn't have to
        # drag the bottom edge every time. Capped at ~90% of screen so the save
        # button can't drift off-screen on a runaway add.
        ROW_HEIGHT = 36
        CHROME_HEIGHT = 180  # header + col header + add button + status + save row + margins
        minHeight = 480
        maxHeight = 900
        screen = self.screen()
        if screen is not None:
            maxHeight = max(minHeight, int(screen.availableGeometry().height() * 0.9))
        desired = max(minHeight, min(CHROME_HEIGHT + len(self.rows) * ROW_HEIGHT, maxHeight))
        if desired != self.height():
            self.resize(self.width(), desired)

    def _onActionChanged(self, _text: str):
        targetType = self._currentTargetType()
        invalidated = 0
        for row in self.rows:
            if row._populateTargets(targetType):
                invalidated += 1
        if invalidated:
            self.statusLabel.setText(
                f"Action changed — cleared target on {invalidated} row(s); "
                f"pick new targets before saving."
            )
        else:
            self.statusLabel.setText("")

    def _save(self):
        if not self.rows:
            errorMessage(self, ["No rows to save."])
            return

        batchDate = fromQDate(self.dateEdit.date())
        action = self.actionBox.currentText()
        if action not in PRODUCTION_ACTIONS:
            errorMessage(self, [f"Unknown action: {action!r}"])
            return
        targetType = PRODUCTION_ACTION_TARGET[action]

        errors: list[str] = []
        toCreate: list[ProductionRecord] = []
        seenKeys: set[tuple] = set()

        for i, row in enumerate(self.rows, start=1):
            rowErrs: list[str] = []

            empId = row.employeeBox.currentData()
            if empId is None:
                rowErrs.append("no employee selected")
            elif empId not in self.mainApp.db.employees:
                rowErrs.append(f"employee {empId} no longer exists")

            shiftText = row.shiftBox.currentText()
            try:
                shift = int(shiftText)
            except ValueError:
                rowErrs.append(f"invalid shift {shiftText!r}")
                shift = 0

            targetName = row.targetBox.currentText()
            if not targetName:
                rowErrs.append("no target selected")
            elif targetType == "mix" and targetName not in self.mainApp.db.mixtures:
                rowErrs.append(f"mixture {targetName!r} no longer exists")
            elif targetType == "part" and targetName not in self.mainApp.db.parts:
                rowErrs.append(f"part {targetName!r} no longer exists")

            qtyRaw = row.quantityEdit.text().strip()
            if not qtyRaw:
                rowErrs.append("quantity is blank")
                quantity = 0.0
            else:
                quantity = checkInput(qtyRaw, float, "nonneg", rowErrs, "quantity")

            scrapRaw = row.scrapEdit.text().strip()
            if not scrapRaw:
                scrap = 0.0
            else:
                scrap = checkInput(scrapRaw, float, "nonneg", rowErrs, "scrap")

            if not rowErrs:
                key = (empId, batchDate, shift, targetType, targetName, action)
                if key in self.mainApp.db.production:
                    rowErrs.append("a matching production record already exists in the database")
                elif key in seenKeys:
                    rowErrs.append("duplicates an earlier row in this batch")
                else:
                    seenKeys.add(key)

            if rowErrs:
                errors.append(f"Row {i}: " + "; ".join(rowErrs))
            else:
                rec = ProductionRecord()
                rec.setRecord(empId, batchDate, shift, action, targetName, quantity, scrap)
                toCreate.append(rec)

        if errors:
            errorMessage(self, errors)
            return

        for rec in toCreate:
            self.mainApp.db.production[rec.key()] = rec

        self.parentTab.refresh()
        QMessageBox.information(self, "Success",
                                f"{len(toCreate)} production record(s) added!")
        self.close()
