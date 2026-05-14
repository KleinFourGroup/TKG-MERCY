import datetime
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QCalendarWidget, QComboBox
from PySide6.QtCore import QDate, Qt
import random
import math

from table import DBTable
from app import MainWindow
from employee_detail_tab import EmployeeDetailTab
from records import Employee, EmployeeReview, EmployeeReviewsDB
from error import errorMessage
from utils import getComboBox, widgetFromList, checkInput, toQDate, fromQDate, centerOnScreen

class ReviewsTab(QWidget):
    def __init__(self, mainTab: EmployeeDetailTab) -> None:
        super().__init__()
        self.mainTab = mainTab
        self.mainApp = self.mainTab.mainApp
        
        self.currentEmployee: Employee | None = None
        self.currentEmployeeReviews: EmployeeReviewsDB | None = None
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
        self.tableData = []
        if db is not None:
            for entry, review in db.reviews.items():
                nextReview = "?" if review.nextReview is None else review.nextReview.isoformat()
                self.tableData.append([
                    entry.isoformat(),
                    nextReview,
                    "{}".format(review.details)
                ])
        self.tableData.sort(key=lambda row: row[0])
    
    def setSelection(self, selection):
        self.selection = list(map(lambda x: datetime.date.fromisoformat(x), selection))
        self.selectLabel.setText(f"Selection: {",".join(map(lambda x: str(x), self.selection))}")
    
    def setEmployee(self, employeeID: int | None):
        self.currentEmployee = None if employeeID is None else self.mainApp.db.employees[employeeID]
        self.currentEmployeeReviews = None if employeeID is None else self.mainApp.db.reviews[employeeID]
        if self.currentEmployee is not None:
            lastName = (self.currentEmployee.lastName or "?").upper()
            firstName = self.currentEmployee.firstName or "?"
            anniversary = self.currentEmployee.anniversary.isoformat() if self.currentEmployee.anniversary is not None else "?"
            self.currentEmployeeLabel.setText(f"Employee: {lastName} {firstName} ({self.currentEmployee.idNum})")
            self.anniversary.setText(f"Anniversary: {anniversary}")
        else:
            self.currentEmployeeLabel.setText("Employee: N/A")
            self.anniversary.setText("Anniversary: N/A")

        self.newB.setEnabled(self.currentEmployee is not None)
        self.editB.setEnabled(self.currentEmployee is not None)
        self.deleteB.setEnabled(self.currentEmployee is not None)
    
    def refreshReviews(self):
        self.genTableData()
        self.table.setData(self.tableData)
        selection = [entry.isoformat() for entry in self.selection if self.currentEmployeeReviews is not None and entry in self.currentEmployeeReviews.reviews]
        self.setSelection(selection)

        isEmpty = False
        if self.currentEmployeeReviews is not None:
            last = self.currentEmployeeReviews.lastReview()
            if last is not None:
                lastStr = "?" if last.date is None else last.date.isoformat()
                nextStr = "?" if last.nextReview is None else last.nextReview.isoformat()
                self.reviewLast.setText(f"Last Review: {lastStr}")
                self.reviewNext.setText(f"Next Review: {nextStr}")
            else:
                isEmpty = True
        else:
            isEmpty = True
        
        if isEmpty:
            self.reviewLast.setText(f"Last Review: N/A")
            self.reviewNext.setText(f"Next Review: N/A")
    
    def openNew(self):
        if self.currentEmployeeReviews is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        ReviewsEditWindow(self.currentEmployeeReviews.idNum, None, self.mainApp)

    def openEdits(self):
        if self.currentEmployeeReviews is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No reviews selected."])
            return
        for date in self.selection:
            ReviewsEditWindow(self.currentEmployeeReviews.idNum, self.currentEmployeeReviews.reviews[date], self.mainApp)

    def deleteReviews(self):
        if self.currentEmployeeReviews is None:
            errorMessage(self.mainApp, ["No employee selected."])
            return
        if len(self.selection) == 0:
            errorMessage(self.mainApp, ["No reviews selected."])
            return
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
    def __init__(self, employeeID, review: EmployeeReview | None, mainApp: MainWindow):
        super().__init__(mainApp, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if employeeID is None:
            raise RuntimeError('employeeID is None')
        self.mainApp = mainApp
        self.setWindowTitle(f"Review: {employeeID}")
        self.employeeID = employeeID

        self.reviewDB = self.mainApp.db.reviews[employeeID]
        if self.reviewDB is None:
            raise RuntimeError('self.reviewDB is None')

        self.review = review
        self.isNew = review is None

        self.calendar = QCalendarWidget()
        daysText = ""
        detailsText = ""

        if review is not None:
            if review.date is None:
                raise RuntimeError('review.date is None')
            if review.date not in self.reviewDB.reviews:
                raise RuntimeError('review.date not in self.reviewDB.reviews')
            if not (review == self.reviewDB.reviews[review.date]):
                raise RuntimeError('review == self.reviewDB.reviews[review.date]')
            self.calendar.setSelectedDate(toQDate(review.date))
            if review.nextReview is not None:
                daysText = f"{(review.nextReview - review.date).days}"
            detailsText = review.details

        self.mainLayout = [
            [
                QLabel("Review Date:"), self.calendar
            ],
            [
                QLabel("Days to Next Review:"), QLineEdit(daysText),
            ],
            [
                QLabel("Details:"), QLineEdit(detailsText),
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
        centerOnScreen(self)
        self.show()

    def readData(self, isNew):
        res = False
        errors = []

        date = fromQDate(self.calendar.selectedDate())
        isSameDate = (
            not isNew
            and self.review is not None
            and date == self.review.date
        )
        if date in self.reviewDB.reviews and not isSameDate:
            errors.append(f"Employee {self.employeeID} was already reviewed on {date.isoformat()}")

        days = checkInput(self.mainLayout[1][1].text(), int, "pos", errors, "Days to Next Review")
        details = self.mainLayout[2][1].text()

        if len(errors) == 0:
            if isNew:
                review = EmployeeReview(self.employeeID, date, date + datetime.timedelta(days=days), details)
                self.review = review
            else:
                if self.review is None:
                    raise RuntimeError('self.review is None despite not isNew')
                if self.review.date is None:
                    raise RuntimeError('self.review.date is None')
                del self.reviewDB.reviews[self.review.date]
                self.review.date = date
                self.review.nextReview = date + datetime.timedelta(days=days)
                self.review.details = details
                review = self.review
            self.reviewDB.reviews[date] = review

            self.mainApp.overviewTab.reviewsTab.refresh()
            res = True
        else:
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
