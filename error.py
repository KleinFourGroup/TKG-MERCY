from PySide6.QtWidgets import QMessageBox

def errorMessage(parent, errors):
    QMessageBox.critical(parent, "Error!", "\n".join(errors))
