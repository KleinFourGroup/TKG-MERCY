from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from app import MainWindow
from pref_grid import PrefGrid, makeHeatLegend


class PartPressPrefTab(QWidget):
    # Interactive part-press preference grid (Step 64, a rewrite of the Step 48
    # list + per-part modal editor). Rows are parts, columns are the registered
    # presses, and each cell is a click-to-open "Not set / 1-5" drop-down set
    # directly in-grid (no edit window). Scores are written straight through
    # Database.setPartPressScore, so "Not set" clears the (part, press) pair back
    # to no row — the record / schema / migration are all unchanged from Step 48.
    # The grid widget itself lives in pref_grid.py and is reused by Step 65's
    # Presser-Press tab. Lives under "Production and Scheduling" -> "Scheduling
    # config" -> "Part-Press Preference".
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.selection = []
        self.genTableData()
        self.table = PrefGrid(
            self.rowKeys, self.headers, self.data, self.pressNames,
            self._getScore, self._setScore,
        )
        self.table.parentTab = self  # type: ignore

        caption = QLabel(
            "Score how much each part prefers each press: 5 = most preferred, "
            "1 = least. Leave a cell 'Not set' for no preference (scheduled as "
            "neutral). Click a cell to choose."
        )
        caption.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(caption)
        layout.addWidget(self.table)
        layout.addWidget(makeHeatLegend())
        self.setLayout(layout)

    def _getScore(self, part, press):
        pref = self.mainApp.db.partPressPref.get(part)
        return pref.getScore(press) if pref is not None else None

    def _setScore(self, part, press, score):
        self.mainApp.db.setPartPressScore(part, press, score)

    def genTableData(self):
        # Recompute the score matrix from db: one row per part, the part name in
        # column 0, then a score (or None) per press. Kept in sync with headers /
        # rowKeys so the Step 55 stale-view net can diff self.data directly.
        db = self.mainApp.db
        presses = sorted(db.presses)
        self.pressNames = presses
        self.headers = ["Part"] + presses
        self.rowKeys = sorted(db.parts)
        self.data = []
        for part in self.rowKeys:
            pref = db.partPressPref.get(part)
            row = [part] + [pref.getScore(p) if pref is not None else None for p in presses]
            self.data.append(row)

    def setSelection(self, selection):
        self.selection = selection

    def refreshTable(self):
        # Full structural rebuild — parts and presses (the columns) can both change
        # under us via renames / deletes elsewhere, so headers are recomputed too.
        self.genTableData()
        self.table.rebuild(self.rowKeys, self.headers, self.data)
        self.selection = [part for part in self.selection if part in self.mainApp.db.parts]
