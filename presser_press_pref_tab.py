from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from app import MainWindow
from pref_grid import PrefGrid, makeHeatLegend
from pressers_tab import _presserLabel


class PresserPressPrefTab(QWidget):
    # Interactive presser-press preference grid (Step 65, MERGE_PLAN §13.44) — the
    # presser twin of Step 64's PartPressPrefTab, and the first *reuse* of the
    # pref_grid.PrefGrid widget. Rows are the pressers, columns are the registered
    # presses, and each cell is a click-to-open "Not set / 1-5" drop-down set
    # directly in-grid (no edit window). Any presser can work any press but they
    # specialize; the score is a pure assignment preference (Step 66 staffs pressers
    # onto press work by it) and does not affect throughput. Scores are written
    # straight through Database.setPresserPressScore, so "Not set" clears the
    # (presser, press) pair back to no row. Lives under "Production and Scheduling"
    # -> "Scheduling config" -> "Presser-Press Preference".
    #
    # The one structural difference from the part grid: a presser's stable key is its
    # employeeId (an int), but the row is *labeled* by the employee's name. PrefGrid
    # already separates the two — it carries `rowKeys` (the keys it hands to
    # setScore) alongside the column-0 label in each data row — so this tab passes
    # employeeIds as rowKeys and the friendly label as the visible column-0 value.
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
            "Score how much each presser prefers each press: 5 = most preferred, "
            "1 = least. Leave a cell 'Not set' for no preference (scheduled as "
            "neutral). Click a cell to choose."
        )
        caption.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(caption)
        layout.addWidget(self.table)
        layout.addWidget(makeHeatLegend())
        self.setLayout(layout)

    def _getScore(self, employeeId, press):
        pref = self.mainApp.db.presserPressPref.get(employeeId)
        return pref.getScore(press) if pref is not None else None

    def _setScore(self, employeeId, press, score):
        self.mainApp.db.setPresserPressScore(employeeId, press, score)

    def genTableData(self):
        # Recompute the score matrix from db: one row per presser, the presser's
        # employee label in column 0, then a score (or None) per press. rowKeys holds
        # the parallel employeeId keys. Rows are ordered by (label, employeeId) so the
        # display is alphabetical and deterministic — the Step 55 stale-view net diffs
        # self.data directly, so the ordering must be reproducible.
        db = self.mainApp.db
        presses = sorted(db.presses)
        self.pressNames = presses
        self.headers = ["Presser"] + presses
        pressers = sorted(db.pressers, key=lambda empId: (_presserLabel(db, empId).lower(), empId))
        self.rowKeys = pressers
        self.data = []
        for empId in pressers:
            pref = db.presserPressPref.get(empId)
            row = [_presserLabel(db, empId)] + [pref.getScore(p) if pref is not None else None for p in presses]
            self.data.append(row)

    def setSelection(self, selection):
        self.selection = selection

    def refreshTable(self):
        # Full structural rebuild — the pressers (rows) and presses (columns) can both
        # change under us via renames / deletes / employee edits elsewhere, so headers
        # and rowKeys are recomputed too. Selection is column-0 labels; keep only those
        # still on screen.
        self.genTableData()
        self.table.rebuild(self.rowKeys, self.headers, self.data)
        liveLabels = {row[0] for row in self.data}
        self.selection = [label for label in self.selection if label in liveLabels]
