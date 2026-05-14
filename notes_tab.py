import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QTextEdit, QTimeEdit
from PySide6.QtCore import QTime, Qt

from table import DBTable
from app import MainWindow
from employee_detail_tab import EmployeeDetailTab
from records import Employee, EmployeeNote, EmployeeNotesDB
from error import errorMessage
from utils import widgetFromList, toQDate, fromQDate, startfile, tempReportPath, centerOnScreen
from report import PDFReport

class NotesTab(QWidget):
    def __init__(self, mainTab: EmployeeDetailTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp

        self.currentEmployee: Employee | None = None
        self.currentEmployeeNotes: EmployeeNotesDB | None = None
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
        self.tableData = []
        if db is not None:
            for note in db.notes.values():
                if note.date is None or note.time is None:
                    raise RuntimeError('note.date or note.time is None')
                self.tableData.append([
                    f"{note.date.isoformat()} {note.time}",
                    "{}".format(note.details[:60] + "..." if len(note.details) > 60 else note.details)
                ])
        self.tableData.sort(key=lambda row: row[0])

    def setSelection(self, selection):
        parsed = []
        for s in selection:
            parts = s.split(" ", 1)
            if len(parts) == 2:
                parsed.append((datetime.date.fromisoformat(parts[0]), parts[1]))
        self.selection = parsed
        self.selectLabel.setText(f"Selection: {', '.join([f'{d.isoformat()} {t}' for d, t in self.selection])}")

    def setEmployee(self, employeeID: int | None):
        self.currentEmployee = None if employeeID is None else self.mainApp.db.employees[employeeID]
        self.currentEmployeeNotes = None if employeeID is None else self.mainApp.db.notes[employeeID]
        if self.currentEmployee is not None:
            lastName = (self.currentEmployee.lastName or "?").upper()
            firstName = self.currentEmployee.firstName or "?"
            self.currentEmployeeLabel.setText(f"Employee: {lastName} {firstName} ({self.currentEmployee.idNum})")
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
        if self.currentEmployeeNotes is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        NotesEditWindow(self.currentEmployeeNotes.idNum, None, self.mainApp)

    def openEdits(self):
        if self.currentEmployeeNotes is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No notes selected."])
            return
        for key in self.selection:
            if key in self.currentEmployeeNotes.notes:
                NotesEditWindow(self.currentEmployeeNotes.idNum, self.currentEmployeeNotes.notes[key], self.mainApp)

    def deleteNotes(self):
        if self.currentEmployeeNotes is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No notes selected."])
            return
        for key in self.selection:
            if key in self.currentEmployeeNotes.notes:
                dateStr = f"{key[0].isoformat()} {key[1]}"
                confirm = QMessageBox.question(self, f"Delete {dateStr}?", f"Are you sure you want to delete the note on {dateStr}?")
                if confirm == QMessageBox.StandardButton.Yes:
                    del self.currentEmployeeNotes.notes[key]
                    QMessageBox.information(self.mainApp, "Success", f"Note {dateStr} successfully deleted!")
        self.refresh()

    def report(self):
        if self.currentEmployee is None or self.currentEmployeeNotes is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        path = tempReportPath(f"employee-{self.currentEmployee.idNum}-notes")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.employeeNotesReport(self.currentEmployee.idNum)
        startfile(path)

    def incidentReport(self):
        if self.currentEmployee is None or self.currentEmployeeNotes is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No note selected."])
            return
        if len(self.selection) > 1:
            errorMessage(self.mainApp, ["Please select only one note for an incident report."])
            return
        key = self.selection[0]
        if key in self.currentEmployeeNotes.notes:
            path = tempReportPath(f"employee-{self.currentEmployee.idNum}-incident")
            pdf = PDFReport(self.mainApp.db, path)
            pdf.employeeIncidentReport(self.currentEmployee.idNum, key[0], key[1])
            startfile(path)

    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshNotes()

class NotesEditWindow(QWidget):
    def __init__(self, employeeID, note: EmployeeNote | None, mainApp: MainWindow):
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
        self.isNew = note is None

        self.calendar = QCalendarWidget()
        self.timeInput = QTimeEdit()
        self.detailsInput = QTextEdit()

        if note is not None:
            if note.date is None or note.time is None:
                raise RuntimeError('note.date or note.time is None')
            if (note.date, note.time) not in self.notesDB.notes:
                raise RuntimeError('(note.date, note.time) not in self.notesDB.notes')
            if not (note == self.notesDB.notes[(note.date, note.time)]):
                raise RuntimeError('note == self.notesDB.notes[(note.date, note.time)]')
            self.calendar.setSelectedDate(toQDate(note.date))
            hours = int(note.time.split(":")[0])
            minutes = int(note.time.split(":")[1])
            self.timeInput.setTime(QTime(hours, minutes))
            self.detailsInput.setPlainText(note.details)

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
        centerOnScreen(self)
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

        isSameKey = (
            not isNew
            and self.note is not None
            and (date, timeStr) == (self.note.date, self.note.time)
        )
        if (date, timeStr) in self.notesDB.notes and not isSameKey:
            errors.append(f"Employee {self.employeeID} already has a note on {date.isoformat()} {timeStr}")

        details = self.detailsInput.toPlainText()

        if len(errors) == 0:
            if isNew:
                note = EmployeeNote(self.employeeID, date, timeStr, details)
                self.note = note
            else:
                if self.note is None:
                    raise RuntimeError('self.note is None despite not isNew')
                if self.note.date is None or self.note.time is None:
                    raise RuntimeError('self.note.date or self.note.time is None')
                del self.notesDB.notes[(self.note.date, self.note.time)]
                self.note.date = date
                self.note.time = timeStr
                self.note.details = details
                note = self.note
            self.notesDB.notes[(date, timeStr)] = note

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
