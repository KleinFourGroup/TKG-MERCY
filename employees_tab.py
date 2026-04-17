import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox, QFileDialog
from PySide6.QtCore import QDate
import random
import math
import os

from table import DBTable
from app import MainWindow
from records import Employee, EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB, EmployeePTODB, EmployeeNotesDB
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, startfile
from report import PDFReport

class EmployeeOverviewTab(QWidget):
    def __init__(self, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp

        # Create a QTabWidget
        self.tab_widget = QTabWidget()

        self.activeEmployeesTab = EmployeeTab(self, True)
        self.tab_widget.addTab(self.activeEmployeesTab, "Active Employees")
        self.inactiveEmployeesTab = EmployeeTab(self, False)
        self.tab_widget.addTab(self.inactiveEmployeesTab, "Inactive Employees")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tab_widget)

        # Set the layout for the main window
        self.setLayout(layout)

class EmployeeTab(QWidget):
    def __init__(self, mainTab: EmployeeOverviewTab, active: bool) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        self.active = active
        self.windows = []
        # self.error = None
        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        new = QPushButton("New")
        new.clicked.connect(self.openNew)
        edit = QPushButton("Edit")
        edit.clicked.connect(self.openEdits)
        toggle = QPushButton(f"Toggle {"Inactive" if self.active else "Active"}")
        toggle.clicked.connect(self.toggleSelection)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.deleteSelection)
        report = QPushButton("Report")
        report.clicked.connect(self.reportAll)
        report.setEnabled(self.active)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        if self.active:
            barLayout.addWidget(new)
            barLayout.addWidget(edit)
        barLayout.addWidget(toggle)
        barLayout.addWidget(delete)
        barLayout.addWidget(report)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.mainApp.db
        self.headers = ["ID Number", "Last Name", "First Name", "Anniversary", "Role", "Shift", "Full Time?", "Address", "Telephone", "Email"]
        self.tableData = [[
            entry,
            "{}".format(db.employees[entry].lastName),
            "{}".format(db.employees[entry].firstName),
            "{}".format(db.employees[entry].anniversary.isoformat()),
            "{}".format(db.employees[entry].role),
            "{}".format(db.employees[entry].shift),
            "{}".format(db.employees[entry].fullTime),
            "{}, {}, {} {}".format(
                ", ".join([str(line) for line in [db.employees[entry].addressLine1, db.employees[entry].addressLine2] if not line == None or not line == ""]),
                db.employees[entry].addressCity,
                db.employees[entry].addressState,
                db.employees[entry].addressZip
            ),
            "{}".format(db.employees[entry].addressTel),
            "{}".format(db.employees[entry].addressEmail)
        ] for entry in db.employees if db.employees[entry].status == self.active]
        self.tableData.sort(key=lambda row: (row[1], row[2], row[3]))
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def openEdits(self):
        for employee in self.selection:
            print(employee)
            self.windows.append(EmployeeEditWindow(employee, self.mainApp, self.active))
    
    def openNew(self):
        self.windows.append(EmployeeEditWindow(None, self.mainApp, self.active))

    def toggleSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No employees selected."])
        for employee in self.selection:
            confirm = QMessageBox.question(self, f"Toggle {employee}?", f"Are you sure you want to set {employee} as {"inactive" if self.active else "active"}?")
            if confirm == QMessageBox.StandardButton.Yes:
                self.mainApp.db.employees[employee].setStatus(not self.active)
                self.mainApp.overviewTab.refresh()
                self.mainTab.activeEmployeesTab.refreshTable()
                self.mainTab.inactiveEmployeesTab.refreshTable()
                QMessageBox.information(self, "Success", "Update successful!")

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No employees selected."])
        for employee in self.selection:
            confirm = QMessageBox.question(self, f"Delete {employee}?", f"Are you sure you want to delete {employee}?")

            if confirm == QMessageBox.StandardButton.Yes:
                self.mainApp.db.delEmployee(employee)
                self.mainApp.overviewTab.refresh()
                self.mainTab.activeEmployeesTab.refreshTable()
                self.mainTab.inactiveEmployeesTab.refreshTable()
                QMessageBox.information(self, "Success", "Update successful!")
    
    def reportAll(self):
        reportFile  = QFileDialog.getSaveFileName(self, f"Save Active Employee Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
        if not reportFile[0] == "":
            pdf = PDFReport(self.mainApp.db, reportFile[0])
            pdf.employeeActiveReport()
            startfile(reportFile[0])
    
    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [entry for entry in self.selection if entry in self.mainApp.db.employees]
        self.setSelection(selection)

SHIFTS = ["1", "2", "3"]

STATES = [
    # https://en.wikipedia.org/wiki/List_of_states_and_territories_of_the_United_States#States.
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "IA",
    "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO",
    "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI",
    "WV", "WY",
    # https://en.wikipedia.org/wiki/List_of_states_and_territories_of_the_United_States#Federal_district.
    "DC",
    # https://en.wikipedia.org/wiki/List_of_states_and_territories_of_the_United_States#Inhabited_territories.
    "AS", "GU", "MP", "PR", "VI",
]

class EmployeeEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow, active: bool):
        super().__init__()
        self.mainApp = mainApp
        self.active = active
        self.setWindowTitle(f"Edit: {entry if not entry == None else "New Employee"}")

        employee = self.mainApp.db.employees[entry] if not entry == None else None
        self.employee = employee

        self.calendar = QCalendarWidget()
        if not self.employee == None:
            self.calendar.setSelectedDate(toQDate(self.employee.anniversary))

        self.shift = QComboBox()
        self.shift.setEditable(False)
        self.shift.addItems(SHIFTS)
        if not self.employee == None:
            self.shift.setCurrentText(str(self.employee.shift))

        self.fullTime = QComboBox()
        self.fullTime.setEditable(False)
        self.fullTime.addItems(["True", "False"])
        if not self.employee == None:
            self.fullTime.setCurrentText(str(self.employee.fullTime))

        self.states = QComboBox()
        self.states.setEditable(False)
        self.states.addItems(STATES)
        if not self.employee == None:
            self.states.setCurrentText(str(self.employee.addressState))
        else:
            self.states.setCurrentText("PA")

        self.error = None

        def randID():
            SCREEN = 10000000
            idRand = math.floor(9 * SCREEN * random.random())
            tries = 0
            while (SCREEN + ((idRand + tries * tries) % (9 * SCREEN))) in self.mainApp.db.employees:
                tries += 1
            return SCREEN + ((idRand + tries * tries) % (9 * SCREEN))

        self.mainLayout = [
            [QLabel("ID Number:"), QLineEdit(f"{entry if not entry == None else randID()}")],
            [
                QLabel("Last Name:"), QLineEdit(f"{employee.lastName if not employee == None else ""}"),
                QLabel("First Name:"), QLineEdit(f"{employee.firstName if not employee == None else ""}")
            ],
            [
                QLabel("Role:"), QLineEdit(f"{employee.role if not employee == None else ""}")
            ],
            [
                QLabel("Shift:"), self.shift, QLabel("Full Time:"), self.fullTime
            ],
            [
                QLabel("Address Line 1:"), QLineEdit(f"{employee.addressLine1 if not employee == None else ""}")
            ],
            [
                QLabel("Address Line 2:"), QLineEdit(f"{employee.addressLine2 if not employee == None else ""}")
            ],
            [
                QLabel("City:"), QLineEdit(f"{employee.addressCity if not employee == None else ""}"), QLabel("State:"), self.states, QLabel("ZIP:"), QLineEdit(f"{employee.addressZip if not employee == None else ""}")
            ],
            [
                QLabel("Telephone:"), QLineEdit(f"{employee.addressTel if not employee == None else ""}")
            ],
            [
                QLabel("Email:"), QLineEdit(f"{employee.addressEmail if not employee == None else ""}")
            ],
            [
                QLabel("Anniversary:"), self.calendar
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not employee == None:
            self.mainLayout[-1][0].clicked.connect(self.updateEmployee)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newEmployee)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        id = checkInput(self.mainLayout[0][1].text(), int, "nonneg", errors, "ID Number")
        if id in self.mainApp.db.employees:
            if isNew or (not id == self.employee.idNum):
                errors.append(f"Employee number '{id}' already in use")
        lastName = self.mainLayout[1][1].text()
        if lastName == "":
            errors.append(f"Employee last name is blank")
        firstName = self.mainLayout[1][3].text()
        if firstName == "":
            errors.append(f"Employee first name is blank")
        role = self.mainLayout[2][1].text()
        if role == "":
            errors.append(f"Employee role is blank")
        addressLine1 = self.mainLayout[4][1].text()
        if addressLine1 == "":
            errors.append(f"Employee address is blank")
        addressLine2 = self.mainLayout[5][1].text()
        addressCity = self.mainLayout[6][1].text()
        if addressCity == "":
            errors.append(f"Employee city is blank")
        addressState = self.states.currentText()
        addressZip = self.mainLayout[6][5].text()
        if addressZip == "":
            errors.append(f"Employee ZIP is blank")
        addressTel = self.mainLayout[7][1].text()
        addressEmail = self.mainLayout[8][1].text()
        if addressTel == "" and addressEmail == "":
            errors.append(f"Employee telephone and email are both blank")

        if len(errors) == 0:
            isNone = self.employee == None
            if isNew:
                self.employee = Employee()
                self.employee.setID(id)
                self.mainApp.db.addEmployee(self.employee)
                reviews = EmployeeReviewsDB(id)
                self.mainApp.db.addEmployeeReviews(reviews)
                training = EmployeeTrainingDB(id)
                self.mainApp.db.addEmployeeTraining(training)
                points = EmployeePointsDB(id)
                self.mainApp.db.addEmployeePoints(points)
                PTO = EmployeePTODB(id)
                self.mainApp.db.addEmployeePTO(PTO)
                notes = EmployeeNotesDB(id)
                self.mainApp.db.addEmployeeNotes(notes)
            else:
                if not (not isNone):
                    raise RuntimeError('not isNone')
                self.mainApp.db.updateEmployee(self.employee.idNum, id)
            self.employee.setName(lastName, firstName)
            print(self.calendar.selectedDate())
            self.employee.setAnniversary(fromQDate(self.calendar.selectedDate()))
            self.employee.setStatus(self.active)
            self.employee.setJob(role, int(self.shift.currentText()), self.fullTime.currentText() == "True")
            self.employee.setAddress(addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail)
            if isNone:
                self.employee = None
            self.mainApp.overviewTab.refresh()
            self.mainApp.employeesTab.activeEmployeesTab.refreshTable()
            self.mainApp.employeesTab.inactiveEmployeesTab.refreshTable()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.employee.idNum if not self.employee == None else "New Employee"}")
        return res
    
    def updateEmployee(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()
    
    def newEmployee(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()