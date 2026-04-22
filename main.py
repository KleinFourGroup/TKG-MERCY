from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
import logging
import os

from app import MainWindow

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

try:
    from ctypes import windll  # Only exists on Windows.
    myappid = 'tkg.mercySuite.products'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass

basedir = os.path.dirname(__file__)

# from converter import importDatabase
# db = importDatabase(False)
db = None

if __name__ == "__main__":
    QCoreApplication.setOrganizationName("tkg")
    QCoreApplication.setApplicationName("MERCY")
    app = QApplication([])
    app.setWindowIcon(QIcon(os.path.join(basedir, 'ceramics_icon.ico')))
    window = MainWindow(db)
    window.show()

    lastPath = QSettings().value("lastDbPath")
    if lastPath and os.path.isfile(lastPath):
        reply = QMessageBox.question(window, "Reopen Last Database?",
                                     f"Reopen {lastPath}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                window._loadPath(lastPath)
            except Exception as e:
                logging.error(f"Auto-reopen failed for {lastPath}: {e!r}")

    app.exec()
