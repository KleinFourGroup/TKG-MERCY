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
    schedule, ScheduleConfig, ScheduleResult, MAX_HORIZON_DAYS,
    filterSchedule, groupScheduleRows, scheduleGroupHeading, scheduleFilterDescription,
    formatPressHours,
    LATE, INFEASIBLE_NO_CAPACITY, INFEASIBLE_NO_RATE,
    WARN_FALLBACK_RATE, WARN_MISSING_FIRESCRAP,
)
from utils import startfile, tempReportPath, centerOnScreen

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
        return f"{flag.daysLate} day(s) late; {flag.piecesShort:,} pcs short at deadline"
    if flag.kind == INFEASIBLE_NO_CAPACITY:
        return f"{flag.shortHours:g} press-hr / {flag.piecesShort:,} pcs unplaced by horizon"
    if flag.kind == INFEASIBLE_NO_RATE:
        return "no pressing history and no Part.pressing rate"
    return ""


# Flagged-order client / due-date presentation (Step 73). Looked up from the
# order at render time so OrderFlag stays a pure data carrier; mirrors
# report/scheduling.py so the detail window and the PDF read identically.
def _flagClient(db, flag) -> str:
    order = db.orders.get(flag.orderNum)
    return order.client if order is not None else ""


def _flagDueStr(db, flag) -> str:
    order = db.orders.get(flag.orderNum)
    if order is None or order.dueDate is None:
        return "?"
    return order.dueDate.isoformat()


def _flagSortKey(db, flag):
    # Sort flagged orders by due date (undated last), orderNum breaking ties.
    order = db.orders.get(flag.orderNum)
    due = order.dueDate if order is not None else None
    return (due is None, due or datetime.date.max, flag.orderNum)


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


class _FlagListWindow(QWidget):
    # A read-only pop-up listing the flagged orders / flagged parts behind the
    # Schedule tab's one-line summaries (Step 72). Pure view over a prebuilt
    # (headers, data) — no selection or editing. Parented to mainApp so Qt keeps
    # it alive without the tab holding a Python reference (the codebase's detail-
    # window pattern; WA_DeleteOnClose frees it on close).
    def __init__(self, mainApp: MainWindow, title: str, headers, data):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title)
        table = DBTable(data, headers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.resizeColumnsToContents()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(title))
        layout.addWidget(table)
        self.setLayout(layout)
        # Size the window to show the whole table: the default QTableView size hint
        # is too narrow, so the wide columns (Client / Detail) were cut off. Sum the
        # column widths (+ frame + a vertical scrollbar's width for when rows
        # overflow) and cap to a sane max so a long Detail can't exceed the screen.
        width = 2 * table.frameWidth() + table.verticalScrollBar().sizeHint().width()
        for c in range(len(headers)):
            width += table.columnWidth(c)
        self.resize(min(width + 40, 1100), 420)
        centerOnScreen(self, adjustSize=False)
        self.show()


class ScheduleTab(QWidget):
    # Production Schedule Report (Step 53; regrouped + filtered in Step 67). The
    # scheduler result is shown grouped by (date, shift) subheadings, each over a
    # 5-col Press/Part/Quantity/Press time/Presser mini-table — Date and Shift
    # move out of the columns into the heading, freeing width for the Presser
    # column (Step 66). A single unified control row (Step 71) — Generate, a
    # From/To/Shift filter built into the display, and Export — drives everything:
    # the From/To/Shift widgets live-filter the shown schedule (a view slice, never
    # a recompute) and Export writes exactly what's on screen. Stateless like the
    # scheduler: holds the last full result (self.result), the displayed slice
    # (self.displayed), and that slice's filter description (self._displayedDesc)
    # only to feed Export, and clears on DB load.
    groupHeaders = ["Press", "Part", "Quantity", "Press time", "Presser"]

    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.result = None       # last full ScheduleResult (None until Generate)
        self.displayed = None    # what's on screen now (full or a filtered slice)
        self._displayedDesc = None  # filter description for `displayed`, None if full
        self._fullLo = None      # schedule's full date span, for detecting an active
        self._fullHi = None      # filter (a range tighter than [_fullLo, _fullHi])
        self._groupTables: list[DBTable] = []

        # --- Unified report row (Step 71): one row drives everything —
        # [Generate] [From] [To] [Shift] [Export PDF]. Generate computes the full
        # schedule; the From/To/Shift widgets are built into the display and
        # live-filter it (a cheap view slice of the already-computed result via the
        # Step 67 filterSchedule, never a shortened scheduler horizon); Export
        # writes exactly what's on screen. The filter widgets + Export are disabled
        # until a schedule exists. Replaces the Step 67 two-row split (Show / Export
        # Filtered), whose separate full-vs-filtered actions the team found
        # redundant. The horizon knob lives in the collapsed Advanced panel below
        # (Step 70). ---
        self.generateB = QPushButton("Generate Schedule")
        self.generateB.clicked.connect(self.generate)

        self.fromDate = QDateEdit()
        self.fromDate.setCalendarPopup(True)
        self.fromDate.setDisplayFormat("yyyy-MM-dd")
        self.toDate = QDateEdit()
        self.toDate.setCalendarPopup(True)
        self.toDate.setDisplayFormat("yyyy-MM-dd")
        self.shiftCombo = QComboBox()
        self.shiftCombo.addItem("All shifts", None)
        for s in (1, 2, 3):
            self.shiftCombo.addItem(f"Shift {s}", s)

        self.exportB = QPushButton("Export PDF")
        self.exportB.clicked.connect(self.exportPdf)
        self.exportB.setEnabled(False)  # nothing to export until a Generate

        # The date range is built into the display: adjusting From/To/Shift
        # re-slices the shown schedule live (no recompute). Connected after the
        # widgets exist so the initial addItem / _syncFilterBounds setup doesn't
        # spuriously fire (setup blocks these signals too).
        self.fromDate.dateChanged.connect(self._applyFilter)
        self.toDate.dateChanged.connect(self._applyFilter)
        self.shiftCombo.currentIndexChanged.connect(self._applyFilter)

        self._filterWidgets = [self.shiftCombo, self.fromDate, self.toDate]
        self._setFiltersEnabled(False)

        controls = QHBoxLayout()
        controls.addWidget(self.generateB)
        controls.addWidget(QLabel("From:"))
        controls.addWidget(self.fromDate)
        controls.addWidget(QLabel("To:"))
        controls.addWidget(self.toDate)
        controls.addWidget(self.shiftCombo)
        controls.addWidget(self.exportB)
        controls.addStretch()

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

        # --- Flagged orders / parts: condensed to one-line summaries + detail
        # buttons (Step 72) so the full tables no longer crowd the schedule scroll
        # area. Both are order-level / part-level and dateless, so they're always
        # shown in full (never filtered) — a slice must never hide a late order.
        # The detail rows are prebuilt in _populate; the buttons pop a read-only
        # list window and are disabled when their count is zero. ---
        self.flagHeaders = ["Order", "Client", "Part", "Due Date", "Issue", "Detail"]
        self.warnHeaders = ["Part", "Warning"]
        self._flagData: list[list[str]] = []
        self._warnData: list[list[str]] = []

        self.flagsSummary = QLabel("0 orders flagged")
        self.flagsButton = QPushButton("Flagged Orders")
        self.flagsButton.clicked.connect(self._openFlags)
        self.flagsButton.setEnabled(False)
        self.warnSummary = QLabel("0 parts flagged")
        self.warnButton = QPushButton("Flagged Parts")
        self.warnButton.clicked.connect(self._openWarnings)
        self.warnButton.setEnabled(False)

        flagRow = QHBoxLayout()
        flagRow.addWidget(self.flagsSummary)
        flagRow.addWidget(self.flagsButton)
        flagRow.addSpacing(24)
        flagRow.addWidget(self.warnSummary)
        flagRow.addWidget(self.warnButton)
        flagRow.addStretch()

        # --- Advanced (collapsed by default): the horizon knob, de-emphasized per
        # Step 70 so the average user doesn't mistake it for a display filter. ---
        self.horizonSpin = QSpinBox()
        self.horizonSpin.setRange(1, MAX_HORIZON_DAYS)
        self.horizonSpin.setValue(MAX_HORIZON_DAYS)
        self.horizonSpin.setSuffix(" days")

        self.advancedToggle = QPushButton("Advanced ▸")  # ▸ collapsed
        self.advancedToggle.setCheckable(True)
        self.advancedToggle.setFlat(True)
        self.advancedToggle.toggled.connect(self._toggleAdvanced)

        self.advancedPanel = QWidget()
        advLayout = QHBoxLayout(self.advancedPanel)
        advLayout.setContentsMargins(0, 0, 0, 0)
        advLayout.addWidget(QLabel("Horizon:"))
        advLayout.addWidget(self.horizonSpin)
        advLayout.addWidget(QLabel(
            "— how many days ahead the scheduler plans, not a display filter."))
        advLayout.addStretch()
        self.advancedPanel.setVisible(False)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.statusLabel)
        layout.addWidget(QLabel("Schedule"))
        layout.addWidget(self.scrollArea, stretch=1)
        layout.addLayout(flagRow)
        layout.addWidget(self.advancedToggle)
        layout.addWidget(self.advancedPanel)
        self.setLayout(layout)

    # --- config / actions ---

    def _toggleAdvanced(self, checked: bool):
        # Show/hide the collapsed Advanced (horizon) panel and flip the disclosure
        # arrow (Step 70).
        self.advancedPanel.setVisible(checked)
        self.advancedToggle.setText("Advanced ▾" if checked else "Advanced ▸")

    def _config(self) -> ScheduleConfig:
        return ScheduleConfig(maxHorizonDays=self.horizonSpin.value())

    def generate(self):
        self.result = schedule(self.mainApp.db, None, self._config())
        self._syncFilterBounds(self.result)
        self._setFiltersEnabled(True)
        self.exportB.setEnabled(True)
        self._applyFilter()

    def _applyFilter(self, *_):
        # Re-slice the on-screen schedule for the current From/To/Shift widgets — a
        # cheap view slice of the already-computed result (Step 67 filterSchedule),
        # never a recompute. No-op until a schedule exists. Stores the slice + its
        # filter description so Export writes exactly what's shown. Connected to the
        # filter widgets' change signals, so the date range is live in the display.
        if self.result is None:
            return
        shift, start, end = self._filterArgs()
        if self._filterActive(shift, start, end):
            self.displayed = filterSchedule(self.result, shift, start, end)
            self._displayedDesc = scheduleFilterDescription(shift, start, end)
        else:
            self.displayed = self.result
            self._displayedDesc = None
        self._populate(self.displayed, self._displayedDesc)

    def exportPdf(self):
        # Exports exactly what's on screen — the current filter slice (Step 71).
        if self.displayed is None:
            return
        suffix = "-filtered" if self._displayedDesc else ""
        path = tempReportPath(f"production-schedule{suffix}")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.scheduleReport(self.displayed, self.horizonSpin.value(),
                           filterDesc=self._displayedDesc)
        startfile(path)

    def refresh(self):
        # Called from MainWindow._refreshAllTabs on DB open. The schedule is
        # stateless and recomputed on demand, so a freshly-loaded DB clears any
        # prior schedule rather than showing one computed from the old file.
        self.result = None
        self.displayed = None
        self._displayedDesc = None
        self._clearGroups()
        self._flagData = []
        self._warnData = []
        self.flagsSummary.setText("0 orders flagged")
        self.warnSummary.setText("0 parts flagged")
        self.flagsButton.setEnabled(False)
        self.warnButton.setEnabled(False)
        self.exportB.setEnabled(False)
        self._setFiltersEnabled(False)
        self.statusLabel.setText(_PROMPT)

    def _openFlags(self):
        if self._flagData:
            _FlagListWindow(self.mainApp, "Flagged Orders", self.flagHeaders, self._flagData)

    def _openWarnings(self):
        if self._warnData:
            _FlagListWindow(self.mainApp, "Flagged Parts", self.warnHeaders, self._warnData)

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
        # Signals are blocked while we set the widgets so the live _applyFilter
        # connection doesn't fire mid-setup (generate() calls it once afterward).
        dates = [r.date for r in result.rows]
        lo = min(dates) if dates else result.today
        hi = max(dates) if dates else result.today
        self._fullLo, self._fullHi = lo, hi
        qlo = QDate(lo.year, lo.month, lo.day)
        qhi = QDate(hi.year, hi.month, hi.day)
        for w in self._filterWidgets:
            w.blockSignals(True)
        for de in (self.fromDate, self.toDate):
            de.setDateRange(qlo, qhi)
        self.fromDate.setDate(qlo)
        self.toDate.setDate(qhi)
        self.shiftCombo.setCurrentIndex(0)  # "All shifts"
        for w in self._filterWidgets:
            w.blockSignals(False)

    def _filterActive(self, shift, start, end) -> bool:
        # A filter is "active" (narrowing) when a specific shift is chosen or the
        # date range is tighter than the schedule's full span — used to decide
        # whether the display / PDF is annotated as filtered and Export names the
        # file "-filtered".
        if self._fullLo is None or self._fullHi is None:
            return shift is not None
        return shift is not None or start > self._fullLo or end < self._fullHi

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
            data = [[r.press, r.part, f"{r.quantity:,}", formatPressHours(r.hours),
                     _presserCell(self.mainApp.db, r.presser)] for r in grp]
            table = self._makeGroupTable(data)
            self.groupsLayout.insertWidget(insertAt, table)
            insertAt += 1
            self._groupTables.append(table)

    def _makeGroupTable(self, data):
        # A read-only mini-table sized to its FULL content — every row and every
        # column — with both of its own scrollbars off, so the groups stack in the
        # outer scroll area with no scroll-inside-a-scroll. The outer QScrollArea
        # does all the scrolling: vertically across the stacked groups, and
        # horizontally if the widest row (a long presser name) exceeds the viewport.
        table = DBTable(data, self.groupHeaders)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        # Full content height (no inner vertical scroll). Use the header's sizeHint
        # rather than its .height() — the latter is unreliable before the table is
        # shown, and was under-counting, which clipped the last row — plus the
        # vertical header's total section length for the rows and the frame, with a
        # couple px of slack for grid lines.
        height = (table.horizontalHeader().sizeHint().height()
                  + table.verticalHeader().length()
                  + 2 * table.frameWidth() + 4)
        table.setFixedHeight(height)
        # Full content width so the last column (Presser) is never clipped; the
        # outer scroll area scrolls horizontally rather than an inner scrollbar.
        # (When the viewport is wider than this, stretchLastSection fills it.)
        width = 2 * table.frameWidth()
        for c in range(len(self.groupHeaders)):
            width += table.columnWidth(c)
        table.setMinimumWidth(width)
        return table

    def _populate(self, result: ScheduleResult, filterDesc=None):
        self._renderGroups(result.rows)

        # Flagged orders / parts are prebuilt here and shown via the summary
        # buttons (Step 72). Order-level / part-level and dateless, so a filtered
        # view still counts + lists them all. Flagged orders carry their client and
        # sort by due date (Step 73), looked up from the order at render time.
        db = self.mainApp.db
        self._flagData = [[
            f.orderNum,
            _flagClient(db, f),
            f.part,
            _flagDueStr(db, f),
            _FLAG_LABEL.get(f.kind, f.kind),
            _flagDetail(f),
        ] for f in sorted(result.flags, key=lambda fl: _flagSortKey(db, fl))]
        self._warnData = [[w.part, _warningNote(w)] for w in result.warnings]

        n, m = len(self._flagData), len(self._warnData)
        self.flagsSummary.setText(f"{n} order{'' if n == 1 else 's'} flagged")
        self.warnSummary.setText(f"{m} part{'' if m == 1 else 's'} flagged")
        self.flagsButton.setEnabled(n > 0)
        self.warnButton.setEnabled(m > 0)

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
