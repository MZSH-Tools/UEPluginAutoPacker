from PySide2.QtWidgets import QListView
from PySide2.QtCore import Signal
from PySide2.QtGui import QDropEvent

class EngineListView(QListView):
    OrderChanged = Signal()

    def dropEvent(self, event: QDropEvent):
        super().dropEvent(event)
        self.OrderChanged.emit()
