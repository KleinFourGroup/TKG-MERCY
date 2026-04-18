import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox, QFileDialog
from PySide6.QtCore import QDate, Qt
import random
import math
import os

from table import DBTable
from app import MainWindow
from employee_overview_tab import MainTab
from records import Employee, EmployeePoint, EmployeePointsDB
from defaults import POINT_VALS
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, startfile, centerOnScreen
from report import PDFReport

class PointsTab(QWidget):
    def __init__(self, mainTab: MainTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        
        self.currentEmployee: Employee = None
        self.currentEmployeePoints: EmployeePointsDB = None
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
        self.tableData = [] if db == None else [[
            "{}".format(entry.date.isoformat()),
            "{}".format(entry.value),
            "{}".format(entry.reason)

        ] for entry in db.currentPointsList(datetime.date.today())]
        self.tableData.sort(key=lambda row: row[0])
    
    def setSelection(self, selection):
        self.selection = list(map(lambda x: datetime.date.fromisoformat(x), selection))
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def setEmployee(self, employeeID: int):
        self.currentEmployee = None if employeeID == None else self.mainApp.db.employees[self.mainTab.employeeID] 
        self.currentEmployeePoints = None if employeeID == None else self.mainApp.db.attendance[self.mainTab.employeeID] 
        if self.currentEmployee is not None:
            self.currentEmployeeLabel.setText(f"Employee: {self.currentEmployee.lastName.upper()} {self.currentEmployee.firstName} ({self.currentEmployee.idNum})")
            self.anniversary.setText(f"Anniversary: {self.currentEmployee.anniversary.isoformat()}")
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
        PointsEditWindow(self.currentEmployeePoints.idNum, None, self.mainApp)
    
    def openEdits(self):
        pass
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
        for date in self.selection:
            if not date in self.currentEmployeePoints.points:
                errorMessage(self.mainApp, [f"{date} is an automatic deduction and cannot be edited."])
            else:
                PointsEditWindow(self.currentEmployeePoints.idNum, self.currentEmployeePoints.points[date], self.mainApp)
    
    def deletePoints(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
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
        if self.currentEmployeePoints == None:
            errorMessage(self.mainApp, ["No employee selected."])
        else:
            reportFile  = QFileDialog.getSaveFileName(self, f"Save {self.currentEmployee.idNum} Attendance Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
            if not reportFile[0] == "":
                pdf = PDFReport(self.mainApp.db, reportFile[0])
                pdf.employeePointsReport(self.currentEmployee.idNum)
                startfile(reportFile[0])
    
    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshPoints()

class PointsEditWindow(QWidget):
    def __init__(self, employeeID, point: EmployeePoint, mainApp: MainWindow):
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
        self.isNew = point == None
        if not self.isNew:
            if point.date not in self.pointDB.points:
                raise RuntimeError('point.date not in self.pointDB.points')
            if not (point == self.pointDB.points[point.date]):
                raise RuntimeError('point == self.pointDB.points[point.date]')

        self.calendar = QCalendarWidget()
        if not self.isNew:
            self.calendar.setSelectedDate(toQDate(self.point.date))
        
        self.otherReason = QLineEdit()
        if not self.isNew and not self.point.reason in POINT_VALS:
            self.otherReason.setText(self.point.reason)

        self.pointsInput = QLineEdit()
        def setReason(reason: str):
            if not reason == "Other":
                if reason not in POINT_VALS:
                    raise RuntimeError('reason not in POINT_VALS')
                self.pointsInput.setText(f"{POINT_VALS[reason]}")
                self.otherReason.setEnabled(False)
                self.pointsInput.setEnabled(False)
            else:
                self.pointsInput.setText(f"{self.point.value if not self.isNew else ""}")
                self.otherReason.setEnabled(True)
                self.pointsInput.setEnabled(True)
            
        reasonList = ["Other"]
        reasonList.extend(list(POINT_VALS.keys()))

        self.reasons = QComboBox()
        self.reasons.setEditable(False)
        self.reasons.currentTextChanged.connect(setReason)
        self.reasons.addItems(reasonList)
        if not self.isNew:
            self.reasons.setCurrentText(self.point.reason)

        self.mainLayout = [
            [
                QLabel("Point Date:"), self.calendar
            ],
            [
                QLabel("Reason:"), self.reasons
            ],
            [
                QLabel("Other:"), self.otherReason
            ],
            [
                QLabel("Points:"), self.pointsInput
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.mainLayout[-1][0].clicked.connect(self.updatePoint)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newPoint)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        
        date = fromQDate(self.calendar.selectedDate())
        if date in self.pointDB.points and not (not isNew and date == self.point.date):
            errors.append(f"Employee {self.employeeID} already has points on {date.isoformat()}")
        
        reason = self.reasons.currentText()
        other = self.otherReason.text()
        if reason == "Other" and other in POINT_VALS:
            errors.append(f"Other reason \"{other}\" is a default reason")
        points = checkInput(self.pointsInput.text(), float, "nonneg", errors, "Point Value")

        if len(errors) == 0:
            if isNew:
                self.point = EmployeePoint(self.employeeID, date, other if reason == "Other" else reason, points)
            if not isNew:
                del self.pointDB.points[self.point.date]
                self.point.date = date
                self.point.reason = reason
                self.point.value = points
            self.pointDB.points[self.point.date] = self.point

            self.mainApp.overviewTab.pointsTab.refresh()
            res = True
        else:
            # self.error = ErrorWindow(errors)
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
