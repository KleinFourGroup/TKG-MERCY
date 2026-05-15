import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QSlider
from PySide6.QtCore import QDate, Qt
import random
import math

from table import DBTable
from app import MainWindow
from employee_detail_tab import EmployeeDetailTab
from records import Employee, EmployeePTORange, EmployeePTODB
from defaults import POINT_VALS, PTO_ELIGIBILITY
from error import errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, startfile, tempReportPath, centerOnScreen
from report import PDFReport

class PTOTab(QWidget):
    def __init__(self, mainTab: EmployeeDetailTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        
        self.currentEmployee: Employee | None = None
        self.currentEmployeePTO: EmployeePTODB | None = None
        self.currentEmployeeLabel = QLabel("Employee: N/A")

        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        topLayout = QVBoxLayout()

        self.PTOHoursLabel = QLabel(f"PTO hours in {datetime.date.today().year}: N/A")
        self.PTOUsedLabel = QLabel(f"PTO used in {datetime.date.today().year}: N/A")
        self.PTORemainingLabel = QLabel(f"PTO remaining in {datetime.date.today().year}: N/A")
        self.anniversary = QLabel("Anniversary: N/A")
        topLayout0 = QHBoxLayout()
        topLayout0.addWidget(self.currentEmployeeLabel)

        topLayout1 = QHBoxLayout()
        topLayout1.addWidget(self.PTOHoursLabel)
        topLayout1.addWidget(self.PTOUsedLabel)
        topLayout1.addWidget(self.PTORemainingLabel)
        topLayout1.addWidget(self.anniversary)

        self.PTOBaseLabel = QLabel(f"Base PTO in {datetime.date.today().year}: N/A")
        self.PTOAttendanceLabel = QLabel(f"PTO attendance bonus in {datetime.date.today().year}: N/A")
        self.carryLabel = QLabel(f"PTO carryover from {datetime.date.today().year - 1}: N/A")
        self.carryButton = QPushButton("Manage Carryover")
        self.carryButton.clicked.connect(self.manageCarry)
        self.carryButton.setEnabled(False)
        topLayout2 = QHBoxLayout()
        topLayout2.addWidget(self.PTOBaseLabel)
        topLayout2.addWidget(self.PTOAttendanceLabel)
        topLayout2.addWidget(self.carryLabel)
        topLayout2.addWidget(self.carryButton)

        topLayout.addLayout(topLayout0)
        topLayout.addLayout(topLayout1)
        topLayout.addLayout(topLayout2)

        self.newB = QPushButton("New PTO")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit PTO")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete PTO")
        self.deleteB.clicked.connect(self.deletePTO)
        self.reportB = QPushButton("Generate Report")
        self.reportB.clicked.connect(self.report)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)
        barLayout.addWidget(self.reportB)

        layout = QVBoxLayout()
        layout.addLayout(topLayout)
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.currentEmployeePTO
        self.headers = ["Start", "End", "Hours"]
        self.tableData = []
        if db is not None:
            for entry, ptoRange in db.PTO.items():
                start, end = entry
                endStr = end.isoformat() if isinstance(end, datetime.date) else end
                self.tableData.append([
                    start.isoformat(),
                    endStr,
                    f"{ptoRange.hours}",
                ])
        self.tableData.sort(key=lambda row: (row[0], row[1]))
    
    def setSelection(self, selection):
        def getPair(start: str):
            rows = [row for row in self.tableData if row[0] == start]
            if not (len(rows) == 1):
                raise RuntimeError('len(rows) == 1')
            end = rows[0][1]
            try:
                end = datetime.date.fromisoformat(rows[0][1])
            except:
                pass
            return (datetime.date.fromisoformat(rows[0][0]), end)
        self.selection = list(map(getPair, selection))
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: f"{x[0].isoformat()} -- {x[1].isoformat() if isinstance(x[1], datetime.date) else x[1]}", self.selection))}")
    
    def setEmployee(self, employeeID: int | None):
        self.currentEmployee = None if employeeID is None else self.mainApp.db.employees[employeeID]
        self.currentEmployeePTO = None if employeeID is None else self.mainApp.db.PTO[employeeID]
        if self.currentEmployee is not None:
            lastName = (self.currentEmployee.lastName or "?").upper()
            firstName = self.currentEmployee.firstName or "?"
            anniversary = self.currentEmployee.anniversary.isoformat() if self.currentEmployee.anniversary is not None else "?"
            self.currentEmployeeLabel.setText(f"Employee: {lastName} {firstName} ({self.currentEmployee.idNum})")
            self.anniversary.setText(f"Anniversary: {anniversary}")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")
            self.anniversary.setText("Anniversary: N/A")

        self.newB.setEnabled(self.currentEmployee is not None and self.currentEmployee.fullTime)
        self.editB.setEnabled(self.currentEmployee is not None and self.currentEmployee.fullTime)
        self.deleteB.setEnabled(self.currentEmployee is not None and self.currentEmployee.fullTime)
        self.reportB.setEnabled(self.currentEmployee is not None and self.currentEmployee.fullTime)
    
    def refreshPTO(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [entry[0].isoformat() for entry in self.selection if self.currentEmployeePTO is not None and entry in self.currentEmployeePTO.PTO]
        self.setSelection(selection)

        isEmpty = False
        if (
            self.currentEmployeePTO is not None
            and self.currentEmployee is not None
            and self.currentEmployee.fullTime
            and self.currentEmployee.anniversary is not None
            and self.currentEmployee.idNum is not None
        ):
            today = datetime.date.today()
            anniversary = self.currentEmployee.anniversary
            attendance = self.mainApp.db.attendance[self.currentEmployee.idNum]
            available = self.currentEmployeePTO.getAvailableHours(anniversary, attendance, today)
            used = self.currentEmployeePTO.getUsedHours(today.year)
            eligibilityDate = (anniversary + datetime.timedelta(days=PTO_ELIGIBILITY)).isoformat()
            eligibilityNote = "" if (today - anniversary).days >= PTO_ELIGIBILITY else f" (available {eligibilityDate})"
            self.PTOHoursLabel.setText(f"PTO hours in {today.year}: {available}{eligibilityNote}")
            self.PTOUsedLabel.setText(f"PTO used in {today.year}: {used}")
            self.PTORemainingLabel.setText(f"PTO remaining in {today.year}: {available - used}")
            self.PTOBaseLabel.setText(f"Base PTO in {today.year}: {self.currentEmployeePTO.getAvailableBaseHours(anniversary, today.year)}")
            self.PTOAttendanceLabel.setText(f"PTO attendance bonus in {today.year}: {self.currentEmployeePTO.getQuarterHours(anniversary, attendance, today)}")
            self.carryLabel.setText(f"PTO carryover from {today.year - 1}: {self.currentEmployeePTO.getCarryHours(today.year)}")
            self.carryButton.setEnabled(True)
        else:
            isEmpty = True
        
        if isEmpty:
            self.PTOHoursLabel.setText(f"PTO hours in {datetime.date.today().year}: N/A")
            self.PTOUsedLabel.setText(f"PTO used in {datetime.date.today().year}: N/A")
            self.PTOBaseLabel.setText(f"Base PTO in {datetime.date.today().year}: N/A")
            self.PTOAttendanceLabel.setText(f"PTO attendance bonus in {datetime.date.today().year}: N/A")
            self.carryLabel.setText(f"PTO carryover from {datetime.date.today().year - 1}: N/A")
            self.carryButton.setEnabled(False)
    
    def openNew(self):
        if self.currentEmployeePTO is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        PTOEditWindow(self.currentEmployeePTO.idNum, None, self.mainApp)

    def manageCarry(self):
        if self.currentEmployeePTO is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        PTOCarryWindow(self.currentEmployeePTO.idNum, self.mainApp)

    def openEdits(self):
        if self.currentEmployeePTO is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
            return
        for PTOrange in self.selection:
            if isinstance(PTOrange[1], str):
                errorMessage(self.mainApp, ["Carryover cannot be edited through this interface.  Please use the \"Manage Carryover\" button."])
            else:
                PTOEditWindow(self.currentEmployeePTO.idNum, self.currentEmployeePTO.PTO[PTOrange], self.mainApp)

    def deletePTO(self):
        if self.currentEmployeePTO is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
            return
        for PTOrange in self.selection:
            if isinstance(PTOrange[1], str):
                errorMessage(self.mainApp, ["Carryover cannot be deleted through this interface.  Please use the \"Manage Carryover\" button."])
            else:
                confirm = QMessageBox.question(self, f"Delete {PTOrange[0].isoformat()} -- {PTOrange[1].isoformat()}?", f"Are you sure you want to delete the PTO from {PTOrange[0].isoformat()} to {PTOrange[1].isoformat()}?")
                if confirm == QMessageBox.StandardButton.Yes:
                    del self.currentEmployeePTO.PTO[PTOrange]
                QMessageBox.information(self.mainApp, "Success", f"PTO from {PTOrange[0].isoformat()} to {PTOrange[1].isoformat()} successfully deleted!")
        self.refresh()

    def report(self):
        if self.currentEmployeePTO is None or self.currentEmployee is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        path = tempReportPath(f"employee-{self.currentEmployee.idNum}-pto")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.employeePTOReport(self.currentEmployee.idNum)
        startfile(path)
    
    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshPTO()

class PTOCarryWindow(QWidget):
    def __init__(self, employeeID, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if employeeID is None:
            raise RuntimeError('employeeID is None')
        self.mainApp = mainApp
        self.setWindowTitle(f"PTO carryover: {employeeID}")
        self.employeeID = employeeID

        self.PTODB = self.mainApp.db.PTO[employeeID]
        self.attendanceDB = self.mainApp.db.attendance[employeeID]
        self.employee = self.mainApp.db.employees[employeeID]
        if self.PTODB is None:
            raise RuntimeError('self.PTODB is None')
        if self.attendanceDB is None:
            raise RuntimeError('self.attendanceDB is None')
        if self.employee is None:
            raise RuntimeError('self.employee is None')
        if self.employee.anniversary is None:
            raise RuntimeError('self.employee.anniversary is None')

        lastYearEnd = datetime.date(year=datetime.date.today().year - 1, month=12, day=31)
        self.unusedHours = max(
            self.PTODB.getAvailableHours(self.employee.anniversary, self.attendanceDB, lastYearEnd) - self.PTODB.getUsedHours(datetime.date.today().year - 1),
            0
        )
        self.unusedType = self.PTODB.getCarryType(datetime.date.today().year)

        self.statusLabel = QLabel("Unassigned")

        self.toUseSlider = QSlider()
        self.toUseSlider.setOrientation(Qt.Orientation.Horizontal)
        self.toUseSlider.setMinimum(1)
        self.toUseSlider.setMaximum(min(int(self.unusedHours), 20))
        self.toUseSlider.setValue(min(int(self.unusedHours), 20))
        self.toUseSlider.setTickInterval(1)

        self.toUseLabel = QLabel(f"Hours: {self.toUseSlider.value()}")

        def setHoursLabel():
            self.toUseLabel.setText(f"Hours: {self.toUseSlider.value()}")
        
        self.toUseSlider.valueChanged.connect(setHoursLabel)

        if self.unusedType == "CARRY":
            self.statusLabel.setText("Carried over")
        elif self.unusedType == "CASH":
            self.statusLabel.setText("Cashed out")
        elif self.unusedType == "DROP":
            self.statusLabel.setText("Dropped")
        
        self.carryButton = QPushButton("Carry Over")
        self.cashButton = QPushButton("Cash Out")
        self.dropButton = QPushButton("Drop")
        self.resetButton = QPushButton("Reset")
        self.cancelButton = QPushButton("Cancel")

        self.mainLayout = [
            [
                QLabel(f"Unused hours: {self.unusedHours}")
            ],
            [
                QLabel("Unused status:"), self.statusLabel
            ],
            [
                self.toUseSlider, self.toUseLabel
            ],
            [
                self.carryButton
            ],
            [
                self.cashButton
            ],
            [
                self.dropButton
            ],
            [
                self.resetButton, self.cancelButton
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if self.unusedType is None:
            self.resetButton.setEnabled(False)
        else:
            self.resetButton.clicked.connect(self.reset)
        self.carryButton.clicked.connect(self.carry)
        self.cashButton.clicked.connect(self.cash)
        self.dropButton.clicked.connect(self.drop)
        self.cancelButton.clicked.connect(self.cancel)
        centerOnScreen(self)
        self.show()

    def carry(self):
        abort = False
        if self.unusedType == "CARRY":
            errorMessage(self, ["Unused hours have already been carried over"])
        else:
            if self.unusedType is not None:
                confirm = QMessageBox.question(self, f"Overwrite?", f"Are you sure you want to overwrite {self.employeeID}'s carryover'?")
                if confirm == QMessageBox.StandardButton.Yes:
                    self.PTODB.clearCarry(datetime.date.today().year)
                else:
                    abort = True
            if not abort:
                today = datetime.date.today()
                self.PTORange = EmployeePTORange(self.employeeID, today, "CARRY", self.toUseSlider.value())
                self.PTODB.PTO[(today, "CARRY")] = self.PTORange
                QMessageBox.information(self, "Success", "PTO successfully carried over!")
        self.mainApp.overviewTab.PTOTab.refresh()
        self.close()

    def cash(self):
        abort = False
        if self.unusedType == "CASH":
            errorMessage(self, ["Unused hours have already been cashed out"])
        else:
            if self.unusedType is not None:
                confirm = QMessageBox.question(self, f"Overwrite?", f"Are you sure you want to overwrite {self.employeeID}'s carryover'?")
                if confirm == QMessageBox.StandardButton.Yes:
                    self.PTODB.clearCarry(datetime.date.today().year)
                else:
                    abort = True
            if not abort:
                today = datetime.date.today()
                self.PTORange = EmployeePTORange(self.employeeID, today, "CASH", self.toUseSlider.value())
                self.PTODB.PTO[(today, "CASH")] = self.PTORange
                QMessageBox.information(self, "Success", "PTO successfully cashed out!")
        self.mainApp.overviewTab.PTOTab.refresh()
        self.close()

    def drop(self):
        abort = False
        if self.unusedType == "DROP":
            errorMessage(self, ["Unused hours have already been dropped"])
        else:
            if self.unusedType is not None:
                confirm = QMessageBox.question(self, f"Overwrite?", f"Are you sure you want to overwrite {self.employeeID}'s carryover'?")
                if confirm == QMessageBox.StandardButton.Yes:
                    self.PTODB.clearCarry(datetime.date.today().year)
                else:
                    abort = True
            if not abort:
                today = datetime.date.today()
                self.PTORange = EmployeePTORange(self.employeeID, today, "DROP", self.toUseSlider.value())
                self.PTODB.PTO[(today, "DROP")] = self.PTORange
                QMessageBox.information(self, "Success", "PTO successfully dropped!")
        self.close()

    def reset(self):
        confirm = QMessageBox.question(self, f"Overwrite?", f"Are you sure you want to overwrite {self.employeeID}'s carryover'?")
        if confirm == QMessageBox.StandardButton.Yes:
            self.PTODB.clearCarry(datetime.date.today().year)
            QMessageBox.information(self, "Success", "PTO carryover successfully reset!")
        self.mainApp.overviewTab.PTOTab.refresh()
        self.close()

    def cancel(self):
        self.close()


class PTOEditWindow(QWidget):
    def __init__(self, employeeID, PTORange: EmployeePTORange | None, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if employeeID is None:
            raise RuntimeError('employeeID is None')
        self.mainApp = mainApp
        self.setWindowTitle(f"PTO: {employeeID}")
        self.employeeID = employeeID

        self.PTODB = self.mainApp.db.PTO[employeeID]
        self.employee = self.mainApp.db.employees[employeeID]
        self.attendanceDB = self.mainApp.db.attendance[employeeID]
        if self.PTODB is None:
            raise RuntimeError('self.PTODB is None')
        if self.employee is None:
            raise RuntimeError('self.employee is None')
        if self.employee.anniversary is None:
            raise RuntimeError('self.employee.anniversary is None')

        self.PTORange = PTORange
        self.isNew = PTORange is None

        self.calendarStart = QCalendarWidget()
        self.calendarEnd = QCalendarWidget()
        self.hours = QLineEdit()

        if PTORange is not None:
            if PTORange.start is None or PTORange.end is None:
                raise RuntimeError('PTORange.start or PTORange.end is None')
            if isinstance(PTORange.end, str):
                raise RuntimeError('PTORange.end is a carryover marker; edit window should not have opened')
            if (PTORange.start, PTORange.end) not in self.PTODB.PTO:
                raise RuntimeError('(PTORange.start, PTORange.end) not in self.PTODB.PTO')
            if not (PTORange == self.PTODB.PTO[(PTORange.start, PTORange.end)]):
                raise RuntimeError('PTORange == self.PTODB.PTO[(PTORange.start, PTORange.end)]')
            self.calendarStart.setSelectedDate(toQDate(PTORange.start))
            self.calendarEnd.setSelectedDate(toQDate(PTORange.end))
            self.hours.setText(f"{PTORange.hours}")

        self.mainLayout = [
            [
                QLabel("Start:"), self.calendarStart
            ],
            [
                QLabel("End:"), self.calendarEnd
            ],
            [
                QLabel("Hours:"), self.hours
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.mainLayout[-1][0].clicked.connect(self.updatePTO)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newPTO)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []

        start = fromQDate(self.calendarStart.selectedDate())
        end = fromQDate(self.calendarEnd.selectedDate())

        if self.employee.anniversary is None:
            raise RuntimeError('self.employee.anniversary is None')
        anniversary = self.employee.anniversary

        if end < start:
            errors.append(f"Start date {start.isoformat()} comes after end date {end.isoformat()}")
        else:
            for dates in self.PTODB.PTO:
                if isinstance(dates[1], datetime.date) and not (start > dates[1] or dates[0] > end):
                    # Intersection?
                    if isNew or (self.PTORange is not None and not dates == (self.PTORange.start, self.PTORange.end)):
                        errors.append(f"Employee {self.employeeID} already has conflicting PTO from {dates[0].isoformat()} to {dates[1].isoformat()}")
        if not start.year == end.year:
            errors.append(f"Range spans multiple calendar years ({start.year} to {end.year})")

        if (start - anniversary).days < PTO_ELIGIBILITY:
            errors.append(f"Employee {self.employeeID} is not eligible for PTO until {(anniversary + datetime.timedelta(days=PTO_ELIGIBILITY)).isoformat()}")

        hours = checkInput(self.hours.text(), float, "pos", errors, "hours")

        used = self.PTODB.getUsedHours(start.year)
        if not isNew and self.PTORange is not None and self.PTORange.start is not None and self.PTORange.start.year == start.year:
            used -= self.PTORange.hours
        available = self.PTODB.getAvailableHours(anniversary, self.attendanceDB, end) # In case bonus hours apply mid range
        if used + hours > available:
            errors.append(f"Employee {self.employeeID} is only eligible for {available} PTO hours in {start.year} (would use {used + hours})")

        if len(errors) == 0:
            if isNew:
                ptoRange = EmployeePTORange(self.employeeID, start, end, hours)
                self.PTORange = ptoRange
            else:
                if self.PTORange is None:
                    raise RuntimeError('self.PTORange is None despite not isNew')
                if self.PTORange.start is None or self.PTORange.end is None:
                    raise RuntimeError('self.PTORange.start or self.PTORange.end is None')
                del self.PTODB.PTO[(self.PTORange.start, self.PTORange.end)]
                self.PTORange.start = start
                self.PTORange.end = end
                self.PTORange.hours = hours
                ptoRange = self.PTORange
            self.PTODB.PTO[(start, end)] = ptoRange

            self.mainApp.overviewTab.PTOTab.refresh()
            res = True
        else:
            errorMessage(self, errors)
        return res
    
    def newPTO(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "PTO added successful!")
            self.close()
    
    def updatePTO(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "PTO updated successful!")
            self.close()
