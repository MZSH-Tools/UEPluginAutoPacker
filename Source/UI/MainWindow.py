from PySide2 import QtWidgets
from PySide2.QtCore import Qt, QPoint
from PySide2.QtGui import QStandardItemModel, QStandardItem
import os
from Source.UI.AddEngineDialog import AddEngineDialog
from Source.Logic.EngineManager import EngineManager

class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.Layout = QtWidgets.QHBoxLayout(self)
        self.EngineListWidget = QtWidgets.QListView()
        self.EngineModel = QStandardItemModel()
        self.EngineListWidget.setModel(self.EngineModel)

        self.PluginBox = QtWidgets.QComboBox()
        self.OutputEdit = QtWidgets.QLineEdit()
        self.CbWin64 = QtWidgets.QCheckBox("Win64")
        self.CbLinux = QtWidgets.QCheckBox("Linux")
        self.CbMac = QtWidgets.QCheckBox("Mac")
        self.FabOptions = {}

        self._BuildUI()

    def _BuildUI(self):
        # 左侧：引擎列表 + 添加按钮
        LeftLayout = QtWidgets.QVBoxLayout()
        self.EngineListWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.EngineListWidget.customContextMenuRequested.connect(self.ShowEngineContextMenu)
        LeftLayout.addWidget(self.EngineListWidget)

        BtnAddEngine = QtWidgets.QPushButton("➕ 添加引擎")
        BtnAddEngine.clicked.connect(self.OnAddEngineClicked)
        LeftLayout.addWidget(BtnAddEngine)
        self.Layout.addLayout(LeftLayout, 2)

        # 右侧设置
        RightLayout = QtWidgets.QVBoxLayout()

        # 插件选择
        PluginRow = QtWidgets.QHBoxLayout()
        PluginRow.addWidget(QtWidgets.QLabel("插件选择："))
        PluginRow.addWidget(self.PluginBox)
        RightLayout.addLayout(PluginRow)

        # 输出路径
        OutputRow = QtWidgets.QHBoxLayout()
        self.BtnChooseOutput = QtWidgets.QPushButton("选择输出")
        OutputRow.addWidget(QtWidgets.QLabel("输出目录："))
        OutputRow.addWidget(self.OutputEdit)
        OutputRow.addWidget(self.BtnChooseOutput)
        RightLayout.addLayout(OutputRow)

        # 平台选择
        PlatformGroup = QtWidgets.QGroupBox("目标平台选择")
        PlatformLayout = QtWidgets.QVBoxLayout(PlatformGroup)
        self.CbWin64.setChecked(True)
        for cb in [self.CbWin64, self.CbLinux, self.CbMac]:
            PlatformLayout.addWidget(cb)
        RightLayout.addWidget(PlatformGroup)

        # Fab格式化整理
        FabGroup = QtWidgets.QGroupBox("Fab格式化整理")
        FabLayout = QtWidgets.QVBoxLayout(FabGroup)
        OptionLabels = [
            "转换MarketplaceURL为FabURL",
            "删除Binaries文件夹",
            "删除Intermediate文件夹",
            "拷贝项目README文件到插件",
            "拷贝项目LICENSE文件到插件",
            "拷贝项目Docs文件夹到插件",
            "为插件生成FilterPlugin.ini文件"
        ]
        for Label in OptionLabels:
            Checkbox = QtWidgets.QCheckBox(Label)
            Checkbox.setChecked(True)
            self.FabOptions[Label] = Checkbox
            FabLayout.addWidget(Checkbox)
        RightLayout.addWidget(FabGroup)

        self.BtnBuild = QtWidgets.QPushButton("开始打包")
        RightLayout.addWidget(self.BtnBuild)
        RightLayout.addStretch()
        self.Layout.addLayout(RightLayout, 3)

    def BindCallbacks(self, OnAddEngine=None, OnBuild=None, OnChooseOutput=None):
        self.OnAddEngine = OnAddEngine
        self.BtnBuild.clicked.connect(OnBuild)
        self.BtnChooseOutput.clicked.connect(OnChooseOutput)

    def OnAddEngineClicked(self):
        if self.OnAddEngine:
            self.OnAddEngine()

    def AddEngineItem(self, EngineData):
        Name = EngineData["Name"]
        Tag = "源码版" if EngineData["SourceBuild"] else "Launcher"
        Item = QStandardItem(f"{Name} ({Tag})")
        Item.setEditable(False)
        Item.setCheckable(True)
        Item.setCheckState(Qt.Checked)
        self.EngineModel.appendRow(Item)

    def ShowEngineContextMenu(self, Pos: QPoint):
        Index = self.EngineListWidget.indexAt(Pos)
        if not Index.isValid():
            return

        Menu = QtWidgets.QMenu(self)
        ActionEdit = Menu.addAction("编辑")
        ActionDelete = Menu.addAction("删除")
        Action = Menu.exec_(self.EngineListWidget.mapToGlobal(Pos))
        Row = Index.row()

        Engines = EngineManager().GetEngines()

        if Action == ActionEdit:
            Current = Engines[Row]
            Dialog = AddEngineDialog([e["Name"] for i, e in enumerate(Engines) if i != Row], self)
            Dialog.SetInitialData(Current["Name"], Current["Path"], Current["SourceBuild"])

            if Dialog.exec_() == QtWidgets.QDialog.Accepted:
                NewData = Dialog.GetResult()
                Engines[Row] = NewData
                Tag = "源码版" if NewData["SourceBuild"] else "Launcher"
                self.EngineModel.item(Row).setText(f"{NewData['Name']} ({Tag})")
                EngineManager().Save()

        elif Action == ActionDelete:
            self.EngineModel.removeRow(Row)
            EngineManager().RemoveEngine(Engines[Row]["Name"])

# ✅ 自测试入口
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    window = QtWidgets.QMainWindow()
    ui = MainWindow()
    window.setCentralWidget(ui)
    window.resize(1000, 600)
    window.setWindowTitle("MainWindow 测试")
    # 添加测试数据
    from Source.Logic.EngineManager import EngineManager
    for engine in EngineManager().GetEngines():
        ui.AddEngineItem(engine)
    window.show()
    sys.exit(app.exec_())
