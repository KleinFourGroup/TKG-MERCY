import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from records import Database
    from records.sales import Order
    from reportlab.pdfgen import canvas

# Order-status report filter sentinels (Step 77 / §13.47). The report and its
# helper window (order_report_window.py) share these so the two never drift.
ORDER_STATUS_OPEN = "open"
ORDER_STATUS_CLOSED = "closed"
ORDER_STATUS_ALL = "all"

_STATUS_LABEL = {
    ORDER_STATUS_OPEN: "Open",
    ORDER_STATUS_CLOSED: "Closed",
    ORDER_STATUS_ALL: "All",
}

# The report is wide (up to nine columns), so it renders in landscape at a slightly
# reduced body font and with content-proportional column widths rather than the
# equal split drawTable defaults to — enough to fit long order codes / client / part
# names + two dates without cramping (the alternative, a tiny font, hurts more than
# it helps). The window constructs the PDFReport in landscape; here we only pick the
# font + the per-column width weights.
_TABLE_FONT_SIZE = 10
# Relative column widths (any positive scale — normalized to the usable page width).
_WIDTH_WEIGHTS_SIMPLE = [1.5, 1.6, 1.5, 0.9, 1.1, 1.1, 1.0]
#                        Order Client Part Qty  Value Due  Status
_WIDTH_WEIGHTS_DETAIL = [1.5, 1.5, 1.4, 0.8, 1.1, 1.0, 1.1, 0.9, 0.9]
#                        Order Client Part Qty Value Due  Snap RemP RemS


def _isClosed(db, order) -> bool:
    # An order is "closed" once it's fulfilled — its latest remaining-to-ship is 0
    # (OrderStatus.isFulfilled, spec §3.7). No snapshot yet => open (§5.2).
    status = db.orderStatus.get(order.orderNum)
    return status is not None and status.isFulfilled()


class OrderReportsMixin:
    # Orders / Order Status PDF report (Step 77 / §13.47). One tabular report over
    # db.orders filtered by due-date range, open/closed status, client, and part,
    # with the order value and a total-value summary line. A "Status details" mode
    # swaps the single Open/Closed column for the latest snapshot date +
    # remaining-to-press / -ship figures. Consumes only db.orders / db.orderStatus
    # (never the scheduler), so it reflects the recorded status, not a computed
    # schedule. Builds on the PDFReportCore primitives — see report/__init__.py.

    if TYPE_CHECKING:
        # Attributes + helpers provided by PDFReportCore (composed in last).
        db: Database
        pdf: canvas.Canvas
        left: float
        right: float
        lastLine: float
        bottom: float
        font: str
        fontSize: int
        lineSpace: float
        def setupPage(self) -> None: ...
        def nextPage(self) -> None: ...
        def skipLines(self, numLines) -> None: ...
        def setFont(self, font: str, size: int) -> None: ...
        def drawText(self, text: str) -> None: ...
        def drawTitle(self, text: str) -> None: ...
        def drawSection(self, text: str) -> None: ...
        def drawParagraph(self, text: str) -> None: ...
        def drawTable(self, data: list[list[str]], headers: list[str] | None = None, widths: list[float] | None = None) -> int: ...

    def orderStatusReport(self, start: datetime.date, end: datetime.date,
                          statusFilter: str = ORDER_STATUS_ALL,
                          client: str | None = None, part: str | None = None,
                          showDetails: bool = False) -> None:
        rows = self._filterOrders(start, end, statusFilter, client, part)
        headers = (["Order #", "Client", "Part", "Quantity", "Value", "Due Date",
                    "Latest Snapshot", "Rem. Press", "Rem. Ship"] if showDetails
                   else ["Order #", "Client", "Part", "Quantity", "Value", "Due Date",
                         "Status"])
        widths = self._columnWidths(showDetails)
        data = [self._orderRow(order, showDetails) for order in rows]
        totalValue = sum(order.price for order in rows)
        totalsRow = self._totalsRow(totalValue, showDetails)
        meta = self._filterDescription(start, end, statusFilter, client, part, showDetails)

        title = "TKG Order Status Report"

        def banner(cont: bool) -> None:
            # Per-page header: title + the wrapped filter/meta line + the section
            # heading (setupPage resets lastLine to the top first). Leaves the font at
            # the body default (12) — the caller drops to the table font after.
            self.setupPage()
            self.drawTitle(title)
            self.drawParagraph(meta)
            self.skipLines(1)
            self.drawSection("Orders (cont.)" if cont else "Orders")

        if not data:
            banner(False)
            self.drawText("No orders match the selected filters.")
            self.nextPage()
            self.pdf.save()
            return

        # Paginate the way the product / inventory reports do (report/products.py),
        # re-drawing the banner + a "(cont.)" heading per overflow page. The bold
        # total-value line lands after the last data row (drawTable([], row) renders
        # its argument in Times-Bold — the house totals convention); if the page has
        # no room left for it, it moves to a fresh continued page so it's never
        # silently dropped.
        olen = len(data)
        while len(data) > 0:
            banner(len(data) != olen)
            self.setFont("Times-Roman", _TABLE_FONT_SIZE)
            drawn = self.drawTable(data, headers, widths)
            data = data[drawn:]
            if len(data) == 0:
                if self.lastLine - self.fontSize * self.lineSpace * 2 < self.bottom:
                    self.nextPage()
                    banner(True)
                    self.setFont("Times-Roman", _TABLE_FONT_SIZE)
                self.drawTable([], totalsRow, widths)
            self.setFont("Times-Roman", 12)
            self.nextPage()
        self.pdf.save()

    def _columnWidths(self, showDetails: bool) -> list[float]:
        # Content-proportional column widths (in points) normalized to the usable
        # page width, so wide fields (order code / client / part / dates) get room and
        # the count columns stay narrow — instead of drawTable's equal split.
        usable = self.right - self.left
        weights = _WIDTH_WEIGHTS_DETAIL if showDetails else _WIDTH_WEIGHTS_SIMPLE
        total = sum(weights)
        return [usable * w / total for w in weights]

    def _filterOrders(self, start: datetime.date, end: datetime.date,
                      statusFilter: str, client: str | None,
                      part: str | None) -> "list[Order]":
        db = self.db
        rows = []
        for order in db.orders.values():
            due = order.dueDate
            # Due-date range, inclusive. Undated orders (dueDate is None) are ALWAYS
            # included (§13.47 safety net): there's no date to filter them on, and
            # dropping them would silently hide open orders.
            if due is not None and not (start <= due <= end):
                continue
            closed = _isClosed(db, order)
            if statusFilter == ORDER_STATUS_OPEN and closed:
                continue
            if statusFilter == ORDER_STATUS_CLOSED and not closed:
                continue
            if client is not None and order.client != client:
                continue
            if part is not None and order.part != part:
                continue
            rows.append(order)
        # Due date (undated last), client (case-insensitive), then orderNum — the
        # Step 73 flagged-order ordering applied to the whole list.
        rows.sort(key=lambda o: (o.dueDate is None, o.dueDate or datetime.date.max,
                                 (o.client or "").casefold(), o.orderNum))
        return rows

    def _orderRow(self, order, showDetails: bool) -> list[str]:
        db = self.db
        due = order.dueDate.isoformat() if order.dueDate is not None else "?"
        # order.price is the ORDER TOTAL (records/sales.py), so the order value is the
        # price directly — no quantity multiply.
        base = [order.orderNum, order.client, order.part, f"{order.quantity}",
                f"${order.price:.2f}", due]
        if not showDetails:
            return base + ["Closed" if _isClosed(db, order) else "Open"]
        # Details mode: latest snapshot date + remaining-to-press / -ship. No snapshot
        # yet => outstanding defaults to the full ordered quantity (spec §5.2), shown
        # with a "(none)" snapshot so the default isn't mistaken for a recorded value
        # (mirrors the Order Status tab's own display).
        status = db.orderStatus.get(order.orderNum)
        latestDate = status.latestDate() if status is not None else None
        latest = latestDate.isoformat() if latestDate is not None else "(none)"
        press = status.remainingToPress() if status is not None else None
        ship = status.remainingToShip() if status is not None else None
        press = order.quantity if press is None else press
        ship = order.quantity if ship is None else ship
        return base + [latest, f"{press}", f"{ship}"]

    def _totalsRow(self, totalValue: float, showDetails: bool) -> list[str]:
        # A bold summary line: "Total" under Order #, the summed order value under the
        # Value column (index 4), blanks elsewhere. Width must match the header count.
        ncols = 9 if showDetails else 7
        row = [""] * ncols
        row[0] = "Total"
        row[4] = f"${totalValue:.2f}"
        return row

    def _filterDescription(self, start: datetime.date, end: datetime.date,
                           statusFilter: str, client: str | None, part: str | None,
                           showDetails: bool) -> str:
        parts = [
            f"Generated {datetime.date.today().isoformat()}",
            f"Due {start.isoformat()} to {end.isoformat()}",
            f"Status: {_STATUS_LABEL.get(statusFilter, 'All')}",
            f"Client: {client or 'All'}",
            f"Part: {part or 'All'}",
        ]
        if showDetails:
            parts.append("with status details")
        return "  |  ".join(parts)
