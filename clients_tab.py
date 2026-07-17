from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from records import Client
from error import errorMessage
from utils import checkInput, centerOnScreen
import logging


class ClientsTab(QWidget):
    # Flat CRUD list of clients (Sales, Step 46). Clients are keyed by unique name
    # and carry a transportDays field (typical shipment transit in business days).
    # Delete is blocked when an order references the client (Step 47, like
    # packaging). Lives under "Production and Scheduling" -> "Sales" -> "Clients".
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
        new = QPushButton("New")
        new.clicked.connect(self.openNew)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.deleteSelection)

        barLayout = QHBoxLayout()
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
        self.headers = ["Client", "Transport (business days)"]
        self.data = [[name, f"{db.clients[name].transportDays}"] for name in db.clients]
        self.data.sort(key=lambda row: row[0])

    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {", ".join(selection)}")

    def openEdits(self):
        for item in self.selection:
            logging.debug(item)
            ClientEditWindow(item, self.mainApp)

    def openNew(self):
        ClientEditWindow(None, self.mainApp)

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No client selected."])
        for client in self.selection:
            confirm = QMessageBox.question(self, f"Delete {client}?", f"Are you sure you want to delete {client}?")
            if confirm == QMessageBox.StandardButton.Yes:
                usedIn = self.mainApp.db.delClient(client)
                if len(usedIn) == 0:
                    self.refreshTable()
                    QMessageBox.information(self.mainApp, "Success!", f"Deleted client {client}")
                else:
                    errorMessage(self.mainApp, [f"{client} is used in order {item}!" for item in usedIn])

    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.data)
        selection = [client for client in self.selection if client in self.mainApp.db.clients]
        self.setSelection(selection)


class ClientEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry if entry is not None else "New Client"}")

        item = self.mainApp.db.clients[entry] if entry is not None else None
        self.item = item

        self.nameEdit = QLineEdit(f"{entry if entry is not None else ""}")
        self.transportEdit = QLineEdit(f"{item.transportDays}" if item is not None else "")
        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        nameLayout = QHBoxLayout()
        nameLayout.addWidget(QLabel("Client name:"))
        nameLayout.addWidget(self.nameEdit)

        transportLayout = QHBoxLayout()
        transportLayout.addWidget(QLabel("Transport time (business days):"))
        transportLayout.addWidget(self.transportEdit)

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.updateButton)
        buttonLayout.addWidget(self.createButton)

        layout = QVBoxLayout()
        layout.addLayout(nameLayout)
        layout.addLayout(transportLayout)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        # Create stays enabled on an Edit window (pre-populate-then-create-variant
        # shortcut the team relies on); only Update is gated to the edit case.
        if item is not None:
            self.updateButton.clicked.connect(self.updateClient)
        else:
            self.updateButton.setEnabled(False)
        self.createButton.clicked.connect(self.newClient)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        name = self.nameEdit.text().strip()
        if name == "":
            errors.append("Client name cannot be empty.")
        if name in self.mainApp.db.clients:
            if isNew or (self.item is not None and not name == self.item.name):
                errors.append(f"Client name '{name}' already in use")
        # transportDays is whole business days; 0 is allowed (local/same-ship-day client).
        # int(...) wrap narrows checkInput's int|float return to int (the field's type),
        # matching the employees_tab idNum pattern.
        transportDays = int(checkInput(self.transportEdit.text(), int, "nonneg", errors, "Transport time"))

        if len(errors) == 0:
            isNone = self.item is None
            if isNew:
                self.item = Client(name, transportDays)
                self.mainApp.db.addClient(self.item)
            else:
                if self.item is None:
                    raise RuntimeError('self.item is None')
                self.mainApp.db.updateClient(self.item.name, name)
                self.item.transportDays = transportDays
            if isNone:
                self.item = None
            self.mainApp.refreshAllViews()
            res = True
        else:
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.item.name if self.item is not None else "New Client"}")
        return res

    def updateClient(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()

    def newClient(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()
