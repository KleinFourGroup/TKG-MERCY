import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox
from PySide6.QtCore import QDate, Qt
import random
import math

from table import DBTable
from app import MainWindow
from employee_detail_tab import EmployeeDetailTab
from records import Employee, EmployeePoint, EmployeePointsDB
from defaults import POINT_VALS
from error import errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, startfile, tempReportPath, centerOnScreen
from report import PDFReport

class PointsTab(QWidget):
    def __init__(self, mainTab: EmployeeDetailTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        
        self.currentEmployee: Employee | None = None
        self.currentEmployeePoints: EmployeePointsDB | None = None
        self.currentEmployeeLabel = QLabel("Employee: N/A")

        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        self.pointsLabel = QLabel("Points: N/A")
        self.anniversary = QLabel("Anniversary: N/A")
        topLayout = QHBoxLayout()
        topLayout.addWidget(self.currentEmployeeLabel)
        topLayout.addWidget(self.pointsLabel)
        topLayout.addWidget(self.anniversary)

        self.newB = QPushButton("New Points")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Points")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Points")
        self.deleteB.clicked.connect(self.deletePoints)
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
        db = self.currentEmployeePoints
        self.headers = ["Date", "Points", "Reason"]
        self.tableData = []
        if db is not None:
            for entry in db.currentPointsList(datetime.date.today()):
                if entry.date is None:
                    raise RuntimeError('entry.date is None')
                self.tableData.append([
                    "{}".format(entry.date.isoformat()),
                    "{}".format(entry.value),
                    "{}".format(entry.reason)
                ])
        self.tableData.sort(key=lambda row: row[0])
    
    def setSelection(self, selection):
        self.selection = list(map(lambda x: datetime.date.fromisoformat(x), selection))
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def setEmployee(self, employeeID: int | None):
        self.currentEmployee = None if employeeID is None else self.mainApp.db.employees[employeeID]
        self.currentEmployeePoints = None if employeeID is None else self.mainApp.db.attendance[employeeID]
        if self.currentEmployee is not None:
            lastName = (self.currentEmployee.lastName or "?").upper()
            firstName = self.currentEmployee.firstName or "?"
            anniversary = self.currentEmployee.anniversary.isoformat() if self.currentEmployee.anniversary is not None else "?"
            self.currentEmployeeLabel.setText(f"Employee: {lastName} {firstName} ({self.currentEmployee.idNum})")
            self.anniversary.setText(f"Anniversary: {anniversary}")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")
            self.anniversary.setText("Anniversary: N/A")

        self.newB.setEnabled(self.currentEmployee is not None)
        self.editB.setEnabled(self.currentEmployee is not None)
        self.deleteB.setEnabled(self.currentEmployee is not None)
        self.reportB.setEnabled(self.currentEmployee is not None)
    
    def refreshPoints(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [entry.isoformat() for entry in self.selection if self.currentEmployeePoints is not None and entry in self.currentEmployeePoints.points]
        self.setSelection(selection)

        isEmpty = False
        if self.currentEmployeePoints is not None:
            today = datetime.date.today()
            currentPoints = self.currentEmployeePoints.currentPoints(today)
            if currentPoints is not None:
                self.pointsLabel.setText(f"Points: {currentPoints}")
            else:
                isEmpty = True
        else:
            isEmpty = True
        
        if isEmpty:
            self.pointsLabel.setText("Points: N/A")
    
    def openNew(self):
        if self.currentEmployeePoints is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        PointsEditWindow(self.currentEmployeePoints.idNum, None, self.mainApp)

    def openEdits(self):
        if self.currentEmployeePoints is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
            return
        for date in self.selection:
            if not date in self.currentEmployeePoints.points:
                errorMessage(self.mainApp, [f"{date} is an automatic deduction and cannot be edited."])
            else:
                PointsEditWindow(self.currentEmployeePoints.idNum, self.currentEmployeePoints.points[date], self.mainApp)

    def deletePoints(self):
        if self.currentEmployeePoints is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
            return
        for date in self.selection:
            if not date in self.currentEmployeePoints.points:
                errorMessage(self.mainApp, [f"{date} is an automatic deduction and cannot be deleted."])
            else:
                confirm = QMessageBox.question(self, f"Delete {date.isoformat()}?", f"Are you sure you want to delete the points on {date.isoformat()}?")
                if confirm == QMessageBox.StandardButton.Yes:
                    del self.currentEmployeePoints.points[date]
                    QMessageBox.information(self.mainApp, "Success", f"{date.isoformat()} successfully deleted!")
        self.refresh()

    def report(self):
        if self.currentEmployee is None or self.currentEmployeePoints is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        path = tempReportPath(f"employee-{self.currentEmployee.idNum}-attendance")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.employeePointsReport(self.currentEmployee.idNum)
        startfile(path)
    
    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshPoints()

class PointsEditWindow(QWidget):
    def __init__(self, employeeID, point: EmployeePoint | None, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if employeeID is None:
            raise RuntimeError('employeeID is None')
        self.mainApp = mainApp
        self.setWindowTitle(f"Point: {employeeID}")
        self.employeeID = employeeID

        self.pointDB = self.mainApp.db.attendance[employeeID]
        if self.pointDB is None:
            raise RuntimeError('self.pointDB is None')

        self.point = point
        self.isNew = point is None

        self.calendar = QCalendarWidget()
        self.otherReason = QLineEdit()

        if point is not None:
            if point.date is None:
                raise RuntimeError('point.date is None')
            if point.date not in self.pointDB.points:
                raise RuntimeError('point.date not in self.pointDB.points')
            if not (point == self.pointDB.points[point.date]):
                raise RuntimeError('point == self.pointDB.points[point.date]')
            self.calendar.setSelectedDate(toQDate(point.date))
            if point.reason not in POINT_VALS:
                self.otherReason.setText(point.reason)

        self.pointsInput = QLineEdit()
        def setReason(reason: str):
            if not reason == "Other":
                if reason not in POINT_VALS:
                    raise RuntimeError('reason not in POINT_VALS')
                self.pointsInput.setText(f"{POINT_VALS[reason]}")
                self.otherReason.setEnabled(False)
                self.pointsInput.setEnabled(False)
            else:
                self.pointsInput.setText(f"{self.point.value if self.point is not None else ""}")
                self.otherReason.setEnabled(True)
                self.pointsInput.setEnabled(True)

        reasonList = ["Other"]
        reasonList.extend(list(POINT_VALS.keys()))

        self.reasons = QComboBox()
        self.reasons.setEditable(False)
        self.reasons.currentTextChanged.connect(setReason)
        self.reasons.addItems(reasonList)
        if point is not None and point.reason is not None:
            self.reasons.setCurrentText(point.reason)

        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        self.mainLayout = [
            [QLabel("Point Date:"), self.calendar],
            [QLabel("Reason:"), self.reasons],
            [QLabel("Other:"), self.otherReason],
            [QLabel("Points:"), self.pointsInput],
            [self.updateButton, self.createButton],
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.updateButton.clicked.connect(self.updatePoint)
        else:
            self.updateButton.setEnabled(False)
        self.createButton.clicked.connect(self.newPoint)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []

        date = fromQDate(self.calendar.selectedDate())
        isSameDate = (
            not isNew
            and self.point is not None
            and date == self.point.date
        )
        if date in self.pointDB.points and not isSameDate:
            errors.append(f"Employee {self.employeeID} already has points on {date.isoformat()}")

        reason = self.reasons.currentText()
        other = self.otherReason.text()
        if reason == "Other" and other in POINT_VALS:
            errors.append(f"Other reason \"{other}\" is a default reason")
        points = checkInput(self.pointsInput.text(), float, "nonneg", errors, "Point Value")

        if len(errors) == 0:
            if isNew:
                point = EmployeePoint(self.employeeID, date, other if reason == "Other" else reason, points)
                self.point = point
            else:
                if self.point is None:
                    raise RuntimeError('self.point is None despite not isNew')
                if self.point.date is None:
                    raise RuntimeError('self.point.date is None')
                del self.pointDB.points[self.point.date]
                self.point.date = date
                self.point.reason = reason
                self.point.value = points
                point = self.point
            self.pointDB.points[date] = point

            self.mainApp.overviewTab.pointsTab.refresh()
            res = True
        else:
            errorMessage(self, errors)
        return res
    
    def newPoint(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Points added successful!")
            self.close()
    
    def updatePoint(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Points updated successful!")
            self.close()
