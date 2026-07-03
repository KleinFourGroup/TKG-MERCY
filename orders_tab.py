import random
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QDateEdit, QMessageBox,
)
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from records import Order
from records.sales import formatOrderNum
from error import errorMessage
from utils import (
    checkInput, toQDate, fromQDate, centerOnScreen,
    orderSortCombo, orderSortKey, ORDER_SORT_DUEDATE,
)
import datetime
import logging


def _genOrderNum(db, clientName, partName):
    # Suggest a unique order number {client}-{part}-{6 digits} for a new order,
    # mirroring the employee idNum auto-fill. Retries the random suffix until it
    # doesn't collide with an existing order (the format/initials live in
    # records.sales.formatOrderNum so fuzz_db and the UI never drift).
    for _ in range(50):
        candidate = formatOrderNum(clientName, partName, random.randint(0, 999999))
        if candidate not in db.orders:
            return candidate
    return formatOrderNum(clientName, partName, random.randint(0, 999999))


class OrdersTab(QWidget):
    # Flat CRUD list of shop orders (Sales, Step 47). Each order is one part for
    # one client, keyed by a unique orderNum, with quantity / price (order total) /
    # dueDate. Delete is unconditional; an order's dated status snapshots cascade
    # away with it (Step 49, db.delOrder). Lives under "Production and Scheduling" ->
    # "Sales" -> "Orders".
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
        new = QPushButton("New")
        new.clicked.connect(self.openNew)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.deleteSelection)

        barLayout = QHBoxLayout()
        barLayout.addWidget(QLabel("Sort by:"))
        barLayout.addWidget(self.sortCombo)
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(edit)
        barLayout.addWidget(new)
        barLayout.addWidget(delete)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)

    def genTableData(self):
        db = self.mainApp.db
        self.headers = ["Order #", "Client", "Part", "Quantity", "Price", "Due Date"]
        self.data = []
        for num, order in sorted(db.orders.items(),
                                 key=lambda kv: orderSortKey(kv[1], self.sortMode)):
            due = order.dueDate.isoformat() if order.dueDate is not None else "?"
            self.data.append([num, order.client, order.part,
                              f"{order.quantity}", f"{order.price:.2f}", due])

    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {", ".join(selection)}")

    def openEdits(self):
        for item in self.selection:
            logging.debug(item)
            OrderEditWindow(item, self.mainApp)

    def openNew(self):
        if len(self.mainApp.db.clients) == 0:
            errorMessage(self.mainApp, ["Cannot add an order: no clients in the database."])
            return
        if len(self.mainApp.db.parts) == 0:
            errorMessage(self.mainApp, ["Cannot add an order: no parts in the database."])
            return
        OrderEditWindow(None, self.mainApp)

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No order selected."])
        for order in self.selection:
            confirm = QMessageBox.question(self, f"Delete {order}?", f"Are you sure you want to delete order {order}?")
            if confirm == QMessageBox.StandardButton.Yes:
                self.mainApp.db.delOrder(order)
                self.refreshTable()
                # delOrder cascades the order's status snapshots away, so refresh the
                # Order Status table too or it keeps showing the deleted order (Step 49).
                self.mainApp.orderStatusTab.refreshTable()
                QMessageBox.information(self.mainApp, "Success!", f"Deleted order {order}")

    def changeSort(self):
        self.sortMode = self.sortCombo.currentData()
        self.refreshTable()

    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.data)
        selection = [order for order in self.selection if order in self.mainApp.db.orders]
        self.setSelection(selection)


class OrderEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry if entry is not None else "New Order"}")

        item = self.mainApp.db.orders[entry] if entry is not None else None
        self.item = item

        # --- client + part FK combos (sorted name keys) ---
        self.clientCombo = QComboBox()
        self.clientCombo.addItems(sorted(self.mainApp.db.clients))
        self.partCombo = QComboBox()
        self.partCombo.addItems(sorted(self.mainApp.db.parts))
        if item is not None:
            if item.client in self.mainApp.db.clients:
                self.clientCombo.setCurrentText(item.client)
            if item.part in self.mainApp.db.parts:
                self.partCombo.setCurrentText(item.part)

        # --- order number (auto-suggested on New, akin to the employee idNum) ---
        if item is not None:
            self._suggested = entry
        else:
            self._suggested = _genOrderNum(
                self.mainApp.db, self.clientCombo.currentText(), self.partCombo.currentText())
        self.orderNumEdit = QLineEdit(self._suggested)
        # Re-suggest when the client/part changes, but only on a New window and
        # only while the field still holds the last suggestion (don't clobber a
        # number the user typed). Connected after the initial value is in place.
        self.clientCombo.currentTextChanged.connect(self._maybeResuggest)
        self.partCombo.currentTextChanged.connect(self._maybeResuggest)

        self.quantityEdit = QLineEdit(f"{item.quantity}" if item is not None else "")
        self.priceEdit = QLineEdit(f"{item.price}" if item is not None else "")

        self.dueDateEdit = QDateEdit()
        self.dueDateEdit.setCalendarPopup(True)
        if item is not None and item.dueDate is not None:
            self.dueDateEdit.setDate(toQDate(item.dueDate))
        else:
            self.dueDateEdit.setDate(toQDate(datetime.date.today()))

        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        def row(label, widget):
            line = QHBoxLayout()
            line.addWidget(QLabel(label))
            line.addWidget(widget)
            return line

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.updateButton)
        buttonLayout.addWidget(self.createButton)

        layout = QVBoxLayout()
        layout.addLayout(row("Order number:", self.orderNumEdit))
        layout.addLayout(row("Client:", self.clientCombo))
        layout.addLayout(row("Part:", self.partCombo))
        layout.addLayout(row("Quantity:", self.quantityEdit))
        layout.addLayout(row("Price (order total):", self.priceEdit))
        layout.addLayout(row("Due date:", self.dueDateEdit))
        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        # Create stays enabled on an Edit window (pre-populate-then-create-variant
        # shortcut the team relies on); only Update is gated to the edit case.
        if item is not None:
            self.updateButton.clicked.connect(self.updateOrder)
        else:
            self.updateButton.setEnabled(False)
        self.createButton.clicked.connect(self.newOrder)
        centerOnScreen(self)
        self.show()

    def _maybeResuggest(self):
        # Only auto-resuggest for a New order, and only if the user hasn't typed
        # over the last suggestion.
        if self.item is not None:
            return
        if self.orderNumEdit.text() == self._suggested:
            self._suggested = _genOrderNum(
                self.mainApp.db, self.clientCombo.currentText(), self.partCombo.currentText())
            self.orderNumEdit.setText(self._suggested)

    def readData(self, isNew):
        res = False
        errors = []
        orderNum = self.orderNumEdit.text().strip()
        if orderNum == "":
            errors.append("Order number cannot be empty.")
        if orderNum in self.mainApp.db.orders:
            if isNew or (self.item is not None and not orderNum == self.item.orderNum):
                errors.append(f"Order number '{orderNum}' already in use")

        client = self.clientCombo.currentText()
        if client not in self.mainApp.db.clients:
            errors.append("A valid client must be selected.")
        part = self.partCombo.currentText()
        if part not in self.mainApp.db.parts:
            errors.append("A valid part must be selected.")

        quantity = int(checkInput(self.quantityEdit.text(), int, "pos", errors, "Quantity"))
        price = checkInput(self.priceEdit.text(), float, "nonneg", errors, "Price")
        dueDate = fromQDate(self.dueDateEdit.date())

        if len(errors) == 0:
            isNone = self.item is None
            if isNew:
                self.item = Order(orderNum, client, part, quantity, price, dueDate)
                self.mainApp.db.addOrder(self.item)
            else:
                if self.item is None:
                    raise RuntimeError('self.item is None')
                self.mainApp.db.updateOrder(self.item.orderNum, orderNum)
                self.item.client = client
                self.item.part = part
                self.item.quantity = quantity
                self.item.price = price
                self.item.dueDate = dueDate
            if isNone:
                self.item = None
            self.mainApp.ordersTab.refreshTable()
            # An order rename rekeys its status snapshots (db.updateOrder) and every
            # order's row (number / client / part / quantity) shows in the Order
            # Status table, so refresh it too (Step 49 downstream-refresh rule).
            self.mainApp.orderStatusTab.refreshTable()
            res = True
        else:
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.item.orderNum if self.item is not None else "New Order"}")
        return res

    def updateOrder(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()

    def newOrder(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()
