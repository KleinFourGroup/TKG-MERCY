import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox
from PySide6.QtCore import QDate, Qt
import random
import math

from table import DBTable
from app import MainWindow
from records import Employee, EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB, EmployeePTODB, EmployeeNotesDB
from error import errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, startfile, tempReportPath, centerOnScreen
from report import PDFReport
import logging

class EmployeeListTab(QWidget):
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
    def __init__(self, mainTab: EmployeeListTab, active: bool) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        self.active = active
        # self.error = None
        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        self.newButton = QPushButton("New")
        self.newButton.clicked.connect(self.openNew)
        self.editButton = QPushButton("Edit")
        self.editButton.clicked.connect(self.openEdits)
        self.toggleButton = QPushButton(f"Toggle {"Inactive" if self.active else "Active"}")
        self.toggleButton.clicked.connect(self.toggleSelection)
        self.deleteButton = QPushButton("Delete")
        self.deleteButton.clicked.connect(self.deleteSelection)
        self.reportButton = QPushButton("Report")
        self.reportButton.clicked.connect(self.reportAll)
        self.reportButton.setEnabled(self.active)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        if self.active:
            barLayout.addWidget(self.newButton)
            barLayout.addWidget(self.editButton)
        barLayout.addWidget(self.toggleButton)
        barLayout.addWidget(self.deleteButton)
        barLayout.addWidget(self.reportButton)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.mainApp.db
        self.headers = ["ID Number", "Last Name", "First Name", "Anniversary", "Role", "Shift", "Full Time?", "Address", "Telephone", "Email"]
        self.tableData = []
        for entry in db.employees:
            emp = db.employees[entry]
            if emp.status != self.active:
                continue
            anniversary = emp.anniversary.isoformat() if emp.anniversary is not None else "?"
            self.tableData.append([
                entry,
                "{}".format(emp.lastName),
                "{}".format(emp.firstName),
                anniversary,
                "{}".format(emp.role),
                "{}".format(emp.shift),
                "{}".format(emp.fullTime),
                "{}, {}, {} {}".format(
                    ", ".join([str(line) for line in [emp.addressLine1, emp.addressLine2] if line is not None or not line == ""]),
                    emp.addressCity,
                    emp.addressState,
                    emp.addressZip
                ),
                "{}".format(emp.addressTel),
                "{}".format(emp.addressEmail)
            ])
        self.tableData.sort(key=lambda row: (row[1], row[2], row[3]))
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def openEdits(self):
        for employee in self.selection:
            logging.debug(employee)
            EmployeeEditWindow(employee, self.mainApp, self.active)
    
    def openNew(self):
        EmployeeEditWindow(None, self.mainApp, self.active)

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
                self.mainApp.productionTab.refresh()
                QMessageBox.information(self, "Success", "Update successful!")

    def reportAll(self):
        path = tempReportPath("active-employees")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.employeeActiveReport()
        startfile(path)
    
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
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.active = active
        self.setWindowTitle(f"Edit: {entry if entry is not None else "New Employee"}")

        employee = self.mainApp.db.employees[entry] if entry is not None else None
        self.employee = employee

        self.calendar = QCalendarWidget()
        if self.employee is not None and self.employee.anniversary is not None:
            self.calendar.setSelectedDate(toQDate(self.employee.anniversary))

        self.shift = QComboBox()
        self.shift.setEditable(False)
        self.shift.addItems(SHIFTS)
        if self.employee is not None:
            self.shift.setCurrentText(str(self.employee.shift))

        self.fullTime = QComboBox()
        self.fullTime.setEditable(False)
        self.fullTime.addItems(["True", "False"])
        if self.employee is not None:
            self.fullTime.setCurrentText(str(self.employee.fullTime))

        self.states = QComboBox()
        self.states.setEditable(False)
        self.states.addItems(STATES)
        if self.employee is not None:
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

        self.idEdit = QLineEdit(f"{entry if entry is not None else randID()}")
        self.lastNameEdit = QLineEdit(f"{employee.lastName if employee is not None else ""}")
        self.firstNameEdit = QLineEdit(f"{employee.firstName if employee is not None else ""}")
        self.roleEdit = QLineEdit(f"{employee.role if employee is not None else ""}")
        self.addressLine1Edit = QLineEdit(f"{employee.addressLine1 if employee is not None else ""}")
        self.addressLine2Edit = QLineEdit(f"{employee.addressLine2 if employee is not None else ""}")
        self.addressCityEdit = QLineEdit(f"{employee.addressCity if employee is not None else ""}")
        self.addressZipEdit = QLineEdit(f"{employee.addressZip if employee is not None else ""}")
        self.addressTelEdit = QLineEdit(f"{employee.addressTel if employee is not None else ""}")
        self.addressEmailEdit = QLineEdit(f"{employee.addressEmail if employee is not None else ""}")
        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        self.mainLayout = [
            [QLabel("ID Number:"), self.idEdit],
            [
                QLabel("Last Name:"), self.lastNameEdit,
                QLabel("First Name:"), self.firstNameEdit
            ],
            [QLabel("Role:"), self.roleEdit],
            [QLabel("Shift:"), self.shift, QLabel("Full Time:"), self.fullTime],
            [QLabel("Address Line 1:"), self.addressLine1Edit],
            [QLabel("Address Line 2:"), self.addressLine2Edit],
            [
                QLabel("City:"), self.addressCityEdit,
                QLabel("State:"), self.states,
                QLabel("ZIP:"), self.addressZipEdit
            ],
            [QLabel("Telephone:"), self.addressTelEdit],
            [QLabel("Email:"), self.addressEmailEdit],
            [QLabel("Anniversary:"), self.calendar],
            [self.updateButton, self.createButton],
        ]

        widgetFromList(self, self.mainLayout)
        if employee is not None:
            self.updateButton.clicked.connect(self.updateEmployee)
        else:
            self.updateButton.setEnabled(False)
        self.createButton.clicked.connect(self.newEmployee)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        id = int(checkInput(self.idEdit.text(), int, "nonneg", errors, "ID Number"))
        if id in self.mainApp.db.employees:
            if isNew or (self.employee is not None and not id == self.employee.idNum):
                errors.append(f"Employee number '{id}' already in use")
        lastName = self.lastNameEdit.text()
        if lastName == "":
            errors.append(f"Employee last name is blank")
        firstName = self.firstNameEdit.text()
        if firstName == "":
            errors.append(f"Employee first name is blank")
        role = self.roleEdit.text()
        if role == "":
            errors.append(f"Employee role is blank")
        addressLine1 = self.addressLine1Edit.text()
        if addressLine1 == "":
            errors.append(f"Employee address is blank")
        addressLine2 = self.addressLine2Edit.text()
        addressCity = self.addressCityEdit.text()
        if addressCity == "":
            errors.append(f"Employee city is blank")
        addressState = self.states.currentText()
        addressZip = self.addressZipEdit.text()
        if addressZip == "":
            errors.append(f"Employee ZIP is blank")
        addressTel = self.addressTelEdit.text()
        addressEmail = self.addressEmailEdit.text()
        if addressTel == "" and addressEmail == "":
            errors.append(f"Employee telephone and email are both blank")

        if len(errors) == 0:
            isNone = self.employee is None
            if isNew:
                employee = Employee()
                self.employee = employee
                employee.setID(id)
                self.mainApp.db.addEmployee(employee)
                self.mainApp.db.addEmployeeReviews(EmployeeReviewsDB(id))
                self.mainApp.db.addEmployeeTraining(EmployeeTrainingDB(id))
                self.mainApp.db.addEmployeePoints(EmployeePointsDB(id))
                self.mainApp.db.addEmployeePTO(EmployeePTODB(id))
                self.mainApp.db.addEmployeeNotes(EmployeeNotesDB(id))
            else:
                if self.employee is None:
                    raise RuntimeError('self.employee is None despite not isNew')
                employee = self.employee
                if employee.idNum is None:
                    raise RuntimeError('employee.idNum is None')
                self.mainApp.db.updateEmployee(employee.idNum, id)
            employee.setName(lastName, firstName)
            logging.debug(self.calendar.selectedDate())
            employee.setAnniversary(fromQDate(self.calendar.selectedDate()))
            employee.setStatus(self.active)
            employee.setJob(role, int(self.shift.currentText()), self.fullTime.currentText() == "True")
            employee.setAddress(addressLine1, addressLine2, addressCity, addressState, addressZip, addressTel, addressEmail)
            if isNone:
                self.employee = None
            self.mainApp.overviewTab.refresh()
            self.mainApp.employeesTab.activeEmployeesTab.refreshTable()
            self.mainApp.employeesTab.inactiveEmployeesTab.refreshTable()
            res = True
        else:
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.employee.idNum if self.employee is not None else "New Employee"}")
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