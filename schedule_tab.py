from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
)

from table import DBTable
from app import MainWindow
from report import PDFReport
from scheduling import (
    schedule, ScheduleConfig, MAX_HORIZON_DAYS,
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


_PROMPT = 'Press "Generate Schedule" to compute the schedule from current orders.'


class ScheduleTab(QWidget):
    # Production Schedule Report (Step 53). An on-screen, regenerable table of
    # (date, shift, press, part) -> quantity from the stateless scheduler
    # (scheduling.schedule), with an explicit flagged-orders section, soft
    # warnings, and a reportlab PDF export. Stateless like the scheduler itself:
    # it holds the last ScheduleResult only to feed Export and clears it on DB
    # load so a schedule from a previous file never lingers.
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.result = None  # last generated ScheduleResult (None until Generate)

        # Horizon caps the scheduler's forward walk (ScheduleConfig.maxHorizonDays,
        # addendum §6). Default is the full horizon — "project until every
        # outstanding order is placed" (spec §5.1); a shorter horizon surfaces
        # NO_CAPACITY flags sooner for a near-term view.
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

        self.statusLabel = QLabel(_PROMPT)

        self.scheduleHeaders = ["Date", "Shift", "Press", "Part", "Quantity", "Press-hours"]
        self.scheduleTable = DBTable([], self.scheduleHeaders)
        self.flagHeaders = ["Order", "Part", "Issue", "Detail"]
        self.flagsTable = DBTable([], self.flagHeaders)
        # No parentTab on either table: these are read-only report views, so row
        # selection is a no-op (DBTable.onSelect guards on parentTab is None).

        self.warningsLabel = QLabel("")
        self.warningsLabel.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.statusLabel)
        layout.addWidget(QLabel("Schedule"))
        layout.addWidget(self.scheduleTable)
        layout.addWidget(QLabel("Flagged Orders (late / infeasible)"))
        layout.addWidget(self.flagsTable)
        layout.addWidget(self.warningsLabel)
        self.setLayout(layout)

    def _config(self) -> ScheduleConfig:
        return ScheduleConfig(maxHorizonDays=self.horizonSpin.value())

    def generate(self):
        self.result = schedule(self.mainApp.db, None, self._config())
        self._populate(self.result)
        self.exportB.setEnabled(True)

    def _populate(self, result):
        scheduleData = [[
            r.date.isoformat(),
            str(r.shift),
            r.press,
            r.part,
            f"{r.quantity:g}",
            f"{r.hours:g}",
        ] for r in result.rows]
        self.scheduleTable.setData(scheduleData)

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

        self.statusLabel.setText(
            f"Generated {result.today.isoformat()} — "
            f"{len(result.rows)} schedule row(s), "
            f"{len(result.flags)} flagged order(s)."
        )

    def exportPdf(self):
        if self.result is None:
            return
        path = tempReportPath("production-schedule")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.scheduleReport(self.result, self.horizonSpin.value())
        startfile(path)

    def refresh(self):
        # Called from MainWindow._refreshAllTabs on DB open. The schedule is
        # stateless and recomputed on demand, so a freshly-loaded DB clears any
        # prior schedule rather than showing one computed from the old file.
        self.result = None
        self.scheduleTable.setData([])
        self.flagsTable.setData([])
        self.warningsLabel.setText("")
        self.exportB.setEnabled(False)
        self.statusLabel.setText(_PROMPT)
