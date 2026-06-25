from typing import TYPE_CHECKING

from scheduling import (
    LATE, INFEASIBLE_NO_CAPACITY, INFEASIBLE_NO_RATE,
    WARN_FALLBACK_RATE, WARN_MISSING_FIRESCRAP,
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
        return f"{flag.daysLate} day(s) late; {flag.piecesShort:g} pcs short at deadline"
    if flag.kind == INFEASIBLE_NO_CAPACITY:
        return f"{flag.shortHours:g} press-hr / {flag.piecesShort:g} pcs unplaced by horizon"
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
        def setupPage(self) -> None: ...
        def nextPage(self) -> None: ...
        def skipLines(self, numLines) -> None: ...
        def drawText(self, text: str) -> None: ...
        def drawTitle(self, text: str) -> None: ...
        def drawSubtitle(self, text: str) -> None: ...
        def drawSection(self, text: str) -> None: ...
        def drawTable(self, data: list[list[str]], headers: list[str] | None = None, widths: list[float] | None = None) -> int: ...

    def _scheduleSection(self, title: str, subtitle: str, sectionName: str,
                         headers: list[str], rows: list[list[str]],
                         emptyText: str) -> None:
        # One report section with its own title/subtitle banner, paginating the
        # table the way the production reports do — re-drawing the banner and a
        # "-- Continued" heading on each overflow page. setupPage resets lastLine
        # to the top so drawTable always fits at least one row per page.
        olen = len(rows)
        if olen == 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(1)
            self.drawSection(sectionName)
            self.drawText(emptyText)
            self.nextPage()
            return
        while len(rows) > 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(1)
            self.drawSection(sectionName if len(rows) == olen
                             else f"{sectionName} -- Continued")
            drawn = self.drawTable(rows, headers)
            rows = rows[drawn:]
            self.nextPage()

    def scheduleReport(self, result: "ScheduleResult", horizonDays: int | None = None):
        title = "TKG Production Schedule"
        subtitle = f"Generated {result.today.isoformat()}"
        if horizonDays is not None:
            subtitle += f" — horizon {horizonDays} day(s)"

        scheduleHeaders = ["Date", "Shift", "Press", "Part", "Quantity", "Press-hours"]
        scheduleData = [[
            r.date.isoformat(),
            str(r.shift),
            r.press,
            r.part,
            f"{r.quantity:g}",
            f"{r.hours:g}",
        ] for r in result.rows]
        self._scheduleSection(title, subtitle, "Schedule", scheduleHeaders,
                              scheduleData, "No production scheduled.")

        flagHeaders = ["Order", "Part", "Issue", "Detail"]
        flagData = [[
            f.orderNum,
            f.part,
            _FLAG_LABEL.get(f.kind, f.kind),
            _flagDetail(f),
        ] for f in result.flags]
        self._scheduleSection(
            title, subtitle, "Flagged Orders", flagHeaders, flagData,
            "No late or infeasible orders — all eligible orders fit before their "
            "effective press-by dates.")

        # Soft warnings only get a section when there are any — they're
        # incidental data-quality notes, not a standing report fixture.
        if result.warnings:
            warnHeaders = ["Part", "Warning"]
            warnData = [[w.part, _warningNote(w)] for w in result.warnings]
            self._scheduleSection(title, subtitle, "Warnings", warnHeaders,
                                  warnData, "")

        self.pdf.save()
