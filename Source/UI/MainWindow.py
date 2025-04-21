from PySide2 import QtWidgets, QtCore
from PySide2.QtGui import QStandardItemModel, QStandardItem
from Source.UI.Item.AddEngineDialog import AddEngineDialog
from Source.UI.Item.EngineListView import EngineListView

class MainWindow(QtWidgets.QWidget):
    AddEngineRequested     = QtCore.Signal()
    BuildRequested         = QtCore.Signal()
    EngineCheckedChanged   = QtCore.Signal(str, bool)
    EngineOrderChanged     = QtCore.Signal(list)
    EngineEditRequested    = QtCore.Signal(int)
    EngineDeleteRequested  = QtCore.Signal(int)
    GlobalOptionChanged    = QtCore.Signal(str, dict)  # ✅ 改为 (SectionName, PatchDict)

    def __init__(self):
        super().__init__()
        self._BuildUi()

    def _BuildUi(self):
        self.setLayout(QtWidgets.QGridLayout())

        # 引擎列表
        self.EngineView = EngineListView()
        self.EngineModel = QStandardItemModel()
        self.EngineView.setModel(self.EngineModel)
        self.EngineView.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.EngineView.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.EngineModel.itemChanged.connect(self._OnEngineItemChanged)
        self.EngineView.OrderChanged.connect(self._EmitEngineOrderChanged)
        self.EngineView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.EngineView.customContextMenuRequested.connect(self._ShowContextMenu)

        LeftLayout = QtWidgets.QVBoxLayout()
        LeftLayout.addWidget(self.EngineView)
        ButtonAddEngine = QtWidgets.QPushButton("➕ 添加引擎")
        ButtonAddEngine.clicked.connect(lambda: self.AddEngineRequested.emit())
        LeftLayout.addWidget(ButtonAddEngine)
        self.layout().addLayout(LeftLayout, 0, 0)

        # 插件选择 + Fab 设置
        self.PluginBox = QtWidgets.QComboBox()
        self.FabOptions = {}
        FabLabels = [
            "转换MarketplaceURL为FabURL",
            "删除Binaries文件夹",
            "删除Intermediate文件夹",
            "拷贝项目README文件到插件",
            "拷贝项目LICENSE文件到插件",
            "拷贝项目Docs文件夹到插件",
            "为插件生成FilterPlugin.ini文件"
        ]

        RightLayout = QtWidgets.QVBoxLayout()
        RowPlugin = QtWidgets.QHBoxLayout()
        RowPlugin.addWidget(QtWidgets.QLabel("插件选择："))
        RowPlugin.addWidget(self.PluginBox)
        RightLayout.addLayout(RowPlugin)

        GroupFab = QtWidgets.QGroupBox("Fab格式化整理")
        LayoutFab = QtWidgets.QVBoxLayout(GroupFab)
        for Label in FabLabels:
            Checkbox = QtWidgets.QCheckBox(Label)
            Checkbox.stateChanged.connect(
                lambda _, K=Label, C=Checkbox: self.GlobalOptionChanged.emit("FabSettings", {K: C.isChecked()})
            )
            self.FabOptions[Label] = Checkbox
            LayoutFab.addWidget(Checkbox)
        RightLayout.addWidget(GroupFab)

        self.layout().addLayout(RightLayout, 0, 1)

        # 打包按钮
        ButtonBuild = QtWidgets.QPushButton("🚀 开始打包")
        ButtonBuild.setMinimumSize(240, 40)
        ButtonBuild.clicked.connect(lambda: self.BuildRequested.emit())
        self.layout().addWidget(ButtonBuild, 1, 0, 1, 2)

    def AddEngineItem(self, EngineData):
        Name = EngineData["Name"]
        Tag = "源码版" if EngineData.get("SourceBuild", False) else "Launcher"
        Item = QStandardItem(f"{Name} ({Tag})")
        Item.setEditable(False)
        Item.setCheckable(True)
        Item.setCheckState(QtCore.Qt.Checked if EngineData.get("Selected", True) else QtCore.Qt.Unchecked)
        self.EngineModel.appendRow(Item)

    def _OnEngineItemChanged(self, Item: QStandardItem):
        Name = Item.text().split(" ")[0]
        Checked = Item.checkState() == QtCore.Qt.Checked
        self.EngineCheckedChanged.emit(Name, Checked)

    def _EmitEngineOrderChanged(self):
        NameOrder = [self.EngineModel.item(Row).text().split(" ")[0]
                     for Row in range(self.EngineModel.rowCount())]
        self.EngineOrderChanged.emit(NameOrder)

    def _ShowContextMenu(self, Pos: QtCore.QPoint):
        Index = self.EngineView.indexAt(Pos)
        if not Index.isValid():
            return

        Row = Index.row()
        Menu = QtWidgets.QMenu(self)
        ActionEdit = Menu.addAction("编辑")
        ActionDelete = Menu.addAction("删除")
        Selected = Menu.exec_(self.EngineView.mapToGlobal(Pos))

        if Selected == ActionEdit:
            self.EngineEditRequested.emit(Row)
        elif Selected == ActionDelete:
            self.EngineDeleteRequested.emit(Row)
