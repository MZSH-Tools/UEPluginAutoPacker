from PySide2.QtWidgets import QListWidget, QListWidgetItem
from PySide2.QtCore import Signal, Qt
from Source.UI.Item.EngineItemWidget import EngineItemWidget

class EngineListWidget(QListWidget):
    CheckedChanged = Signal(str, bool)
    EditRequested = Signal(int)
    DeleteRequested = Signal(int)
    OrderChanged = Signal(list)  # 拖拽顺序（名称列表）

    def __init__(self, Parent=None):
        super().__init__(Parent)
        self.setDragDropMode(self.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)

    def AddEngineItem(self, EngineData):
        Name = EngineData["Name"]
        SourceBuild = EngineData.get("SourceBuild", False)
        Checked = EngineData.get("Selected", True)

        Widget = EngineItemWidget(Name, SourceBuild, Checked)
        Item = QListWidgetItem()
        Item.setSizeHint(Widget.sizeHint())

        self.addItem(Item)
        self.setItemWidget(Item, Widget)

        Index = self.count() - 1
        Widget.CheckedChanged.connect(lambda State, N=Name: self.CheckedChanged.emit(N, State))
        Widget.EditClicked.connect(lambda I=Index: self.EditRequested.emit(I))
        Widget.DeleteClicked.connect(lambda I=Index: self.DeleteRequested.emit(I))

    def ClearAll(self):
        self.clear()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.OrderChanged.emit(self.GetEngineOrder())

    def GetEngineOrder(self):
        Order = []
        for i in range(self.count()):
            Widget = self.itemWidget(self.item(i))
            Order.append(Widget.GetName())
        return Order
