from PySide6.QtCore import QAbstractTableModel, QItemSelection, Qt
from PySide6.QtWidgets import QTableView, QWidget

class DBTableModel(QAbstractTableModel):
    def __init__(self, data, headers):
        super(DBTableModel, self).__init__()
        self._data = data
        self.headers = headers

    def data(self, index, role): # type: ignore
        if role == Qt.DisplayRole: # type: ignore
            # See below for the nested-list data structure.
            # .row() indexes into the outer list,
            # .column() indexes into the sub-list
            return self._data[index.row()][index.column()]

    def rowCount(self, index): # type: ignore
        # The length of the outer list.
        return len(self._data)

    def columnCount(self, index): # type: ignore
        # The following takes the first sub-list, and returns
        # the length (only works if all rows are an equal length)
        return len(self.headers)
    
    def headerData(self, section, orientation, role): # type: ignore
        # section is the index of the column/row.
        if role == Qt.DisplayRole: # type: ignore
            if orientation == Qt.Horizontal: # type: ignore
                return str(self.headers[section])

            if orientation == Qt.Vertical: # type: ignore
                return str(section)
    
    def setData(self, data): # type: ignore
        self.beginResetModel()
        self._data = data
        self.endResetModel()

class DBTable(QTableView):
    def __init__(self, data, headers) -> None:
        super().__init__()
        self.parentTab = None
        self.dbModel = DBTableModel(data, headers)
        self.setModel(self.dbModel)
        self.selector = self.selectionModel()
        self.selector.selectionChanged.connect(self.onSelect)
    
    def setData(self, data):
        self.dbModel.setData(data)
    
    def onSelect(self, selected: QItemSelection, deselected):
        selection = []
        for ind in selected.indexes():
            row = ind.row()
            selection.append(self.dbModel._data[row][0])
        if not self.parentTab == None:
            self.parentTab.setSelection(list(dict.fromkeys(selection)))