from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QDateEdit, QMessageBox, QCheckBox,
)
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from error import errorMessage
from utils import (
    checkInput, toQDate, fromQDate, centerOnScreen,
    orderSortCombo, orderSortKey, ORDER_SORT_DUEDATE,
)
import datetime
import logging


class OrderStatusTab(QWidget):
    # Nested editor for order status (Sales, Step 49). Like Part-Press Preference,
    # status hangs off existing orders rather than being its own create/delete list:
    # the table lists every order with its latest dated snapshot (remaining to press /
    # ship) and whether it's fulfilled, and Edit opens a per-order window for the
    # dated snapshots. There is no New/Delete here — orders are born and deleted from
    # the Orders tab (which cascades their status away). Lives under "Production and
    # Scheduling" -> "Sales" -> "Order Status".
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.sortMode = ORDER_SORT_DUEDATE
        self.genTableData()
        self.table = DBTable(self.data, self.headers)
        self.table.parentTab = self  # type: ignore

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        self.sortCombo = orderSortCombo(self.sortMode)
        self.sortCombo.currentIndexChanged.connect(self.changeSort)

        edit = QPushButton("Edit")
        edit.clicked.connect(self.openEdits)
        report = QPushButton("Report")
        report.clicked.connect(self.openReport)

        barLayout = QHBoxLayout()
        barLayout.addWidget(QLabel("Sort by:"))
        barLayout.addWidget(self.sortCombo)
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(edit)
        barLayout.addWidget(report)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)

    def genTableData(self):
        db = self.mainApp.db
        self.headers = ["Order #", "Client", "Part", "Quantity",
                        "Latest Snapshot", "Rem. to Press", "Rem. to Ship", "Fulfilled?"]
        self.data = []
        for num, order in sorted(db.orders.items(),
                                 key=lambda kv: orderSortKey(kv[1], self.sortMode)):
            status = db.orderStatus.get(num)
            latestDate = status.latestDate() if status is not None else None
            latest = latestDate.isoformat() if latestDate is not None else "(none)"
            # No snapshot recorded yet => outstanding defaults to the full ordered
            # quantity (spec §5.2); the "(none)" latest column makes the default
            # status visible so the displayed counts aren't mistaken for recorded 0s.
            press = status.remainingToPress() if status is not None else None
            ship = status.remainingToShip() if status is not None else None
            press = order.quantity if press is None else press
            ship = order.quantity if ship is None else ship
            fulfilled = "Yes" if status is not None and status.isFulfilled() else "No"
            self.data.append([num, order.client, order.part, f"{order.quantity}",
                              latest, f"{press}", f"{ship}", fulfilled])

    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {", ".join(selection)}")

    def openEdits(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No order selected."])
            return
        for orderNum in self.selection:
            logging.debug(orderNum)
            # Skip an order that was deleted elsewhere while still selected here (the
            # Orders tab's delete doesn't clear this tab's selection); refreshTable
            # filters it out, but guard the open path so a stale row can't KeyError.
            if orderNum not in self.mainApp.db.orders:
                continue
            OrderStatusEditWindow(orderNum, self.mainApp)

    def changeSort(self):
        self.sortMode = self.sortCombo.currentData()
        self.refreshTable()

    def openReport(self):
        # Orders / Order Status PDF report (Step 77). Linked from both tabs; the
        # window is import-deferred to keep the app -> tab import chain acyclic.
        from order_report_window import OrderReportWindow
        OrderReportWindow(self.mainApp)

    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.data)
        selection = [num for num in self.selection if num in self.mainApp.db.orders]
        self.setSelection(selection)


class OrderStatusEditWindow(QWidget):
    # Per-order nested editor: a sub-table of the order's dated snapshots plus an
    # inline (date, remaining-to-press, remaining-to-ship) editor. "Add / Update
    # Snapshot" writes through Database.setOrderSnapshot — one snapshot per date
    # (UNIQUE(orderNum, date)), so re-entering an existing date overwrites it (the
    # spec's "correcting a value just means adding a newer snapshot"). Selecting a
    # row loads it into the inline fields; "Delete Snapshot" removes the selected
    # date. The two counts are independent (press feeds the scheduler, ship tracks
    # fulfillment); both are non-negative, and 0 remaining-to-ship marks the order
    # fulfilled.
    def __init__(self, orderNum, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.orderNum = orderNum
        self.snapshotSelection = []
        self.setWindowTitle(f"Order Status: {orderNum}")

        order = self.mainApp.db.orders[orderNum]
        self.order = order

        # --- snapshot sub-table ---
        self.genSnapshotData()
        self.snapshotTable = DBTable(self.snapshotData, self.snapshotHeaders)
        self.snapshotTable.parentTab = self  # type: ignore

        # --- inline (date, press, ship) editor ---
        self.dateEdit = QDateEdit()
        self.dateEdit.setCalendarPopup(True)
        self.dateEdit.setDate(toQDate(datetime.date.today()))
        self.pressEdit = QLineEdit()
        self.shipEdit = QLineEdit()
        # The press field's label carries the current input unit and flips with the
        # trucks checkbox (Step 74b); remaining-to-ship is always in pieces (Step 76),
        # so its label is fixed. The fields still store + display pieces regardless.
        self.pressLabel = QLabel()
        self.shipLabel = QLabel()

        # "Enter in trucks" (Step 74b): a live, unpersisted per-window toggle that
        # reinterprets the remaining-to-press field as trucks (half-truck steps) and
        # converts to pieces via this part's parts-per-truck before storing. Blocked
        # outright when the part has no truck size (checked at toggle time, below).
        # Remaining-to-ship is *always* entered in pieces (Step 76) — it never converts.
        # Everything stays stored + displayed in pieces.
        self.trucksCheck = QCheckBox("Enter in trucks")
        self.trucksCheck.setToolTip(
            "Interpret the remaining-to-press field as trucks (in half-truck steps) and "
            "convert to pieces using this part's parts-per-truck figure. Remaining to "
            "ship is always in pieces. Everything is still stored and shown in pieces.")
        self.trucksCheck.toggled.connect(self.onTrucksToggled)
        self._applyUnitLabels()

        self.addButton = QPushButton("Add / Update Snapshot")
        self.addButton.clicked.connect(self.addSnapshot)
        self.deleteButton = QPushButton("Delete Snapshot")
        self.deleteButton.clicked.connect(self.deleteSnapshot)

        def row(label, widget):
            line = QHBoxLayout()
            line.addWidget(label if isinstance(label, QLabel) else QLabel(label))
            line.addWidget(widget)
            return line

        fieldsLayout = QHBoxLayout()
        fieldsLayout.addLayout(row("Date:", self.dateEdit))
        fieldsLayout.addLayout(row(self.pressLabel, self.pressEdit))
        fieldsLayout.addLayout(row(self.shipLabel, self.shipEdit))

        editorLayout = QVBoxLayout()
        editorLayout.addWidget(self.trucksCheck)
        editorLayout.addLayout(fieldsLayout)

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.addButton)
        buttonLayout.addWidget(self.deleteButton)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(
            f"Order {orderNum} — {order.client} / {order.part} (ordered {order.quantity})"))
        layout.addWidget(QLabel(
            "Each row is the quantity STILL LEFT to press / ship as of its date; "
            "the latest date wins."))
        layout.addWidget(self.snapshotTable)
        layout.addLayout(editorLayout)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)
        centerOnScreen(self)
        self.show()

    def genSnapshotData(self):
        status = self.mainApp.db.orderStatus.get(self.orderNum)
        self.snapshotHeaders = ["Date", "Remaining to Press", "Remaining to Ship"]
        self.snapshotData = []
        if status is not None:
            for date in sorted(status.snapshots):
                press, ship = status.snapshots[date]
                self.snapshotData.append([date.isoformat(), f"{press}", f"{ship}"])

    def setSelection(self, selection):
        # The snapshot sub-table feeds back the selected date(s) here. Load the most
        # recent selection into the inline editor so the user can edit it in place
        # (re-adding the same date overwrites it).
        self.snapshotSelection = selection
        if len(selection) == 0:
            return
        dateStr = selection[-1]
        status = self.mainApp.db.orderStatus.get(self.orderNum)
        if status is None:
            return
        date = datetime.date.fromisoformat(dateStr)
        if date in status.snapshots:
            press, ship = status.snapshots[date]
            # Snapshots are stored in pieces, so drop back to pieces mode before
            # prefilling (unchecking clears + relabels via onTrucksToggled) — otherwise
            # a pieces value would be misread as trucks (Step 74b).
            if self.trucksCheck.isChecked():
                self.trucksCheck.setChecked(False)
            self.dateEdit.setDate(toQDate(date))
            self.pressEdit.setText(f"{press}")
            self.shipEdit.setText(f"{ship}")

    def snapshotWarnings(self, date, press, ship):
        # Plausibility checks for an out-of-the-ordinary snapshot. Both cases are
        # still allowed (a destroyed crate / lost shipment legitimately raises
        # remaining; a back-dated correction is legitimate but won't change the
        # current state) — they just earn an are-you-sure. Returns a list of
        # human-readable reasons; empty means the snapshot is unremarkable.
        warnings = []
        status = self.mainApp.db.orderStatus.get(self.orderNum)
        if status is None or not status.snapshots:
            return warnings
        # Back-dated: a newer snapshot already exists, so this one won't change the
        # order's current (latest-by-date) status.
        laterDates = [dt for dt in status.snapshots if dt > date]
        if laterDates:
            warnings.append(
                f"This snapshot's date ({date.isoformat()}) is earlier than the most "
                f"recent snapshot ({max(status.snapshots).isoformat()}), so it won't "
                f"change the order's current remaining quantities.")
        # Increasing: remaining should normally only fall over time, so flag a value
        # higher than the immediately preceding (in time) snapshot.
        priorDates = [dt for dt in status.snapshots if dt < date]
        if priorDates:
            predDate = max(priorDates)
            predPress, predShip = status.snapshots[predDate]
            increases = []
            if press > predPress:
                increases.append(f"remaining to press {press} > {predPress}")
            if ship > predShip:
                increases.append(f"remaining to ship {ship} > {predShip}")
            if increases:
                warnings.append(
                    f"Remaining quantity is higher than the previous snapshot "
                    f"({predDate.isoformat()}): {", ".join(increases)}.")
        return warnings

    def _applyUnitLabels(self):
        # The press field's label carries the current input unit so the mode is
        # unmistakable (Step 74b); remaining-to-ship is always in pieces (Step 76), so
        # its label is fixed. Storage + display stay in pieces regardless.
        unit = "trucks" if self.trucksCheck.isChecked() else "pieces"
        self.pressLabel.setText(f"Remaining to press ({unit}):")
        self.shipLabel.setText("Remaining to ship (pieces):")

    def onTrucksToggled(self, checked):
        # Block trucks mode outright when the part has no parts-per-truck set — there's
        # nothing to convert with, so revert the checkbox immediately rather than let
        # the user enter trucks that can't be stored (block, don't guess; design call
        # 2026-07-03). The odd-count / fractional-piece case can't be known until a
        # value is typed, so it's caught at commit in _readPressRemaining instead.
        if checked:
            truck = self.mainApp.db.partTruck.get(self.order.part)
            if truck is None or truck.partsPerTruck is None:
                errorMessage(self, [
                    f"{self.order.part} has no parts-per-truck figure set. Set it on "
                    f"the Parts per Truck tab first, then you can enter in trucks."])
                self.trucksCheck.blockSignals(True)
                self.trucksCheck.setChecked(False)
                self.trucksCheck.blockSignals(False)
                return
        # Unit changed for the press field only (ship is always pieces, Step 76):
        # clear + relabel the press field so a value typed / prefilled in the old unit
        # can't be misread in the new one (design call: clear + relabel, don't
        # auto-convert). The ship field is untouched.
        self.pressEdit.clear()
        self._applyUnitLabels()

    def _readPressRemaining(self, text, label, errors):
        # Read the remaining-to-press field as a piece count, honoring the trucks
        # toggle (Step 76: only the press field converts; ship is always pieces).
        # Pieces mode: a non-negative integer, stored as-is. Trucks mode: a non-negative
        # multiple of 0.5 (half-truck precision) converted to pieces via the part's
        # parts-per-truck; a half-truck of an odd count (=> a fractional piece) is
        # rejected rather than rounded (block, don't guess). Appends to `errors` and
        # returns 0 on any problem — the caller bails on a non-empty error list.
        if not self.trucksCheck.isChecked():
            return int(checkInput(text, int, "nonneg", errors, label))
        before = len(errors)
        trucks = checkInput(text, float, "nonneg", errors, label)
        if len(errors) > before:
            return 0
        if (trucks * 2) % 1 != 0:
            errors.append(f"{label}: {trucks:g} isn't a whole or half truck — enter it in 0.5 steps.")
            return 0
        truck = self.mainApp.db.partTruck.get(self.order.part)
        if truck is None or truck.partsPerTruck is None:
            errors.append(f"{self.order.part} has no parts-per-truck figure set — set it on the "
                          f"Parts per Truck tab, or uncheck 'Enter in trucks'.")
            return 0
        pieces = trucks * truck.partsPerTruck
        if pieces % 1 != 0:
            errors.append(f"{label}: {trucks:g} trucks x {truck.partsPerTruck} = {pieces:g} pieces, "
                          f"not a whole number. Enter a whole number of trucks, or switch to pieces.")
            return 0
        return int(pieces)

    def addSnapshot(self):
        errors = []
        date = fromQDate(self.dateEdit.date())
        # Remaining-to-press honors the trucks toggle (converted here); remaining-to-ship
        # is always pieces (Step 76), read as a plain non-negative integer.
        press = self._readPressRemaining(self.pressEdit.text(), "Remaining to press", errors)
        ship = int(checkInput(self.shipEdit.text(), int, "nonneg", errors, "Remaining to ship"))
        if len(errors) > 0:
            errorMessage(self, errors)
            return
        warnings = self.snapshotWarnings(date, press, ship)
        if warnings:
            confirm = QMessageBox.question(
                self, "Confirm snapshot",
                "\n\n".join(warnings) + "\n\nAdd this snapshot anyway?")
            if confirm != QMessageBox.StandardButton.Yes:
                return
        self.mainApp.db.setOrderSnapshot(self.orderNum, date, press, ship)
        self.refreshSnapshots()
        QMessageBox.information(self, "Success", "Snapshot saved!")

    def deleteSnapshot(self):
        if len(self.snapshotSelection) == 0:
            errorMessage(self, ["No snapshot selected."])
            return
        for dateStr in self.snapshotSelection:
            self.mainApp.db.removeOrderSnapshot(self.orderNum, datetime.date.fromisoformat(dateStr))
        self.refreshSnapshots()
        QMessageBox.information(self, "Success", "Snapshot deleted!")

    def refreshSnapshots(self):
        self.genSnapshotData()
        self.snapshotTable.setData(self.snapshotData)
        self.snapshotSelection = []
        self.mainApp.orderStatusTab.refreshTable()
