from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QComboBox
from records import Database, emptyDB
from utils import newHLine

from app import MainWindow

class EmployeeDetailTab(QWidget):
    def __init__(self, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp

        self.employeePicker = QComboBox()
        self.employeePicker.setEditable(False)
        self.employeeID: int | None = None
        self.employeeLabel = QLabel()

        self.employeePicker.currentTextChanged.connect(self.selectEmployee)
        
        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel("Employees:"))
        hlayout.addWidget(self.employeePicker)
        hlayout.addWidget(self.employeeLabel)

        # Create a QTabWidget
        self.tab_widget = QTabWidget()

        # Add tabs to the QTabWidget
        from reviews_tab import ReviewsTab
        self.reviewsTab = ReviewsTab(self)
        self.tab_widget.addTab(self.reviewsTab, "Reviews")
        from training_tab import TrainingTab
        self.trainingTab = TrainingTab(self)
        self.tab_widget.addTab(self.trainingTab, "Safety Training")
        from points_tab import PointsTab
        self.pointsTab = PointsTab(self)
        self.tab_widget.addTab(self.pointsTab, "Points and Absences")
        from pto_tab import PTOTab
        self.PTOTab = PTOTab(self)
        self.tab_widget.addTab(self.PTOTab, "PTO Tracker")
        from notes_tab import NotesTab
        self.notesTab = NotesTab(self)
        self.tab_widget.addTab(self.notesTab, "Notes and Incidents")

        layout = QVBoxLayout(self)
        layout.addLayout(hlayout)
        layout.addWidget(self.tab_widget)

        # Set the layout for the main window
        self.setLayout(layout)

        self.refreshPicker()

    def selectEmployee(self, pick: str):
        if pick == "" or pick == "None":
            self.employeeID = None
        else:
            self.employeeID = int(pick.split(" ")[-1][1:-1])
        self.reviewsTab.refresh()
        self.trainingTab.refresh()
        self.pointsTab.refresh()
        self.PTOTab.refresh()
        self.notesTab.refresh()
    
    def refreshPicker(self, hard: bool = True):
        db = self.mainApp.db
        activeEmployees: list[tuple[str, str, int]] = [(
            (db.employees[entry].lastName or "?").upper(),
            "{}".format(db.employees[entry].firstName),
            entry
        ) for entry in db.employees if db.employees[entry].status]
        activeEmployees.sort()
        # Each row carries its employee ID as userData so a soft refresh can
        # re-find the picked employee by *ID* rather than by label — a rename
        # rewrites the label, and surviving renames is the whole point of Step 81.
        previous = self.employeeID
        self.employeePicker.blockSignals(True)
        self.employeePicker.clear()
        self.employeePicker.addItem("None", userData=None)
        for last, first, entry in activeEmployees:
            self.employeePicker.addItem(f"{last} {first} ({entry})", userData=entry)
        index = 0
        if not hard and previous is not None:
            for i in range(self.employeePicker.count()):
                if self.employeePicker.itemData(i) == previous:
                    index = i
                    break
            # else: the employee was deleted or deactivated out of the list —
            # fall back to "None" rather than silently picking someone else.
        self.employeePicker.setCurrentIndex(index)
        self.employeePicker.blockSignals(False)
        # Signals stayed blocked across the rebuild (so a preserved pick doesn't
        # thrash the five detail subtabs mid-rebuild), which means the
        # currentTextChanged -> selectEmployee hop that normally syncs
        # employeeID and repaints those subtabs never fired. Drive it once here.
        self.selectEmployee(self.employeePicker.currentText())

    def refresh(self, hard: bool = True):
        self.refreshPicker(hard)
