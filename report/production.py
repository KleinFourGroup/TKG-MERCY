import datetime
from typing import TYPE_CHECKING

from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics import renderPDF

from records import ProductionRecord
from defaults import (
    PRODUCTION_ACTIONS, PRODUCTION_ACTION_TARGET, PRODUCTION_TARGET_UNIT,
)

if TYPE_CHECKING:
    from records import Database
    from reportlab.pdfgen import canvas

# Step 19 trend-report knobs. Module-level so the team can flip modes without a
# signature change if the default doesn't match their gut. See MERGE_PLAN.md
# §13.6 for the decision on ratio-of-sums as default.
TREND_WINDOW_DAYS = 30
TREND_MIN_RANGE_DAYS = 30
# "ratioOfSums": sum(qty in window) / sum(hours in window). Matches Step 18's
# aggregation. Zero-production days contribute nothing to numerator or
# denominator and fall out naturally.
# "meanOfRates": mean of per-day rates (qty/hours), skipping days with no
# production so they don't drag the mean toward zero.
TREND_MODE = "ratioOfSums"

# Colorblind-friendly palette for trend lines (matplotlib's tab10 subset). The
# aggregate/"All shifts" line is always rendered last and gets the final color.
_TREND_LINE_COLORS = [
    colors.HexColor('#1f77b4'),  # blue
    colors.HexColor('#ff7f0e'),  # orange
    colors.HexColor('#2ca02c'),  # green
    colors.HexColor('#d62728'),  # red
    colors.HexColor('#9467bd'),  # purple
    colors.HexColor('#000000'),  # black
]


class ProductionReportsMixin:
    # Production-domain PDF reports (Steps 11-12, 18-19, 22, 24, 26-27): summary
    # by employee, per-action drill, per-target drill, per-employee drill,
    # productivity rate report (Step 18), per-employee productivity (Step 24),
    # and the 30-day rolling-rate trend chart (Step 19). All build on the
    # primitives in PDFReportCore — see report/__init__.py for the composition.
    #
    # Eventual goal (Matthew, 2026-05-13): split this further so each report
    # lives in its own file once the team has finalized the layouts. Tracked
    # in MERGE_PLAN.md §13.21.

    if TYPE_CHECKING:
        # Attributes + helpers provided by PDFReportCore (composed in last).
        db: Database
        pdf: canvas.Canvas
        lastLine: float
        left: float
        right: float
        def setupPage(self) -> None: ...
        def nextPage(self) -> None: ...
        def skipLines(self, numLines) -> None: ...
        def drawText(self, text: str) -> None: ...
        def drawTitle(self, text: str) -> None: ...
        def drawSubtitle(self, text: str) -> None: ...
        def drawSection(self, text: str) -> None: ...
        def drawTable(self, data: list[list[str]], headers: list[str] | None = None, widths: list[float] | None = None) -> int: ...

    def _filterProduction(self, startDate: datetime.date, endDate: datetime.date,
                          action: str | None = None,
                          employeeId: int | None = None,
                          targetType: str | None = None,
                          targetName: str | None = None) -> list[ProductionRecord]:
        out = []
        for rec in self.db.production.values():
            if rec.date is None:
                continue
            if rec.date < startDate or rec.date > endDate:
                continue
            if action is not None and rec.action != action:
                continue
            if employeeId is not None and rec.employeeId != employeeId:
                continue
            if targetType is not None and rec.targetType != targetType:
                continue
            if targetName is not None and rec.targetName != targetName:
                continue
            out.append(rec)
        return out

    def _employeeName(self, employeeId) -> str:
        emp = self.db.employees.get(employeeId)
        if emp is None:
            return f"(missing #{employeeId})"
        last = (emp.lastName or "").upper()
        first = emp.firstName or ""
        return f"{last} {first} ({employeeId})"

    def _fmtRate(self, q: float, h: float) -> str:
        if h <= 0:
            return "—"
        return f"{q / h:.2f}"

    def productionSummaryReport(self, startDate: datetime.date, endDate: datetime.date):
        recs = self._filterProduction(startDate, endDate)

        grid: dict[tuple[int | None, str | None], tuple[float, float, float]] = {}
        empIds: set = set()
        for r in recs:
            key = (r.employeeId, r.action)
            q, s, h = grid.get(key, (0.0, 0.0, 0.0))
            grid[key] = (q + (r.quantity or 0), s + r.scrapQuantity, h + r.hours)
            empIds.add(r.employeeId)

        def empSortKey(eid):
            emp = self.db.employees.get(eid)
            if emp is None:
                return (1, "", "", eid if eid is not None else 0)
            return (0, (emp.lastName or "").lower(), (emp.firstName or "").lower(), eid or 0)

        sortedIds = sorted(empIds, key=empSortKey)

        headers = ["Employee"] + [
            f"{a} ({PRODUCTION_TARGET_UNIT[PRODUCTION_ACTION_TARGET[a]]})"
            for a in PRODUCTION_ACTIONS
        ]

        def _format(q: float, s: float, h: float, action: str) -> str:
            if q == 0 and s == 0 and h == 0:
                return "—"
            extras = []
            if s > 0:
                extras.append(f"scrap: {s:g}")
            if h > 0:
                extras.append(f"{h:g}h")
                if PRODUCTION_ACTION_TARGET[action] != "" and q > 0:
                    extras.append(f"{q / h:.2f}/h")
            return f"{q:g} ({', '.join(extras)})" if extras else f"{q:g}"

        def cell(eid, action) -> str:
            q, s, h = grid.get((eid, action), (0.0, 0.0, 0.0))
            return _format(q, s, h, action)

        data = [[self._employeeName(eid)] + [cell(eid, a) for a in PRODUCTION_ACTIONS]
                for eid in sortedIds]

        totalsRow = ["Total"]
        for a in PRODUCTION_ACTIONS:
            tq = sum(grid.get((eid, a), (0.0, 0.0, 0.0))[0] for eid in empIds)
            ts = sum(grid.get((eid, a), (0.0, 0.0, 0.0))[1] for eid in empIds)
            th = sum(grid.get((eid, a), (0.0, 0.0, 0.0))[2] for eid in empIds)
            totalsRow.append(_format(tq, ts, th, a))

        olen = len(data)
        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle("TKG Production Summary")
            self.drawSubtitle(rangeText)
            self.skipLines(2)
            self.drawSection("Production by Employee")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle("TKG Production Summary")
                self.drawSubtitle(rangeText)
                self.skipLines(2)
                self.drawSection("Production by Employee" if len(data) == olen
                                 else "Production by Employee -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    self.drawTable([], totalsRow)
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionActionReport(self, action: str, startDate: datetime.date, endDate: datetime.date):
        if action not in PRODUCTION_ACTIONS:
            raise RuntimeError(f'unknown action {action!r}')

        recs = self._filterProduction(startDate, endDate, action=action)
        recs.sort(key=lambda r: (r.date, r.shift if r.shift is not None else 0,
                                 r.targetName or "",
                                 r.employeeId if r.employeeId is not None else 0))

        targetType = PRODUCTION_ACTION_TARGET[action]
        unit = PRODUCTION_TARGET_UNIT[targetType]
        # Targetless actions (Tool Change) drop the target + scrap columns — both
        # are always empty/zero for those records and would just clutter the table.
        hasTarget = targetType != ""
        targetLabel = "Mixture" if targetType == "mix" else "Part"

        if hasTarget:
            headers = ["Date", "Shift", "Employee", targetLabel,
                       f"Quantity ({unit})", f"Scrap ({unit})", "Hours",
                       "Rate (per hr)"]
            data = [[
                r.date.isoformat() if r.date else "",
                str(r.shift) if r.shift is not None else "",
                self._employeeName(r.employeeId),
                r.targetName or "",
                f"{r.quantity:g}" if r.quantity is not None else "",
                f"{r.scrapQuantity:g}",
                f"{r.hours:g}",
                self._fmtRate(r.quantity or 0, r.hours),
            ] for r in recs]
        else:
            headers = ["Date", "Shift", "Employee",
                       f"Quantity ({unit})", "Hours"]
            data = [[
                r.date.isoformat() if r.date else "",
                str(r.shift) if r.shift is not None else "",
                self._employeeName(r.employeeId),
                f"{r.quantity:g}" if r.quantity is not None else "",
                f"{r.hours:g}",
            ] for r in recs]
        olen = len(data)

        totalQ = sum((r.quantity or 0) for r in recs)
        totalS = sum(r.scrapQuantity for r in recs)
        totalH = sum(r.hours for r in recs)
        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle(f"TKG {action} Report")
            self.drawSubtitle(rangeText)
            self.skipLines(2)
            self.drawSection(f"{action} Records")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle(f"TKG {action} Report")
                self.drawSubtitle(rangeText)
                self.skipLines(2)
                self.drawSection(f"{action} Records" if len(data) == olen
                                 else f"{action} Records -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    if hasTarget:
                        self.drawTable([], ["", "", "", "Total",
                                            f"{totalQ:g}", f"{totalS:g}", f"{totalH:g}",
                                            self._fmtRate(totalQ, totalH)])
                    else:
                        self.drawTable([], ["", "", "Total",
                                            f"{totalQ:g}", f"{totalH:g}"])
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionTargetReport(self, targetType: str, targetName: str,
                               startDate: datetime.date, endDate: datetime.date):
        if targetType not in PRODUCTION_TARGET_UNIT:
            raise RuntimeError(f'unknown targetType {targetType!r}')

        recs = self._filterProduction(startDate, endDate,
                                      targetType=targetType, targetName=targetName)
        recs.sort(key=lambda r: (r.date, r.shift if r.shift is not None else 0,
                                 r.action or "",
                                 r.employeeId if r.employeeId is not None else 0))

        unit = PRODUCTION_TARGET_UNIT[targetType]
        targetLabel = "Mixture" if targetType == "mix" else "Part"

        headers = ["Date", "Shift", "Employee", "Action",
                   f"Quantity ({unit})", f"Scrap ({unit})", "Hours",
                   "Rate (per hr)"]
        data = [[
            r.date.isoformat() if r.date else "",
            str(r.shift) if r.shift is not None else "",
            self._employeeName(r.employeeId),
            r.action or "",
            f"{r.quantity:g}" if r.quantity is not None else "",
            f"{r.scrapQuantity:g}",
            f"{r.hours:g}",
            self._fmtRate(r.quantity or 0, r.hours),
        ] for r in recs]
        olen = len(data)

        perAction: dict[str, tuple[float, float, float]] = {}
        for r in recs:
            q, s, h = perAction.get(r.action or "", (0.0, 0.0, 0.0))
            perAction[r.action or ""] = (q + (r.quantity or 0), s + r.scrapQuantity, h + r.hours)

        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle(f"TKG Production Report: {targetName}")
            self.drawSubtitle(f"{targetLabel} ({rangeText})")
            self.skipLines(2)
            self.drawSection("Production Records")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle(f"TKG Production Report: {targetName}")
                self.drawSubtitle(f"{targetLabel} ({rangeText})")
                self.skipLines(2)
                self.drawSection("Production Records" if len(data) == olen
                                 else "Production Records -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    for a in PRODUCTION_ACTIONS:
                        if a in perAction:
                            q, s, h = perAction[a]
                            self.drawTable([], ["", "", "", f"Total {a}", f"{q:g}", f"{s:g}", f"{h:g}",
                                                self._fmtRate(q, h)])
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionEmployeeReport(self, employeeId: int,
                                 startDate: datetime.date, endDate: datetime.date):
        if employeeId not in self.db.employees:
            raise RuntimeError(f'employeeId {employeeId} not in self.db.employees')

        recs = self._filterProduction(startDate, endDate, employeeId=employeeId)
        recs.sort(key=lambda r: (r.date, r.shift if r.shift is not None else 0,
                                 r.action or "", r.targetName or ""))

        # Tool Change rows are targetless and have no produced quantity, so
        # rate-per-hour is meaningless for them — render "—" rather than 0.00.
        def rowRate(r) -> str:
            if PRODUCTION_ACTION_TARGET.get(r.action or "", "") == "":
                return "—"
            return self._fmtRate(r.quantity or 0, r.hours)

        headers = ["Date", "Shift", "Action", "Target", "Quantity", "Unit",
                   "Scrap", "Hours", "Rate (per hr)"]
        data = [[
            r.date.isoformat() if r.date else "",
            str(r.shift) if r.shift is not None else "",
            r.action or "",
            r.targetName or "",
            f"{r.quantity:g}" if r.quantity is not None else "",
            PRODUCTION_TARGET_UNIT.get(r.targetType or "", ""),
            f"{r.scrapQuantity:g}",
            f"{r.hours:g}",
            rowRate(r),
        ] for r in recs]
        olen = len(data)

        perAction: dict[str, tuple[float, float, float]] = {}
        for r in recs:
            q, s, h = perAction.get(r.action or "", (0.0, 0.0, 0.0))
            perAction[r.action or ""] = (q + (r.quantity or 0), s + r.scrapQuantity, h + r.hours)

        empName = self._employeeName(employeeId)
        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle("TKG Production Report")
            self.drawSubtitle(empName)
            self.skipLines(1)
            self.drawText(rangeText)
            self.skipLines(1)
            self.drawSection("Production Records")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle("TKG Production Report")
                self.drawSubtitle(empName)
                self.skipLines(1)
                self.drawText(rangeText)
                self.skipLines(1)
                self.drawSection("Production Records" if len(data) == olen
                                 else "Production Records -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    for a in PRODUCTION_ACTIONS:
                        if a in perAction:
                            q, s, h = perAction[a]
                            unit = PRODUCTION_TARGET_UNIT[PRODUCTION_ACTION_TARGET[a]]
                            rate = ("—" if PRODUCTION_ACTION_TARGET[a] == ""
                                    else self._fmtRate(q, h))
                            self.drawTable([], ["", "", f"Total {a}", "",
                                                f"{q:g}", unit, f"{s:g}", f"{h:g}",
                                                rate])
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionProductivityReport(self, action: str,
                                     targetName: str | None,
                                     shift: int | None,
                                     startDate: datetime.date,
                                     endDate: datetime.date):
        # Step 18: rate-per-hour drill-down feeding the costing code.
        # targetName is None for "all targets"; shift is None for "all shifts".
        # Tool Change has its own shape (no rate, no per-employee) and dispatches
        # to a helper below.
        if action not in PRODUCTION_ACTIONS:
            raise RuntimeError(f'unknown action {action!r}')
        if action == "Tool Change":
            self._toolChangeProductivityReport(shift, startDate, endDate)
            return

        targetType = PRODUCTION_ACTION_TARGET[action]
        unit = PRODUCTION_TARGET_UNIT[targetType]
        allTargets = targetName is None
        allShifts = shift is None

        filterKwargs: dict = {"action": action}
        if not allTargets:
            filterKwargs["targetType"] = targetType
            filterKwargs["targetName"] = targetName
        recs = self._filterProduction(startDate, endDate, **filterKwargs)
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        perTarget: dict[str, tuple[float, float]] = {}
        perTargetEmp: dict[tuple[str, int | None], tuple[float, float]] = {}
        perShift: dict[int | None, tuple[float, float]] = {}
        totalQ = 0.0
        totalH = 0.0
        for r in recs:
            tn = r.targetName or ""
            q = r.quantity or 0
            h = r.hours
            cq, ch = perTarget.get(tn, (0.0, 0.0))
            perTarget[tn] = (cq + q, ch + h)
            key = (tn, r.employeeId)
            cq, ch = perTargetEmp.get(key, (0.0, 0.0))
            perTargetEmp[key] = (cq + q, ch + h)
            cq, ch = perShift.get(r.shift, (0.0, 0.0))
            perShift[r.shift] = (cq + q, ch + h)
            totalQ += q
            totalH += h

        title = f"TKG {action} Productivity"
        subtitleBits = []
        if not allTargets:
            subtitleBits.append(str(targetName))
        if not allShifts:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        def fmtNum(x: float) -> str:
            return f"{x:g}"

        headersTarget = ["Target", f"Quantity ({unit})", "Hours", "Rate (per hr)"]
        headersEmp = ["Employee", f"Quantity ({unit})", "Hours", "Rate (per hr)"]
        headersShift = ["Shift", f"Quantity ({unit})", "Hours", "Rate (per hr)"]

        if len(recs) == 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(2)
            self.drawText("No production recorded in this range.")
            self.nextPage()
            self.pdf.save()
            return

        def empSortKey(eid):
            emp = self.db.employees.get(eid)
            if emp is None:
                return (1, "", "", eid if eid is not None else 0)
            return (0, (emp.lastName or "").lower(),
                    (emp.firstName or "").lower(), eid or 0)

        def shiftSortKey(s):
            return (s is None, s or 0)

        def renderSection(sectionName: str, rows: list[list[str]],
                          headers: list[str],
                          totalsRow: list[str] | None = None):
            # Totals render as their own pure-header table after the main rows
            # so they come out bold — same pattern productionSummaryReport
            # uses to emphasize its "Total" row.
            olen = len(rows)
            while len(rows) > 0:
                self.setupPage()
                self.drawTitle(title)
                self.drawSubtitle(subtitle)
                self.skipLines(2)
                self.drawSection(sectionName if len(rows) == olen
                                 else f"{sectionName} -- Continued")
                drawn = self.drawTable(rows, headers)
                if drawn == len(rows) and totalsRow is not None:
                    self.drawTable([], totalsRow)
                rows = rows[drawn:]
                self.nextPage()

        def renderTargetDetail(tn: str):
            empsHere = sorted(
                {eid for (t, eid) in perTargetEmp if t == tn},
                key=empSortKey,
            )
            rows = []
            for eid in empsHere:
                eq, eh = perTargetEmp[(tn, eid)]
                rows.append([self._employeeName(eid),
                             fmtNum(eq), fmtNum(eh), self._fmtRate(eq, eh)])
            tq, th = perTarget[tn]
            totalsRow = ["Total", fmtNum(tq), fmtNum(th),
                         self._fmtRate(tq, th)]
            renderSection(f"{action}: {tn}", rows, headersEmp, totalsRow)

        if allTargets:
            sortedTargets = sorted(perTarget.keys())
            summaryRows = []
            for tn in sortedTargets:
                tq, th = perTarget[tn]
                summaryRows.append([tn, fmtNum(tq), fmtNum(th),
                                    self._fmtRate(tq, th)])
            summaryTotals = ["Total", fmtNum(totalQ), fmtNum(totalH),
                             self._fmtRate(totalQ, totalH)]
            renderSection("Summary by Target", summaryRows, headersTarget,
                          summaryTotals)

            if allShifts:
                shiftRows = []
                for s in sorted(perShift.keys(), key=shiftSortKey):
                    sq, sh = perShift[s]
                    lbl = str(s) if s is not None else "(none)"
                    shiftRows.append([lbl, fmtNum(sq), fmtNum(sh),
                                      self._fmtRate(sq, sh)])
                shiftTotals = ["Total", fmtNum(totalQ), fmtNum(totalH),
                               self._fmtRate(totalQ, totalH)]
                renderSection("Overview by Shift", shiftRows, headersShift,
                              shiftTotals)

            for tn in sortedTargets:
                renderTargetDetail(tn)
        else:
            renderTargetDetail(targetName)

        self.pdf.save()

    def _toolChangeProductivityReport(self, shift: int | None,
                                      startDate: datetime.date,
                                      endDate: datetime.date):
        # Tool Change collapse: no rate/hr, no per-employee. Just total hours
        # per shift (or a single row when a shift is selected). The shift
        # selector stays active at the UI layer so "specific shift" is legal;
        # it just produces a one-row table.
        recs = self._filterProduction(startDate, endDate, action="Tool Change")
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        perShift: dict[int | None, float] = {}
        totalH = 0.0
        for r in recs:
            perShift[r.shift] = perShift.get(r.shift, 0.0) + r.hours
            totalH += r.hours

        title = "TKG Tool Change Productivity"
        subtitleBits = []
        if shift is not None:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        if len(recs) == 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(2)
            self.drawText("No production recorded in this range.")
            self.nextPage()
            self.pdf.save()
            return

        headers = ["Shift", "Total Hours"]
        rows: list[list[str]] = []
        totalsRow: list[str] | None = None
        if shift is None:
            for s in sorted(perShift.keys(),
                            key=lambda k: (k is None, k or 0)):
                lbl = str(s) if s is not None else "(none)"
                rows.append([lbl, f"{perShift[s]:g}"])
            totalsRow = ["Total", f"{totalH:g}"]
        else:
            # Specific-shift: the single row is already the total; no separate
            # totals row would add anything.
            rows.append([str(shift), f"{totalH:g}"])

        olen = len(rows)
        while len(rows) > 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(2)
            self.drawSection("Hours by Shift" if len(rows) == olen
                             else "Hours by Shift -- Continued")
            drawn = self.drawTable(rows, headers)
            if drawn == len(rows) and totalsRow is not None:
                self.drawTable([], totalsRow)
            rows = rows[drawn:]
            self.nextPage()
        self.pdf.save()

    def productionEmployeeProductivityReport(self,
                                             action: str | None,
                                             employeeId: int | None,
                                             startDate: datetime.date,
                                             endDate: datetime.date):
        # Step 24: per-employee productivity report. Mirrors Step 18's structure
        # but pivots on employee instead of target. action=None means "all
        # actions"; employeeId=None means "all employees". Tool Change is
        # included to preempt "the Tool Change report is missing" tickets when
        # users have a specific employee selected; it rolls up by shift instead
        # of per-target, matching the productivity-report convention. Cross-
        # action rate totals show "—" because mixing Tool Change hours into a
        # rate denominator is misleading.
        if action is not None and action not in PRODUCTION_ACTIONS:
            raise RuntimeError(f'unknown action {action!r}')
        if employeeId is not None and employeeId not in self.db.employees:
            raise RuntimeError(f'employeeId {employeeId} not in self.db.employees')

        filterKwargs: dict = {}
        if action is not None:
            filterKwargs["action"] = action
        if employeeId is not None:
            filterKwargs["employeeId"] = employeeId
        recs = self._filterProduction(startDate, endDate, **filterKwargs)

        allEmps = employeeId is None
        allActions = action is None

        if allEmps and allActions:
            title = "TKG Productivity by Employee"
        elif allEmps:
            title = f"TKG {action} Productivity by Employee"
        elif allActions:
            title = f"TKG Productivity: {self._employeeName(employeeId)}"
        else:
            title = f"TKG {action} Productivity: {self._employeeName(employeeId)}"
        subtitle = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if len(recs) == 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(2)
            self.drawText("No production recorded in this range.")
            self.nextPage()
            self.pdf.save()
            return

        perAction: dict[str, tuple[float, float]] = {}
        perEmployee: dict[int | None, tuple[float, float]] = {}
        perEmpAction: dict[tuple[int | None, str], tuple[float, float]] = {}
        perEmpActionTarget: dict[tuple[int | None, str, str],
                                 tuple[float, float]] = {}
        perEmpToolChangeShift: dict[tuple[int | None, int | None], float] = {}
        # Record counts per action / per (employee, action). Used in overview
        # rows to give Tool Change a meaningful Quantity-column value (the
        # number of tool change events) rather than "—".
        perActionCount: dict[str, int] = {}
        perEmpActionCount: dict[tuple[int | None, str], int] = {}
        totalQ = 0.0
        totalH = 0.0
        for r in recs:
            a = r.action or ""
            eid = r.employeeId
            q = r.quantity or 0
            h = r.hours
            tn = r.targetName or ""
            s = r.shift
            totalQ += q
            totalH += h
            cq, ch = perAction.get(a, (0.0, 0.0))
            perAction[a] = (cq + q, ch + h)
            cq, ch = perEmployee.get(eid, (0.0, 0.0))
            perEmployee[eid] = (cq + q, ch + h)
            cq, ch = perEmpAction.get((eid, a), (0.0, 0.0))
            perEmpAction[(eid, a)] = (cq + q, ch + h)
            cq, ch = perEmpActionTarget.get((eid, a, tn), (0.0, 0.0))
            perEmpActionTarget[(eid, a, tn)] = (cq + q, ch + h)
            perActionCount[a] = perActionCount.get(a, 0) + 1
            perEmpActionCount[(eid, a)] = perEmpActionCount.get((eid, a), 0) + 1
            if a == "Tool Change":
                perEmpToolChangeShift[(eid, s)] = (
                    perEmpToolChangeShift.get((eid, s), 0.0) + h)

        def fmtNum(x: float) -> str:
            return f"{x:g}"

        def empSortKey(eid):
            emp = self.db.employees.get(eid)
            if emp is None:
                return (1, "", "", eid if eid is not None else 0)
            return (0, (emp.lastName or "").lower(),
                    (emp.firstName or "").lower(), eid or 0)

        def shiftSortKey(s):
            return (s is None, s or 0)

        def renderSection(sectionName: str, rows: list[list[str]],
                          headers: list[str],
                          totalsRow: list[str] | None = None):
            olen = len(rows)
            while len(rows) > 0:
                self.setupPage()
                self.drawTitle(title)
                self.drawSubtitle(subtitle)
                self.skipLines(2)
                self.drawSection(sectionName if len(rows) == olen
                                 else f"{sectionName} -- Continued")
                drawn = self.drawTable(rows, headers)
                if drawn == len(rows) and totalsRow is not None:
                    self.drawTable([], totalsRow)
                rows = rows[drawn:]
                self.nextPage()

        # Aggregate overviews. Each is shown only when the dimension is
        # actually multi-valued in the filtered recordset — a single-row
        # summary table is just noise.
        if allActions and len(perAction) > 1:
            rows = []
            for a in PRODUCTION_ACTIONS:
                if a not in perAction:
                    continue
                q, h = perAction[a]
                rows.append([a, fmtNum(q), fmtNum(h), self._fmtRate(q, h)])
            # Cross-action total: rate suppressed (would mix produced hours
            # with Tool Change hours); Quantity also "—" because the column
            # mixes units across rows (drops, parts, count of changes).
            totalsRow = ["Total", "—", fmtNum(totalH), "—"]
            renderSection("Summary by Action", rows,
                          ["Action", "Quantity", "Hours", "Rate (per hr)"],
                          totalsRow)

        if allEmps and len(perEmployee) > 1:
            sortedEmps = sorted(perEmployee.keys(), key=empSortKey)
            rows = []
            actionIsTC = (action is not None
                          and PRODUCTION_ACTION_TARGET[action] == "")
            for eid in sortedEmps:
                q, h = perEmployee[eid]
                if actionIsTC:
                    assert action is not None
                    # Tool Change: per-employee event count.
                    count = perEmpActionCount.get((eid, action), 0)
                    rows.append([self._employeeName(eid), str(count),
                                 fmtNum(h), "—"])
                elif not allActions:
                    rows.append([self._employeeName(eid), fmtNum(q),
                                 fmtNum(h), self._fmtRate(q, h)])
                else:
                    # All actions — rate would mix Tool Change hours, leave "—".
                    rows.append([self._employeeName(eid), fmtNum(q),
                                 fmtNum(h), "—"])
            if actionIsTC:
                assert action is not None
                totalsRow = ["Total",
                             str(perActionCount.get(action, 0)),
                             fmtNum(totalH), "—"]
            elif not allActions:
                totalsRow = ["Total", fmtNum(totalQ), fmtNum(totalH),
                             self._fmtRate(totalQ, totalH)]
            else:
                totalsRow = ["Total", fmtNum(totalQ), fmtNum(totalH), "—"]
            renderSection("Summary by Employee", rows,
                          ["Employee", "Quantity", "Hours", "Rate (per hr)"],
                          totalsRow)

        # Detail sections.
        def renderToolChangeDetail(eid, sectionName: str):
            shiftKeys = sorted(
                {s for (e, s) in perEmpToolChangeShift if e == eid},
                key=shiftSortKey,
            )
            rows = []
            empTotalH = 0.0
            for s in shiftKeys:
                h = perEmpToolChangeShift[(eid, s)]
                empTotalH += h
                lbl = str(s) if s is not None else "(none)"
                rows.append([lbl, fmtNum(h)])
            totalsRow = ["Total", fmtNum(empTotalH)]
            renderSection(sectionName, rows, ["Shift", "Hours"], totalsRow)

        def renderTargetDetail(eid, a: str, sectionName: str):
            unit = PRODUCTION_TARGET_UNIT[PRODUCTION_ACTION_TARGET[a]]
            targetsHere = sorted(
                {tn for (e, ax, tn) in perEmpActionTarget
                 if e == eid and ax == a}
            )
            rows = []
            actionQ = 0.0
            actionH = 0.0
            for tn in targetsHere:
                q, h = perEmpActionTarget[(eid, a, tn)]
                actionQ += q
                actionH += h
                rows.append([tn, fmtNum(q), fmtNum(h), self._fmtRate(q, h)])
            totalsRow = ["Total", fmtNum(actionQ), fmtNum(actionH),
                         self._fmtRate(actionQ, actionH)]
            renderSection(sectionName, rows,
                          ["Target", f"Quantity ({unit})", "Hours",
                           "Rate (per hr)"],
                          totalsRow)

        def actionsForEmployee(eid):
            return [a for a in PRODUCTION_ACTIONS if (eid, a) in perEmpAction]

        if allEmps:
            sortedEmps = sorted(perEmployee.keys(), key=empSortKey)
            for eid in sortedEmps:
                empName = self._employeeName(eid)
                for a in actionsForEmployee(eid):
                    if PRODUCTION_ACTION_TARGET[a] == "":
                        sectionName = (f"{empName} — Tool Change: Hours by Shift"
                                       if allActions
                                       else f"{empName}: Hours by Shift")
                        renderToolChangeDetail(eid, sectionName)
                    else:
                        sectionName = (f"{empName} — {a}: by Target"
                                       if allActions
                                       else f"{empName}: by Target")
                        renderTargetDetail(eid, a, sectionName)
        else:
            for a in actionsForEmployee(employeeId):
                if PRODUCTION_ACTION_TARGET[a] == "":
                    sectionName = ("Tool Change: Hours by Shift"
                                   if allActions
                                   else "Hours by Shift")
                    renderToolChangeDetail(employeeId, sectionName)
                else:
                    sectionName = (f"{a}: by Target" if allActions
                                   else "Summary by Target")
                    renderTargetDetail(employeeId, a, sectionName)

        self.pdf.save()

    def productionTrendReport(self, action: str,
                              targetName: str | None,
                              shift: int | None,
                              startDate: datetime.date,
                              endDate: datetime.date):
        # Step 19: 30-day rolling-rate line chart. Graph-only; numbers for the
        # same window come from the Step 18 productivity report. Range is
        # validated to be at least TREND_MIN_RANGE_DAYS so the window always
        # has a meaningful span; the UI enforces this too, but the report is a
        # public entrypoint so we belt-and-suspender it.
        if action not in PRODUCTION_ACTIONS:
            raise RuntimeError(f'unknown action {action!r}')
        if (endDate - startDate).days < TREND_MIN_RANGE_DAYS - 1:
            raise RuntimeError(
                f'Trend reports require a date range of at least '
                f'{TREND_MIN_RANGE_DAYS} days.'
            )
        if action == "Tool Change":
            self._toolChangeTrendReport(shift, startDate, endDate)
            return

        targetType = PRODUCTION_ACTION_TARGET[action]
        unit = PRODUCTION_TARGET_UNIT[targetType]
        allTargets = targetName is None
        allShifts = shift is None

        # Only plot days whose full 30-day lookback fits inside the requested
        # range — reaching outside the range would mean partial windows and a
        # noisy leading edge (first 30 points climbing up to a steady state).
        # Per Matthew 2026-04-24: every datapoint must represent a full window.
        plotStart = startDate + datetime.timedelta(days=TREND_WINDOW_DAYS - 1)

        filterKwargs: dict = {"action": action}
        if not allTargets:
            filterKwargs["targetType"] = targetType
            filterKwargs["targetName"] = targetName
        recs = self._filterProduction(startDate, endDate, **filterKwargs)
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        title = f"TKG {action} Trend"
        subtitleBits = []
        if not allTargets:
            subtitleBits.append(str(targetName))
        if not allShifts:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        yLabel = f"Rate ({unit}/hr, 30-day avg)"

        if allTargets:
            # Leading aggregate chart across every target, then one chart per
            # target. Order: total first (team wants the fleet view up front),
            # then alphabetical by target name.
            aggSeries = self._buildTrendSeries(recs, plotStart, endDate,
                                               splitByShift=allShifts)
            self._drawTrendPage(title, subtitle, "All targets (aggregate)",
                                aggSeries, yLabel)
            targets = sorted({r.targetName for r in recs if r.targetName})
            for tn in targets:
                subset = [r for r in recs if r.targetName == tn]
                series = self._buildTrendSeries(subset, plotStart, endDate,
                                                splitByShift=allShifts)
                self._drawTrendPage(title, subtitle, f"Target: {tn}",
                                    series, yLabel)
        else:
            series = self._buildTrendSeries(recs, plotStart, endDate,
                                            splitByShift=allShifts)
            self._drawTrendPage(title, subtitle, f"Target: {targetName}",
                                series, yLabel)
        self.pdf.save()

    def _toolChangeTrendReport(self, shift: int | None,
                               startDate: datetime.date,
                               endDate: datetime.date):
        # Tool Change has no rate/hr — "time spent" is the metric. We plot the
        # 30-day rolling *sum* of hours so the y-axis reads as "hours spent on
        # tool changes in the preceding 30 days." This mirrors Step 18's Tool
        # Change collapse (which surfaces total hours by shift) and gives the
        # team a trend line they can compare month-over-month.
        plotStart = startDate + datetime.timedelta(days=TREND_WINDOW_DAYS - 1)
        recs = self._filterProduction(startDate, endDate, action="Tool Change")
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        title = "TKG Tool Change Trend"
        subtitleBits = []
        if shift is not None:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        series = self._buildToolChangeTrendSeries(
            recs, plotStart, endDate, splitByShift=(shift is None))
        self._drawTrendPage(title, subtitle, "Time spent",
                            series, "Hours (30-day total)")
        self.pdf.save()

    def _rollingRate(self, perDay: dict, startDate: datetime.date,
                     endDate: datetime.date, mode: str | None = None):
        # Given perDay: {date: (qty, hours)}, return [(date, rate_or_None), ...]
        # for every date in [startDate, endDate]. rate is None when the window
        # has no usable data (caller drops None points before plotting).
        mode = mode if mode is not None else TREND_MODE
        out: list[tuple[datetime.date, float | None]] = []
        d = startDate
        step = datetime.timedelta(days=1)
        while d <= endDate:
            windowStart = d - datetime.timedelta(days=TREND_WINDOW_DAYS - 1)
            if mode == "ratioOfSums":
                sumQ = 0.0
                sumH = 0.0
                wd = windowStart
                while wd <= d:
                    if wd in perDay:
                        q, h = perDay[wd]
                        sumQ += q
                        sumH += h
                    wd += step
                rate = (sumQ / sumH) if sumH > 0 else None
            elif mode == "meanOfRates":
                rates = []
                wd = windowStart
                while wd <= d:
                    if wd in perDay:
                        q, h = perDay[wd]
                        if q > 0 and h > 0:
                            rates.append(q / h)
                    wd += step
                rate = (sum(rates) / len(rates)) if rates else None
            else:
                raise RuntimeError(f'unknown TREND_MODE {mode!r}')
            out.append((d, rate))
            d += step
        return out

    def _buildTrendSeries(self, recs, startDate, endDate, splitByShift):
        # Build [(label, [(date, y_or_None), ...]), ...] for non-Tool-Change
        # trends. When splitByShift is True, emit one series per shift plus
        # a final "All shifts" aggregate.
        def toPerDay(subset):
            perDay: dict[datetime.date, tuple[float, float]] = {}
            for r in subset:
                if r.date is None:
                    continue
                q, h = perDay.get(r.date, (0.0, 0.0))
                perDay[r.date] = (q + (r.quantity or 0), h + r.hours)
            return perDay

        if not splitByShift:
            return [("Rate", self._rollingRate(toPerDay(recs), startDate, endDate))]

        out = []
        shifts = sorted({r.shift for r in recs if r.shift is not None})
        for s in shifts:
            subset = [r for r in recs if r.shift == s]
            out.append((f"Shift {s}",
                        self._rollingRate(toPerDay(subset), startDate, endDate)))
        noneSubset = [r for r in recs if r.shift is None]
        if len(noneSubset) > 0:
            out.append(("Shift (none)",
                        self._rollingRate(toPerDay(noneSubset), startDate, endDate)))
        out.append(("All shifts",
                    self._rollingRate(toPerDay(recs), startDate, endDate)))
        return out

    def _buildToolChangeTrendSeries(self, recs, startDate, endDate, splitByShift):
        # Tool Change variant: 30-day rolling *sum* of hours instead of a rate.
        def toPerDay(subset):
            perDay: dict[datetime.date, float] = {}
            for r in subset:
                if r.date is None:
                    continue
                perDay[r.date] = perDay.get(r.date, 0.0) + r.hours
            return perDay

        def rollingSum(perDay):
            out = []
            d = startDate
            step = datetime.timedelta(days=1)
            while d <= endDate:
                windowStart = d - datetime.timedelta(days=TREND_WINDOW_DAYS - 1)
                total = 0.0
                wd = windowStart
                while wd <= d:
                    if wd in perDay:
                        total += perDay[wd]
                    wd += step
                out.append((d, total))
                d += step
            return out

        if not splitByShift:
            return [("Hours", rollingSum(toPerDay(recs)))]

        out = []
        shifts = sorted({r.shift for r in recs if r.shift is not None})
        for s in shifts:
            subset = [r for r in recs if r.shift == s]
            out.append((f"Shift {s}", rollingSum(toPerDay(subset))))
        noneSubset = [r for r in recs if r.shift is None]
        if len(noneSubset) > 0:
            out.append(("Shift (none)", rollingSum(toPerDay(noneSubset))))
        out.append(("All shifts", rollingSum(toPerDay(recs))))
        return out

    def _drawTrendPage(self, title: str, subtitle: str, sectionLabel: str,
                       series: list, yLabel: str):
        # One trend chart per page. Header matches the productivity report's
        # title/subtitle/section cadence so switching between the two reports
        # feels consistent.
        self.setupPage()
        self.drawTitle(title)
        self.drawSubtitle(subtitle)
        self.skipLines(1)
        self.drawSection(sectionLabel)

        # Drop series whose every point is None (e.g., a shift with no data in
        # the window). A series that's mostly data but has occasional None
        # points is kept; those None points are filtered out before plotting,
        # so the line connects across small gaps. Require >= 2 concrete points
        # so reportlab has a line to draw.
        cleaned = []
        anyConcrete = False
        for (label, pts) in series:
            concrete = [(d, y) for (d, y) in pts if y is not None]
            if len(concrete) > 0:
                anyConcrete = True
            if len(concrete) >= 2:
                cleaned.append((label, concrete))

        if len(cleaned) == 0:
            self.skipLines(1)
            if anyConcrete:
                # Data exists but the range leaves < 2 full-window datapoints
                # — i.e. the user picked the 30-day floor, which gives a
                # single plot point. Tell them plainly.
                self.drawText("Not enough data in this range to plot a trend line "
                              "(try a longer date range).")
            else:
                self.drawText("No production recorded in this range.")
            self.nextPage()
            return

        self.drawLinePlot(cleaned, yLabel)
        self.nextPage()

    def drawLinePlot(self, series: list, yLabel: str):
        # Renders one LinePlot + Legend inside a single Drawing placed at
        # self.lastLine. series is [(label, [(date, y), ...]), ...] with every
        # y already non-None and every series having >= 2 points.
        #
        # reportlab's type stubs declare LinePlot/Legend dimensions as int and
        # don't expose XValueAxis.labels — both are wrong (the library accepts
        # floats at runtime and labels is a real Drawing attr). Per-line pyright
        # ignores below mark the stub limitations, not real bugs.
        plotWidth = self.right - self.left
        plotHeight = 3.5 * inch

        drawing = Drawing(plotWidth, plotHeight)  # pyright: ignore[reportArgumentType]

        lp = LinePlot()
        lp.x = 55
        lp.y = 55
        lp.width = plotWidth - 180  # pyright: ignore[reportAttributeAccessIssue]
        lp.height = plotHeight - 85  # pyright: ignore[reportAttributeAccessIssue]

        # x-axis in date ordinals so reportlab's numeric axis tick picker works.
        # labelTextFormat converts back to an ISO date for display.
        lp.data = [[(d.toordinal(), y) for (d, y) in pts]  # pyright: ignore[reportAttributeAccessIssue]
                   for (_, pts) in series]

        for i in range(len(series)):
            color = _TREND_LINE_COLORS[i % len(_TREND_LINE_COLORS)]
            lp.lines[i].strokeColor = color
            lp.lines[i].strokeWidth = 1.2

        lp.xValueAxis.labelTextFormat = (
            lambda x: datetime.date.fromordinal(int(x)).isoformat()
        )
        lp.xValueAxis.labels.angle = 45  # pyright: ignore[reportAttributeAccessIssue]
        lp.xValueAxis.labels.boxAnchor = 'e'  # pyright: ignore[reportAttributeAccessIssue]
        lp.xValueAxis.labels.fontSize = 7  # pyright: ignore[reportAttributeAccessIssue]
        lp.xValueAxis.visibleGrid = True
        lp.xValueAxis.gridStrokeColor = colors.lightgrey

        lp.yValueAxis.labels.fontSize = 8  # pyright: ignore[reportAttributeAccessIssue]
        lp.yValueAxis.visibleGrid = True
        lp.yValueAxis.gridStrokeColor = colors.lightgrey

        drawing.add(lp)

        # Axis labels (non-rotated — keeps the helper simple and legible).
        drawing.add(String(lp.x + lp.width / 2, 8,
                           "Date", fontSize=9, textAnchor='middle'))
        drawing.add(String(10, lp.y + lp.height + 6,
                           yLabel, fontSize=9, textAnchor='start'))

        legend = Legend()
        legend.x = plotWidth - 110  # pyright: ignore[reportAttributeAccessIssue]
        legend.y = lp.y + lp.height - 10
        legend.colorNamePairs = [
            (_TREND_LINE_COLORS[i % len(_TREND_LINE_COLORS)], series[i][0])
            for i in range(len(series))
        ]
        legend.fontSize = 8
        legend.deltay = 11
        legend.alignment = 'right'
        legend.columnMaximum = 10
        drawing.add(legend)

        renderPDF.draw(drawing, self.pdf, self.left, self.lastLine - plotHeight)
        self.lastLine -= plotHeight
