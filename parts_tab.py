from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QCheckBox, QMessageBox
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from records import Part
from error import errorMessage
from utils import getComboBox, widgetFromList, checkInput, startfile, tempReportPath, centerOnScreen

from report import PDFReport
import math
import logging

class PartsTab(QWidget):
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        # self.error = None
        self.genTableData()
        self.table = DBTable(self.parts, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        self.detailsButton = QPushButton("Details")
        self.detailsButton.clicked.connect(self.openDetails)
        self.editButton = QPushButton("Edit")
        self.editButton.clicked.connect(self.openEdits)
        self.marginsButton = QPushButton("Margins")
        self.marginsButton.clicked.connect(self.openMargins)
        self.newButton = QPushButton("New")
        self.newButton.clicked.connect(self.openNew)
        self.deleteButton = QPushButton("Delete")
        self.deleteButton.clicked.connect(self.deleteSelection)
        self.reportButton = QPushButton("Report")
        self.reportButton.clicked.connect(self.reportSales)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(self.detailsButton)
        barLayout.addWidget(self.editButton)
        barLayout.addWidget(self.marginsButton)
        barLayout.addWidget(self.newButton)
        barLayout.addWidget(self.deleteButton)
        barLayout.addWidget(self.reportButton)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.mainApp.db
        def getKey(entry):
            item = db.parts[entry]
            isQuote = 0 if isinstance(item.sales, int) else 1
            return (isQuote, entry)
        self.headers = ["Part", "Weight", "Mix", "Materials", "Labor", "Scrap", "Packaging", "Total Cost", "Price", "GM", "CM", "Sales"]
        self.parts = [[
            entry,
            "{} lbs".format(db.parts[entry].weight),
            db.parts[entry].mix,
            "${:.4f}".format(db.parts[entry].getMatlCost()),
            "${:.4f}".format(db.parts[entry].getLaborCost()),
            "{:.2f}%".format(100 * db.parts[entry].getScrap()),
            "${:.4f}".format(db.parts[entry].getPackagingCost()),
            # "${:.4f}".format(db.parts[entry].getVariableCost()),
            # "${:.4f}".format(db.parts[entry].getManufacturingCost()),
            "${:.4f}".format(db.parts[entry].getTotalCost()),
            "${:.4f}".format(db.parts[entry].price),
            "{:.2f}%".format(db.parts[entry].getGM() * 100),
            "{:.2f}%".format(db.parts[entry].getCM() * 100),
            str(db.parts[entry].sales)
        ] for entry in db.parts]
        self.parts.sort(key=lambda row: getKey(row[0]))
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(selection)}")
    
    def openDetails(self):
        if len(self.selection) == 0:
            # self.error = ErrorWindow(["No parts selected."])
            errorMessage(self.mainApp, ["No parts selected."])
        for part in self.selection:
            logging.debug(part)
            PartsDetailsWindow(part, self.mainApp)
    
    def openMargins(self):
        if len(self.selection) == 0:
            # self.error = ErrorWindow(["No parts selected."])
            errorMessage(self.mainApp, ["No parts selected."])
        for part in self.selection:
            logging.debug(part)
            PartsMarginsWindow(part, self.mainApp)
    
    def openEdits(self):
        for part in self.selection:
            logging.debug(part)
            PartsEditWindow(part, self.mainApp)

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No parts selected."])
        for part in self.selection:
            confirm = QMessageBox.question(self, f"Delete {part}?", f"Are you sure you want to delete {part}?")

            if confirm == QMessageBox.StandardButton.Yes:
                self.mainApp.db.delPart(part)
                self.refreshTable()
                QMessageBox.information(self.mainApp, "Success!", f"Deleted part {part}")

    def reportSales(self):
        path = tempReportPath("sales")
        pdf = PDFReport(self.mainApp.db, path)
        pdf.salesReport()
        startfile(path)
    
    def openNew(self):
        PartsEditWindow(None, self.mainApp)
    
    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.parts)
        selection = [part for part in self.selection if part in self.mainApp.db.parts]
        self.setSelection(selection)

class PartsDetailsWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Details: {entry}")

        part = self.mainApp.db.parts[entry]
        padsStr = ", ".join(part.pad or [])
        padsPerBoxStr = ", ".join(map(str, part.padsPerBox or []))
        greenScrap = part.db.globals.greenScrap if part.db is not None else "?"
        fireScrapStr = f"{100 * part.fireScrap}" if part.fireScrap is not None else "?"
        labels: list[list[QWidget]] = [
            [QLabel(f"Part: {entry}")],
            [QLabel(f"Weight: {part.weight} lbs"), QLabel(f"Mix: {part.mix}")],
            [QLabel(f"Pressing: {part.pressing} pieces/hour"), QLabel(f"Turning: {part.turning} pieces/hour")],
            [QLabel(f"Box: {part.box}"), QLabel(f"Pieces / box: {part.piecesPerBox}"), QLabel(f"Pallet: {part.pallet}"), QLabel(f"Boxes / pallet: {part.boxesPerPallet}"), QLabel(f"Pads: {padsStr}"), QLabel(f"Pads / box: {padsPerBoxStr}"), QLabel(f"Misc.: {", ".join(part.misc)}")],
            [QLabel(f"Green scrap: {greenScrap}%"), QLabel(f"Fire scrap: {fireScrapStr}%")],
            [QLabel(f"Var. Cost: ${part.getVariableCost():.3f}"), QLabel(f"Man. Cost: ${part.getManufacturingCost():.3f}")],
            [QLabel(f"Price: ${part.price}"), QLabel(f"Annual sales: ${part.sales}")]
        ]

        widgetFromList(self, labels)
        centerOnScreen(self)
        self.show()

class PartsMarginsWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Margin Calculator: {entry}")

        part = self.mainApp.db.parts[entry]        
        labels = []
        for percent in range(20, 70, 5):
            target = percent / 100
            priceG = math.floor(part.solveGM(target) * 10000) / 10000
            priceC = math.floor(part.solveCM(target) * 10000) / 10000
            def getUpdate(wind, part, price):
                def updatePrice():
                    part.price = price
                    QMessageBox.information(self, "Success", f"{entry} price set to ${price}!")
                    wind.mainApp.partsTab.refreshTable()
                    wind.close()
                return updatePrice
            buttonG = QPushButton("Apply")
            buttonG.clicked.connect(getUpdate(self, part, priceG))
            buttonC = QPushButton("Apply")
            buttonC.clicked.connect(getUpdate(self, part, priceC))
            labels.append([
                QLabel(f"{percent}% GM price: ${priceG:.4f}"), buttonG,
                QLabel(f"{percent}% CM price: ${priceC:.4f}"), buttonC
            ])

        widgetFromList(self, labels)
        centerOnScreen(self)
        self.show()

class PartsEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry if entry is not None else "New Part"}")

        part = self.mainApp.db.parts[entry] if entry is not None else None
        self.part = part

        self.error = None

        padsWidget = QWidget()
        self.padsLayout = []

        pads = ["None"]
        pads.extend([key for key in self.mainApp.db.packaging if self.mainApp.db.packaging[key].kind == "pad"])

        for i in range(5):
            if part is not None and part.pad is not None and part.padsPerBox is not None and i < len(part.pad):
                self.padsLayout.append([
                    QLabel("Pad:"),
                    getComboBox(pads, part.pad[i]),
                    QLabel("Pads / box:"),
                    QLineEdit(f"{part.padsPerBox[i]}")
                ])
            else:
                self.padsLayout.append([
                    QLabel("Pad:"),
                    getComboBox(pads, None),
                    QLabel("Pads / box:"),
                    QLineEdit()
                ])
        
        widgetFromList(padsWidget, self.padsLayout)

        miscWidget = QWidget()
        self.miscLayout = []
        miscs = ["None"]
        miscs.extend([key for key in self.mainApp.db.packaging if self.mainApp.db.packaging[key].kind == "misc"])

        for i in range(5):
            if (part is not None) and i < len(part.misc):
                self.miscLayout.append([QLabel("Misc.:"), getComboBox(miscs, part.misc[i])])
            else:
                self.miscLayout.append([QLabel("Misc.:"), getComboBox(miscs, None)])
        
        widgetFromList(miscWidget, self.miscLayout)

        boxNames = [key for key in self.mainApp.db.packaging if self.mainApp.db.packaging[key].kind == "box"]
        palletNames = [key for key in self.mainApp.db.packaging if self.mainApp.db.packaging[key].kind == "pallet"]

        self.nameEdit = QLineEdit(f"{entry if entry is not None else "New Part"}")
        self.weightEdit = QLineEdit(f"{part.weight if part is not None else ""}")
        self.mixCombo = getComboBox(list(self.mainApp.db.mixtures.keys()), part.mix if part is not None else None)
        self.pressingEdit = QLineEdit(f"{part.pressing if part is not None else ""}")
        self.turningEdit = QLineEdit(f"{part.turning if part is not None else ""}")
        self.boxCombo = getComboBox(boxNames, part.box if part is not None else None)
        self.piecesPerBoxEdit = QLineEdit(f"{part.piecesPerBox if part is not None else ""}")
        self.palletCombo = getComboBox(palletNames, part.pallet if part is not None else None)
        self.boxesPerPalletEdit = QLineEdit(f"{part.boxesPerPallet if part is not None else ""}")
        self.fireScrapEdit = QLineEdit(f"{100 * part.fireScrap if part is not None and part.fireScrap is not None else ""}")
        self.priceEdit = QLineEdit(f"{part.price if part is not None else ""}")
        self.salesEdit = QLineEdit(f"{part.sales if part is not None else ""}")
        self.quoteCheck = QCheckBox("Quote")
        self.updateButton = QPushButton("Update")
        self.createButton = QPushButton("Create")

        self.mainLayout = [
            [QLabel("Part:"), self.nameEdit],
            [
                QLabel("Weight:"), self.weightEdit, QLabel("lbs"),
                QLabel("Mix:"), self.mixCombo
            ],
            [
                QLabel("Pressing:"), self.pressingEdit, QLabel("pieces/hour"),
                QLabel("Turning:"), self.turningEdit, QLabel("pieces/hour")
            ],
            [
                QLabel("Box:"), self.boxCombo,
                QLabel("Pieces / box:"), self.piecesPerBoxEdit,
                QLabel("Pallet:"), self.palletCombo,
                QLabel("Boxes / pallet:"), self.boxesPerPalletEdit,
                padsWidget,
                miscWidget
            ],
            [
                QLabel("Fire scrap:"), self.fireScrapEdit, QLabel("%")
            ],
            [
                QLabel("Price:"), self.priceEdit,
                QLabel("Annual sales:"), self.salesEdit, self.quoteCheck
            ],
            [self.updateButton, self.createButton],
        ]

        widgetFromList(self, self.mainLayout)
        if part is not None:
            self.updateButton.clicked.connect(self.updatePart)
        else:
            self.updateButton.setEnabled(False)
            self.salesEdit.setEnabled(False)
            self.quoteCheck.setCheckState(Qt.CheckState.Checked)
        self.createButton.clicked.connect(self.newPart)
        self.quoteCheck.stateChanged.connect(self.quote)
        
        centerOnScreen(self)
        self.show()
    
    def quote(self, state):
        if state == Qt.CheckState.Checked.value:
            logging.debug("Disable")
            self.salesEdit.setEnabled(False)
        else:
            logging.debug("Enable")
            self.salesEdit.setEnabled(True)

    def readData(self, isNew):
        res = False
        errors = []
        name = self.nameEdit.text()
        if name in self.mainApp.db.parts:
            if isNew or (self.part is not None and not name == self.part.name):
                errors.append(f"Part name '{name}' already in use")
        weight = checkInput(self.weightEdit.text(), float, "pos", errors, "weight")
        mix = self.mixCombo.currentText()
        pressing = checkInput(self.pressingEdit.text(), float, "pos", errors, "pressing")
        turning = checkInput(self.turningEdit.text(), float, "pos", errors, "turning")
        box = self.boxCombo.currentText()
        piecesPerBox = checkInput(self.piecesPerBoxEdit.text(), int, "pos", errors, "pieces / box")
        pallet = self.palletCombo.currentText()
        boxesPerPallet = checkInput(self.boxesPerPalletEdit.text(), int, "pos", errors, "boxes / pallet")
        fireScrap = checkInput(self.fireScrapEdit.text(), float, "nonneg", errors, "fire scrap") / 100
        price = checkInput(self.priceEdit.text(), float, "nonneg", errors, "price")
        sales = "Quote" if self.quoteCheck.isChecked() else checkInput(self.salesEdit.text(), int, "nonneg", errors, "annual sales")

        pad = []
        padsPerBox = []
        for row in self.padsLayout:
            if not row[1].currentText() == "None":
                pad.append(row[1].currentText())
                padsPerBox.append(checkInput(row[3].text(), int, "pos", errors, "pads / box"))
        misc = []
        for row in self.miscLayout:
            if not row[1].currentText() == "None":
                misc.append(row[1].currentText())

        if len(errors) == 0:
            isNone = self.part is None
            if isNew:
                part = Part(name)
                self.part = part
                self.mainApp.db.addPart(part)
            else:
                if self.part is None:
                    raise RuntimeError('self.part is None despite not isNew')
                part = self.part
                self.mainApp.db.updatePart(part.name, name)
            part.setProduction(weight, mix, pressing, turning, fireScrap, price)
            part.setPackaging(box, piecesPerBox, pallet, boxesPerPallet, pad, padsPerBox, misc)
            part.sales = sales
            if isNone:
                self.part = None
            self.mainApp.partsTab.refreshTable()
            res = True
        else:
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.part.name if self.part is not None else "New Part"}")
        return res
    
    def updatePart(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()
    
    def newPart(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()