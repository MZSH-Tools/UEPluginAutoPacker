from PySide2 import QtWidgets, QtCore
from Source.UI.Item.EngineListWidget import EngineListWidget
from Source.Logic.Packaging import BuildOptions

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
            "自动添加版本信息",
            "自动添加版权声明",
            "转换MarketplaceURL为FabURL",
            "删除Intermediate文件夹",
            "拷贝项目README文件到插件",
            "拷贝项目Docs文件夹到插件",
            "自动生成FilterPlugin.ini"  # 文案更新 ✅
        ]

        RightLayout = QtWidgets.QVBoxLayout()
        RowPlugin = QtWidgets.QHBoxLayout()
        RowPlugin.addWidget(QtWidgets.QLabel("插件选择："))
        RowPlugin.addWidget(self.PluginBox)
        RightLayout.addLayout(RowPlugin)

        self.AutoZip = QtWidgets.QCheckBox('构建完成后自动压缩')
        self.AutoZip.setToolTip('生成源码 ZIP；是否保留构建目录由下级选项决定。ZIP 不包含本插件可重建的 DLL 和缓存，必要的第三方依赖保留。')
        RightLayout.addWidget(self.AutoZip)
        self.DeleteOutput = QtWidgets.QCheckBox('压缩完成后删除源码')
        self.DeleteOutput.setToolTip('ZIP 校验成功后，只删除该 ZIP 对应的引擎构建输出目录（包括源码、DLL 等），保留 ZIP；不会删除项目原始源码或其他版本输出。')
        DeleteLayout = QtWidgets.QHBoxLayout()
        DeleteLayout.addSpacing(24)
        DeleteLayout.addWidget(self.DeleteOutput)
        RightLayout.addLayout(DeleteLayout)
        self.AutoZip.toggled.connect(self._UpdateCompressionControls)
        self._UpdateCompressionControls(False)

        GroupFab = QtWidgets.QGroupBox("Fab格式化整理")
        LayoutFab = QtWidgets.QVBoxLayout(GroupFab)

        for Label in FabLabels:
            Text = '补齐 FabURL（保留 MarketplaceURL）' if Label == '转换MarketplaceURL为FabURL' else Label
            Checkbox = QtWidgets.QCheckBox(Text)
            Checkbox.setChecked(Label == '自动添加版本信息')
            if Label == '自动添加版本信息':
                Checkbox.setToolTip('从目标引擎读取版本并写入构建产物和 ZIP 的 EngineVersion，不修改原始插件描述符。')
            Checkbox.stateChanged.connect(
                lambda _, K=Label, C=Checkbox:
                self._OnFabOptionChanged(K, C)
            )
            self.FabOptions[Label] = Checkbox
            LayoutFab.addWidget(Checkbox)

        RightLayout.addWidget(GroupFab)
        self.layout().addLayout(RightLayout, 0, 1)

        # 打包按钮
        self.BtnBuild = QtWidgets.QPushButton('开始打包')
        self.BtnBuild.setMinimumHeight(40)
        self.BtnBuild.clicked.connect(lambda: self.BuildRequested.emit())
        self.layout().addWidget(self.BtnBuild, 1, 0, 1, 2)

        # 信号转发
        self.EngineView.CheckedChanged.connect(self.EngineCheckedChanged.emit)
        self.EngineView.EditRequested.connect(self.EngineEditRequested.emit)
        self.EngineView.DeleteRequested.connect(self.EngineDeleteRequested.emit)
        self.EngineView.OrderChanged.connect(self.EngineOrderChanged.emit)

    def GetBuildOptions(self):
        return BuildOptions('deploy', Zip=self.AutoZip.isChecked(),
                            DeleteOutput=self.AutoZip.isChecked() and self.DeleteOutput.isChecked(),
                            AddVersion=self.FabOptions['自动添加版本信息'].isChecked())

    def _UpdateCompressionControls(self, Enabled):
        self.DeleteOutput.setEnabled(Enabled)
        if not Enabled:
            self.DeleteOutput.setChecked(False)

    def _OnFabOptionChanged(self, Key, Checkbox):
        State = Checkbox.isChecked()
        self.GlobalOptionChanged.emit("FabSettings", {Key: State})

    def AddEngineItem(self, EngineData):
        self.EngineView.AddEngineItem(EngineData)
