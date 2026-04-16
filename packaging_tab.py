from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox
from table import DBTable
from app import MainWindow
from records import Package
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput

class PackagingTab(QWidget):
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.windows = []
        # self.error = None
        self.genTableData()
        self.table = DBTable(self.data, self.headers)
        self.table.parentTab = self # type: ignore

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        # details = QPushButton("Details")
        # details.clicked.connect(self.openDetails)
        edit = QPushButton("Edit")
        edit.clicked.connect(self.openEdits)
        new = QPushButton("New")
        new.clicked.connect(self.openNew)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.deleteSelection)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        # barLayout.addWidget(details)
        barLayout.addWidget(edit)
        barLayout.addWidget(new)
        barLayout.addWidget(delete)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.mainApp.db
        def getKey(entry):
            item = db.packaging[entry]
            return (item.kind, entry)
        self.headers = ["Item", "Type", "Price"]
        self.data = [[
            entry,
            db.packaging[entry].kind,
            "${:.4f}".format(db.packaging[entry].price)
        ] for entry in db.packaging]
        self.data.sort(key=lambda row: getKey(row[0]))
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(selection)}")
    
    def openDetails(self):
        pass
    
    def openEdits(self):
        for item in self.selection:
            print(item)
            self.windows.append(PackagingEditWindow(item, self.mainApp))
    
    def openNew(self):
        self.windows.append(PackagingEditWindow(None, self.mainApp))

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No packaging selected."])
        for packaging in self.selection:
            confirm = QMessageBox.question(self, f"Delete {packaging}?", f"Are you sure you want to delete {packaging}?")

            if confirm == QMessageBox.StandardButton.Yes:
                usedIn = self.mainApp.db.delPackaging(packaging)
                if len(usedIn) == 0:
                    self.refreshTable()
                    QMessageBox.information(self.mainApp, "Success!", f"Deleted packaging {packaging}")
                else:
                    errorMessage(self.mainApp, [f"{packaging} is used in {item}!" for item in usedIn])
    
    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.data)
        selection = [package for package in self.selection if package in self.mainApp.db.packaging]
        self.setSelection(selection)
        
class PackagingEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry if not entry == None else "New Packaging"}")

        item = self.mainApp.db.packaging[entry] if not entry == None else None
        self.item = item

        self.error = None

        kinds = [self.mainApp.db.packaging[name].kind for name in self.mainApp.db.packaging]
        kinds.extend(["box", "pad", "pallet", "misc"])

        self.mainLayout = [
            [QLabel("Item:"), QLineEdit(f"{entry if not entry == None else "New Packaging"}")],
            [
                QLabel("Type:"), getComboBox(list(dict.fromkeys(kinds)),
                                             item.kind if not item == None else None),
                QLabel("Price:"), QLineEdit(f"{item.price if not item == None else ""}")
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not item == None:
            self.mainLayout[2][0].clicked.connect(self.updatePackaging)
        else:
            self.mainLayout[2][0].setEnabled(False)
        self.mainLayout[2][1].clicked.connect(self.newPackaging)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        name = self.mainLayout[0][1].text()
        if name in self.mainApp.db.packaging:
            if isNew or (self.item is not None and not name == self.item.name):
                errors.append(f"Packaging name '{name}' already in use")
        kind = self.mainLayout[1][1].currentText()
        price = checkInput(self.mainLayout[1][3].text(), float, "nonneg", errors, "price")

        if len(errors) == 0:
            isNone = self.item == None
            if isNew:
                self.item = Package(name, None, None)
                self.mainApp.db.addPackaging(self.item)
            else:
                assert(not self.item == None)
                self.mainApp.db.updatePackaging(self.item.name, name)
            self.item.kind = kind
            self.item.price = price
            if isNone:
                self.item = None
            self.mainApp.packagingTab.refreshTable()
            self.mainApp.partsTab.refreshTable()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.item.name if not self.item == None else "New Packaging"}")
        return res
    
    def updatePackaging(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()
    
    def newPackaging(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()