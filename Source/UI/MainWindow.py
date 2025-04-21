from PySide2 import QtWidgets, QtCore
from Source.UI.Item.EngineListWidget import EngineListWidget

class MainWindow(QtWidgets.QWidget):
    AddEngineRequested     = QtCore.Signal()
    BuildRequested         = QtCore.Signal()
    EngineCheckedChanged   = QtCore.Signal(str, bool)
    EngineOrderChanged     = QtCore.Signal(list)
    EngineEditRequested    = QtCore.Signal(int)
    EngineDeleteRequested  = QtCore.Signal(int)
    GlobalOptionChanged    = QtCore.Signal(str, dict)

    def __init__(self):
        super().__init__()
        self._BuildUi()

    def _BuildUi(self):
        self.setLayout(QtWidgets.QGridLayout())

        # 引擎列表（左侧）
        self.EngineView = EngineListWidget()
        LeftLayout = QtWidgets.QVBoxLayout()
        LeftLayout.addWidget(self.EngineView)

        BtnAddEngine = QtWidgets.QPushButton("➕ 添加引擎")
        BtnAddEngine.clicked.connect(lambda: self.AddEngineRequested.emit())
        LeftLayout.addWidget(BtnAddEngine)
        self.layout().addLayout(LeftLayout, 0, 0)

        # 插件选择 + Fab 设置（右侧）
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
                lambda _, K=Label, C=Checkbox:
                self.GlobalOptionChanged.emit("FabSettings", {K: C.isChecked()})
            )
            self.FabOptions[Label] = Checkbox
            LayoutFab.addWidget(Checkbox)
        RightLayout.addWidget(GroupFab)

        self.layout().addLayout(RightLayout, 0, 1)

        # 打包按钮（底部）
        BtnBuild = QtWidgets.QPushButton("🚀 开始打包")
        BtnBuild.setMinimumSize(240, 40)
        BtnBuild.clicked.connect(lambda: self.BuildRequested.emit())
        self.layout().addWidget(BtnBuild, 1, 0, 1, 2)

        # 信号转发
        self.EngineView.CheckedChanged.connect(self.EngineCheckedChanged.emit)
        self.EngineView.EditRequested.connect(self.EngineEditRequested.emit)
        self.EngineView.DeleteRequested.connect(self.EngineDeleteRequested.emit)
        self.EngineView.OrderChanged.connect(self.EngineOrderChanged.emit)

    def AddEngineItem(self, EngineData):
        self.EngineView.AddEngineItem(EngineData)
