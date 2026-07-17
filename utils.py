from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, QFrame
from PySide6.QtCore import QDate
import base64, os, sys, datetime, tempfile

def getComboBox(items: list[str], item):
    box = QComboBox()
    box.addItems(items)
    if item is not None:
        idx = box.findText(item)
        if idx < 0:
            # The stored value isn't among the current options — e.g. a part
            # referencing packaging whose kind changed, or a record edited while
            # its referent was removed. Append it so it stays visible and selected
            # (the user can see and correct it) instead of ValueError-ing on
            # items.index() or silently dropping the value.
            box.addItem(item)
            idx = box.count() - 1
        box.setCurrentIndex(idx)
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

def tempReportPath(prefix: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in prefix)
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"{safe}-")
    os.close(fd)
    return path

def centerOnScreen(widget: QWidget, adjustSize: bool = True):
    if adjustSize:
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

# Order sort modes shared by the Orders and Order Updates tabs (Step 69). The
# team sorts by due date or client name — deliberately never by order number.
ORDER_SORT_DUEDATE = "duedate"
ORDER_SORT_CLIENT = "client"
_ORDER_SORT_LABELS = [("Due date", ORDER_SORT_DUEDATE), ("Client name", ORDER_SORT_CLIENT)]

def orderSortCombo(mode: str) -> QComboBox:
    # A sort-mode selector preloaded with the shared order sort modes and set to
    # `mode`. The caller connects currentIndexChanged and reads currentData().
    box = QComboBox()
    for label, key in _ORDER_SORT_LABELS:
        box.addItem(label, key)
    idx = box.findData(mode)
    box.setCurrentIndex(idx if idx >= 0 else 0)
    return box

def orderSortKey(order, mode: str):
    # Sort key for an Order under the selected mode (Step 69). Client name is
    # case-insensitive; due date sorts undated orders last; orderNum breaks ties
    # so the order stays deterministic (matching the scheduler's tiebreak style).
    if mode == ORDER_SORT_CLIENT:
        return (order.client.casefold(), order.orderNum)
    return (order.dueDate is None, order.dueDate or datetime.date.max, order.orderNum)

def orderIsOpen(db, orderNum: str) -> bool:
    # Whether an order is still open, i.e. not yet fully shipped (Step 83). Shared
    # by the Orders and Order Status tabs' open-orders filter so the two agree
    # structurally. An order with no snapshot recorded yet is OPEN — None means
    # "nothing shipped so far", not "done" — matching the Order Status tab's
    # `status is not None and status.isFulfilled()` reading; a never-snapshotted
    # order must not vanish behind the filter.
    status = db.orderStatus.get(orderNum)
    return status is None or not status.isFulfilled()

def openOrdersCheck() -> QCheckBox:
    # The "Open orders only" filter toggle shared by the Orders and Order Status
    # tabs (Step 83). Default ON (team call 2026-07-17): the everyday view is the
    # outstanding orders; untick to include fulfilled history. The caller connects
    # toggled and re-filters via orderIsOpen.
    box = QCheckBox("Open orders only")
    box.setChecked(True)
    box.setToolTip(
        "Show only open orders (not yet fully shipped). An order with no status "
        "snapshot yet counts as open. Untick to show fulfilled orders too.")
    return box