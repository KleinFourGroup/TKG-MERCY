from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QComboBox
from records import Database, emptyDB
from utils import newHLine

from app import MainWindow

def createTab():
    tab = QWidget()
    label = QLabel("TODO")
    layout = QVBoxLayout(tab)
    layout.addWidget(label)
    tab.setLayout(layout)
    return tab

class MainTab(QWidget):
    def __init__(self, mainApp: MainWindow):
        super().__init__()
        self.mainApp = mainApp

        self.employeePicker = QComboBox()
        self.employeePicker.setEditable(False)
        self.employeeID: int = None
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
    
    def refreshPicker(self):
        db = self.mainApp.db
        activeEmployees: list[tuple[str, str, int]] = [(
            "{}".format(db.employees[entry].lastName.upper()),
            "{}".format(db.employees[entry].firstName),
            entry
        ) for entry in db.employees if db.employees[entry].status]
        activeEmployees.sort()
        selections = [f"{row[0]} {row[1]} ({row[2]})" for row in activeEmployees]
        selections.insert(0, "None")
        self.employeePicker.clear()
        self.employeePicker.addItems(selections)
        self.employeePicker.setCurrentIndex(0)

    def refresh(self):
        self.refreshPicker()
