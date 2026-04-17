import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox
from PySide6.QtCore import QDate
import random
import math

from table import DBTable
from app import MainWindow
from employee_overview_tab import MainTab
from records import Employee, EmployeeReview, EmployeeReviewsDB
from error import ErrorWindow, errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate

class ReviewsTab(QWidget):
    def __init__(self, mainTab: MainTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        self.windows = []
        
        self.currentEmployee: Employee = None
        self.currentEmployeeReviews: EmployeeReviewsDB = None
        self.currentEmployeeLabel = QLabel("Employee: N/A")

        self.genTableData()
        self.table = DBTable(self.tableData, self.headers)
        self.table.parentTab = self

        self.selection = []
        self.selectLabel = QLabel("Selection: N/A")

        self.reviewLast = QLabel("Last Review: N/A")
        self.reviewNext = QLabel("Next Review: N/A")
        self.anniversary = QLabel("Anniversary: N/A")
        topLayout = QHBoxLayout()
        topLayout.addWidget(self.currentEmployeeLabel)
        topLayout.addWidget(self.reviewLast)
        topLayout.addWidget(self.reviewNext)
        topLayout.addWidget(self.anniversary)

        self.newB = QPushButton("New Review")
        self.newB.clicked.connect(self.openNew)
        self.editB = QPushButton("Edit Review")
        self.editB.clicked.connect(self.openEdits)
        self.deleteB = QPushButton("Delete Review")
        self.deleteB.clicked.connect(self.deleteReviews)

        barLayout = QHBoxLayout()
        barLayout.addWidget(self.newB)
        barLayout.addWidget(self.editB)
        barLayout.addWidget(self.deleteB)

        layout = QVBoxLayout()
        layout.addLayout(topLayout)
        layout.addWidget(self.table)
        layout.addWidget(self.selectLabel)
        layout.addLayout(barLayout)
        self.setLayout(layout)
    
    def genTableData(self):
        db = self.currentEmployeeReviews
        self.headers = ["Review Date", "Next Review", "Details"]
        self.tableData = [] if db == None else [[
            "{}".format(db.reviews[entry].date.isoformat()),
            "{}".format(db.reviews[entry].nextReview.isoformat()),
            "{}".format(db.reviews[entry].details)

        ] for entry in db.reviews]
        self.tableData.sort(key=lambda row: row[0])
    
    def setSelection(self, selection):
        self.selection = list(map(lambda x: datetime.date.fromisoformat(x), selection))
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def setEmployee(self, employeeID: int):
        self.currentEmployee = None if employeeID == None else self.mainApp.db.employees[self.mainTab.employeeID] 
        self.currentEmployeeReviews = None if employeeID == None else self.mainApp.db.reviews[self.mainTab.employeeID] 
        if not self.currentEmployee == None:
            self.currentEmployeeLabel.setText(f"Employee: {self.currentEmployee.lastName.upper()} {self.currentEmployee.firstName} ({self.currentEmployee.idNum})")
            self.anniversary.setText(f"Anniversary: {self.currentEmployee.anniversary.isoformat()}")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")
            self.anniversary.setText("Anniversary: N/A")

        self.newB.setEnabled(not self.currentEmployee == None)
        self.editB.setEnabled(not self.currentEmployee == None)
        self.deleteB.setEnabled(not self.currentEmployee == None)
    
    def refreshReviews(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [entry.isoformat() for entry in self.selection if not self.currentEmployeeReviews == None and entry in self.currentEmployeeReviews.reviews]
        self.setSelection(selection)

        isEmpty = False
        if not self.currentEmployeeReviews == None:
            last = self.currentEmployeeReviews.lastReview()
            if not last == None:
                self.reviewLast.setText(f"Last Review: {last.date.isoformat()}")
                self.reviewNext.setText(f"Next Review: {last.nextReview.isoformat()}")
            else:
                isEmpty = True
        else:
            isEmpty = True
        
        if isEmpty:
            self.reviewLast.setText(f"Last Review: N/A")
            self.reviewNext.setText(f"Next Review: N/A")
    
    def openNew(self):
        self.windows.append(ReviewsEditWindow(self.currentEmployeeReviews.idNum, None, self.mainApp))
    
    def openEdits(self):
        pass
        # self.windows.append(EmployeeEditWindow(None, self.mainApp, self.active))
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No reviews selected."])
        for date in self.selection:
            self.windows.append(ReviewsEditWindow(self.currentEmployeeReviews.idNum, self.currentEmployeeReviews.reviews[date], self.mainApp))
    
    def deleteReviews(self):
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No reviews selected."])
        for date in self.selection:
            confirm = QMessageBox.question(self, f"Delete {date.isoformat()}?", f"Are you sure you want to delete the review on {date.isoformat()}?")

            if confirm == QMessageBox.StandardButton.Yes:
                del self.currentEmployeeReviews.reviews[date]

                QMessageBox.information(self.mainApp, "Success", f"{date.isoformat()} successfully deleted!")
        self.refresh()
    
    def refresh(self):
        self.setEmployee(self.mainTab.employeeID)
        self.refreshReviews()

class ReviewsEditWindow(QWidget):
    def __init__(self, employeeID, review: EmployeeReview, mainApp: MainWindow):
        super().__init__()
        if employeeID is None:
            raise RuntimeError('employeeID is None')
        self.mainApp = mainApp
        self.setWindowTitle(f"Review: {employeeID}")
        self.employeeID = employeeID

        self.reviewDB = self.mainApp.db.reviews[employeeID]
        if self.reviewDB is None:
            raise RuntimeError('self.reviewDB is None')

        self.review = review
        self.isNew = review == None
        if not self.isNew:
            if review.date not in self.reviewDB.reviews:
                raise RuntimeError('review.date not in self.reviewDB.reviews')
            if not (review == self.reviewDB.reviews[review.date]):
                raise RuntimeError('review == self.reviewDB.reviews[review.date]')

        self.calendar = QCalendarWidget()
        if not self.isNew:
            self.calendar.setSelectedDate(toQDate(self.review.date))

        self.mainLayout = [
            [
                QLabel("Review Date:"), self.calendar
            ],
            [
                QLabel("Days to Next Review:"), QLineEdit(f"{(self.review.nextReview - self.review.date).days if not self.isNew else ""}"),
            ],
            [
                QLabel("Details:"), QLineEdit(f"{self.review.details if not self.isNew else ""}"),
            ],
            [
                QPushButton("Update"), QPushButton("Create")
            ]
        ]

        widgetFromList(self, self.mainLayout)
        if not self.isNew:
            self.mainLayout[-1][0].clicked.connect(self.updateReview)
        else:
            self.mainLayout[-1][0].setEnabled(False)
        self.mainLayout[-1][1].clicked.connect(self.newReview)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []
        
        date = fromQDate(self.calendar.selectedDate())
        if date in self.reviewDB.reviews and not (not isNew and date == self.review.date):
            errors.append(f"Employee {self.employeeID} was already reviewed on {date.isoformat()}")
        
        days = checkInput(self.mainLayout[1][1].text(), int, "pos", errors, "Days to Next Review")
        details = self.mainLayout[2][1].text()

        if len(errors) == 0:
            if isNew:
                self.review = EmployeeReview(self.employeeID, date, date + datetime.timedelta(days=days), details)
            if not isNew:
                del self.reviewDB.reviews[self.review.date]
                self.review.date = date
                self.review.nextReview = date + datetime.timedelta(days=days)
                self.review.details = details
            self.reviewDB.reviews[self.review.date] = self.review

            self.mainApp.overviewTab.reviewsTab.refresh()
            res = True
        else:
            # self.error = ErrorWindow(errors)
            errorMessage(self, errors)
        return res
    
    def newReview(self):
        success = self.readData(True)
        if success:
            QMessageBox.information(self, "Success", "Review added successful!")
            self.close()
    
    def updateReview(self):
        success = self.readData(False)
        if success:
            QMessageBox.information(self, "Success", "Review updated successful!")
            self.close()
