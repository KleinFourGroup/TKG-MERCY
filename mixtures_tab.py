from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QFileDialog
from PySide6.QtCore import Qt
from table import DBTable
from app import MainWindow
from records import Mixture
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, startfile, centerOnScreen

from report import PDFReport
import os
import logging

class MixturesTab(QWidget):
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        # self.error = None
        self.genTableData()
        self.table = DBTable(self.mixtures, self.headers)
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
        report = QPushButton("Report")
        report.clicked.connect(self.reportSelection)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.selectLabel)
        barLayout.addWidget(details)
        barLayout.addWidget(edit)
        barLayout.addWidget(new)
        barLayout.addWidget(delete)
        barLayout.addWidget(report)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.mainApp.db
        def getKey(entry):
            item = db.mixtures[entry]
            return (entry, )
        self.headers = ["Mixture", "Price", "Batch Weight", "+50", "-50+100", "-100+200", "-200+325", "-325", "Al2O3", "SiO2", "Fe2O3"]
        self.mixtures = [[
            entry,
            "${:.4f} / lb".format(db.mixtures[entry].getCost()) if db.mixtures[entry].getCost() is not None else "N/A",
            "{:.4f} lbs".format(db.mixtures[entry].getBatchWeight()),
            "{:.2f}%".format(db.mixtures[entry].getProp("Plus50", False)),
            "{:.2f}%".format(db.mixtures[entry].getProp("Sub50Plus100", False)),
            "{:.2f}%".format(db.mixtures[entry].getProp("Sub100Plus200", False)),
            "{:.2f}%".format(db.mixtures[entry].getProp("Sub200Plus325", False)),
            "{:.2f}%".format(db.mixtures[entry].getProp("Sub325", False)),
            "{:.2f}%".format(db.mixtures[entry].getProp("Al2O3")),
            "{:.2f}%".format(db.mixtures[entry].getProp("SiO2")),
            "{:.2f}%".format(db.mixtures[entry].getProp("Fe2O3"))
        ] for entry in db.mixtures]
        self.mixtures.sort(key=lambda row: getKey(row[0]))
    
    def setSelection(self, selection):
        self.selection = selection
        self.selectLabel.setText(f"Selection: {",".join(selection)}")
    
    def openDetails(self):
        if len(self.selection) == 0:
            # self.error = ErrorWindow(["No mixtures selected."])
            errorMessage(self.mainApp, ["No mixtures selected."])
        for mixture in self.selection:
            logging.debug(mixture)
            MixturesDetailsWindow(mixture, self.mainApp)
    
    def openEdits(self):
        for mixture in self.selection:
            logging.debug(mixture)
            MixturesEditWindow(mixture, self.mainApp)
    
    def openNew(self):
        MixturesEditWindow(None, self.mainApp)

    def deleteSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No mixtures selected."])
        for mixture in self.selection:
            confirm = QMessageBox.question(self, f"Delete {mixture}?", f"Are you sure you want to delete {mixture}?")

            if confirm == QMessageBox.StandardButton.Yes:
                usedIn = self.mainApp.db.delMixture(mixture)
                if len(usedIn) == 0:
                    self.refreshTable()
                    QMessageBox.information(self.mainApp, "Success!", f"Deleted mixture {mixture}")
                else:
                    errorMessage(self.mainApp, [f"{mixture} is used in {item}!" for item in usedIn])

    def reportSelection(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No mixtures selected."])
        for mixture in self.selection:
            reportFile  = QFileDialog.getSaveFileName(self, f"Save {mixture} Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
            if not reportFile[0] == "":
                pdf = PDFReport(self.mainApp.db, reportFile[0])
                pdf.mixReport(mixture)
                startfile(reportFile[0])
    
    def refreshTable(self):
        self.genTableData()
        self.table.setData(self.mixtures)
        selection = [mixture for mixture in self.selection if mixture in self.mainApp.db.mixtures]
        self.setSelection(selection)

class MixturesDetailsWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Details: {entry}")

        mixture = self.mainApp.db.mixtures[entry]        
        labels = [
            [QLabel(f"Mixture: {entry}")],
            [QLabel(f"Price: ${mixture.getCost()} per ton" if mixture.getCost() is not None else "Price: N/A")]
        ]
        for i in range(len(mixture.materials)):
            labels.append([QLabel(f"Material {i+1}: {mixture.materials[i]}"), QLabel(f"Weight: {mixture.weights[i]}")])
        labels.extend([
            [
                QLabel(f"SiO2: {mixture.getProp("SiO2"):.4f}%"),
                QLabel(f"Al2O3: {mixture.getProp("Al2O3"):.4f}%"),
                QLabel(f"Fe2O3: {mixture.getProp("Fe2O3"):.4f}%"),
                QLabel(f"TiO2: {mixture.getProp("TiO2"):.4f}%"),
                QLabel(f"Li2O: {mixture.getProp("Li2O"):.4f}%")
            ],
            [
                QLabel(f"P2O5: {mixture.getProp("P2O5"):.4f}%"),
                QLabel(f"Na2O: {mixture.getProp("Na2O"):.4f}%"),
                QLabel(f"CaO: {mixture.getProp("CaO"):.4f}%"),
                QLabel(f"K2O: {mixture.getProp("K2O"):.4f}%"),
                QLabel(f"MgO: {mixture.getProp("MgO"):.4f}%"),
                QLabel(f"Other: {mixture.getProp("otherChem"):.4f}%")
            ],
            [
                QLabel(f"+50: {mixture.getProp("Plus50", False):.4f}%"),
                QLabel(f"-50+100: {mixture.getProp("Sub50Plus100", False):.4f}%"),
                QLabel(f"-100+200: {mixture.getProp("Sub100Plus200", False):.4f}%"),
                QLabel(f"-200+325: {mixture.getProp("Sub200Plus325", False):.4f}%"),
                QLabel(f"-325: {mixture.getProp("Sub325", False):.4f}%")
            ]
        ])

        widgetFromList(self, labels) # type: ignore
        centerOnScreen(self)
        self.show()

class MixturesEditWindow(QWidget):
    def __init__(self, entry, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mainApp = mainApp
        self.setWindowTitle(f"Edit: {entry if entry is not None else "New Mixture"}")

        mixture = self.mainApp.db.mixtures[entry] if entry is not None else None
        self.mixture = mixture

        self.error = None

        materials = ["None"]
        materials.extend([key for key in self.mainApp.db.materials if self.mainApp.db.materials[key].price is not None])

        self.mainLayout = [
            [QLabel("Mixture:"), QLineEdit(f"{entry if entry is not None else "New Mixture"}")],
        ]
        for i in range(12):
            if mixture == None or i >= len(mixture.materials):
                self.mainLayout.append([QLabel("Material:"), getComboBox(materials, None), QLabel("Weight:"), QLineEdit()])
            else:
                self.mainLayout.append([QLabel("Material:"), getComboBox(materials, mixture.materials[i]), QLabel("Weight:"), QLineEdit(f"{mixture.weights[i]}")])
        self.mainLayout.append([QPushButton("Update"), QPushButton("Create")])

        widgetFromList(self, self.mainLayout)
        if mixture is not None:
            self.mainLayout[13][0].clicked.connect(self.updateMixture)
        else:
            self.mainLayout[13][0].setEnabled(False)
        self.mainLayout[13][1].clicked.connect(self.newMixture)
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        name = self.mainLayout[0][1].text()
        if name in self.mainApp.db.mixtures:
            if isNew or (self.mixture is not None and not name == self.mixture.name):
                errors.append(f"Mixture name '{name}' already in use")
        materials = []
        weights = []
        for i in range(12):
            material = self.mainLayout[i+1][1].currentText()
            if not material == "None":
                materials.append(material)
                weights.append(checkInput(self.mainLayout[i+1][3].text(), float, "pos", errors, "weight"))
        if len(materials) == 0:
            errors.append("Mixture must have at least one material")

        if len(errors) == 0:
            isNone = self.mixture == None
            if isNew:
                self.mixture = Mixture(name)
                self.mainApp.db.addMixture(self.mixture)
            else:
                if self.mixture is None:
                    raise RuntimeError('self.mixture is None')
                self.mainApp.db.updateMixture(self.mixture.name, name)
            self.mixture.materials = []
            self.mixture.weights = []
            for i in range(len(materials)):
                self.mixture.add(materials[i], weights[i])
            if isNone:
                self.mixture = None
            self.mainApp.mixturesTab.refreshTable()
            self.mainApp.partsTab.refreshTable()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        self.setWindowTitle(f"Edit: {self.mixture.name if self.mixture is not None else "New Mixture"}")
        return res
    
    def updateMixture(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Update successful!")
            self.close()
    
    def newMixture(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Creation successful!")
            self.close()