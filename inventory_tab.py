from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QComboBox, QPushButton, QCalendarWidget, QMessageBox, QLineEdit, QFileDialog
from records import Database, emptyDB, MaterialInventoryRecord, PartInventoryRecord
from error import errorMessage
from utils import newHLine, widgetFromList, checkInput, toQDate, fromQDate, getComboBox, startfile

from app import MainWindow
from table import DBTable
from report import PDFReport

import os, datetime

def createTab():
    tab = QWidget()
    label = QLabel("TODO")
    layout = QVBoxLayout(tab)
    layout.addWidget(label)
    tab.setLayout(layout)
    return tab

class InventoryTab(QWidget):
    def __init__(self, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp
        self.windows = []

        self.datePicker = QComboBox()
        self.datePicker.setEditable(False)
        self.date: datetime.date | None = None

        self.datePicker.currentTextChanged.connect(self.selectDate)
        
        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel("Inventory Dates:"))
        hlayout.addWidget(self.datePicker)

        self.newB = QPushButton("New Inventory Date")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Inventory Date")
        self.editB.clicked.connect(self.openEdit)
        self.deleteB = QPushButton("Delete Inventory Date")
        self.deleteB.clicked.connect(self.deleteDate)
        self.reportB = QPushButton("Generate Report")
        self.reportB.clicked.connect(self.report)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)
        barLayout.addWidget(self.reportB)
        # Create a QTabWidget
        self.tab_widget = QTabWidget()

        # Add tabs to the QTabWidget
        self.materialsTab = MaterialsInventoryTab(self)
        self.tab_widget.addTab(self.materialsTab, "Materials")
        self.partsTab = PartsInventoryTab(self)
        self.tab_widget.addTab(self.partsTab, "Parts")

        layout = QVBoxLayout(self)
        layout.addLayout(hlayout)
        layout.addLayout(barLayout)
        layout.addWidget(self.tab_widget)

        # Set the layout for the main window
        self.setLayout(layout)

        self.refreshPicker()

    def selectDate(self, pick: str):
        if pick == "" or pick == "None":
            self.date = None
        else:
            self.date = datetime.date.fromisoformat(pick)
        self.materialsTab.refresh()
        self.partsTab.refresh()
    
    def refreshPicker(self):
        db = self.mainApp.db
        dates = [date for date in db.inventories]
        dates.sort(reverse=True)
        selections = [f"{date.isoformat()}" for date in dates]
        selections.insert(0, "None")
        self.datePicker.clear()
        self.datePicker.addItems(selections)
        self.datePicker.setCurrentIndex(0)

    def refresh(self):
        self.refreshPicker()
    
    def openNew(self):
        self.windows.append(InventoryDateEditWindow(None, self.mainApp))
    
    def openEdit(self):
        if self.date is None:
            errorMessage(self.mainApp, ["No date selected."])
        else:
            if not self.date in self.mainApp.db.inventories: # Should never happen, but if I screwed something up, fail gracefully
                errorMessage(self.mainApp, [f"No inventory on {self.date.isoformat()}"])
            else:
                self.windows.append(InventoryDateEditWindow(self.date, self.mainApp))
    
    def deleteDate(self):
        if self.date is None:
            errorMessage(self.mainApp, ["No date selected."])
        else:
            if not self.date in self.mainApp.db.inventories: # Should never happen, but if I screwed something up, fail gracefully
                errorMessage(self.mainApp, [f"No inventory on {self.date.isoformat()}"])
            else:
                confirm = QMessageBox.question(self, f"Delete {self.date.isoformat()}?", f"Are you sure you want to delete the inventory on {self.date.isoformat()}?")
                if confirm == QMessageBox.StandardButton.Yes:
                    self.mainApp.db.delInventory(self.date)
                    QMessageBox.information(self.mainApp, "Success", f"{self.date.isoformat()} successfully deleted!")
        self.refresh()

    def report(self):
        if self.date == None:
            errorMessage(self.mainApp, ["No date selected."])
        else:
            reportFile  = QFileDialog.getSaveFileName(self, f"Save {self.date.isoformat()} Inventory Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
            if not reportFile[0] == "":
                pdf = PDFReport(self.mainApp.db, reportFile[0])
                pdf.inventoryReport(self.date)
                startfile(reportFile[0])

class InventoryDateEditWindow(QWidget):
    def __init__(self, date: datetime.date | None, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {date.isoformat()}" if date is not None else "New Inventory Date")
        self.date = date

        self.calendar = QCalendarWidget()
        if self.date is not None:
            self.calendar.setSelectedDate(toQDate(self.date))

        self.mainLayout = [
            [
                QLabel("Inventory Date:"), self.calendar
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if self.date is not None:
            self.mainLayout[-1][0].clicked.connect(self.updateInventory)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newInventory)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        
        date = fromQDate(self.calendar.selectedDate())
        if date in self.mainApp.db.inventories and not (self.date is not None and date == self.date):
            errors.append(f"Inventory already exists on {date.isoformat()}")

        if len(errors) == 0:
            if isNew:
                self.mainApp.db.addInventory(date)
            else:
                if self.date is None:
                    raise RuntimeError('self.date is None')
                self.mainApp.db.updateInventory(self.date, date)

            self.mainApp.inventoryTab.refresh()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        return res
    
    def newInventory(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Inventory added successful!")
            self.close()
    
    def updateInventory(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Inventory updated successful!")
            self.close()

class MaterialsInventoryTab(QWidget):
    def __init__(self, mainTab: InventoryTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        self.windows = []

        self.newB = QPushButton("New Material Inventory Record")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Material Inventory Record")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Material Inventory Record")
        self.deleteB.clicked.connect(self.deleteRecords)

        self.setCurrentDate(None)
        
        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self # type: ignore

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)

        valLayout = QHBoxLayout()
        self.currValueLabel = QLabel("Current Total Materials Value: N/A")
        self.origValueLabel = QLabel("Original Total Materials Value: N/A")
        valLayout.addWidget(self.currValueLabel)
        valLayout.addWidget(self.origValueLabel)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(valLayout)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def setCurrentDate(self, date: datetime.date | None):
        self.currentDate = date
        self.newB.setEnabled(date is not None)
        self.editB.setEnabled(date is not None)
        self.deleteB.setEnabled(date is not None)
    
    def genTableData(self):
        db = self.mainApp.db.inventories[self.currentDate].materials if self.currentDate is not None else None
        self.headers = ["Material", "Current Cost", "Original Cost", "Amount"]
        self.tableData = [] if db == None else [[
            "{}".format(entry),
            "{:.4f}".format(self.mainApp.db.materials[entry].getCostPerLb() if entry in self.mainApp.db.materials and self.mainApp.db.materials[entry].getCostPerLb() is not None else 0),
            "{}".format(db[entry].cost),
            "{}".format(db[entry].amount)

        ] for entry in db]
        self.tableData.sort(key=lambda row: row[0])
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(self.selection)}")

    def openNew(self):
        if self.currentDate is None:
            raise RuntimeError('self.currentDate is None')
        self.windows.append(MaterialInventoryEditWindow(self.currentDate, None, self.mainApp))
    
    def openEdits(self):
        if self.currentDate is None:
            raise RuntimeError('self.currentDate is None')
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No materials selected."])
        for material in self.selection:
            self.windows.append(MaterialInventoryEditWindow(self.currentDate, self.mainApp.db.inventories[self.currentDate].materials[material], self.mainApp))
    
    def deleteRecords(self):
        if self.currentDate is None:
            raise RuntimeError('self.currentDate is None')
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No dates selected."])
        for material in self.selection:
            confirm = QMessageBox.question(self, f"Delete record for {material} on {self.currentDate.isoformat()}?", f"Are you sure you want to delete the inventory for {material} on {self.currentDate.isoformat()}?")
            if confirm == QMessageBox.StandardButton.Yes:
                del self.mainApp.db.inventories[self.currentDate].materials[material]
                QMessageBox.information(self.mainApp, "Success", f"{material} on {self.currentDate.isoformat()} successfully deleted!")
        self.refresh()
    
    def refresh(self):
        self.setCurrentDate(self.mainTab.date)
        self.refreshTable()
        self.refreshValueLabels()
    
    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [material for material in self.selection if material in self.mainApp.db.inventories[self.currentDate].materials] if self.currentDate is not None and self.currentDate in self.mainApp.db.inventories else []
        self.setSelection(selection)
    
    def refreshValueLabels(self):
        if self.currentDate is None or not self.currentDate in self.mainApp.db.inventories:
            self.currValueLabel.setText("Current Total Materials Value: N/A")
            self.origValueLabel.setText("Original Total Materials Value: N/A")
        else:
            db = self.mainApp.db.inventories[self.currentDate].materials
            currVal = 0
            origVal = 0
            for entry in db:
                if db[entry].cost is None:
                    raise RuntimeError('db[entry].cost is None')
                if db[entry].amount is None:
                    raise RuntimeError('db[entry].amount is None')
                if entry in self.mainApp.db.materials:
                    currCost = self.mainApp.db.materials[entry].getCostPerLb()
                    if currCost is not None:
                        currVal += currCost * db[entry].amount
                origVal += db[entry].cost * db[entry].amount # type: ignore
            self.currValueLabel.setText(f"Current Total Materials Value: {currVal:.4f}")
            self.origValueLabel.setText(f"Original Total Materials Value: {origVal:.4f}")

class MaterialInventoryEditWindow(QWidget):
    def __init__(self, date: datetime.date, entry: MaterialInventoryRecord | None, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry.name} for {date.isoformat()}" if not entry == None else f"New Material Record for {date.isoformat()}")

        self.date = date
        self.entry = entry
        if entry is not None:
            if not (entry.date == date):
                raise RuntimeError('entry.date == date')

        materials = ["None"]
        if entry is not None:
            if entry.name is None:
                raise RuntimeError('entry.name is None')
            if not entry.name in self.mainApp.db.materials or self.mainApp.db.materials[entry.name].getCostPerLb() is None:
                materials.append(entry.name)
        materials.extend([key for key in self.mainApp.db.materials if self.mainApp.db.materials[key].getCostPerLb() is not None])

        self.selectedName = None if entry is None else entry.name
        self.options = getComboBox(materials, self.selectedName)
        self.options.currentTextChanged.connect(self.selectName)

        self.costEntry = QLineEdit("" if entry is None else f"{entry.cost}")

        self.costB = QPushButton(f"Get Latest Cost ({"N/A" if self.getCurrentCost() is None else f"${self.getCurrentCost():.2f}"})")
        self.costB.clicked.connect(self.refreshCost)

        self.mainLayout = [
            [QLabel("Material:"), self.options],
            [QLabel("Cost:"), self.costEntry, self.costB],
            [QLabel("Amount:"), QLineEdit("" if entry is None else f"{entry.amount}")],
        ]
        self.mainLayout.append([QPushButton("Update"), QPushButton("Create")])

        widgetFromList(self, self.mainLayout)
        if entry is not None:
            self.mainLayout[-1][0].clicked.connect(self.updateEntry)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newEntry)
        self.show()
    
    def getCurrentCost(self):
        if self.selectedName is None:
            return None
        elif not self.selectedName in self.mainApp.db.materials:
            return None
        else:
            return self.mainApp.db.materials[self.selectedName].getCostPerLb()

    def selectName(self, pick: str):
        if pick == "" or pick == "None":
            self.selectedName = None
        else:
            self.selectedName = pick
            self.costB.setText(f"Get Latest Cost ({"N/A" if self.getCurrentCost() is None else f"${self.getCurrentCost():.2f}"})")
    
    def refreshCost(self):
        self.costEntry.setText("0" if self.getCurrentCost() is None else f"{self.getCurrentCost():.4f}")

    def readData(self, isNew):
        res = False
        errors = []
        if not self.date in self.mainApp.db.inventories:
            errors.append(f"{self.date.isoformat()} no longer has an associated inventory")
        name = self.selectedName
        if name is None:
            errors.append("Must select a material")
        if name in self.mainApp.db.inventories[self.date].materials:
            if isNew or (self.entry is not None and not name == self.entry.name):
                errors.append(f"Material '{name}' already has an inventory record for {self.date.isoformat()}")
        cost = checkInput(self.costEntry.text(), float, "nonneg", errors, "cost")
        amount = checkInput(self.mainLayout[2][1].text(), float, "nonneg", errors, "amount")

        if len(errors) == 0:
            if name is None:
                raise RuntimeError('name is None')
            if isNew:
                self.entry = MaterialInventoryRecord()
                self.entry.setDate(self.date)
                self.entry.setName(name)
                self.entry.setInventory(cost, amount)
                self.mainApp.db.inventories[self.date].addMaterialRecord(self.entry)
            else:
                if not (self.entry is not None and self.entry.name is not None and name is not None):
                    raise RuntimeError('self.entry is not None and self.entry.name is not None and name is not None')
                if not self.entry.name == name:
                    self.mainApp.db.inventories[self.date].updateMaterialRecord(self.entry.name, name)
                self.entry.setInventory(cost, amount)
            self.mainApp.inventoryTab.materialsTab.refreshTable()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.entry.name} for {self.date.isoformat()}" if not self.entry == None else f"New Material Record for {self.date.isoformat()}")
        return res
    
    def updateEntry(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()
    
    def newEntry(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()

class PartsInventoryTab(QWidget):
    def __init__(self, mainTab: InventoryTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        self.windows = []
        
        self.newB = QPushButton("New Parts Inventory Record")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Parts Inventory Record")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Parts Inventory Record")
        self.deleteB.clicked.connect(self.deleteRecords)

        self.setCurrentDate(None)

        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self # type: ignore

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        valLayout = QHBoxLayout()
        self.currValueLabel = QLabel("Current Total Parts Value: N/A")
        self.origValueLabel = QLabel("Original Total Parts Value: N/A")
        valLayout.addWidget(self.currValueLabel)
        valLayout.addWidget(self.origValueLabel)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(valLayout)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def setCurrentDate(self, date: datetime.date | None):
        self.currentDate = date
        self.newB.setEnabled(date is not None)
        self.editB.setEnabled(date is not None)
        self.deleteB.setEnabled(date is not None)
    
    def genTableData(self):
        db = self.mainApp.db.inventories[self.currentDate].parts if self.currentDate is not None else None
        self.headers = ["Part", "Current Cost", "Original Cost", "Pressed", "Finished", "Fired", "Completed"]
        self.tableData = [] if db == None else [[
            "{}".format(entry),
            "{:.4f}".format(self.mainApp.db.parts[entry].getManufacturingCost() if entry in self.mainApp.db.parts else 0),
            "{}".format(db[entry].cost),
            "{}".format(db[entry].amount40),
            "{}".format(db[entry].amount60),
            "{}".format(db[entry].amount80),
            "{}".format(db[entry].amount100)
        ] for entry in db]
        self.tableData.sort(key=lambda row: row[0])
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(self.selection)}")

    def openNew(self):
        if self.currentDate is None:
            raise RuntimeError('self.currentDate is None')
        self.windows.append(PartInventoryEditWindow(self.currentDate, None, self.mainApp))
    
    def openEdits(self):
        if self.currentDate is None:
            raise RuntimeError('self.currentDate is None')
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No parts selected."])
        for part in self.selection:
            self.windows.append(PartInventoryEditWindow(self.currentDate, self.mainApp.db.inventories[self.currentDate].parts[part], self.mainApp))
    
    def deleteRecords(self):
        if self.currentDate is None:
            raise RuntimeError('self.currentDate is None')
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No parts selected."])
        for part in self.selection:
            confirm = QMessageBox.question(self, f"Delete record for {part} on {self.currentDate.isoformat()}?", f"Are you sure you want to delete the inventory for {part} on {self.currentDate.isoformat()}?")
            if confirm == QMessageBox.StandardButton.Yes:
                del self.mainApp.db.inventories[self.currentDate].parts[part]
                QMessageBox.information(self.mainApp, "Success", f"{part} on {self.currentDate.isoformat()} successfully deleted!")
        self.refresh()
    
    def refresh(self):
        self.setCurrentDate(self.mainTab.date)
        self.refreshTable()
        self.refreshValueLabels()
    
    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [part for part in self.selection if part in self.mainApp.db.inventories[self.currentDate].parts] if self.currentDate is not None and self.currentDate in self.mainApp.db.inventories else []
        self.setSelection(selection)
    
    def refreshValueLabels(self):
        if self.currentDate is None or not self.currentDate in self.mainApp.db.inventories:
            self.currValueLabel.setText("Current Total Parts Value: N/A")
            self.origValueLabel.setText("Original Total Parts Value: N/A")
        else:
            db = self.mainApp.db.inventories[self.currentDate].parts
            currVal = 0
            origVal = 0
            for entry in db:
                if db[entry].cost is None:
                    raise RuntimeError('db[entry].cost is None')
                if db[entry].amount40 is None:
                    raise RuntimeError('db[entry].amount40 is None')
                if db[entry].amount60 is None:
                    raise RuntimeError('db[entry].amount60 is None')
                if db[entry].amount80 is None:
                    raise RuntimeError('db[entry].amount80 is None')
                if db[entry].amount100 is None:
                    raise RuntimeError('db[entry].amount100 is None')
                if entry in self.mainApp.db.parts:
                    currCost = self.mainApp.db.parts[entry].getManufacturingCost()
                    if currCost is None:
                        raise RuntimeError('currCost is None')
                    currVal += 0.4 * currCost * db[entry].amount40 + 0.6 * currCost * db[entry].amount60 + 0.8 * currCost * db[entry].amount80 + currCost * db[entry].amount100
                origVal += 0.4 * db[entry].cost * db[entry].amount40 + 0.6 * db[entry].cost * db[entry].amount60 + 0.8 * db[entry].cost * db[entry].amount80 + db[entry].cost * db[entry].amount100 # type: ignore
            self.currValueLabel.setText(f"Current Total Parts Value: {currVal:.4f}")
            self.origValueLabel.setText(f"Original Total Parts Value: {origVal:.4f}")

class PartInventoryEditWindow(QWidget):
    def __init__(self, date: datetime.date, entry: PartInventoryRecord | None, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry.name} for {date.isoformat()}" if not entry == None else f"New Part Record for {date.isoformat()}")

        self.date = date
        self.entry = entry
        if entry is not None:
            if not (entry.date == date):
                raise RuntimeError('entry.date == date')

        parts = ["None"]
        if entry is not None and not entry.name in self.mainApp.db.parts:
            if entry.name is None:
                raise RuntimeError('entry.name is None')
            parts.append(entry.name)
        parts.extend([key for key in self.mainApp.db.parts])

        self.selectedName = None if entry is None else entry.name
        self.options = getComboBox(parts, self.selectedName)
        self.options.currentTextChanged.connect(self.selectName)

        self.costEntry = QLineEdit("" if entry is None else f"{entry.cost}")

        self.costB = QPushButton(f"Get Latest Cost ({"N/A" if self.getCurrentCost() is None else f"${self.getCurrentCost():.2f}"})")
        self.costB.clicked.connect(self.refreshCost)

        self.mainLayout = [
            [QLabel("Part:"), self.options],
            [QLabel("Cost:"), self.costEntry, self.costB],
            [QLabel("Amount Pressed:"), QLineEdit("0" if entry is None else f"{entry.amount40}")],
            [QLabel("Amount Finished:"), QLineEdit("0" if entry is None else f"{entry.amount60}")],
            [QLabel("Amount Fired:"), QLineEdit("0" if entry is None else f"{entry.amount80}")],
            [QLabel("Amount Completed:"), QLineEdit("0" if entry is None else f"{entry.amount100}")],
        ]
        self.mainLayout.append([QPushButton("Update"), QPushButton("Create")])

        widgetFromList(self, self.mainLayout)
        if entry is not None:
            self.mainLayout[-1][0].clicked.connect(self.updateEntry)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newEntry)
        self.show()
    
    def getCurrentCost(self):
        if self.selectedName is None:
            return None
        elif not self.selectedName in self.mainApp.db.parts:
            return None
        else:
            return self.mainApp.db.parts[self.selectedName].getManufacturingCost()

    def selectName(self, pick: str):
        if pick == "" or pick == "None":
            self.selectedName = None
        else:
            self.selectedName = pick
            self.costB.setText(f"Get Latest Cost ({"N/A" if self.getCurrentCost() is None else f"${self.getCurrentCost():.2f}"})")
    
    def refreshCost(self):
        self.costEntry.setText("0" if self.getCurrentCost() is None else f"{self.getCurrentCost():.4f}")

    def readData(self, isNew):
        res = False
        errors = []
        if not self.date in self.mainApp.db.inventories:
            errors.append(f"{self.date.isoformat()} no longer has an associated inventory")
        name = self.selectedName
        if name is None:
            errors.append("Must select a part")
        if name in self.mainApp.db.inventories[self.date].materials:
            if isNew or (self.entry is not None and not name == self.entry.name):
                errors.append(f"Part '{name}' already has an inventory record for {self.date.isoformat()}")
        cost = checkInput(self.costEntry.text(), float, "nonneg", errors, "cost")
        amount40 = checkInput(self.mainLayout[2][1].text(), int, "nonneg", errors, "amount pressed")
        amount60 = checkInput(self.mainLayout[3][1].text(), int, "nonneg", errors, "amount finished")
        amount80 = checkInput(self.mainLayout[4][1].text(), int, "nonneg", errors, "amount fired")
        amount100 = checkInput(self.mainLayout[5][1].text(), int, "nonneg", errors, "amount completed")

        if len(errors) == 0:
            if name is None:
                raise RuntimeError('name is None')
            if isNew:
                self.entry = PartInventoryRecord()
                self.entry.setDate(self.date)
                self.entry.setName(name)
                self.entry.setInventory(cost, amount40, amount60, amount80, amount100)
                self.mainApp.db.inventories[self.date].addPartRecord(self.entry)
            else:
                if not (self.entry is not None and self.entry.name is not None and name is not None):
                    raise RuntimeError('self.entry is not None and self.entry.name is not None and name is not None')
                if not self.entry.name == name:
                    self.mainApp.db.inventories[self.date].updatePartRecord(self.entry.name, name)
                self.entry.setInventory(cost, amount40, amount60, amount80, amount100)
            self.mainApp.inventoryTab.partsTab.refreshTable()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.entry.name} for {self.date.isoformat()}" if not self.entry == None else f"New Part Record for {self.date.isoformat()}")
        return res
    
    def updateEntry(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()
    
    def newEntry(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()