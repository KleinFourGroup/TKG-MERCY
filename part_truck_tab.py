"""Parts-per-truck config grid (MERGE_PLAN.md Step 74a).

A single-value editable grid: one row per part (every part in db.parts, so a part
with no figure shows a blank cell — the "show all parts, blank = unset" design
call), one "Parts per truck" column whose cell is a click-to-open integer entry.
A value is written straight through Database.setPartTruck; clearing the cell (blank)
deletes the part's row back to unset. The figure is a data-entry convenience the
Order Status trucks-mode input (Step 74b) multiplies a remaining-in-trucks figure by
to store pieces — everything stays stored + displayed in pieces.

Mirrors table.DBTable's duck-typed contract (dbModel._data, setData, parentTab +
onSelect) so the Step 55 stale-view net and the crash fuzzer treat it like the flat
CRUD tables, the same way pref_grid.PrefGrid does. A separate small widget rather
than a reuse of PrefGrid: that grid is a 1-5 score drop-down with a heat map across N
press columns, which doesn't fit a single free-integer column. Lives under
"Production and Scheduling" -> "Scheduling config" -> "Parts per Truck".
"""

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel, QItemSelection, QModelIndex, QRegularExpression, Qt,
)
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app import MainWindow


class TruckValueDelegate(QStyledItemDelegate):
    """In-cell editor for the parts-per-truck column: a click opens a digits-only
    QLineEdit; committing an empty field clears the value back to unset (no row). No
    persistent widgets — the editor exists only while a cell is being edited (the
    pref_grid pattern)."""

    def createEditor(self, parent, option, index) -> QLineEdit:
        edit = QLineEdit(parent)
        # Digits only, and — crucially — the empty string must stay *acceptable* so
        # the cell can be cleared back to unset. A QIntValidator with a minimum of 1
        # marks an empty field unacceptable, and Qt's delegate then refuses to commit
        # the blank (silently reverting to the old value); an all-digits regex that
        # matches the empty string avoids that. Up to 7 digits keeps the figure sane
        # without a hard business cap; a non-positive parse is cleared in setModelData.
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9]{0,7}"), edit))
        return edit

    def setEditorData(self, editor, index) -> None:
        if not isinstance(editor, QLineEdit):
            return
        value = index.data(Qt.ItemDataRole.EditRole)
        editor.setText("" if value is None else str(value))

    def setModelData(self, editor, model, index) -> None:
        if not isinstance(editor, QLineEdit):
            return
        text = editor.text().strip()
        # Empty (or a non-positive parse the validator let through as intermediate)
        # clears the figure back to unset; a truck of 0 pieces is meaningless.
        value = int(text) if text else None
        if value is not None and value < 1:
            value = None
        model.setData(index, value, Qt.ItemDataRole.EditRole)


class PartTruckModel(QAbstractTableModel):
    """Editable per-part parts-per-truck table. Column 0 is the part name
    (non-editable); column 1 holds the integer figure or None (unset). `_data`
    mirrors table.DBTableModel._data (a list of [part, value|None] rows) so the
    stale-view net compares it the same way."""

    HEADERS = ["Part", "Parts per truck"]

    def __init__(self, data, setValue) -> None:
        super().__init__()
        self._data = data                 # [[part, value|None], ...]
        self._setValue = setValue

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        value = self._data[index.row()][index.column()]
        if index.column() == 0:
            return str(value) if role == Qt.ItemDataRole.DisplayRole else None
        if role == Qt.ItemDataRole.EditRole:
            return value  # raw None / int for the delegate to prefill from
        if role == Qt.ItemDataRole.DisplayRole:
            return "" if value is None else str(value)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section] if section < len(self.HEADERS) else ""
        return str(section)

    def flags(self, index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 1:
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        # value is None (unset) or a positive int, straight from TruckValueDelegate.
        if role != Qt.ItemDataRole.EditRole or index.column() != 1:
            return False
        row = index.row()
        self._data[row][1] = value
        self._setValue(self._data[row][0], value)
        self.dataChanged.emit(index, index)
        return True

    def setMatrix(self, data) -> None:
        # Full row-list swap — the parts set (rows) can change under us via
        # add/rename/delete elsewhere; the columns are fixed so no header rebuild.
        self.beginResetModel()
        self._data = data
        self.endResetModel()


class PartTruckGrid(QTableView):
    """The grid view. Mirrors table.DBTable's duck-typed contract (dbModel with
    _data, setData(rows) swap, parentTab + onSelect) so the owning tab, the
    stale-view net, and the fuzzer treat it like any CRUD table."""

    def __init__(self, data, setValue) -> None:
        super().__init__()
        self.parentTab: Any = None
        self.dbModel = PartTruckModel(data, setValue)
        self.setModel(self.dbModel)
        self.valueDelegate = TruckValueDelegate(self)
        self.setItemDelegate(self.valueDelegate)
        # Click-to-open: a click on the current (selected) cell, a double-click, or F2
        # opens the editor. Column 0 isn't editable (flags), so it never opens there.
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.selector = self.selectionModel()
        if self.selector is not None:
            self.selector.selectionChanged.connect(self.onSelect)

    def setData(self, data) -> None:
        self.dbModel.setMatrix(data)

    def onSelect(self, selected: QItemSelection, _deselected) -> None:
        selection = []
        for ind in selected.indexes():
            selection.append(self.dbModel._data[ind.row()][0])
        if self.parentTab is not None:
            self.parentTab.setSelection(list(dict.fromkeys(selection)))


class PartTruckTab(QWidget):
    # Interactive parts-per-truck grid (Step 74a). Rows are parts, the single value
    # column is a click-to-open integer entry set directly in-grid (no edit window);
    # values are written straight through Database.setPartTruck, so a blank cell
    # clears the part back to unset (no row). Feeds the Step 74b trucks-mode order
    # entry. Lives under "Production and Scheduling" -> "Scheduling config" ->
    # "Parts per Truck".
    def __init__(self, mainApp: MainWindow) -> None:
        super().__init__()
        self.mainApp = mainApp
        self.selection = []
        self.genTableData()
        self.table = PartTruckGrid(self.data, self._setValue)
        self.table.parentTab = self  # type: ignore

        caption = QLabel(
            "How many finished pieces fill one truck, per part. Used by the Order "
            "Status \"Enter in trucks\" option to convert a trucks figure to pieces "
            "(everything is still stored and shown in pieces). Leave a cell blank for "
            "no truck size. Click a cell to edit."
        )
        caption.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(caption)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def _setValue(self, part, value):
        self.mainApp.db.setPartTruck(part, value)

    def genTableData(self):
        # One row per part (all parts, sorted): the part name in column 0, its
        # parts-per-truck figure (or None for unset) in column 1. Kept in sync with
        # the grid so the Step 55 stale-view net can diff self.data directly.
        db = self.mainApp.db
        self.rowKeys = sorted(db.parts)
        self.data = []
        for part in self.rowKeys:
            truck = db.partTruck.get(part)
            self.data.append([part, truck.partsPerTruck if truck is not None else None])

    def setSelection(self, selection):
        self.selection = selection

    def refreshTable(self):
        # Parts (the rows) can change under us via renames / deletes elsewhere; the
        # columns are fixed, so a row-list swap suffices (no structural rebuild).
        self.genTableData()
        self.table.setData(self.data)
        self.selection = [part for part in self.selection if part in self.mainApp.db.parts]
