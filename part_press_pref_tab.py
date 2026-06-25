from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from records.scheduling import MIN_PRESS_SCORE, MAX_PRESS_SCORE
from error import errorMessage
from utils import getComboBox, centerOnScreen
import logging

# Score selector options for the nested editor: "Neutral" (no preference, stored
# as no row) plus the 1..5 scores. Order matches the combo index so prefill /
# read-back are symmetric.
SCORE_OPTIONS = ["Neutral"] + [str(s) for s in range(MIN_PRESS_SCORE, MAX_PRESS_SCORE + 1)]


class PartPressPrefTab(QWidget):
    # Nested editor for part-press preferences (Production Scheduling, Step 48).
    # Unlike the flat scheduling tables, prefs hang off existing parts: the table
    # lists every part with a summary of its scored presses, and Edit opens a
    # per-part window with one Neutral/1-5 selector per press. There is no
    # New/Delete — parts come from Products and presses from the Presses tab; a
    # part is scored all-neutral simply by clearing its selectors. Lives under
    # "Production and Scheduling" -> "Scheduling config" -> "Part-Press Preference".
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

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(edit)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)

    def genTableData(self):
        db = self.mainApp.db
        self.headers = ["Part", "Scored Presses"]
        self.data = []
        for part in db.parts:
            pref = db.partPressPref.get(part)
            if pref is None or not pref.scores:
                summary = "(neutral)"
            else:
                summary = ", ".join(f"{press}: {pref.scores[press]}" for press in sorted(pref.scores))
            self.data.append([part, summary])
        self.data.sort(key=lambda row: row[0])

    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {", ".join(selection)}")

    def openEdits(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No part selected."])
            return
        if len(self.mainApp.db.presses) == 0:
            errorMessage(self.mainApp, ["Cannot score presses: no presses in the database."])
            return
        for part in self.selection:
            logging.debug(part)
            PartPressPrefEditWindow(part, self.mainApp)

    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.data)
        selection = [part for part in self.selection if part in self.mainApp.db.parts]
        self.setSelection(selection)


class PartPressPrefEditWindow(QWidget):
    # Per-part nested editor: one Neutral/1-5 selector per press, prefilled from
    # the part's current scores. A single Update button writes every selector back
    # through Database.setPartPressScore (Neutral clears the pair to no row).
    def __init__(self, part, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.part = part
        self.setWindowTitle(f"Press Preferences: {part}")

        pref = self.mainApp.db.partPressPref.get(part)

        # One selector per press, keyed by press name so readData / smoke can drive
        # them directly. Presses are listed in sorted order to match the table view.
        self.scoreCombos = {}
        rowsLayout = QVBoxLayout()
        for press in sorted(self.mainApp.db.presses):
            current = pref.getScore(press) if pref is not None else None
            combo = getComboBox(SCORE_OPTIONS, str(current) if current is not None else "Neutral")
            self.scoreCombos[press] = combo
            line = QHBoxLayout()
            line.addWidget(QLabel(f"{press}:"))
            line.addWidget(combo)
            rowsLayout.addLayout(line)

        self.updateButton = QPushButton("Update")
        self.updateButton.clicked.connect(self.updatePref)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Press preferences for part: {part}"))
        layout.addLayout(rowsLayout)
        layout.addWidget(self.updateButton)
        self.setLayout(layout)
        centerOnScreen(self)
        self.show()

    def readData(self):
        # Write every selector back. "Neutral" -> None clears the pair; a numeric
        # choice sets the score. No validation needed — the combo constrains input.
        for press, combo in self.scoreCombos.items():
            choice = combo.currentText()
            score = None if choice == "Neutral" else int(choice)
            self.mainApp.db.setPartPressScore(self.part, press, score)
        self.mainApp.partPressPrefTab.refreshTable()
        return True

    def updatePref(self):
        if self.readData():
            QMessageBox.information(self, "Success", "Preferences updated!")
            self.close()
