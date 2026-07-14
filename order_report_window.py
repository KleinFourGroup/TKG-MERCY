import datetime
from PySide6.QtWidgets import (
    QWidget, QLabel, QComboBox, QDateEdit, QCheckBox, QPushButton,
)
from PySide6.QtCore import Qt
from reportlab.lib.pagesizes import letter, landscape

from app import MainWindow
from error import errorMessage
from report import PDFReport
from report.sales import ORDER_STATUS_OPEN, ORDER_STATUS_CLOSED, ORDER_STATUS_ALL
from utils import (
    toQDate, fromQDate, widgetFromList, startfile, tempReportPath, centerOnScreen,
)


class OrderReportWindow(QWidget):
    # Small helper dialog for the Orders / Order Status PDF report (Step 77 / §13.47).
    # Same paradigm as ProductionReportWindow: pick options, Generate writes a temp
    # PDF and opens it (the Step 14 open-via-temp convention). Opened from a Report
    # button on BOTH the Orders and Order Status tabs (the team didn't specify which,
    # so it lives on both — design call 2026-07-14). Read-only over the DB.
    def __init__(self, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle("Order Status Report")

        # Date range filters on the order's DUE DATE (design call 2026-07-14 — the only
        # date an order carries). Default to the span of dated orders so an unmodified
        # range covers everything; today/today when there are no dated orders.
        start, end = self._defaultRange()
        self.startDateEdit = QDateEdit()
        self.startDateEdit.setCalendarPopup(True)
        self.startDateEdit.setDisplayFormat("yyyy-MM-dd")
        self.startDateEdit.setDate(toQDate(start))
        self.endDateEdit = QDateEdit()
        self.endDateEdit.setCalendarPopup(True)
        self.endDateEdit.setDisplayFormat("yyyy-MM-dd")
        self.endDateEdit.setDate(toQDate(end))

        # Status: closed == none remaining to ship (OrderStatus.isFulfilled).
        self.statusBox = QComboBox()
        self.statusBox.addItem("All", userData=ORDER_STATUS_ALL)
        self.statusBox.addItem("Open", userData=ORDER_STATUS_OPEN)
        self.statusBox.addItem("Closed", userData=ORDER_STATUS_CLOSED)

        # Client / Part: one specific value or "All" (userData None).
        self.clientBox = QComboBox()
        self.clientBox.addItem("All clients", userData=None)
        for name in sorted(self.mainApp.db.clients):
            self.clientBox.addItem(name, userData=name)

        self.partBox = QComboBox()
        self.partBox.addItem("All parts", userData=None)
        for name in sorted(self.mainApp.db.parts):
            self.partBox.addItem(name, userData=name)

        self.detailsCheck = QCheckBox("Status details")
        self.detailsCheck.setToolTip(
            "Show the actual remaining-to-press / -ship figures (and the latest "
            "snapshot date) instead of a single Open/Closed column.")

        self.generateB = QPushButton("Generate")
        self.generateB.clicked.connect(self.generate)

        widgetFromList(self, [
            [QLabel("From (due date):"), self.startDateEdit],
            [QLabel("To (due date):"), self.endDateEdit],
            [QLabel("Status:"), self.statusBox],
            [QLabel("Client:"), self.clientBox],
            [QLabel("Part:"), self.partBox],
            [self.detailsCheck],
            [self.generateB],
        ])
        centerOnScreen(self)
        self.show()

    def _defaultRange(self):
        dues = [o.dueDate for o in self.mainApp.db.orders.values() if o.dueDate is not None]
        if dues:
            return min(dues), max(dues)
        today = datetime.date.today()
        return today, today

    def generate(self):
        start = fromQDate(self.startDateEdit.date())
        end = fromQDate(self.endDateEdit.date())
        if start > end:
            errorMessage(self, ["From date must be on or before To date."])
            return
        path = tempReportPath("order-status")
        # Landscape: the report is up to nine columns wide, so it needs the extra
        # width (report/sales.py sizes the columns to the usable page width).
        pdf = PDFReport(self.mainApp.db, path, pageSize=landscape(letter))
        pdf.orderStatusReport(
            start, end, self.statusBox.currentData(),
            self.clientBox.currentData(), self.partBox.currentData(),
            self.detailsCheck.isChecked())
        startfile(path)
        self.close()
