"""Reusable delegate-based preference grid (MERGE_PLAN.md Step 64).

A spreadsheet-style grid for scoring one set of entities (the rows) against the
registered presses (the columns). Each score cell is a "Not set / 1-5" drop-down
opened on click via a `QStyledItemDelegate` — the app's first in-cell-editing
pattern. The design call (2026-07-02) was a click-to-open delegate rather than a
persistent combo box in every cell: the real DB has ~165 parts, so hundreds of
always-live widgets would be heavy, whereas the delegate scales and reads like a
spreadsheet.

Cells carry a green->amber->red heat-map fill so "5 = most preferred" reads at a
glance; "Not set" is a plain gray tint with no numeral, so an unset cell is
visibly distinct from an explicit 3 (even though the scheduler treats both as the
neutral midpoint — see `scheduling._prefScore`).

Dark-mode note: the five heat fills are fixed *semantic* colours (green..red), and
the numeral drawn on them is a fixed dark colour chosen to stay legible on all five
fills in both the light and dark system themes. The rest of the chrome — headers,
gridlines, the "Not set" tint, and the legend's swatch borders — is drawn from the
active Qt palette so it tracks the system theme the way `style.py` (Step 63) does.

The widget is generic over the row entity so Step 65's Presser->Press grid reuses
it unchanged: the owning tab supplies the row keys + labels, the press columns, and
a `getScore(rowKey, press) -> int | None` / `setScore(rowKey, press, int | None)`
callback pair onto its own db collection. It mirrors `table.DBTable`'s duck-typed
contract (`dbModel._data`, `setData`, `parentTab` + `onSelect`) so the Step 55
stale-view net and the crash fuzzer treat it exactly like the flat CRUD tables.
"""

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QItemSelection, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QStyledItemDelegate,
    QTableView,
    QWidget,
)

from records.scheduling import MAX_PRESS_SCORE, MIN_PRESS_SCORE

# The unscored option's label. "Not set" reads as "no preference recorded" — a
# rename of the old "Neutral" (Step 64), chosen so it's distinct from an explicit
# 3 even though both schedule as neutral. Stored as None / no row, unchanged.
NOT_SET_TEXT = "Not set"

# Drop-down choices, in combo order: "Not set" then the 1..5 scores. A numeric
# choice maps to that int; "Not set" maps to None (clears the pair to no row).
SCORE_CHOICES = [NOT_SET_TEXT] + [str(s) for s in range(MIN_PRESS_SCORE, MAX_PRESS_SCORE + 1)]

# Fixed heat-map fills: 5 (most preferred) green -> 3 amber -> 1 (least) red. Kept
# light enough that the fixed dark numeral below stays legible on every fill in
# both light and dark mode (see module docstring).
_HEAT_HEX = {1: "#ef5350", 2: "#ff8a65", 3: "#ffca28", 4: "#9ccc65", 5: "#66bb6a"}
_SCORE_TEXT_HEX = "#1a1a1a"

# "Not set" tint: a low-alpha gray that blends over whatever cell background the
# palette provides, so it reads as a faint neutral in both themes without picking
# a fixed light-or-dark gray.
_NOT_SET_RGBA = (128, 128, 128, 60)


class ScoreDelegate(QStyledItemDelegate):
    """In-cell editor for a score column: a click opens a "Not set / 1-5" combo
    box; the choice is written straight back through the model's `setData`, which
    calls the owning tab's `setScore` callback. No persistent widgets — the editor
    exists only while a cell is being edited."""

    def createEditor(self, parent, option, index) -> QComboBox:
        combo = QComboBox(parent)
        combo.addItems(SCORE_CHOICES)
        return combo

    def setEditorData(self, editor, index) -> None:
        if not isinstance(editor, QComboBox):
            return
        score = index.data(Qt.ItemDataRole.EditRole)
        text = NOT_SET_TEXT if score is None else str(score)
        pos = editor.findText(text)
        editor.setCurrentIndex(pos if pos >= 0 else 0)

    def setModelData(self, editor, model, index) -> None:
        if not isinstance(editor, QComboBox):
            return
        text = editor.currentText()
        score = None if text == NOT_SET_TEXT else int(text)
        model.setData(index, score, Qt.ItemDataRole.EditRole)


class PrefGridModel(QAbstractTableModel):
    """Editable score matrix. Column 0 is the row label (the part / presser name,
    non-editable); columns 1..N are the presses, each holding a score (1..5) or
    None for "Not set". `_data` mirrors `table.DBTableModel._data` (a list of rows,
    the row label at index 0) so the stale-view net compares it the same way."""

    def __init__(self, rowKeys, headers, data, pressNames, getScore, setScore) -> None:
        super().__init__()
        self.rowKeys = list(rowKeys)      # row entity keys, parallel to _data rows
        self.headers = list(headers)      # ["<Row label>", press0, press1, ...]
        self._data = data                 # [[label, score|None, score|None, ...], ...]
        self.pressNames = list(pressNames)  # column 1..N press names
        self._getScore = getScore
        self._setScore = setScore
        self.notSetBrush = QBrush(QColor(*_NOT_SET_RGBA))
        self.heatBrushes = {s: QBrush(QColor(h)) for s, h in _HEAT_HEX.items()}
        self.scoreTextBrush = QBrush(QColor(_SCORE_TEXT_HEX))

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        # Drive off the row width so a transient headers/_data desync can't index
        # past the data (the net's value-only setData only ever runs same-shape).
        return len(self._data[0]) if self._data else len(self.headers)

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
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            return self.notSetBrush if value is None else self.heatBrushes.get(value)
        if role == Qt.ItemDataRole.ForegroundRole:
            return None if value is None else self.scoreTextBrush
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self.headers[section]) if section < len(self.headers) else ""
        return str(section)

    def flags(self, index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() >= 1:
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        # value is None ("Not set") or an int score, straight from ScoreDelegate.
        if role != Qt.ItemDataRole.EditRole or index.column() < 1:
            return False
        row, col = index.row(), index.column()
        self._data[row][col] = value
        self._setScore(self.rowKeys[row], self.pressNames[col - 1], value)
        self.dataChanged.emit(index, index)
        return True

    def setMatrix(self, data) -> None:
        # Value-only swap (same shape) — the Step 55 net's resync path.
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def rebuild(self, rowKeys, headers, data) -> None:
        # Structural rebuild when the parts/presses set changes (add/rename/delete).
        self.beginResetModel()
        self.rowKeys = list(rowKeys)
        self.headers = list(headers)
        self._data = data
        self.pressNames = list(headers[1:])
        self.endResetModel()


class PrefGrid(QTableView):
    """The grid view. Mirrors `table.DBTable`'s duck-typed contract so the owning
    tab, the stale-view net, and the fuzzer treat it like any CRUD table: it
    exposes `dbModel` (with `_data`), a `setData(rows)` value swap, and calls
    `parentTab.setSelection(list)` on row selection."""

    def __init__(self, rowKeys, headers, data, pressNames, getScore, setScore) -> None:
        super().__init__()
        self.parentTab: Any = None
        self.dbModel = PrefGridModel(rowKeys, headers, data, pressNames, getScore, setScore)
        self.setModel(self.dbModel)
        self.scoreDelegate = ScoreDelegate(self)
        self.setItemDelegate(self.scoreDelegate)
        # Click-to-open: a click on the current (selected) cell, a double-click, or
        # F2 opens the drop-down. Column 0 isn't editable (flags), so the delegate
        # never opens on the label column.
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

    def rebuild(self, rowKeys, headers, data) -> None:
        self.dbModel.rebuild(rowKeys, headers, data)

    def onSelect(self, selected: QItemSelection, _deselected) -> None:
        selection = []
        for ind in selected.indexes():
            selection.append(self.dbModel._data[ind.row()][0])
        if self.parentTab is not None:
            self.parentTab.setSelection(list(dict.fromkeys(selection)))


def _swatch(text: str, fill: str) -> QLabel:
    """A small fixed-size colour swatch for the legend. `fill` is any CSS colour
    (a heat hex or an rgba(...) for 'Not set'); the border uses palette(mid) so it
    reads on both themes (per style.py)."""
    lab = QLabel(text)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lab.setFixedSize(24, 22)
    lab.setStyleSheet(
        f"background-color: {fill}; color: {_SCORE_TEXT_HEX};"
        " border: 1px solid palette(mid); border-radius: 3px;"
    )
    return lab


def makeHeatLegend(parent=None) -> QWidget:
    """A horizontal legend for the heat map: a "Not set" swatch, then Least (1,
    red) -> Most (5, green). Swatch fills are the fixed heat colours; the caption
    text is plain `QLabel`s so it follows the palette in light/dark mode."""
    widget = QWidget(parent)
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(_swatch("", f"rgba({_NOT_SET_RGBA[0]}, {_NOT_SET_RGBA[1]}, "
                              f"{_NOT_SET_RGBA[2]}, {_NOT_SET_RGBA[3] / 255:.2f})"))
    row.addWidget(QLabel("Not set"))
    row.addSpacing(16)
    row.addWidget(QLabel("Least"))
    for score in range(MIN_PRESS_SCORE, MAX_PRESS_SCORE + 1):
        row.addWidget(_swatch(str(score), _HEAT_HEX[score]))
    row.addWidget(QLabel("Most preferred"))
    row.addStretch(1)
    return widget
