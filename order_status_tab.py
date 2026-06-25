from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QDateEdit, QMessageBox,
)
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from error import errorMessage
from utils import checkInput, toQDate, fromQDate, centerOnScreen
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
        self.genTableData()
        self.table = DBTable(self.data, self.headers)
        self.table.parentTab = self  # type: ignore

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        edit = QPushButton("Edit")
        edit.clicked.connect(self.openEdits)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(edit)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)

    def genTableData(self):
        db = self.mainApp.db
        self.headers = ["Order #", "Client", "Part", "Quantity",
                        "Latest Snapshot", "Rem. to Press", "Rem. to Ship", "Fulfilled?"]
        self.data = []
        for num, order in db.orders.items():
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
        self.data.sort(key=lambda row: row[0])

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

        self.addButton = QPushButton("Add / Update Snapshot")
        self.addButton.clicked.connect(self.addSnapshot)
        self.deleteButton = QPushButton("Delete Snapshot")
        self.deleteButton.clicked.connect(self.deleteSnapshot)

        def row(label, widget):
            line = QHBoxLayout()
            line.addWidget(QLabel(label))
            line.addWidget(widget)
            return line

        editorLayout = QHBoxLayout()
        editorLayout.addLayout(row("Date:", self.dateEdit))
        editorLayout.addLayout(row("Remaining to press:", self.pressEdit))
        editorLayout.addLayout(row("Remaining to ship:", self.shipEdit))

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

    def addSnapshot(self):
        errors = []
        date = fromQDate(self.dateEdit.date())
        press = int(checkInput(self.pressEdit.text(), int, "nonneg", errors, "Remaining to press"))
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
