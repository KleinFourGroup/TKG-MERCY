from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
import os

from app import MainWindow

try:
    from ctypes import windll  # Only exists on Windows.
    myappid = 'k4g.anikaSuite.products'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass

basedir = os.path.dirname(__file__)

# from converter import importDatabase
# db = importDatabase(False)
db = None

if __name__ == "__main__":
    app = QApplication([])
    app.setWindowIcon(QIcon(os.path.join(basedir, 'ceramics_icon.ico')))
    window = MainWindow(db)
    window.show()
    app.exec()
