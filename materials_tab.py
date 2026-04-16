from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox
from table import DBTable
from app import MainWindow
from records import Material
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput

class MaterialsTab(QWidget):
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.windows = []
        # self.error = None
        self.genTableData()
        self.table = DBTable(self.materials, self.headers)
        self.table.parentTab = self # type: ignore

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        details = QPushButton("Details")
        details.clicked.connect(self.openDetails)
        edit = QPushButton("Edit")
        edit.clicked.connect(self.openEdits)
        new = QPushButton("New")
        new.clicked.connect(self.openNew)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.deleteSelection)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(details)
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
            item = db.materials[entry]
            hasPrice = 0 if not db.materials[entry].getCostPerLb() == None else 1
            return (hasPrice, entry)
        self.headers = ["Material", "Price", "+50", "-50+100", "-100+200", "-200+325", "-325", "Al2O3", "SiO2", "Fe2O3"]
        self.materials = [[
            entry,
            "${:.4f} / lb".format(db.materials[entry].getCostPerLb()) if not db.materials[entry].getCostPerLb() == None else "N/A",
            "{:.2f}%".format(db.materials[entry].Plus50),
            "{:.2f}%".format(db.materials[entry].Sub50Plus100),
            "{:.2f}%".format(db.materials[entry].Sub100Plus200),
            "{:.2f}%".format(db.materials[entry].Sub200Plus325),
            "{:.2f}%".format(db.materials[entry].Sub325),
            "{:.2f}%".format(db.materials[entry].Al2O3),
            "{:.2f}%".format(db.materials[entry].SiO2),
            "{:.2f}%".format(db.materials[entry].Fe2O3)
        ] for entry in db.materials]
        self.materials.sort(key=lambda row: getKey(row[0]))
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(selection)}")
    
    def openDetails(self):
        if len(self.selection) == 0:
            # self.error = ErrorWindow(["No materials selected."])
            errorMessage(self.mainApp, ["No materials selected."])
        for material in self.selection:
            print(material)
            self.windows.append(MaterialsDetailsWindow(material, self.mainApp))
    
    def openEdits(self):
        for material in self.selection:
            print(material)
            self.windows.append(MaterialsEditWindow(material, self.mainApp))
    
    def openNew(self):
        self.windows.append(MaterialsEditWindow(None, self.mainApp))

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No materials selected."])
        for material in self.selection:
            confirm = QMessageBox.question(self, f"Delete {material}?", f"Are you sure you want to delete {material}?")

            if confirm == QMessageBox.StandardButton.Yes:
                usedIn = self.mainApp.db.delMaterial(material)
                if len(usedIn) == 0:
                    self.refreshTable()
                    QMessageBox.information(self.mainApp, "Success!", f"Deleted material {material}")
                else:
                    errorMessage(self.mainApp, [f"{material} is used in {item}!" for item in usedIn])
    
    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.materials)
        selection = [material for material in self.selection if material in self.mainApp.db.materials]
        self.setSelection(selection)

class MaterialsDetailsWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp
        self.setWindowTitle(f"Details: {entry}")

        material = self.mainApp.db.materials[entry]        
        labels = [
            [QLabel(f"Material: {entry}")],
            [QLabel(f"Price: ${material.price} per ton" if not material.price == None else "Price: N/A"), QLabel(f"Freight: ${material.freight} per ton" if not material.freight == None else "Freight: N/A")],
            [QLabel(f"SiO2: {material.SiO2}"), QLabel(f"Al2O3: {material.Al2O3}"), QLabel(f"Fe2O3: {material.Fe2O3}"), QLabel(f"TiO2: {material.TiO2}"), QLabel(f"Li2O: {material.Li2O}")],
            [QLabel(f"P2O5: {material.P2O5}"), QLabel(f"Na2O: {material.Na2O}"), QLabel(f"CaO: {material.CaO}"), QLabel(f"K2O: {material.K2O}"), QLabel(f"MgO: {material.MgO}"), QLabel(f"Other: {material.otherChem}")],
            [QLabel(f"LOI: {material.LOI}")],
            [
                QLabel(f"+50: {material.Plus50}%"),
                QLabel(f"-50+100: {material.Sub50Plus100}%"),
                QLabel(f"-100+200: {material.Sub100Plus200}%"),
                QLabel(f"-200+325: {material.Sub200Plus325}%"),
                QLabel(f"-325: {material.Sub325}%")
            ]
        ]

        widgetFromList(self, labels) # type: ignore
        self.show()

class MaterialsEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry if not entry == None else "New Material"}")

        material = self.mainApp.db.materials[entry] if not entry == None else None
        self.material = material

        self.error = None

        self.mainLayout = [
            [QLabel("Material:"), QLineEdit(f"{entry if not entry == None else "New Material"}")],
            [
                QLabel("Price:"), QLineEdit(f"{material.price if not material == None else ""}"), QLabel("per ton"),
                QLabel("Freight:"), QLineEdit(f"{material.freight if not material == None else ""}"), QLabel("per ton"),
            ],
            [
                QLabel("SiO2:"), QLineEdit(f"{material.SiO2 if not material == None else ""}"),
                QLabel("Al2O3:"), QLineEdit(f"{material.Al2O3 if not material == None else ""}"),
                QLabel("Fe2O3:"), QLineEdit(f"{material.Fe2O3 if not material == None else ""}"),
                QLabel("TiO2:"), QLineEdit(f"{material.TiO2 if not material == None else ""}"),
                QLabel("Li2O:"), QLineEdit(f"{material.Li2O if not material == None else ""}")
            ],
            [
                QLabel("P2O5:"), QLineEdit(f"{material.P2O5 if not material == None else ""}"),
                QLabel("Na2O:"), QLineEdit(f"{material.Na2O if not material == None else ""}"),
                QLabel("CaO:"), QLineEdit(f"{material.CaO if not material == None else ""}"),
                QLabel("K2O:"), QLineEdit(f"{material.K2O if not material == None else ""}"),
                QLabel("MgO:"), QLineEdit(f"{material.MgO if not material == None else ""}"),
                QLabel("Other:"), QLineEdit(f"{material.otherChem if not material == None else ""}"),
                QLabel("LOI:"), QLineEdit(f"{material.LOI if not material == None else ""}")
            ],
            [
                QLabel("+50:"), QLineEdit(f"{material.Plus50 if not material == None else ""}"), QLabel("%"),
                QLabel("-50+100:"), QLineEdit(f"{material.Sub50Plus100 if not material == None else ""}"), QLabel("%"),
                QLabel("-100+200:"), QLineEdit(f"{material.Sub100Plus200 if not material == None else ""}"), QLabel("%"),
                QLabel("-200+325:"), QLineEdit(f"{material.Sub200Plus325 if not material == None else ""}"), QLabel("%"),
                QLabel("-325:"), QLineEdit(f"{material.Sub325 if not material == None else ""}"), QLabel("%")
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not material == None:
            self.mainLayout[5][0].clicked.connect(self.updateMaterial)
        else:
            self.mainLayout[5][0].setEnabled(False)
        self.mainLayout[5][1].clicked.connect(self.newMaterial)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        name = self.mainLayout[0][1].text()
        if name in self.mainApp.db.materials:
            if isNew or (self.material is not None and not name == self.material.name):
                errors.append(f"Material name '{name}' already in use")
        price = checkInput(self.mainLayout[1][1].text(), float, "nonneg", errors, "price")
        freight = checkInput(self.mainLayout[1][4].text(), float, "nonneg", errors, "freight")
        SiO2 = checkInput(self.mainLayout[2][1].text(), float, "nonneg", errors, "SiO2")
        Al2O3 = checkInput(self.mainLayout[2][3].text(), float, "nonneg", errors, "Al2O3")
        Fe2O3 = checkInput(self.mainLayout[2][5].text(), float, "nonneg", errors, "Fe2O3")
        TiO2 = checkInput(self.mainLayout[2][7].text(), float, "nonneg", errors, "TiO2")
        Li2O = checkInput(self.mainLayout[2][9].text(), float, "nonneg", errors, "Li2O")
        P2O5 = checkInput(self.mainLayout[3][1].text(), float, "nonneg", errors, "P2O5")
        Na2O = checkInput(self.mainLayout[3][3].text(), float, "nonneg", errors, "Na2O")
        CaO = checkInput(self.mainLayout[3][5].text(), float, "nonneg", errors, "CaO")
        K2O = checkInput(self.mainLayout[3][7].text(), float, "nonneg", errors, "K2O")
        MgO = checkInput(self.mainLayout[3][9].text(), float, "nonneg", errors, "MgO")
        otherChem = checkInput(self.mainLayout[3][11].text(), float, "nonneg", errors, "otherChem")
        LOI = checkInput(self.mainLayout[3][13].text(), float, "nonneg", errors, "LOI")
        Plus50 = checkInput(self.mainLayout[4][1].text(), float, "nonneg", errors, "Plus50")
        Sub50Plus100 = checkInput(self.mainLayout[4][4].text(), float, "nonneg", errors, "Sub50Plus100")
        Sub100Plus200 = checkInput(self.mainLayout[4][7].text(), float, "nonneg", errors, "Sub100Plus200")
        Sub200Plus325 = checkInput(self.mainLayout[4][10].text(), float, "nonneg", errors, "Sub200Plus325")
        Sub325 = checkInput(self.mainLayout[4][13].text(), float, "nonneg", errors, "Sub325")

        if len(errors) == 0:
            isNone = self.material == None
            if isNew:
                self.material = Material(name)
                self.mainApp.db.addMaterial(self.material)
            else:
                assert(self.material is not None)
                self.mainApp.db.updateMaterial(self.material.name, name)
            self.material.price = price
            self.material.freight = freight
            self.material.setChems(SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI)
            self.material.setSizes(Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325)
            self.material.otherChem = otherChem
            if isNone:
                self.material = None
            self.mainApp.materialsTab.refreshTable()
            self.mainApp.mixturesTab.refreshTable()
            self.mainApp.partsTab.refreshTable()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.material.name if not self.material == None else "New Material"}")
        return res
    
    def updateMaterial(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()
    
    def newMaterial(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()