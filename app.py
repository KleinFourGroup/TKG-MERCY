from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton, QFileDialog, QSizePolicy, QMessageBox
from records import Database, emptyDB
from utils import newHLine

import os

VERSION = "1.0"

class MainWindow(QWidget):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.setWindowTitle(f"Manufacturing and Employee Records: Costing and Yield v{VERSION}")
        if db == None:
            self.db = emptyDB()
        else:
            self.db = db

        from file_manager import FileManager
        self.fileManager = FileManager(self)

        self.resize(1280, 720)

        # Top-level tabs: Products | Employees | Inventory | Settings
        # (Production tab will be added in Step 11 of MERGE_PLAN.)
        self.tab_widget = QTabWidget()

        # ---- Products top-level tab (nested: Parts | Mixtures | Materials | Packaging) ----
        self.productsTab = QTabWidget()

        from parts_tab import PartsTab
        self.partsTab = PartsTab(self)
        self.productsTab.addTab(self.partsTab, "Parts")

        from mixtures_tab import MixturesTab
        self.mixturesTab = MixturesTab(self)
        self.productsTab.addTab(self.mixturesTab, "Mixtures")

        from materials_tab import MaterialsTab
        self.materialsTab = MaterialsTab(self)
        self.productsTab.addTab(self.materialsTab, "Materials")

        from packaging_tab import PackagingTab
        self.packagingTab = PackagingTab(self)
        self.productsTab.addTab(self.packagingTab, "Packaging")

        self.tab_widget.addTab(self.productsTab, "Products")

        # ---- Employees top-level tab (nested: Overview | Employee List | Holiday Observances) ----
        self.employeesTopTab = QTabWidget()

        from employee_overview_tab import MainTab
        self.overviewTab = MainTab(self)
        self.employeesTopTab.addTab(self.overviewTab, "Overview")

        from employees_tab import EmployeeOverviewTab
        self.employeesTab = EmployeeOverviewTab(self)
        self.employeesTopTab.addTab(self.employeesTab, "Employee List")

        from holidays_tab import HolidayTab
        self.holidaysTab = HolidayTab(self)
        self.employeesTopTab.addTab(self.holidaysTab, "Holiday Observances")

        self.tab_widget.addTab(self.employeesTopTab, "Employees")

        # ---- Inventory top-level tab (ANIKA's existing InventoryTab has its own nested Materials|Parts) ----
        from inventory_tab import InventoryTab
        self.inventoryTab = InventoryTab(self)
        self.tab_widget.addTab(self.inventoryTab, "Inventory")

        # ---- Settings top-level tab (nested: Cost Parameters) ----
        self.settingsTab = QTabWidget()

        from globals_tab import GlobalsTab
        self.globalsTab = GlobalsTab(self)
        self.settingsTab.addTab(self.globalsTab, "Cost Parameters")

        self.tab_widget.addTab(self.settingsTab, "Settings")

        # ---- File controls (unchanged) ----
        self.openButton = QPushButton("Open Database")
        self.openButton.clicked.connect(self.open)
        self.saveButton = QPushButton("Save Database")
        self.saveButton.setEnabled(not self.fileManager.filePath == None)
        self.saveButton.clicked.connect(self.save)
        self.saveAsButton = QPushButton("Save Database As")
        self.saveAsButton.clicked.connect(self.saveAs)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.openButton)
        hlayout.addWidget(self.saveButton)
        hlayout.addWidget(self.saveAsButton)

        hline = newHLine(1)

        self.dbFileLabel = QLabel()
        self.setFileLabel()

        # Top-level window layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.tab_widget)
        layout.addWidget(hline)
        layout.addLayout(hlayout)
        layout.addWidget(self.dbFileLabel)

        self.setLayout(layout)

    def setFileLabel(self):
        self.dbFileLabel.setText(f"File: {self.fileManager.filePath}")

    def _refreshAllTabs(self):
        # Products domain
        self.materialsTab.refreshTable()
        self.mixturesTab.refreshTable()
        self.packagingTab.refreshTable()
        self.partsTab.refreshTable()
        # Inventory
        self.inventoryTab.refresh()
        # Settings
        self.globalsTab.refreshTab()
        # Employees domain
        self.employeesTab.activeEmployeesTab.refreshTable()
        self.employeesTab.inactiveEmployeesTab.refreshTable()
        self.overviewTab.refresh()
        self.holidaysTab.refresh()

    def open(self):
        self.openButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.saveAsButton.setEnabled(False)
        dbFile = QFileDialog.getOpenFileName(self, "Open Database", os.path.expanduser("~"), "Database (*.db)")
        if not dbFile[0] == "":
            if self.fileManager.setFile(dbFile[0]):
                self.fileManager.loadFile()
        self.setFileLabel()
        self.openButton.setEnabled(True)
        self.saveButton.setEnabled(not self.fileManager.filePath == None)
        self.saveAsButton.setEnabled(True)
        self._refreshAllTabs()

    def save(self):
        assert(not self.fileManager.filePath == None)
        self.fileManager.saveFile()
        QMessageBox.information(self, "Success", "Save successful!")

    def saveAs(self):
        self.openButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.saveAsButton.setEnabled(False)
        dbFile = QFileDialog.getSaveFileName(self, "Save Database As", os.path.expanduser("~"), "Database (*.db)")
        if not dbFile[0] == "":
            if self.fileManager.setFile(dbFile[0]):
                self.fileManager.saveFile()
        self.setFileLabel()
        self.openButton.setEnabled(True)
        self.saveButton.setEnabled(not self.fileManager.filePath == None)
        self.saveAsButton.setEnabled(True)
