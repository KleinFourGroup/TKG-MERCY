from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from records import Press
from error import errorMessage
from utils import centerOnScreen, getComboBox
import logging

# The "no die mounted / idle" option in the current-part combo, and how an idle
# press reads in the list (Step 79). Distinct from a real part name so a blank
# cell can't be mistaken for missing data.
NO_PART_LABEL = "(none)"


class PressesTab(QWidget):
    # Flat CRUD list of presses (Production Scheduling, Step 43). Presses are keyed
    # by unique name; nothing references a press yet, so delete is unconditional.
    # Lives under "Production and Scheduling" -> "Scheduling config" -> "Presses".
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.genTableData()
        self.table = DBTable(self.data, self.headers)
        self.table.parentTab = self  # type: ignore

        self.selection = []
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
        self.headers = ["Press", "Current part"]
        # Current part is the mounted die (Step 79); an idle press (currentPart None)
        # shows NO_PART_LABEL so the daily-tracked die location is visible at a glance.
        self.data = [[name, db.presses[name].currentPart or NO_PART_LABEL] for name in db.presses]
        self.data.sort(key=lambda row: row[0])

    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {", ".join(selection)}")

    def openEdits(self):
        for item in self.selection:
            logging.debug(item)
            PressEditWindow(item, self.mainApp)

    def openNew(self):
        PressEditWindow(None, self.mainApp)

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No press selected."])
        for press in self.selection:
            confirm = QMessageBox.question(self, f"Delete {press}?", f"Are you sure you want to delete {press}?")
            if confirm == QMessageBox.StandardButton.Yes:
                self.mainApp.db.delPress(press)
                self.mainApp.refreshAllViews()
                QMessageBox.information(self.mainApp, "Success!", f"Deleted press {press}")

    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.data)
        selection = [press for press in self.selection if press in self.mainApp.db.presses]
        self.setSelection(selection)


class PressEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry if entry is not None else "New Press"}")

        item = self.mainApp.db.presses[entry] if entry is not None else None
        self.item = item

        self.nameEdit = QLineEdit(f"{entry if entry is not None else ""}")
        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        nameLayout = QHBoxLayout()
        nameLayout.addWidget(QLabel("Press name:"))
        nameLayout.addWidget(self.nameEdit)

        # Current part = the die mounted on this press (Step 79). A "(none)" idle
        # option plus every part name (sorted); prefilled from the record on edit and
        # roundtripped through db.setPressCurrentPart. getComboBox tolerates a stale
        # stored value (Step 61) by appending it so it stays visible.
        parts = [NO_PART_LABEL] + sorted(self.mainApp.db.parts)
        self.currentPartCombo = getComboBox(parts, item.currentPart if item is not None else None)
        currentPartLayout = QHBoxLayout()
        currentPartLayout.addWidget(QLabel("Current part (mounted die):"))
        currentPartLayout.addWidget(self.currentPartCombo)

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.updateButton)
        buttonLayout.addWidget(self.createButton)

        layout = QVBoxLayout()
        layout.addLayout(nameLayout)
        layout.addLayout(currentPartLayout)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        # Create stays enabled on an Edit window (pre-populate-then-create-variant
        # shortcut the team relies on); only Update is gated to the edit case.
        if item is not None:
            self.updateButton.clicked.connect(self.updatePress)
        else:
            self.updateButton.setEnabled(False)
        self.createButton.clicked.connect(self.newPress)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        name = self.nameEdit.text().strip()
        if name == "":
            errors.append("Press name cannot be empty.")
        if name in self.mainApp.db.presses:
            if isNew or (self.item is not None and not name == self.item.name):
                errors.append(f"Press name '{name}' already in use")

        if len(errors) == 0:
            isNone = self.item is None
            if isNew:
                self.item = Press(name)
                self.mainApp.db.addPress(self.item)
            else:
                if self.item is None:
                    raise RuntimeError('self.item is None')
                self.mainApp.db.updatePress(self.item.name, name)
            # Roundtrip the mounted die through the setter, keyed by the committed
            # press name (robust to the New-window self.item reset below). "(none)"
            # clears the press to idle.
            selectedPart = self.currentPartCombo.currentText()
            part = None if selectedPart == NO_PART_LABEL else selectedPart
            self.mainApp.db.setPressCurrentPart(name, part)
            if isNone:
                self.item = None
            self.mainApp.refreshAllViews()
            res = True
        else:
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.item.name if self.item is not None else "New Press"}")
        return res

    def updatePress(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()

    def newPress(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()
