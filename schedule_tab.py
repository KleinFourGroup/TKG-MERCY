import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QComboBox, QDateEdit, QScrollArea, QAbstractItemView,
)
from PySide6.QtCore import QDate, Qt

from table import DBTable
from app import MainWindow
from report import PDFReport
from pressers_tab import _presserLabel
from scheduling import (
    schedule, ScheduleConfig, MAX_HORIZON_DAYS,
    filterSchedule, groupScheduleRows, scheduleGroupHeading, scheduleFilterDescription,
    LATE, INFEASIBLE_NO_CAPACITY, INFEASIBLE_NO_RATE,
    WARN_FALLBACK_RATE, WARN_MISSING_FIRESCRAP,
)
from utils import startfile, tempReportPath

# Issue label + magnitude formatting for the on-screen flagged-orders table.
# Mirrors report/scheduling.py so the tab and the PDF read identically; kept
# local rather than imported so the report module stays presentation-only and
# this tab has no report-internal dependency beyond the public flag constants.
_FLAG_LABEL = {
    LATE: "Late",
    INFEASIBLE_NO_CAPACITY: "No capacity",
    INFEASIBLE_NO_RATE: "No rate",
}


def _flagDetail(flag) -> str:
    if flag.kind == LATE:
        return f"{flag.daysLate} day(s) late; {flag.piecesShort:g} pcs short at deadline"
    if flag.kind == INFEASIBLE_NO_CAPACITY:
        return f"{flag.shortHours:g} press-hr / {flag.piecesShort:g} pcs unplaced by horizon"
    if flag.kind == INFEASIBLE_NO_RATE:
        return "no pressing history and no Part.pressing rate"
    return ""


def _warningNote(warning) -> str:
    if warning.kind == WARN_FALLBACK_RATE:
        return "rate from Part.pressing fallback (no recent pressing history)"
    if warning.kind == WARN_MISSING_FIRESCRAP:
        return "fireScrap not set (scrap inflation may be understated)"
    return warning.kind


def _presserCell(db, employeeId) -> str:
    # Presser label for a schedule row, empty when unstaffed (never in practice).
    return _presserLabel(db, employeeId) if employeeId is not None else ""


_PROMPT = 'Press "Generate Schedule" to compute the schedule from current orders.'


class ScheduleTab(QWidget):
    # Production Schedule Report (Step 53; regrouped + filtered in Step 67). The
    # scheduler result is shown grouped by (date, shift) subheadings, each over a
    # 5-col Press/Part/Quantity/Press-hours/Presser mini-table — Date and Shift
    # move out of the columns into the heading, freeing width for the Presser
    # column (Step 66). Two "report variant" actions (Show / Export Filtered)
    # slice the computed result for a per-shift and/or date-range view without
    # re-running the scheduler. Stateless like the scheduler: holds the last full
    # result (self.result) plus the currently displayed slice (self.displayed)
    # only to feed Export, and clears on DB load.
    groupHeaders = ["Press", "Part", "Quantity", "Press-hours", "Presser"]

    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.result = None      # last full ScheduleResult (None until Generate)
        self.displayed = None   # what's on screen now (full or a filtered slice)
        self._groupTables: list[DBTable] = []

        # --- Main controls: horizon + Generate + Export (full schedule) ---
        # Horizon caps the scheduler's forward walk (ScheduleConfig.maxHorizonDays,
        # addendum §6). Default is the full horizon (spec §5.1).
        self.horizonSpin = QSpinBox()
        self.horizonSpin.setRange(1, MAX_HORIZON_DAYS)
        self.horizonSpin.setValue(MAX_HORIZON_DAYS)
        self.horizonSpin.setSuffix(" days")

        self.generateB = QPushButton("Generate Schedule")
        self.generateB.clicked.connect(self.generate)
        self.exportB = QPushButton("Export PDF")
        self.exportB.clicked.connect(self.exportPdf)
        self.exportB.setEnabled(False)  # nothing to export until a Generate

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Horizon:"))
        controls.addWidget(self.horizonSpin)
        controls.addWidget(self.generateB)
        controls.addWidget(self.exportB)
        controls.addStretch()

        # --- Filter controls: per-shift / date-range report variants (Step 67).
        # Separate from the main Generate/Export controls (design call
        # 2026-07-02) and disabled until there's a schedule to slice. They filter
        # the full computed result for display/PDF — a view slice, never a
        # shortened scheduler horizon. ---
        self.shiftCombo = QComboBox()
        self.shiftCombo.addItem("All shifts", None)
        for s in (1, 2, 3):
            self.shiftCombo.addItem(f"Shift {s}", s)
        self.fromDate = QDateEdit()
        self.fromDate.setCalendarPopup(True)
        self.fromDate.setDisplayFormat("yyyy-MM-dd")
        self.toDate = QDateEdit()
        self.toDate.setCalendarPopup(True)
        self.toDate.setDisplayFormat("yyyy-MM-dd")
        self.showFilteredB = QPushButton("Show Filtered")
        self.showFilteredB.clicked.connect(self.showFiltered)
        self.exportFilteredB = QPushButton("Export Filtered PDF")
        self.exportFilteredB.clicked.connect(self.exportFilteredPdf)
        self._filterWidgets = [self.shiftCombo, self.fromDate, self.toDate,
                               self.showFilteredB, self.exportFilteredB]
        self._setFiltersEnabled(False)

        filterRow = QHBoxLayout()
        filterRow.addWidget(QLabel("Filter:"))
        filterRow.addWidget(self.shiftCombo)
        filterRow.addWidget(QLabel("From:"))
        filterRow.addWidget(self.fromDate)
        filterRow.addWidget(QLabel("To:"))
        filterRow.addWidget(self.toDate)
        filterRow.addWidget(self.showFilteredB)
        filterRow.addWidget(self.exportFilteredB)
        filterRow.addStretch()

        self.statusLabel = QLabel(_PROMPT)

        # --- Grouped schedule display: a scroll area holding a (bold subheading +
        # mini-table) pair per (date, shift) group (Step 67). ---
        self.groupsContainer = QWidget()
        self.groupsLayout = QVBoxLayout(self.groupsContainer)
        self.groupsLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setWidget(self.groupsContainer)
        self._clearGroups()

        # --- Flagged orders + warnings: order-level / dateless, always shown in
        # full (never filtered) so a filtered view can't hide a late order. ---
        self.flagHeaders = ["Order", "Part", "Issue", "Detail"]
        self.flagsTable = DBTable([], self.flagHeaders)
        # No parentTab: read-only report view, row selection is a no-op.

        self.warningsLabel = QLabel("")
        self.warningsLabel.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addLayout(filterRow)
        layout.addWidget(self.statusLabel)
        layout.addWidget(QLabel("Schedule"))
        layout.addWidget(self.scrollArea, stretch=1)
        layout.addWidget(QLabel("Flagged Orders (order-level — shown in full, not filtered)"))
        layout.addWidget(self.flagsTable)
        layout.addWidget(self.warningsLabel)
        self.setLayout(layout)

    # --- config / actions ---

    def _config(self) -> ScheduleConfig:
        return ScheduleConfig(maxHorizonDays=self.horizonSpin.value())

    def generate(self):
        self.result = schedule(self.mainApp.db, None, self._config())
        self.displayed = self.result
        self._syncFilterBounds(self.result)
        self._setFiltersEnabled(True)
        self._populate(self.result)
        self.exportB.setEnabled(True)

    def showFiltered(self):
        # A per-shift / date-range view slice of the computed schedule.
        if self.result is None:
            return
        shift, start, end = self._filterArgs()
        self.displayed = filterSchedule(self.result, shift, start, end)
        self._populate(self.displayed, scheduleFilterDescription(shift, start, end))

    def exportPdf(self):
        # Exports the full schedule regardless of any on-screen filter.
        if self.result is None:
            return
        path = tempReportPath("production-schedule")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.scheduleReport(self.result, self.horizonSpin.value())
        startfile(path)

    def exportFilteredPdf(self):
        # Exports the current filter slice (a view of the full result).
        if self.result is None:
            return
        shift, start, end = self._filterArgs()
        filtered = filterSchedule(self.result, shift, start, end)
        desc = scheduleFilterDescription(shift, start, end)
        path = tempReportPath("production-schedule-filtered")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.scheduleReport(filtered, self.horizonSpin.value(), filterDesc=desc)
        startfile(path)

    def refresh(self):
        # Called from MainWindow._refreshAllTabs on DB open. The schedule is
        # stateless and recomputed on demand, so a freshly-loaded DB clears any
        # prior schedule rather than showing one computed from the old file.
        self.result = None
        self.displayed = None
        self._clearGroups()
        self.flagsTable.setData([])
        self.warningsLabel.setText("")
        self.exportB.setEnabled(False)
        self._setFiltersEnabled(False)
        self.statusLabel.setText(_PROMPT)

    # --- filter helpers ---

    def _filterArgs(self):
        # QDate -> datetime.date via components (QDate.toPython is typed `object`
        # in the stubs, so build the date explicitly to keep the types clean).
        shift = self.shiftCombo.currentData()
        fromQ, toQ = self.fromDate.date(), self.toDate.date()
        start = datetime.date(fromQ.year(), fromQ.month(), fromQ.day())
        end = datetime.date(toQ.year(), toQ.month(), toQ.day())
        return shift, start, end

    def _setFiltersEnabled(self, enabled: bool):
        for w in self._filterWidgets:
            w.setEnabled(enabled)

    def _syncFilterBounds(self, result):
        # Bound the date pickers to the schedule's span and default them to the
        # full range, so an unmodified filter is shift-only. Empty schedule -> today.
        dates = [r.date for r in result.rows]
        lo = min(dates) if dates else result.today
        hi = max(dates) if dates else result.today
        qlo = QDate(lo.year, lo.month, lo.day)
        qhi = QDate(hi.year, hi.month, hi.day)
        for de in (self.fromDate, self.toDate):
            de.setDateRange(qlo, qhi)
        self.fromDate.setDate(qlo)
        self.toDate.setDate(qhi)
        self.shiftCombo.setCurrentIndex(0)  # "All shifts"

    # --- rendering ---

    def _clearGroups(self):
        # Tear down the group widgets and leave a single trailing stretch so the
        # groups pack to the top of the scroll area.
        while self.groupsLayout.count():
            item = self.groupsLayout.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._groupTables = []
        self.groupsLayout.addStretch()

    def _renderGroups(self, rows):
        self._clearGroups()
        groups = groupScheduleRows(rows)
        if not groups:
            self.groupsLayout.insertWidget(0, QLabel("No production scheduled."))
            return
        insertAt = 0
        for (d, shift), grp in groups:
            heading = QLabel(scheduleGroupHeading(d, shift))
            f = heading.font()
            f.setBold(True)
            heading.setFont(f)
            self.groupsLayout.insertWidget(insertAt, heading)
            insertAt += 1
            data = [[r.press, r.part, f"{r.quantity:g}", f"{r.hours:g}",
                     _presserCell(self.mainApp.db, r.presser)] for r in grp]
            table = self._makeGroupTable(data)
            self.groupsLayout.insertWidget(insertAt, table)
            insertAt += 1
            self._groupTables.append(table)

    def _makeGroupTable(self, data):
        # A read-only mini-table sized to its rows, so groups stack in the scroll
        # area without nested scrollbars.
        table = DBTable(data, self.groupHeaders)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        height = table.horizontalHeader().height() + 2 * table.frameWidth()
        for i in range(len(data)):
            rowH = table.sizeHintForRow(i)
            height += rowH if rowH > 0 else 24
        table.setFixedHeight(height)
        return table

    def _populate(self, result, filterDesc=None):
        self._renderGroups(result.rows)

        flagData = [[
            f.orderNum,
            f.part,
            _FLAG_LABEL.get(f.kind, f.kind),
            _flagDetail(f),
        ] for f in result.flags]
        self.flagsTable.setData(flagData)

        if result.warnings:
            notes = "; ".join(f"{w.part}: {_warningNote(w)}" for w in result.warnings)
            self.warningsLabel.setText(f"Warnings — {notes}")
        else:
            self.warningsLabel.setText("")

        if filterDesc:
            self.statusLabel.setText(
                f"Filtered view — {filterDesc}: {len(result.rows)} schedule row(s); "
                f"flagged orders shown in full.")
        else:
            self.statusLabel.setText(
                f"Generated {result.today.isoformat()} — "
                f"{len(result.rows)} schedule row(s), "
                f"{len(result.flags)} flagged order(s)."
            )
