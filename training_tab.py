import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox
from PySide6.QtCore import QDate
import random
import math

from table import DBTable
from app import MainWindow
from employee_overview_tab import MainTab
from records import Employee, EmployeeTrainingDate, EmployeeTrainingDB
from defaults import POINT_VALS
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate

class TrainingTab(QWidget):
    def __init__(self, mainTab: MainTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        self.windows = []
        
        self.currentTraining = "None"
        self.trainingOptions = ["None"]

        self.currentEmployee: Employee = None
        self.currentEmployeeTraining: EmployeeTrainingDB = None
        self.currentEmployeeLabel = QLabel("Employee: N/A")

        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        self.trainingPicker = QComboBox()
        self.trainingPicker.setEditable(False)
        self.trainingPicker.currentTextChanged.connect(self.setTraining)

        self.trainingLabel = QLabel("Training: N/A")
        topLayout = QHBoxLayout()
        topLayout.addWidget(self.currentEmployeeLabel)
        topLayout.addWidget(self.trainingPicker)
        topLayout.addWidget(self.trainingLabel)

        self.newB = QPushButton("New Training")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Training")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Training")
        self.deleteB.clicked.connect(self.deleteTraining)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)

        layout = QVBoxLayout()
        layout.addLayout(topLayout)
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(barLayout)
        self.setLayout(layout)

        self.refreshPicker()
    
    def genTableData(self):
        db = self.currentEmployeeTraining

        self.headers = ["Date", "Comments"]
        self.tableData = [] if db == None or not self.currentTraining in db.training else [[
            "{}".format(db.training[self.currentTraining][entry].date.isoformat()),
            "{}".format(db.training[self.currentTraining][entry].comment)

        ] for entry in db.training[self.currentTraining]]
        self.tableData.sort(key=lambda row: row[0])
    
    def setSelection(self, selection):
        self.selection = list(map(lambda x: datetime.date.fromisoformat(x), selection))
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def setTraining(self, pick: str):
        # print(f"Set training to {pick}!")
        if pick in self.trainingOptions:
            self.currentTraining = pick
        else:
            self.currentTraining = "None"

        if not self.currentEmployeeTraining == None and not self.currentTraining == "None":
            self.trainingLabel.setText(f"Training: {self.currentTraining}")
        else:
            self.trainingLabel.setText("Training: N/A")
        
        self.refreshTrainingTab()
    
    def refreshPicker(self):
        self.trainingOptions = ["None"]
        if not self.currentEmployee == None:
            self.trainingOptions.extend(list(self.currentEmployeeTraining.training.keys()))

        oldTraining = self.currentTraining
        self.trainingPicker.clear()
        self.trainingPicker.addItems(self.trainingOptions)

        if not oldTraining in self.trainingOptions:
            oldTraining = "None"
        self.trainingPicker.setCurrentText(oldTraining)
    
    def setEmployee(self, employeeID: int):
        self.currentEmployee = None if employeeID == None else self.mainApp.db.employees[self.mainTab.employeeID] 
        self.currentEmployeeTraining = None if employeeID == None else self.mainApp.db.training[self.mainTab.employeeID]
        
        if not self.currentEmployee == None:
            self.currentEmployeeLabel.setText(f"Employee: {self.currentEmployee.lastName.upper()} {self.currentEmployee.firstName} ({self.currentEmployee.idNum})")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")
        
        self.refreshPicker()
    
    def refreshTrainingTab(self):
        self.genTableData()
        self.table.setData(self.tableData)

        dateDict: dict[datetime.date, EmployeeTrainingDate] = self.currentEmployeeTraining.training[self.currentTraining] if not self.currentEmployeeTraining == None and self.currentTraining in self.currentEmployeeTraining.training else {}
        selection = [entry.isoformat() for entry in self.selection if entry in dateDict]
        self.setSelection(selection)

        self.newB.setEnabled(not self.currentEmployee == None and not self.currentTraining == "None")
        self.editB.setEnabled(not self.currentEmployee == None and not self.currentTraining == "None")
        self.deleteB.setEnabled(not self.currentEmployee == None and not self.currentTraining == "None")
    
    def openNew(self):
        self.windows.append(TrainingEditWindow(self.currentEmployeeTraining.idNum, self.currentTraining, None, self.mainApp))
    
    def openEdits(self):
        pass
        # self.windows.append(EmployeeEditWindow(None, self.mainApp, self.active))
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
        for date in self.selection:
            self.windows.append(TrainingEditWindow(self.currentEmployeeTraining.idNum, self.currentTraining, self.currentEmployeeTraining.training[self.currentTraining][date], self.mainApp))
    
    def deleteTraining(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
        for date in self.selection:
            confirm = QMessageBox.question(self, f"Delete {date.isoformat()}?", f"Are you sure you want to delete the training for {self.currentTraining} on {date.isoformat()}?")

            if confirm == QMessageBox.StandardButton.Yes:
                del self.currentEmployeeTraining.training[self.currentTraining][date]
                QMessageBox.information(self.mainApp, "Success", f"{date.isoformat()} successfully deleted!")
        self.refresh()
    
    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshTrainingTab()

class TrainingEditWindow(QWidget):
    def __init__(self, employeeID, trainingType: str, trainingDate: EmployeeTrainingDate, mainApp: MainWindow):
        super().__init__()
        if employeeID is None:
            raise RuntimeError('employeeID is None')
        self.mainApp = mainApp
        self.setWindowTitle(f"Training ({trainingType}): {employeeID}")
        self.employeeID = employeeID
        self.trainingType = trainingType

        self.trainingDateDB = self.mainApp.db.training[employeeID]
        if self.trainingDateDB is None:
            raise RuntimeError('self.trainingDateDB is None')

        self.trainingDate = trainingDate
        self.isNew = trainingDate == None
        if not self.isNew:
            if trainingDate.date not in self.trainingDateDB.training[trainingType]:
                raise RuntimeError('trainingDate.date not in self.trainingDateDB.training[trainingType]')
            if not (trainingDate.training == trainingType):
                raise RuntimeError('trainingDate.training == trainingType')
            if not (trainingDate == self.trainingDateDB.training[trainingDate.training][trainingDate.date]):
                raise RuntimeError('trainingDate == self.trainingDateDB.training[trainingDate.training][trainingDate.date]')

        self.calendar = QCalendarWidget()
        if not self.isNew:
            self.calendar.setSelectedDate(toQDate(self.trainingDate.date))
        
        self.comment = QLineEdit()
        if not self.isNew:
            self.comment.setText(self.trainingDate.comment)

        self.mainLayout = [
            [
                QLabel("Point Date:"), self.calendar
            ],
            [
                QLabel("Comment:"), self.comment
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.mainLayout[-1][0].clicked.connect(self.updateTraining)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newTraining)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        
        date = fromQDate(self.calendar.selectedDate())
        if date in self.trainingDateDB.training[self.trainingType] and not (not isNew and date == self.trainingDate.date):
            errors.append(f"Employee {self.employeeID} already has training for {self.trainingType} on {date.isoformat()}")
        
        comment = self.comment.text()

        if len(errors) == 0:
            if isNew:
                self.trainingDate = EmployeeTrainingDate(self.employeeID, self.trainingType, date, comment)
            if not isNew:
                del self.trainingDateDB.training[self.trainingType][self.trainingDate.date]
                self.trainingDate.date = date
                self.trainingDate.comment = comment
            self.trainingDateDB.training[self.trainingType][self.trainingDate.date] = self.trainingDate

            self.mainApp.overviewTab.trainingTab.refresh()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        return res
    
    def newTraining(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", f"Training for {self.trainingType} added successful!")
            self.close()
    
    def updateTraining(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", f"Training for {self.trainingType} updated successful!")
            self.close()
