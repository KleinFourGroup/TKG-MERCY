from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton, QFileDialog, QSizePolicy, QMessageBox
from records import Database, emptyDB
from utils import newHLine

import os

VERSION = "1.0rc1"

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

        # Top-level tabs: Products | Employees | Production | Inventory | Settings
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

        # ---- Production top-level tab (MERCY-native, Step 11) ----
        from production_tab import ProductionTab
        self.productionTab = ProductionTab(self)
        self.tab_widget.addTab(self.productionTab, "Production")

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
        self.saveButton.setEnabled(self.fileManager.filePath is not None)
        self.saveButton.clicked.connect(self.save)
        self.saveAsButton = QPushButton("Save Database As")
        self.saveAsButton.clicked.connect(self.saveAs)
        self.importButton = QPushButton("Import Database...")
        self.importButton.clicked.connect(self.importOther)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.openButton)
        hlayout.addWidget(self.saveButton)
        hlayout.addWidget(self.saveAsButton)
        hlayout.addWidget(self.importButton)

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
        # Production domain
        self.productionTab.refresh()

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
        self.saveButton.setEnabled(self.fileManager.filePath is not None)
        self.saveAsButton.setEnabled(True)
        self._refreshAllTabs()

    def save(self):
        if self.fileManager.filePath is None:
            raise RuntimeError('self.fileManager.filePath is None')
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
        self.saveButton.setEnabled(self.fileManager.filePath is not None)
        self.saveAsButton.setEnabled(True)

    def importOther(self):
        # Pick a second .db and merge its non-overlapping contents into the currently-open
        # in-memory DB. Does not write to disk — the user must click Save (or Save As) to
        # persist the merged result (§12.5(d)). The source file is never mutated.
        self.openButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.saveAsButton.setEnabled(False)
        self.importButton.setEnabled(False)
        try:
            dbFile = QFileDialog.getOpenFileName(self, "Import Database", os.path.expanduser("~"), "Database (*.db)")
            if dbFile[0] == "":
                return

            otherDb, fmt = self.fileManager.importOtherDb(dbFile[0])
            if otherDb is None:
                if fmt == "unknown":
                    QMessageBox.warning(self, "Import failed",
                                        f"{dbFile[0]} is not a recognized ANIKA, BECKY, or MERCY database.")
                else:
                    QMessageBox.warning(self, "Import failed",
                                        f"Could not read {dbFile[0]}. See logs for details.")
                return

            plan = self.db.planMergeFrom(otherDb)
            incoming = plan["incoming"]
            collisions = plan["collisions"]

            if any(collisions[k] for k in collisions):
                lines = ["The following entries already exist in the open database "
                         "and would conflict with the import:", ""]
                for key, vals in collisions.items():
                    if vals:
                        lines.append(f"  {key}: {len(vals)}  (e.g. {vals[:3]})")
                lines.append("")
                lines.append("Nothing was imported. Resolve the conflicts (or close the "
                             "current database) and try again.")
                QMessageBox.warning(self, "Import aborted: conflicts", "\n".join(lines))
                return

            summaryLines = [f"Importing from: {dbFile[0]}", ""]
            for key in ("materials", "mixtures", "packaging", "parts",
                        "materialInventory", "partInventory",
                        "employees", "holidays", "observances"):
                n = len(incoming[key])
                if n > 0:
                    summaryLines.append(f"  {key}: {n}")
            if len(summaryLines) == 2:
                summaryLines.append("  (nothing — source DB is empty)")
            summaryLines.append("")
            summaryLines.append("The merged result will live in memory until you Save "
                                "the current database. The source file will not be modified.")
            summaryLines.append("")
            summaryLines.append("Proceed?")

            reply = QMessageBox.question(self, "Confirm import", "\n".join(summaryLines),
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

            self.db.mergeFrom(otherDb)
            self._refreshAllTabs()
            QMessageBox.information(self, "Import complete",
                                    "Import succeeded. Click Save to persist the merged "
                                    "database to the open file.")
        finally:
            self.openButton.setEnabled(True)
            self.saveButton.setEnabled(self.fileManager.filePath is not None)
            self.saveAsButton.setEnabled(True)
            self.importButton.setEnabled(True)
