from PySide6.QtWidgets import QWidget, QLabel, QMessageBox

from utils import widgetFromList

def errorMessage(parent, errors):
    QMessageBox.critical(parent, "Error!", "\n".join(errors))

class ErrorWindow(QWidget):
    def __init__(self, errors):
        super().__init__()     
        labels = [[QLabel(err)] for err in errors]

        widgetFromList(self, labels) # type: ignore
        self.show()