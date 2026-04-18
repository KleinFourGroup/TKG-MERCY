from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QFrame
from PySide6.QtCore import QDate
import base64, os, sys, datetime

def getComboBox(items: list[str], item):
    box = QComboBox()
    box.addItems(items)
    if item is not None:
        box.setCurrentIndex(items.index(item))
    return box

def widgetFromList(widget: QWidget, layoutList: list[list[QWidget]]):
    lines = [QHBoxLayout() for row in layoutList]

    for i in range(len(layoutList)):
        for item in layoutList[i]:
            lines[i].addWidget(item)

    layout = QVBoxLayout()
    for line in lines:
        layout.addLayout(line)
    
    widget.setLayout(layout)

def checkInput(raw, type, range, errors, name = "input"):
    res = 1
    if type == int:
        try:
            res = int(raw)
        except:
            errors.append(f"Invalid {name}: '{raw}' is not a valid integer")
    elif type == float:
        try:
            res = float(raw)
        except:
            errors.append(f"Invalid {name}: '{raw}' is not a valid number")
    else:
        errors.append(f"Bug: {name} is unknown type '{type}'")
    if range == "nonneg":
        if res < 0:
            errors.append(f"Invalid {name}: '{raw}' must be non-negative")
    elif range == "pos":
        if res <= 0:
            errors.append(f"Invalid {name}: '{raw}' must be positive")
    else:
        errors.append(f"Bug: {name} is unknown range '{range}'")
    return res

def stringToB64(data: str):
    return base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")

def stringFromB64(enc: str):
    return base64.urlsafe_b64decode(enc.encode("utf-8")).decode("utf-8")

def listToString(data, kind):
    encodings = []
    for val in data:
        if not (isinstance(val, kind)):
            raise RuntimeError('isinstance(val, kind)')
        enc = stringToB64(str(val))
        encodings.append(enc)
    return "#".join(encodings)

def stringToList(string: str, kind):
    data = []
    if string == "":
        return list()
    encodings = string.split("#")
    for enc in encodings:
        val = kind(stringFromB64(enc))
        data.append(val)
    return data

def newHLine(width):
    hline = QFrame()
    hline.setFrameShape(QFrame.HLine) # type: ignore
    hline.setLineWidth(width)
    return hline

def newVLine(width):
    vline = QFrame()
    vline.setFrameShape(QFrame.VLine) # type: ignore
    vline.setLineWidth(width)
    return vline

def startfile(path):
    if sys.platform.startswith("linux"):
        os.system(f"xdg-open {path}")
    elif sys.platform.startswith("win"):
        os.startfile(path)
    else:
        os.system(f"open {path}")

def centerOnScreen(widget: QWidget):
    widget.adjustSize()
    screen = widget.screen()
    if screen is None:
        return
    geom = screen.availableGeometry()
    size = widget.size()
    x = geom.center().x() - size.width() // 2
    y = geom.center().y() - size.height() // 2
    widget.move(x, y)

def toQDate(date: datetime.date):
    return QDate(date.year, date.month, date.day)

def fromQDate(date: QDate):
    return datetime.date(date.year(), date.month(), date.day())