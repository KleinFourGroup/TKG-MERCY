from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QFileDialog
from table import DBTable
from app import MainWindow
from records import Package
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, newVLine, startfile

from report import PDFReport
import os

class GlobalsTab(QWidget):
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp

        globalKeys = self.mainApp.db.globals.getGlobals()
        globalStrings = self.mainApp.db.globals.getStrings()

        self.titles: dict[str, QLabel] = {}
        self.values: dict[str, QLabel] = {}
        self.inputs: dict[str, QLineEdit] = {}
        self.buttons: dict[str, QPushButton] = {}
        self.calls = {}

        self.mainLayout = []

        for glob in globalKeys:
            self.titles[glob] = QLabel(f"{globalStrings[glob][0]}:")
            self.values[glob] = QLabel(f"{getattr(self.mainApp.db.globals, glob)} ({globalStrings[glob][1]})")
            self.inputs[glob] = QLineEdit(f"{getattr(self.mainApp.db.globals, glob)}")
            self.buttons[glob] = QPushButton("Update")

            def getUpdate(currGlob):
                def update():
                    confirm = QMessageBox.question(self.mainApp, f"Update {currGlob}?", f"Are you sure you want to update {currGlob}?")

                    if confirm == QMessageBox.StandardButton.Yes:
                        errors = []
                        val = checkInput(self.inputs[currGlob].text(), float, "nonneg", errors, currGlob)
                        if len(errors) > 0:
                            errorMessage(self.mainApp, errors)
                        else:
                            setattr(self.mainApp.db.globals, currGlob, val)
                            self.mainApp.partsTab.refreshTable()
                            self.refreshTab()
                return update
            
            self.buttons[glob].clicked.connect(getUpdate(glob))

            self.mainLayout.append([self.titles[glob], self.values[glob], newVLine(1), self.inputs[glob], self.buttons[glob]])
        
        report = QPushButton("Report")
        report.clicked.connect(self.report)
        self.mainLayout.append([report])

        widgetFromList(self, self.mainLayout)
    
    def report(self):
        reportFile  = QFileDialog.getSaveFileName(self, "Save globals Report As", os.path.expanduser("~"), "Portable Document Format (*.pdf)")
        if not reportFile[0] == "":
            pdf = PDFReport(self.mainApp.db, reportFile[0])
            pdf.globalsReport()
            startfile(reportFile[0])
    
    def refreshTab(self):
        globalKeys = self.mainApp.db.globals.getGlobals()
        globalStrings = self.mainApp.db.globals.getStrings()

        for glob in globalKeys:
            self.values[glob].setText(f"{getattr(self.mainApp.db.globals, glob)} ({globalStrings[glob][1]})")