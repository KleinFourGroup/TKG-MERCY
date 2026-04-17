import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QSlider, QFileDialog
from PySide6.QtCore import QDate, Qt
import random
import math
import os

from table import DBTable
from app import MainWindow
from employee_overview_tab import MainTab
from records import Employee, EmployeePTORange, EmployeePTODB
from defaults import POINT_VALS, PTO_ELIGIBILITY
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, startfile
from report import PDFReport

class PTOTab(QWidget):
    def __init__(self, mainTab: MainTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        self.windows = []
        
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
        self.tableData = [] if db == None else [[
            "{}".format(db.PTO[entry].start.isoformat()),
            "{}".format(db.PTO[entry].end.isoformat() if isinstance(db.PTO[entry].end, datetime.date) else db.PTO[entry].end),
            "{}{}".format("" if isinstance(db.PTO[entry].end, datetime.date) else "", db.PTO[entry].hours)

        ] for entry in db.PTO]
        self.tableData.sort(key=lambda row: (row[0], row[1]))
    
    def setSelection(self, selection):
        def getPair(start: str):
            rows = [row for row in self.tableData if row[0] == start]
            assert(len(rows) == 1)
            end = rows[0][1]
            try:
                end = datetime.date.fromisoformat(rows[0][1])
            except:
                pass
            return (datetime.date.fromisoformat(rows[0][0]), end)
        self.selection = list(map(getPair, selection))
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: f"{x[0].isoformat()} -- {x[1].isoformat() if isinstance(x[1], datetime.date) else x[1]}", self.selection))}")
    
    def setEmployee(self, employeeID: int):
        self.currentEmployee = None if employeeID == None else self.mainApp.db.employees[self.mainTab.employeeID] 
        self.currentEmployeePTO = None if employeeID == None else self.mainApp.db.PTO[self.mainTab.employeeID] 
        if not self.currentEmployee == None:
            self.currentEmployeeLabel.setText(f"Employee: {self.currentEmployee.lastName.upper()} {self.currentEmployee.firstName} ({self.currentEmployee.idNum})")
            self.anniversary.setText(f"Anniversary: {self.currentEmployee.anniversary.isoformat()}")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")
            self.anniversary.setText("Anniversary: N/A")

        self.newB.setEnabled(not self.currentEmployee == None and self.currentEmployee.fullTime)
        self.editB.setEnabled(not self.currentEmployee == None and self.currentEmployee.fullTime)
        self.deleteB.setEnabled(not self.currentEmployee == None and self.currentEmployee.fullTime)
        self.reportB.setEnabled(not self.currentEmployee == None and self.currentEmployee.fullTime)
    
    def refreshPTO(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [entry[0].isoformat() for entry in self.selection if not self.currentEmployeePTO == None and entry in self.currentEmployeePTO.PTO]
        self.setSelection(selection)

        isEmpty = False
        if not self.currentEmployeePTO == None and not self.currentEmployee == None and self.currentEmployee.fullTime:
            today = datetime.date.today()
            self.PTOHoursLabel.setText(f"PTO hours in {datetime.date.today().year}: {self.currentEmployeePTO.getAvailableHours(self.currentEmployee.anniversary, self.mainApp.db.attendance[self.mainTab.employeeID], today)}{"" if (today - self.currentEmployee.anniversary).days >= PTO_ELIGIBILITY else f" (available {(self.currentEmployee.anniversary + datetime.timedelta(days=PTO_ELIGIBILITY)).isoformat()})"}")
            self.PTOUsedLabel.setText(f"PTO used in {datetime.date.today().year}: {self.currentEmployeePTO.getUsedHours(today.year)}")
            self.PTORemainingLabel.setText(f"PTO remaining in {datetime.date.today().year}: {self.currentEmployeePTO.getAvailableHours(self.currentEmployee.anniversary, self.mainApp.db.attendance[self.mainTab.employeeID], today) - self.currentEmployeePTO.getUsedHours(today.year)}")
            self.PTOBaseLabel.setText(f"Base PTO in {datetime.date.today().year}: {self.currentEmployeePTO.getAvailableBaseHours(self.currentEmployee.anniversary, today.year)}")
            self.PTOAttendanceLabel.setText(f"PTO attendance bonus in {datetime.date.today().year}: {self.currentEmployeePTO.getQuarterHours(self.currentEmployee.anniversary, self.mainApp.db.attendance[self.mainTab.employeeID], today)}")
            self.carryLabel.setText(f"PTO carryover from {datetime.date.today().year - 1}: {self.currentEmployeePTO.getCarryHours(today.year)}")
            self.carryButton.setEnabled(True)
            # currentPTO = self.currentEmployeePTO.currentPTO(today)
            # if not currentPTO == None:
            #     self.PTOLabel.setText(f"PTO: {currentPTO}")
            # else:
            #     isEmpty = True
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
        assert(not self.currentEmployeePTO == None)
        self.windows.append(PTOEditWindow(self.currentEmployeePTO.idNum, None, self.mainApp))
    
    def manageCarry(self):
        # self.windows.append(EmployeeEditWindow(None, self.mainApp, self.active))
        if self.currentEmployeePTO == None:
            errorMessage(self.mainApp, ["No employee selected."])
        else:
            self.windows.append(PTOCarryWindow(self.currentEmployeePTO.idNum, self.mainApp))
    
    def openEdits(self):
        # self.windows.append(EmployeeEditWindow(None, self.mainApp, self.active))
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
        for PTOrange in self.selection:
            if isinstance(PTOrange[1], str):
                errorMessage(self.mainApp, ["Carryover cannot be edited through this interface.  Please use the \"Manage Carryover\" button."])
            else:
                assert(not self.currentEmployeePTO == None)
                self.windows.append(PTOEditWindow(self.currentEmployeePTO.idNum, self.currentEmployeePTO.PTO[PTOrange], self.mainApp))
    
    def deletePTO(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
        for PTOrange in self.selection:
            if isinstance(PTOrange[1], str):
                errorMessage(self.mainApp, ["Carryover cannot be deleted through this interface.  Please use the \"Manage Carryover\" button."])
            else:
                confirm = QMessageBox.question(self, f"Delete {PTOrange[0].isoformat()} -- {PTOrange[1].isoformat()}?", f"Are you sure you want to delete the PTO from {PTOrange[0].isoformat()} to {PTOrange[1].isoformat()}?")
                if confirm == QMessageBox.StandardButton.Yes:
                    assert(not self.currentEmployeePTO == None)
                    del self.currentEmployeePTO.PTO[PTOrange]
                QMessageBox.information(self.mainApp, "Success", f"PTO from {PTOrange[0].isoformat()} to {PTOrange[1].isoformat()} successfully deleted!")
        self.refresh()

    def report(self):
        if self.currentEmployeePTO == None or self.currentEmployee == None:
            errorMessage(self.mainApp, ["No employee selected."])
        else:
            reportFile  = QFileDialog.getSaveFileName(self, f"Save {self.currentEmployee.idNum} PTO Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
            if not reportFile[0] == "":
                pdf = PDFReport(self.mainApp.db, reportFile[0])
                pdf.employeePTOReport(self.currentEmployee.idNum)
                startfile(reportFile[0])
    
    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshPTO()

class PTOCarryWindow(QWidget):
    def __init__(self, employeeID, mainApp: MainWindow):
        super().__init__()
        assert(not employeeID == None)
        self.mainApp = mainApp
        self.setWindowTitle(f"PTO carryover: {employeeID}")
        self.employeeID = employeeID

        self.PTODB = self.mainApp.db.PTO[employeeID]
        self.attendanceDB = self.mainApp.db.attendance[employeeID]
        self.employee = self.mainApp.db.employees[employeeID]
        assert(not self.PTODB == None)
        assert(not self.attendanceDB == None)
        assert(not self.employee == None)

        self.unusedHours = max(
            self.PTODB.getAvailableHours(self.employee.anniversary, self.attendanceDB, datetime.date(year=datetime.date.today().year - 1, month=12, day=31)) - self.PTODB.getUsedHours(datetime.date.today().year - 1),
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
        if self.unusedType == None:
            self.resetButton.setEnabled(False)
        else:
            self.resetButton.clicked.connect(self.reset)
        self.carryButton.clicked.connect(self.carry)
        self.cashButton.clicked.connect(self.cash)
        self.dropButton.clicked.connect(self.drop)
        self.cancelButton.clicked.connect(self.cancel)
        self.show()

    def carry(self):
        abort = False
        if self.unusedType == "CARRY":
            errorMessage(self, ["Unused hours have already been carried over"])
        else:
            if not self.unusedType == None:
                confirm = QMessageBox.question(self, f"Overwrite?", f"Are you sure you want to overwrite {self.employeeID}'s carryover'?")
                if confirm == QMessageBox.StandardButton.Yes:
                    self.PTODB.clearCarry(datetime.date.today().year)
                else:
                    abort = True
            if not abort:
                self.PTORange = EmployeePTORange(self.employeeID, datetime.date.today(), "CARRY", self.toUseSlider.value())
                self.PTODB.PTO[(self.PTORange.start, self.PTORange.end)] = self.PTORange
                QMessageBox.information(self, "Success", "PTO successfully carried over!")
        self.mainApp.overviewTab.PTOTab.refresh()
        self.close()

    def cash(self):
        abort = False
        if self.unusedType == "CASH":
            errorMessage(self, ["Unused hours have already been cashed out"])
        else:
            if not self.unusedType == None:
                confirm = QMessageBox.question(self, f"Overwrite?", f"Are you sure you want to overwrite {self.employeeID}'s carryover'?")
                if confirm == QMessageBox.StandardButton.Yes:
                    self.PTODB.clearCarry(datetime.date.today().year)
                else:
                    abort = True
            if not abort:
                self.PTORange = EmployeePTORange(self.employeeID, datetime.date.today(), "CASH", self.toUseSlider.value())
                self.PTODB.PTO[(self.PTORange.start, self.PTORange.end)] = self.PTORange
                QMessageBox.information(self, "Success", "PTO successfully cashed out!")
        self.mainApp.overviewTab.PTOTab.refresh()
        self.close()

    def drop(self):
        abort = False
        if self.unusedType == "DROP":
            errorMessage(self, ["Unused hours have already been dropped"])
        else:
            if not self.unusedType == None:
                confirm = QMessageBox.question(self, f"Overwrite?", f"Are you sure you want to overwrite {self.employeeID}'s carryover'?")
                if confirm == QMessageBox.StandardButton.Yes:
                    self.PTODB.clearCarry(datetime.date.today().year)
                else:
                    abort = True
            if not abort:
                self.PTORange = EmployeePTORange(self.employeeID, datetime.date.today(), "DROP", self.toUseSlider.value())
                self.PTODB.PTO[(self.PTORange.start, self.PTORange.end)] = self.PTORange
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
        super().__init__()
        assert(not employeeID == None)
        self.mainApp = mainApp
        self.setWindowTitle(f"PTO: {employeeID}")
        self.employeeID = employeeID

        self.PTODB = self.mainApp.db.PTO[employeeID]
        self.employee = self.mainApp.db.employees[employeeID]
        self.attendanceDB = self.mainApp.db.attendance[employeeID]
        assert(not self.PTODB == None)
        assert(not self.employee == None)

        self.PTORange = PTORange
        self.isNew = PTORange == None
        if not self.isNew:
            assert(not PTORange == None) # Redundant but the type hinter wants it
            assert((PTORange.start, PTORange.end) in self.PTODB.PTO)
            assert(PTORange == self.PTODB.PTO[(PTORange.start, PTORange.end)])

        self.calendarStart = QCalendarWidget()
        if not self.isNew:
            assert(not self.PTORange == None) # Redundant but the type hinter wants it
            self.calendarStart.setSelectedDate(toQDate(self.PTORange.start))

        self.calendarEnd = QCalendarWidget()
        if not self.isNew:
            assert(not self.PTORange == None) # Redundant but the type hinter wants it
            self.calendarEnd.setSelectedDate(toQDate(self.PTORange.end))

        self.hours = QLineEdit()
        if not self.isNew:
            assert(not self.PTORange == None) # Redundant but the type hinter wants it
            self.hours.setText(f"{self.PTORange.hours}")

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
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        
        start = fromQDate(self.calendarStart.selectedDate())
        end = fromQDate(self.calendarEnd.selectedDate())

        if end < start:
            errors.append(f"Start date {start.isoformat()} comes after end date {end.isoformat()}")
        else:
            # if (start, end) in self.PTODB.PTO and not (not isNew and start == self.PTORange.start and end == self.PTORange.end):
            #     errors.append(f"Employee {self.employeeID} already has PTO from {start.isoformat()} to {end.isoformat()}")
            
            for dates in self.PTODB.PTO:
                if isinstance(dates[1], datetime.date) and not (start > dates[1] or dates[0] > end):
                    # Intersection?
                    if isNew or (not self.PTORange == None and not dates == (self.PTORange.start, self.PTORange.end)):
                        errors.append(f"Employee {self.employeeID} already has conflicting PTO from {dates[0].isoformat()} to {dates[1].isoformat()}")
        if not start.year == end.year:
            errors.append(f"Range spans multiple calendar years ({start.year} to {end.year})")
        
        if (start - self.employee.anniversary).days < PTO_ELIGIBILITY:
            errors.append(f"Employee {self.employeeID} is not eligible for PTO until {(self.employee.anniversary + datetime.timedelta(days=PTO_ELIGIBILITY)).isoformat()}")
        
        hours = checkInput(self.hours.text(), float, "pos", errors, "hours")

        used = self.PTODB.getUsedHours(start.year)
        if not isNew and not self.PTORange == None and self.PTORange.start.year == start.year:
            used -= self.PTORange.hours
        available = self.PTODB.getAvailableHours(self.employee.anniversary, self.attendanceDB, end) # In case bonus hours apply mid range
        if used + hours > available:
            errors.append(f"Employee {self.employeeID} is only eligible for {available} PTO hours in {start.year} (would use {used + hours})")
        
        if len(errors) == 0:
            if isNew:
                self.PTORange = EmployeePTORange(self.employeeID, start, end, hours)
            assert(not self.PTORange == None) # Redundant but the type hinter wants it
            if not isNew:
                del self.PTODB.PTO[(self.PTORange.start, self.PTORange.end)]
                self.PTORange.start = start
                self.PTORange.end = end
                self.PTORange.hours = hours
            self.PTODB.PTO[(self.PTORange.start, self.PTORange.end)] = self.PTORange

            self.mainApp.overviewTab.PTOTab.refresh()
            res = True
        else:
            # self.error = ErrorWindow(errors)
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
