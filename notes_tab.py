import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QTextEdit, QFileDialog, QTimeEdit
from PySide6.QtCore import QTime, Qt
import os

from table import DBTable
from app import MainWindow
from employee_overview_tab import MainTab
from records import Employee, EmployeeNote, EmployeeNotesDB
from error import errorMessage
from utils import widgetFromList, toQDate, fromQDate, startfile
from report import PDFReport

class NotesTab(QWidget):
    def __init__(self, mainTab: MainTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp

        self.currentEmployee: Employee = None
        self.currentEmployeeNotes: EmployeeNotesDB = None
        self.currentEmployeeLabel = QLabel("Employee: N/A")

        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        topLayout = QHBoxLayout()
        topLayout.addWidget(self.currentEmployeeLabel)

        self.newB = QPushButton("New Note")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Note")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Note")
        self.deleteB.clicked.connect(self.deleteNotes)
        self.reportB = QPushButton("Generate Summary Report")
        self.reportB.clicked.connect(self.report)
        self.incidentReportB = QPushButton("Generate Incident Report")
        self.incidentReportB.clicked.connect(self.incidentReport)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)
        barLayout.addWidget(self.reportB)
        barLayout.addWidget(self.incidentReportB)

        layout = QVBoxLayout()
        layout.addLayout(topLayout)
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(barLayout)
        self.setLayout(layout)

    def genTableData(self):
        db = self.currentEmployeeNotes
        self.headers = ["Date & Time", "Details"]
        self.tableData = [] if db == None else [[
            f"{note.date.isoformat()} {note.time}",
            "{}".format(note.details[:60] + "..." if len(note.details) > 60 else note.details)
        ] for note in db.notes.values()]
        self.tableData.sort(key=lambda row: row[0])

    def setSelection(self, selection):
        parsed = []
        for s in selection:
            parts = s.split(" ", 1)
            if len(parts) == 2:
                parsed.append((datetime.date.fromisoformat(parts[0]), parts[1]))
        self.selection = parsed
        self.selectLabel.setText(f"Selection: {', '.join([f'{d.isoformat()} {t}' for d, t in self.selection])}")

    def setEmployee(self, employeeID: int):
        self.currentEmployee = None if employeeID == None else self.mainApp.db.employees[self.mainTab.employeeID]
        self.currentEmployeeNotes = None if employeeID == None else self.mainApp.db.notes[self.mainTab.employeeID]
        if self.currentEmployee is not None:
            self.currentEmployeeLabel.setText(f"Employee: {self.currentEmployee.lastName.upper()} {self.currentEmployee.firstName} ({self.currentEmployee.idNum})")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")

        self.newB.setEnabled(self.currentEmployee is not None)
        self.editB.setEnabled(self.currentEmployee is not None)
        self.deleteB.setEnabled(self.currentEmployee is not None)
        self.reportB.setEnabled(self.currentEmployee is not None)
        self.incidentReportB.setEnabled(self.currentEmployee is not None)

    def refreshNotes(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [(d, t) for d, t in self.selection if self.currentEmployeeNotes is not None and (d, t) in self.currentEmployeeNotes.notes]
        self.selection = selection
        self.selectLabel.setText(f"Selection: {', '.join([f'{d.isoformat()} {t}' for d, t in self.selection])}" if len(self.selection) > 0 else "Selection: N/A")

    def openNew(self):
        NotesEditWindow(self.currentEmployeeNotes.idNum, None, self.mainApp)

    def openEdits(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No notes selected."])
        for key in self.selection:
            if key in self.currentEmployeeNotes.notes:
                NotesEditWindow(self.currentEmployeeNotes.idNum, self.currentEmployeeNotes.notes[key], self.mainApp)

    def deleteNotes(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No notes selected."])
        for key in self.selection:
            if key in self.currentEmployeeNotes.notes:
                dateStr = f"{key[0].isoformat()} {key[1]}"
                confirm = QMessageBox.question(self, f"Delete {dateStr}?", f"Are you sure you want to delete the note on {dateStr}?")
                if confirm == QMessageBox.StandardButton.Yes:
                    del self.currentEmployeeNotes.notes[key]
                    QMessageBox.information(self.mainApp, "Success", f"Note {dateStr} successfully deleted!")
        self.refresh()

    def report(self):
        if self.currentEmployeeNotes == None:
            errorMessage(self.mainApp, ["No employee selected."])
        else:
            reportFile = QFileDialog.getSaveFileName(self, f"Save {self.currentEmployee.idNum} Notes Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
            if not reportFile[0] == "":
                pdf = PDFReport(self.mainApp.db, reportFile[0])
                pdf.employeeNotesReport(self.currentEmployee.idNum)
                startfile(reportFile[0])

    def incidentReport(self):
        if self.currentEmployeeNotes == None:
            errorMessage(self.mainApp, ["No employee selected."])
        elif len(self.selection) == 0:
            errorMessage(self.mainApp, ["No note selected."])
        elif len(self.selection) > 1:
            errorMessage(self.mainApp, ["Please select only one note for an incident report."])
        else:
            key = self.selection[0]
            if key in self.currentEmployeeNotes.notes:
                reportFile = QFileDialog.getSaveFileName(self, f"Save {self.currentEmployee.idNum} Incident Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
                if not reportFile[0] == "":
                    pdf = PDFReport(self.mainApp.db, reportFile[0])
                    pdf.employeeIncidentReport(self.currentEmployee.idNum, key[0], key[1])
                    startfile(reportFile[0])

    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshNotes()

class NotesEditWindow(QWidget):
    def __init__(self, employeeID, note: EmployeeNote, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if employeeID is None:
            raise RuntimeError('employeeID is None')
        self.mainApp = mainApp
        self.setWindowTitle(f"Note: {employeeID}")
        self.employeeID = employeeID

        self.notesDB = self.mainApp.db.notes[employeeID]
        if self.notesDB is None:
            raise RuntimeError('self.notesDB is None')

        self.note = note
        self.isNew = note == None
        if not self.isNew:
            if (note.date, note.time) not in self.notesDB.notes:
                raise RuntimeError('(note.date, note.time) not in self.notesDB.notes')
            if not (note == self.notesDB.notes[(note.date, note.time)]):
                raise RuntimeError('note == self.notesDB.notes[(note.date, note.time)]')

        self.calendar = QCalendarWidget()
        if not self.isNew:
            self.calendar.setSelectedDate(toQDate(self.note.date))

        self.timeInput = QTimeEdit()
        if not self.isNew:
            if self.note.time is None:
                raise RuntimeError('self.note.time is None')
            hours = int(self.note.time.split(":")[0])
            minutes = int(self.note.time.split(":")[1])
            self.timeInput.setTime(QTime(hours, minutes))

        self.detailsInput = QTextEdit()
        if not self.isNew:
            self.detailsInput.setPlainText(self.note.details)

        self.mainLayout = [
            [
                QLabel("Date:"), self.calendar
            ],
            [
                QLabel("Time:"), self.timeInput
            ],
            [
                QLabel("Details:"), self.detailsInput
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.mainLayout[-1][0].clicked.connect(self.updateNote)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newNote)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []

        date = fromQDate(self.calendar.selectedDate())
        qTime = self.timeInput.time()
        timeStr = f"{qTime.hour()}:{qTime.minute()}"

        # Validate time format
        timeParts = timeStr.split(":")
        if len(timeParts) != 2:
            errors.append("Time must be in HH:MM format")
        else:
            try:
                hours = int(timeParts[0])
                minutes = int(timeParts[1])
                if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
                    errors.append("Time must be valid (00:00 - 23:59)")
                else:
                    timeStr = f"{hours:02d}:{minutes:02d}"
            except ValueError:
                errors.append("Time must be in HH:MM format with numeric values")

        if (date, timeStr) in self.notesDB.notes and not (not isNew and (date, timeStr) == (self.note.date, self.note.time)):
            errors.append(f"Employee {self.employeeID} already has a note on {date.isoformat()} {timeStr}")

        details = self.detailsInput.toPlainText()

        if len(errors) == 0:
            if isNew:
                self.note = EmployeeNote(self.employeeID, date, timeStr, details)
            if not isNew:
                del self.notesDB.notes[(self.note.date, self.note.time)]
                self.note.date = date
                self.note.time = timeStr
                self.note.details = details
            self.notesDB.notes[(self.note.date, self.note.time)] = self.note

            self.mainApp.overviewTab.notesTab.refresh()
            res = True
        else:
            errorMessage(self, errors)
        return res

    def newNote(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Note added successfully!")
            self.close()

    def updateNote(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Note updated successfully!")
            self.close()
