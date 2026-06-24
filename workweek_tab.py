from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QCheckBox
from PySide6.QtCore import Qt
from app import MainWindow
from records.scheduling import SHIFTS

# Column order matches date.weekday(): Mon=0 .. Sun=6.
WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class WorkweekTab(QWidget):
    # Fixed shift x weekday checkbox grid for the shift workweek (Production
    # Scheduling, Step 45). Rows are the three fixed shifts (SHIFTS — the
    # Employee.shift / observances / production domain); columns are the seven
    # weekdays (Mon=0..Sun=6, matching date.weekday()). Toggling a cell sets or
    # clears that (shift, weekday) working day, live-applied to the db through
    # Database.setShiftWorkday. There is no New/Edit/Delete because shifts aren't
    # user-created — unlike the flat Presses/Pressers tables, this is a fixed
    # matrix. Lives under "Production and Scheduling" -> "Scheduling config" ->
    # "Shift Workweek".
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        # checks[shift][weekday] -> QCheckBox, so refreshTable can re-sync each
        # cell's state from the db without rebuilding the grid.
        self.checks: dict[int, dict[int, QCheckBox]] = {}

        grid = QGridLayout()
        # Header row: weekday labels in columns 1..7 (column 0 holds shift labels).
        for col, label in enumerate(WEEKDAY_ABBR):
            header = QLabel(label)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(header, 0, col + 1)
        for row, shift in enumerate(SHIFTS):
            grid.addWidget(QLabel(f"Shift {shift}"), row + 1, 0)
            self.checks[shift] = {}
            for weekday in range(len(WEEKDAY_ABBR)):
                chk = QCheckBox()
                chk.setObjectName(f"workweek_{shift}_{weekday}")
                # Default args bind the loop vars per-cell (avoid the late-binding trap).
                chk.toggled.connect(
                    lambda checked, s=shift, wd=weekday: self._onToggle(s, wd, checked)
                )
                grid.addWidget(chk, row + 1, weekday + 1, Qt.AlignmentFlag.AlignCenter)
                self.checks[shift][weekday] = chk

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Check the weekdays each shift normally works:"))
        layout.addLayout(grid)
        layout.addStretch()
        self.setLayout(layout)

        self.refreshTable()

    def _onToggle(self, shift, weekday, checked):
        self.mainApp.db.setShiftWorkday(shift, weekday, checked)

    def refreshTable(self):
        # Re-sync every checkbox from the db. Named refreshTable to match the
        # refresh protocol _refreshAllTabs / load drive across all tabs, even
        # though there's no table widget here. Signals are blocked during the
        # sync so setChecked doesn't echo back into setShiftWorkday.
        db = self.mainApp.db
        for shift in SHIFTS:
            workweek = db.shiftWorkweek.get(shift)
            working = workweek.days if workweek is not None else set()
            for weekday, chk in self.checks[shift].items():
                chk.blockSignals(True)
                chk.setChecked(weekday in working)
                chk.blockSignals(False)
