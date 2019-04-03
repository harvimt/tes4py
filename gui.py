from PyQt5 import QtCore, QtWidgets
import sys
from tes4py import EspEsmFormat
esm = None

class RootNode:
    def __init__(self, esm):
        self.esm = esm
        self.parent = None

    def __len__(self):
        return len(self.esm.groups)

    def __getitem__(self, index)
        return GroupNode(self.esm.groups[index])

    def data(self):
        return '#ROOT#'

class GroupNode:
    def __init__(self, group, parent):
        self.parent = parent
        self.group = group

    def __len__(self):
        return len(self.group.records)

    def __getitem__(self, index):
        return self.group.records[index]

    def data(self):
        return self.group.label

class RecordNode:
    def __init__(self, record, parent):
        self.group = record
        self.parent = parent

class ClotTableModel(QtCore.QAbstractItemModel):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._root_node = RootNode(esm)
        self._root_idx = self.createIndex(0, 0, self._root_node)

    def index(self, row, col, parent=ROOT):
        if not parent or not parent.isValid():
            parent = self._root_node
        else:
            parent = in_parent.internalPointer()

        if not super().hasIndex(row, col, parent):
            return QtCore.QModelIndex()

        return self.createIndex(row, col, parent)

    def parent(self, index):
        if not index or not index.isValid():
            return QtCore.QModelIndex()
        elif index.internalPointer() is ROOT:
            return QtCore.QModelIndex()
        elif index.internalPointer() is GROUP:
            return self._root_idx

        return self.createIndex(p.row(), 0, p)

    def rowCount(self, parent):
        if not parent or not parent.isValid():
            return 1
        elif parent.internalPointer() is ROOT:
            return len(esm.groups)
        elif True:
            return len(esm.groups[parent.row()].records)
        else:
           return 0

    def columnCount(self, parent):
        if not parent or not parent.isValid():
            return 0
        elif parent.internalPointer() is ROOT:
            return 1
        elif parent.internalPointer() is GROUP:
            return 1
        else:
            return 0

    def data(self, index, role):
        global esm
        if role == QtCore.Qt.DisplayRole:
            if index.parent() == QtCore.QModelIndex():
                # root of tree
                return esm.groups[index.row()].label
            else:
                group = esm.groups[index.parent().row()]
                record = group.records[index.row()]
            try:
                return record['FULL'].zstring
            except KeyError:
                return '#NO NAME#'
        pass


if __name__ == '__main__':
    esm = EspEsmFormat('E:/HDSteamLib/steamapps/common/Oblivion/data/Oblivion.esm')
    with esm:
        app = QtWidgets.QApplication(sys.argv)
        mdl = ClotTableModel()
        tbl = QtWidgets.QTreeView()
        tbl.setModel(mdl)
        tbl.show()
        #win = QtWidgets.QLabel(text="foobar")
        #win.show()
        app.exec()