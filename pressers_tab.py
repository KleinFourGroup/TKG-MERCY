from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox, QMessageBox
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from records import Presser
from production_tab import _employeeLabel
from error import errorMessage
from utils import checkInput, centerOnScreen
import logging


def _presserLabel(db, employeeId):
    # Friendly label for a presser row / message. Falls back to a visible
    # "(missing #id)" if the referenced employee is gone — the FK is cascaded on
    # employee delete (Database.delEmployee), so this should normally not happen.
    emp = db.employees.get(employeeId)
    return _employeeLabel(emp) if emp is not None else f"(missing #{employeeId})"


class PressersTab(QWidget):
    # Flat CRUD list of pressers (Production Scheduling, Step 44). A presser is an
    # employee (FK -> employees.idNum) plus a per-shift press capacity; the shift
    # itself comes from Employee.shift. Keyed by employeeId; nothing references a
    # presser yet, so delete is unconditional. Lives under "Production and
    # Scheduling" -> "Scheduling config" -> "Pressers".
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        # Column 0 of the table is the (unique) employee label; map it back to the
        # employeeId key so edit/delete operate on the stable key, not the label.
        self._idByLabel: dict[str, int] = {}
        self.genTableData()
        self.table = DBTable(self.data, self.headers)
        self.table.parentTab = self  # type: ignore

        self.selection: list[int] = []
        self.selectLabel = QLabel("Selection: N/A")

        edit = QPushButton("Edit")
        edit.clicked.connect(self.openEdits)
        new = QPushButton("New")
        new.clicked.connect(self.openNew)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.deleteSelection)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(edit)
        barLayout.addWidget(new)
        barLayout.addWidget(delete)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)

    def genTableData(self):
        db = self.mainApp.db
        self.headers = ["Employee", "Hours/Shift"]
        self._idByLabel = {}
        rows = []
        for empId, presser in db.pressers.items():
            label = _presserLabel(db, empId)
            self._idByLabel[label] = empId
            rows.append([label, f"{presser.hoursPerShift}"])
        rows.sort(key=lambda row: row[0])
        self.data = rows

    def setSelection(self, selection):
        # DBTable hands back column-0 strings (employee labels). Map them to
        # employeeIds — the stable key edit/delete operate on.
        self.selection = [self._idByLabel[label] for label in selection if label in self._idByLabel]
        if self.selection:
            labels = [_presserLabel(self.mainApp.db, e) for e in self.selection]
            self.selectLabel.setText(f"Selection: {", ".join(labels)}")
        else:
            self.selectLabel.setText("Selection: N/A")

    def openEdits(self):
        for empId in self.selection:
            logging.debug(empId)
            PresserEditWindow(empId, self.mainApp)

    def openNew(self):
        if len(self.mainApp.db.employees) == 0:
            errorMessage(self.mainApp, ["Cannot add a presser: no employees in the database."])
            return
        PresserEditWindow(None, self.mainApp)

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No presser selected."])
        for empId in self.selection:
            label = _presserLabel(self.mainApp.db, empId)
            confirm = QMessageBox.question(self, f"Delete {label}?", f"Are you sure you want to delete presser {label}?")
            if confirm == QMessageBox.StandardButton.Yes:
                self.mainApp.db.delPresser(empId)
                self.mainApp.refreshAllViews()
                QMessageBox.information(self.mainApp, "Success!", f"Deleted presser {label}")

    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.data)
        surviving = set(self.selection) & set(self.mainApp.db.pressers)
        labels = [label for label, empId in self._idByLabel.items() if empId in surviving]
        self.setSelection(labels)


class PresserEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp

        item = self.mainApp.db.pressers[entry] if entry is not None else None
        self.item = item
        self.setWindowTitle(
            f"Edit: {_presserLabel(mainApp.db, entry) if entry is not None else "New Presser"}"
        )

        # --- employee dropdown (FK -> employees.idNum) ---
        self.employeeCombo = QComboBox()
        self.employeeCombo.setEditable(False)
        emps = list(self.mainApp.db.employees.values())
        emps.sort(key=lambda e: (0 if e.status else 1,
                                 (e.lastName or "").lower(),
                                 (e.firstName or "").lower()))
        for emp in emps:
            suffix = "" if emp.status else " [inactive]"
            self.employeeCombo.addItem(_employeeLabel(emp) + suffix, userData=emp.idNum)
        if item is not None:
            for i in range(self.employeeCombo.count()):
                if self.employeeCombo.itemData(i) == item.employeeId:
                    self.employeeCombo.setCurrentIndex(i)
                    break

        self.hoursEdit = QLineEdit(f"{item.hoursPerShift}" if item is not None else "")

        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        employeeLayout = QHBoxLayout()
        employeeLayout.addWidget(QLabel("Employee:"))
        employeeLayout.addWidget(self.employeeCombo)

        hoursLayout = QHBoxLayout()
        hoursLayout.addWidget(QLabel("Hours per shift:"))
        hoursLayout.addWidget(self.hoursEdit)

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.updateButton)
        buttonLayout.addWidget(self.createButton)

        layout = QVBoxLayout()
        layout.addLayout(employeeLayout)
        layout.addLayout(hoursLayout)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        # Create stays enabled on an Edit window (pre-populate-then-create-variant
        # shortcut the team relies on); only Update is gated to the edit case.
        if item is not None:
            self.updateButton.clicked.connect(self.updatePresser)
        else:
            self.updateButton.setEnabled(False)
        self.createButton.clicked.connect(self.newPresser)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        empId = self.employeeCombo.currentData()
        if empId is None:
            errors.append("No employee selected.")
        elif empId not in self.mainApp.db.employees:
            errors.append(f"Employee {empId} no longer exists.")
        hours = checkInput(self.hoursEdit.text(), float, "pos", errors, "Hours per shift")
        # employeeId is the PK: an employee can be a presser only once. Reject a
        # collision on New, or on Edit when the employee is changed to one that is
        # already a presser.
        if empId is not None and empId in self.mainApp.db.pressers:
            if isNew or (self.item is not None and not empId == self.item.employeeId):
                errors.append(f"{_presserLabel(self.mainApp.db, empId)} is already a presser.")

        if len(errors) == 0:
            isNone = self.item is None
            if isNew:
                self.item = Presser(empId, hours)
                self.mainApp.db.addPresser(self.item)
            else:
                if self.item is None:
                    raise RuntimeError('self.item is None')
                self.mainApp.db.updatePresser(self.item.employeeId, empId)
                self.item.hoursPerShift = hours
            if isNone:
                self.item = None
            self.mainApp.refreshAllViews()
            res = True
        else:
            errorMessage(self, errors)
        self.setWindowTitle(
            f"Edit: {_presserLabel(self.mainApp.db, self.item.employeeId) if self.item is not None else "New Presser"}"
        )
        return res

    def updatePresser(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()

    def newPresser(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()
