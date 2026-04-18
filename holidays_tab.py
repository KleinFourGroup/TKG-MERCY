import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox
from PySide6.QtCore import QDate, Qt
import random
import math

from table import DBTable
from app import MainWindow
from employee_overview_tab import MainTab
from records import Database, ObservancesDB, HolidayObservance
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate

from defaults import HOLIDAYS

from app import MainWindow

def createTab():
    tab = QWidget()
    label = QLabel("TODO")
    layout = QVBoxLayout(tab)
    layout.addWidget(label)
    tab.setLayout(layout)
    return tab

class HolidayTab(QWidget):
    def __init__(self, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp

        # Create a QTabWidget
        self.tab_widget = QTabWidget()

        # Add tabs to the QTabWidget
        self.observancesTab = ObservancesTab(self)
        self.tab_widget.addTab(self.observancesTab, "Observances")
        self.defaultsTab = DefaultHolidaysTab(self)
        self.tab_widget.addTab(self.defaultsTab, "Defaults")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tab_widget)

        # Set the layout for the main window
        self.setLayout(layout)

    def refresh(self):
        self.observancesTab.refresh()
        self.defaultsTab.refresh()

class ObservancesTab(QWidget):
    def __init__(self, holidayTab: HolidayTab) -> None:
        super().__init__()
        self.holidayTab = holidayTab
        self.mainApp = self.holidayTab.mainApp
        self.observancesDB = self.mainApp.db.holidays
        
        self.currentYear = datetime.date.today().year

        self.decYearB = QPushButton("<")
        self.curYearB = QPushButton(f"{self.currentYear}")
        self.incYearB = QPushButton(">")

        self.decYearB.clicked.connect(self.decYear)
        self.incYearB.clicked.connect(self.incYear)

        self.curYearB.clicked.connect(self.openYear)

        self.topLayout = QHBoxLayout()
        self.topLayout.addWidget(self.decYearB)
        self.topLayout.addWidget(self.curYearB)
        self.topLayout.addWidget(self.incYearB)

        self.selectLayout = QVBoxLayout()
        self.observanceRows = []
        self.buildRows()
        

        layout = QVBoxLayout()
        layout.addLayout(self.topLayout)
        layout.addLayout(self.selectLayout)
        self.setLayout(layout)

    def buildRows(self):
        if not (len(self.observanceRows) == 0):
            raise RuntimeError('len(self.observanceRows) == 0')
        for holiday in self.observancesDB.getHolidays(self.currentYear):
            barLayout = QHBoxLayout()
            label = QLabel(f"{holiday}")
            date1 = QLabel(f"Shift 1: {"N/A" if self.observancesDB.getObservance(self.currentYear, holiday, 1) == None else self.observancesDB.getObservance(self.currentYear, holiday, 1).isoformat()}")
            select1 = QPushButton("Select")
            clear1 = QPushButton("Clear")
            select1.clicked.connect(self.setObservanceFn(holiday, 1))
            clear1.clicked.connect(self.delObservanceFn(holiday, 1))
            date2 = QLabel(f"Shift 2: {"N/A" if self.observancesDB.getObservance(self.currentYear, holiday, 2) == None else self.observancesDB.getObservance(self.currentYear, holiday, 2).isoformat()}")
            select2 = QPushButton("Select")
            clear2 = QPushButton("Clear")
            select2.clicked.connect(self.setObservanceFn(holiday, 2))
            clear2.clicked.connect(self.delObservanceFn(holiday, 2))
            date3 = QLabel(f"Shift 3: {"N/A" if self.observancesDB.getObservance(self.currentYear, holiday, 3) == None else self.observancesDB.getObservance(self.currentYear, holiday, 3).isoformat()}")
            select3 = QPushButton("Select")
            clear3 = QPushButton("Clear")
            select3.clicked.connect(self.setObservanceFn(holiday, 3))
            clear3.clicked.connect(self.delObservanceFn(holiday, 3))
            barLayout.addWidget(label)
            barLayout.addWidget(date1)
            barLayout.addWidget(select1)
            barLayout.addWidget(clear1)
            barLayout.addWidget(date2)
            barLayout.addWidget(select2)
            barLayout.addWidget(clear2)
            barLayout.addWidget(date3)
            barLayout.addWidget(select3)
            barLayout.addWidget(clear3)
            self.selectLayout.addLayout(barLayout)
            self.observanceRows.append([holiday, label, date1, select1, clear1, date2, select2, clear2, date3, select3, clear3, barLayout])

    def decYear(self):
        self.currentYear -= 1
        self.refresh()

    def incYear(self):
        self.currentYear += 1
        self.refresh()
    
    def openYear(self):
        YearSelectWindow(self, self.mainApp)
    
    def setObservanceFn(self, holiday, shift):
        def callback():
            ObservanceSelectWindow(self, self.currentYear, holiday, shift, self.mainApp)
        return callback
    
    def delObservanceFn(self, holiday, shift):
        def callback():
            self.observancesDB.delObservance(self.currentYear, holiday, shift)
            self.refresh(False)
        return callback
    
    def refreshRows(self, hard = True):
        if hard:
            while self.selectLayout.count() > 0:
                row = self.selectLayout.takeAt(0)
                while row.layout().count() > 0:
                    widget = row.layout().takeAt(0)
                    widget.widget().setParent(None)
            self.observanceRows = []
            self.buildRows()
        else:
            for row in self.observanceRows:
                holiday: str = row[0]
                date: QPushButton = row[2]
                date.setText(f"Shift 1: {"N/A" if self.observancesDB.getObservance(self.currentYear, holiday, 1) == None else self.observancesDB.getObservance(self.currentYear, holiday, 1).isoformat()}")
                date: QPushButton = row[5]
                date.setText(f"Shift 2: {"N/A" if self.observancesDB.getObservance(self.currentYear, holiday, 2) == None else self.observancesDB.getObservance(self.currentYear, holiday, 2).isoformat()}")
                date: QPushButton = row[8]
                date.setText(f"Shift 3: {"N/A" if self.observancesDB.getObservance(self.currentYear, holiday, 3) == None else self.observancesDB.getObservance(self.currentYear, holiday, 3).isoformat()}")
    
    def refresh(self, hard = True):
        self.observancesDB = self.mainApp.db.holidays
        self.curYearB.setText(f"{self.currentYear}")
        self.refreshRows(hard)

class YearSelectWindow(QWidget):
    def __init__(self, observanceTab: ObservancesTab, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.observanceTab = observanceTab
        self.setWindowTitle(f"Select Observance Year")

        self.yearEntry = QLineEdit(f"{self.observanceTab.currentYear}")

        self.mainLayout = [
            [
                QLabel("Year:"), self.yearEntry
            ],
            [
                QPushButton("Select")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        self.mainLayout[-1][0].clicked.connect(self.readData)
        self.show()

    def readData(self):
        errors = []
        
        year = checkInput(self.yearEntry.text(), int, "pos", errors, "Year")

        if len(errors) == 0:
            self.observanceTab.currentYear = year
            QMessageBox.information(self, "Success", "Year updated successful!")
            self.observanceTab.refresh()
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.close()

class ObservanceSelectWindow(QWidget):
    def __init__(self, observanceTab: ObservancesTab, year: int, holiday: str, shift: int, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.observanceTab = observanceTab
        self.observancesDB = observanceTab.observancesDB
        self.year = year
        self.holiday = holiday
        self.shift = shift
        self.setWindowTitle(f"Select {year} observance: {holiday} (shift {shift})")

        self.calendar = QCalendarWidget()
        date = self.observancesDB.getObservance(year, holiday, shift)
        if date == None:
            date = datetime.date(year=year, month=self.observancesDB.getDefault(holiday), day=1)
        self.calendar.setSelectedDate(toQDate(date))

        self.mainLayout = [
            [
                QLabel("Observance:"), self.calendar
            ],
            [
                QPushButton("Select")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        self.mainLayout[-1][0].clicked.connect(self.readData)
        self.show()

    def readData(self):
        errors = []
        
        date = fromQDate(self.calendar.selectedDate())
        if not date.year == self.year:
            errors.append(f"Observance must be in {self.year}")

        if len(errors) == 0:
            observance = HolidayObservance(self.holiday, date, self.shift)
            self.observancesDB.setObservance(observance)
            QMessageBox.information(self, "Success", "Observance updated successful!")
            self.observanceTab.refresh(False)
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.close()


class DefaultHolidaysTab(QWidget):
    def __init__(self, holidayTab: HolidayTab) -> None:
        super().__init__()
        self.holidayTab = holidayTab
        self.mainApp = self.holidayTab.mainApp
        self.observancesDB = self.mainApp.db.holidays

        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        self.newB = QPushButton("New Holiday")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Holiday")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Holiday")
        self.deleteB.clicked.connect(self.deleteHolidays)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.observancesDB
        self.headers = ["Holiday", "Month"]
        self.tableData = [] if db == None else [[
            "{}".format(entry),
            "{}".format(db.defaults[entry])
        ] for entry in db.defaults]
        self.tableData.sort(key=lambda row: (int(row[1]), row[0]))
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def openNew(self):
        HolidayEditWindow(self, None, self.mainApp)
    
    def openEdits(self):
        pass
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No holidays selected."])
        for holiday in self.selection:
            HolidayEditWindow(self, holiday, self.mainApp)
    
    def deleteHolidays(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No holidays selected."])
        for holiday in self.selection:
            confirm = QMessageBox.question(self, f"Delete {holiday}?", f"Are you sure you want to delete the holiday on {holiday}?")

            if confirm == QMessageBox.StandardButton.Yes:
                del self.observancesDB.defaults[holiday]
                QMessageBox.information(self.mainApp, "Success", f"{holiday} successfully deleted!")
        self.refresh()
    
    def refresh(self):
        self.observancesDB = self.mainApp.db.holidays
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [entry for entry in self.selection if entry in self.observancesDB.defaults]
        self.setSelection(selection)

class HolidayEditWindow(QWidget):
    def __init__(self, defaultsTab: DefaultHolidaysTab, holiday: str, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.defaultsTab = defaultsTab
        self.observancesDB = defaultsTab.observancesDB
        self.holiday = holiday
        self.setWindowTitle(f"Holiday: {holiday if holiday is not None else "New"}")


        self.isNew = holiday == None
        if not self.isNew:
            if holiday not in self.observancesDB.defaults:
                raise RuntimeError('holiday not in self.observancesDB.defaults')
        
        self.holidayName = QLineEdit(holiday if not self.isNew else "")

        self.holidayMonth = QComboBox()
        self.holidayMonth.setEditable(False)
        self.holidayMonth.addItems([str(num + 1) for num in range(12)])
        if not self.isNew:
            self.holidayMonth.setCurrentText(str(self.observancesDB.defaults[self.holiday]))

        self.mainLayout = [
            [
                QLabel("Holiday:"), self.holidayName, QLabel("Month:"), self.holidayMonth
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.mainLayout[-1][0].clicked.connect(self.updateHoliday)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newHoliday)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        
        holiday = self.holidayName.text()
        if isNew and holiday in self.observancesDB.defaults:
            errors.append(f"Holiday \"{holiday}\" already exists!")
        month = int(self.holidayMonth.currentText())

        if len(errors) == 0:
            if not isNew:
                del self.observancesDB.defaults[holiday]
            self.observancesDB.defaults[holiday] = month

            self.defaultsTab.refresh()
            self.defaultsTab.holidayTab.observancesTab.refresh()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        return res
    
    def newHoliday(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Holiday added successful!")
            self.close()
    
    def updateHoliday(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Holiday updated successful!")
            self.close()
