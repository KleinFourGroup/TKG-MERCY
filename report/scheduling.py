import datetime
from typing import TYPE_CHECKING

from scheduling import (
    LATE, INFEASIBLE_NO_CAPACITY, INFEASIBLE_NO_RATE,
    WARN_FALLBACK_RATE, WARN_MISSING_FIRESCRAP,
    groupScheduleRows, scheduleGroupHeading, formatPressHours,
)

if TYPE_CHECKING:
    from records import Database
    from reportlab.pdfgen import canvas
    from scheduling import ScheduleResult, OrderFlag, ScheduleWarning

# Human-readable issue labels for the flag kinds (addendum §4). Kept here, not on
# OrderFlag, so the record stays a pure data carrier and the report owns
# presentation.
_FLAG_LABEL = {
    LATE: "Late",
    INFEASIBLE_NO_CAPACITY: "No capacity",
    INFEASIBLE_NO_RATE: "No rate",
}


def _flagDetail(flag: "OrderFlag") -> str:
    """The magnitude line for a flagged order (addendum §4): which fields are
    meaningful depends on the kind."""
    if flag.kind == LATE:
        return f"{flag.daysLate} day(s) late; {flag.piecesShort:,} pcs short at deadline"
    if flag.kind == INFEASIBLE_NO_CAPACITY:
        return f"{flag.shortHours:g} press-hr / {flag.piecesShort:,} pcs unplaced by horizon"
    if flag.kind == INFEASIBLE_NO_RATE:
        return "no pressing history and no Part.pressing rate"
    return ""


def _warningNote(warning: "ScheduleWarning") -> str:
    """The plain-language note for a soft warning (addendum §4)."""
    if warning.kind == WARN_FALLBACK_RATE:
        return "rate from Part.pressing fallback (no recent pressing history)"
    if warning.kind == WARN_MISSING_FIRESCRAP:
        return "fireScrap not set (scrap inflation may be understated)"
    return warning.kind


# Flagged-order client / due-date presentation (Step 73). Looked up from the
# order at render time so OrderFlag stays a pure data carrier; mirrors
# schedule_tab.py so the PDF and the on-screen detail window read identically.
def _flagClient(db, flag: "OrderFlag") -> str:
    order = db.orders.get(flag.orderNum)
    return order.client if order is not None else ""


def _flagDueStr(db, flag: "OrderFlag") -> str:
    order = db.orders.get(flag.orderNum)
    if order is None or order.dueDate is None:
        return "?"
    return order.dueDate.isoformat()


def _flagSortKey(db, flag: "OrderFlag"):
    # Sort flagged orders by due date (undated last), orderNum breaking ties.
    order = db.orders.get(flag.orderNum)
    due = order.dueDate if order is not None else None
    return (due is None, due or datetime.date.max, flag.orderNum)


def _presserCell(db, employeeId) -> str:
    """The Presser column for a schedule row (Step 66): the staffed presser's
    label, empty when unstaffed (never in practice — a running press always has a
    present presser). Rendered inline from db.employees rather than via the Qt tab
    helpers so the report layer stays decoupled from the widgets, matching the
    inline employee labels in report/employees.py. Format mirrors _employeeLabel /
    pressers_tab._presserLabel so the on-screen table and the PDF read identically."""
    if employeeId is None:
        return ""
    emp = db.employees.get(employeeId)
    if emp is None:
        return f"(missing #{employeeId})"
    return f"{emp.lastName.upper()} {emp.firstName} ({emp.idNum})"


class ScheduleReportsMixin:
    # Production Schedule Report (Step 53). Consumes a `ScheduleResult` from the
    # stateless scheduler seam (scheduling.schedule) — never the algorithm's
    # internals — and lays it out as a (date, shift, press, part) -> quantity
    # grid, an explicit flagged-orders section, and a soft-warnings section.
    # Builds on the PDFReportCore primitives — see report/__init__.py for the
    # composition.

    if TYPE_CHECKING:
        # Attributes + helpers provided by PDFReportCore (composed in last).
        db: Database
        pdf: canvas.Canvas
        font: str
        fontSize: int
        lastLine: float
        bottom: float
        lineSpace: float
        def setFont(self, font: str, size: int) -> None: ...
        def setupPage(self) -> None: ...
        def nextPage(self) -> None: ...
        def skipLines(self, numLines) -> None: ...
        def drawText(self, text: str) -> None: ...
        def drawTitle(self, text: str) -> None: ...
        def drawSubtitle(self, text: str) -> None: ...
        def drawParagraph(self, text: str) -> None: ...
        def drawSection(self, text: str) -> None: ...
        def drawTable(self, data: list[list[str]], headers: list[str] | None = None, widths: list[float] | None = None) -> int: ...

    def _subHeading(self, text: str) -> None:
        # A (date, shift) group subheading (Step 67), sized between drawSection
        # (18) and body text (12) so groups read as a level under the "Schedule"
        # section heading.
        oldFont = (self.font, self.fontSize)
        self.setFont("Times-Bold", 14)
        self.drawText(text)
        self.setFont(*oldFont)

    def _scheduleBanner(self, title: str, subtitle: str, meta: str,
                        sectionName: str, continued: bool) -> None:
        # The per-page banner shared by every schedule section: a big bold title +
        # subtitle (just the generation date, kept short so it never overflows the
        # page), then the horizon / active-filter metadata on a normal-weight line
        # that *wraps* (drawSubtitle doesn't — Step 67 fix for a long filter
        # subtitle running off the page), then the section heading. setupPage
        # resets lastLine to the page top first.
        self.setupPage()
        self.drawTitle(title)
        self.drawSubtitle(subtitle)
        if meta:
            self.drawParagraph(meta)
        self.skipLines(1)
        self.drawSection(f"{sectionName} -- Continued" if continued else sectionName)

    def _groupedScheduleSection(self, title: str, subtitle: str, meta: str,
                                sectionName: str, groups: list[tuple[str, list[list[str]]]],
                                headers: list[str], emptyText: str) -> None:
        # The Step 67 grouped Schedule section: one banner + a "Schedule" heading,
        # then a per-(date, shift) subheading over a table for each group, flowing
        # across pages. Re-draws the banner + a "-- Continued" heading on each
        # overflow page, and repeats a group's subheading with "(cont.)" when its
        # table spans a page break.
        if not groups:
            self._scheduleBanner(title, subtitle, meta, sectionName, False)
            self.drawText(emptyText)
            self.nextPage()
            return

        self._scheduleBanner(title, subtitle, meta, sectionName, False)
        for heading, rows in groups:
            # Don't orphan a subheading at the page bottom: if there isn't room for
            # the heading plus a header row and one data row, start a fresh page.
            if self.lastLine - self.fontSize * self.lineSpace * 4 < self.bottom:
                self.nextPage()
                self._scheduleBanner(title, subtitle, meta, sectionName, True)
            self._subHeading(heading)
            remaining = rows
            while len(remaining) > 0:
                drawn = self.drawTable(remaining, headers)
                remaining = remaining[drawn:]
                if len(remaining) > 0:
                    # Page filled mid-group -> continue on a fresh page. (On a
                    # fresh page at least one row always fits, so this terminates.)
                    self.nextPage()
                    self._scheduleBanner(title, subtitle, meta, sectionName, True)
                    self._subHeading(f"{heading} (cont.)")
        self.nextPage()

    def _scheduleSection(self, title: str, subtitle: str, meta: str, sectionName: str,
                         headers: list[str], rows: list[list[str]],
                         emptyText: str) -> None:
        # One report section with its own banner, paginating the table the way the
        # production reports do — re-drawing the banner and a "-- Continued"
        # heading on each overflow page. _scheduleBanner resets lastLine to the top
        # so drawTable always fits at least one row per page.
        olen = len(rows)
        if olen == 0:
            self._scheduleBanner(title, subtitle, meta, sectionName, False)
            self.drawText(emptyText)
            self.nextPage()
            return
        while len(rows) > 0:
            self._scheduleBanner(title, subtitle, meta, sectionName, len(rows) != olen)
            drawn = self.drawTable(rows, headers)
            rows = rows[drawn:]
            self.nextPage()

    def scheduleReport(self, result: "ScheduleResult", horizonDays: int | None = None,
                       filterDesc: str | None = None):
        title = "TKG Production Schedule"
        subtitle = f"Generated {result.today.isoformat()}"
        # Horizon + active filter go on a wrapped, normal-weight metadata line
        # rather than the bold subtitle: a long filter description on the bold
        # subtitle overflowed the page width (drawSubtitle doesn't wrap) — Step 67.
        metaParts = []
        if horizonDays is not None:
            metaParts.append(f"horizon {horizonDays} day(s)")
        if filterDesc:
            metaParts.append(filterDesc)
        meta = " — ".join(metaParts)

        # Step 67: the schedule is grouped by (date, shift) subheadings, each over
        # a 5-column table — Date and Shift move out of the repeated columns into
        # the group heading, freeing width for the Presser column.
        groupHeaders = ["Press", "Part", "Quantity", "Press-hours", "Presser"]
        groups = [
            (scheduleGroupHeading(key[0], key[1]), [[
                r.press,
                r.part,
                f"{r.quantity:,}",
                formatPressHours(r.hours),
                _presserCell(self.db, r.presser),
            ] for r in rows])
            for key, rows in groupScheduleRows(result.rows)
        ]
        self._groupedScheduleSection(title, subtitle, meta, "Schedule", groups,
                                     groupHeaders, "No production scheduled.")

        # Flagged orders carry their client and sort by due date (Step 73), looked
        # up from the order at render time so OrderFlag stays a pure data carrier.
        flagHeaders = ["Order", "Client", "Part", "Due Date", "Issue", "Detail"]
        flagData = [[
            f.orderNum,
            _flagClient(self.db, f),
            f.part,
            _flagDueStr(self.db, f),
            _FLAG_LABEL.get(f.kind, f.kind),
            _flagDetail(f),
        ] for f in sorted(result.flags, key=lambda fl: _flagSortKey(self.db, fl))]
        # Flags are order-level / dateless, so a filtered variant still shows them
        # all (design call 2026-07-02) — the section name says so when filtered.
        flagSection = "Flagged Orders (all orders)" if filterDesc else "Flagged Orders"
        self._scheduleSection(
            title, subtitle, meta, flagSection, flagHeaders, flagData,
            "No late or infeasible orders — all eligible orders fit before their "
            "effective press-by dates.")

        # Soft warnings only get a section when there are any — they're
        # incidental data-quality notes, not a standing report fixture.
        if result.warnings:
            warnHeaders = ["Part", "Warning"]
            warnData = [[w.part, _warningNote(w)] for w in result.warnings]
            self._scheduleSection(title, subtitle, meta, "Warnings", warnHeaders,
                                  warnData, "")

        self.pdf.save()
