from PySide2.QtWidgets import QWidget, QHBoxLayout, QCheckBox, QLabel, QPushButton
from PySide2.QtCore import Signal

class EngineItemWidget(QWidget):
    CheckedChanged = Signal(bool)
    EditClicked = Signal()
    DeleteClicked = Signal()

    def __init__(self, Name, SourceBuild, Checked=True, Parent=None):
        super().__init__(Parent)
        Layout = QHBoxLayout(self)
        Layout.setContentsMargins(6, 2, 6, 2)

        self.CheckBox = QCheckBox()
        self.CheckBox.setChecked(Checked)
        self.CheckBox.stateChanged.connect(lambda State: self.CheckedChanged.emit(State == 2))

        self.Label = QLabel(f"{Name} ({'源码版' if SourceBuild else 'Launcher'})")

        BtnEdit = QPushButton("编辑")
        BtnEdit.setFixedSize(60, 28)  # ✅ 放大按钮
        BtnEdit.clicked.connect(self.EditClicked.emit)

        BtnDelete = QPushButton("删除")
        BtnDelete.setFixedSize(60, 28)  # ✅ 放大按钮
        BtnDelete.clicked.connect(self.DeleteClicked.emit)

        Layout.addWidget(self.CheckBox)
        Layout.addWidget(self.Label)
        Layout.addStretch()
        Layout.addWidget(BtnEdit)
        Layout.addWidget(BtnDelete)

    def GetName(self):
        return self.Label.text().split(" ")[0]

    def SetChecked(self, Checked: bool):
        self.CheckBox.setChecked(Checked)

    def IsChecked(self) -> bool:
        return self.CheckBox.isChecked()
