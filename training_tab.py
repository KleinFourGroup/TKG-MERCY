import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox
from PySide6.QtCore import QDate, Qt
import random
import math

from table import DBTable
from app import MainWindow
from employee_detail_tab import EmployeeDetailTab
from records import Employee, EmployeeTrainingDate, EmployeeTrainingDB
from defaults import POINT_VALS
from error import errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, centerOnScreen

class TrainingTab(QWidget):
    def __init__(self, mainTab: EmployeeDetailTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        
        self.currentTraining = "None"
        self.trainingOptions = ["None"]

        self.currentEmployee: Employee | None = None
        self.currentEmployeeTraining: EmployeeTrainingDB | None = None
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
        self.tableData = []
        if db is not None and self.currentTraining in db.training:
            for entry, td in db.training[self.currentTraining].items():
                self.tableData.append([
                    entry.isoformat(),
                    "{}".format(td.comment)
                ])
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

        if self.currentEmployeeTraining is not None and not self.currentTraining == "None":
            self.trainingLabel.setText(f"Training: {self.currentTraining}")
        else:
            self.trainingLabel.setText("Training: N/A")
        
        self.refreshTrainingTab()
    
    def refreshPicker(self):
        self.trainingOptions = ["None"]
        if self.currentEmployeeTraining is not None:
            self.trainingOptions.extend(list(self.currentEmployeeTraining.training.keys()))

        oldTraining = self.currentTraining
        self.trainingPicker.clear()
        self.trainingPicker.addItems(self.trainingOptions)

        if not oldTraining in self.trainingOptions:
            oldTraining = "None"
        self.trainingPicker.setCurrentText(oldTraining)
    
    def setEmployee(self, employeeID: int | None):
        self.currentEmployee = None if employeeID is None else self.mainApp.db.employees[employeeID]
        self.currentEmployeeTraining = None if employeeID is None else self.mainApp.db.training[employeeID]

        if self.currentEmployee is not None:
            lastName = (self.currentEmployee.lastName or "?").upper()
            firstName = self.currentEmployee.firstName or "?"
            self.currentEmployeeLabel.setText(f"Employee: {lastName} {firstName} ({self.currentEmployee.idNum})")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")

        self.refreshPicker()
    
    def refreshTrainingTab(self):
        self.genTableData()
        self.table.setData(self.tableData)

        dateDict: dict[datetime.date, EmployeeTrainingDate] = self.currentEmployeeTraining.training[self.currentTraining] if self.currentEmployeeTraining is not None and self.currentTraining in self.currentEmployeeTraining.training else {}
        selection = [entry.isoformat() for entry in self.selection if entry in dateDict]
        self.setSelection(selection)

        self.newB.setEnabled(self.currentEmployee is not None and not self.currentTraining == "None")
        self.editB.setEnabled(self.currentEmployee is not None and not self.currentTraining == "None")
        self.deleteB.setEnabled(self.currentEmployee is not None and not self.currentTraining == "None")
    
    def openNew(self):
        if self.currentEmployeeTraining is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        TrainingEditWindow(self.currentEmployeeTraining.idNum, self.currentTraining, None, self.mainApp)

    def openEdits(self):
        if self.currentEmployeeTraining is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
            return
        for date in self.selection:
            TrainingEditWindow(self.currentEmployeeTraining.idNum, self.currentTraining, self.currentEmployeeTraining.training[self.currentTraining][date], self.mainApp)

    def deleteTraining(self):
        if self.currentEmployeeTraining is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
            return
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
    def __init__(self, employeeID, trainingType: str, trainingDate: EmployeeTrainingDate | None, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
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
        self.isNew = trainingDate is None

        self.calendar = QCalendarWidget()
        self.comment = QLineEdit()

        if trainingDate is not None:
            if trainingDate.date is None:
                raise RuntimeError('trainingDate.date is None')
            if trainingDate.training is None:
                raise RuntimeError('trainingDate.training is None')
            if trainingDate.date not in self.trainingDateDB.training[trainingType]:
                raise RuntimeError('trainingDate.date not in self.trainingDateDB.training[trainingType]')
            if not (trainingDate.training == trainingType):
                raise RuntimeError('trainingDate.training == trainingType')
            if not (trainingDate == self.trainingDateDB.training[trainingDate.training][trainingDate.date]):
                raise RuntimeError('trainingDate == self.trainingDateDB.training[trainingDate.training][trainingDate.date]')
            self.calendar.setSelectedDate(toQDate(trainingDate.date))
            self.comment.setText(trainingDate.comment)

        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        self.mainLayout = [
            [QLabel("Point Date:"), self.calendar],
            [QLabel("Comment:"), self.comment],
            [self.updateButton, self.createButton],
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.updateButton.clicked.connect(self.updateTraining)
        else:
            self.updateButton.setEnabled(False)
        self.createButton.clicked.connect(self.newTraining)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []

        date = fromQDate(self.calendar.selectedDate())
        isSameDate = (
            not isNew
            and self.trainingDate is not None
            and date == self.trainingDate.date
        )
        if date in self.trainingDateDB.training[self.trainingType] and not isSameDate:
            errors.append(f"Employee {self.employeeID} already has training for {self.trainingType} on {date.isoformat()}")

        comment = self.comment.text()

        if len(errors) == 0:
            if isNew:
                trainingDate = EmployeeTrainingDate(self.employeeID, self.trainingType, date, comment)
                self.trainingDate = trainingDate
            else:
                if self.trainingDate is None:
                    raise RuntimeError('self.trainingDate is None despite not isNew')
                if self.trainingDate.date is None:
                    raise RuntimeError('self.trainingDate.date is None')
                del self.trainingDateDB.training[self.trainingType][self.trainingDate.date]
                self.trainingDate.date = date
                self.trainingDate.comment = comment
                trainingDate = self.trainingDate
            self.trainingDateDB.training[self.trainingType][date] = trainingDate

            self.mainApp.overviewTab.trainingTab.refresh()
            res = True
        else:
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
