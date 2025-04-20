# ✅ MainWindow.py（适配统一ConfigManager）

from PySide2 import QtWidgets
from PySide2.QtCore import Qt, QPoint
from PySide2.QtGui import QStandardItemModel, QStandardItem
import os
from Source.UI.AddEngineDialog import AddEngineDialog
from Source.Logic.ConfigManager import ConfigManager

class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.Layout = QtWidgets.QHBoxLayout(self)
        self.EngineListWidget = QtWidgets.QListView()
        self.EngineModel = QStandardItemModel()
        self.EngineListWidget.setModel(self.EngineModel)
        self.EngineModel.itemChanged.connect(self.OnEngineCheckChanged)

        self.PluginBox = QtWidgets.QComboBox()
        self.OutputEdit = QtWidgets.QLineEdit()
        self.CbWin64 = QtWidgets.QCheckBox("Win64")
        self.CbLinux = QtWidgets.QCheckBox("Linux")
        self.CbMac = QtWidgets.QCheckBox("Mac")
        self.FabOptions = {}

        self._BuildUI()

    def _BuildUI(self):
        LeftLayout = QtWidgets.QVBoxLayout()
        self.EngineListWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.EngineListWidget.customContextMenuRequested.connect(self.ShowEngineContextMenu)
        LeftLayout.addWidget(self.EngineListWidget)

        BtnAddEngine = QtWidgets.QPushButton("➕ 添加引擎")
        BtnAddEngine.clicked.connect(self.OnAddEngineClicked)
        LeftLayout.addWidget(BtnAddEngine)
        self.Layout.addLayout(LeftLayout, 2)

        RightLayout = QtWidgets.QVBoxLayout()

        PluginRow = QtWidgets.QHBoxLayout()
        PluginRow.addWidget(QtWidgets.QLabel("插件选择："))
        PluginRow.addWidget(self.PluginBox)
        RightLayout.addLayout(PluginRow)

        OutputRow = QtWidgets.QHBoxLayout()
        self.BtnChooseOutput = QtWidgets.QPushButton("选择输出")
        OutputRow.addWidget(QtWidgets.QLabel("输出目录："))
        OutputRow.addWidget(self.OutputEdit)
        OutputRow.addWidget(self.BtnChooseOutput)
        RightLayout.addLayout(OutputRow)

        PlatformGroup = QtWidgets.QGroupBox("目标平台选择")
        PlatformLayout = QtWidgets.QVBoxLayout(PlatformGroup)
        for cb in [self.CbWin64, self.CbLinux, self.CbMac]:
            PlatformLayout.addWidget(cb)
        RightLayout.addWidget(PlatformGroup)

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
            self.FabOptions[Label] = Checkbox
            FabLayout.addWidget(Checkbox)
        RightLayout.addWidget(FabGroup)

        for key, cb in zip(["Win64", "Linux", "Mac"], [self.CbWin64, self.CbLinux, self.CbMac]):
            cb.stateChanged.connect(lambda _, k=key, c=cb: self.SaveGlobalCheckbox(f"Platform.{k}", c))

        for Label, Checkbox in self.FabOptions.items():
            Checkbox.stateChanged.connect(lambda _, K=Label, C=Checkbox: self.SaveGlobalCheckbox(f"FabSettings.{K}", C))

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
        Selected = EngineData.get("Selected")
        if Selected is None:
            Selected = True
            config = ConfigManager()
            config.SetEngineField(Name, "Selected", True)
            config.Save()
        Item = QStandardItem(f"{Name} ({Tag})")
        Item.setEditable(False)
        Item.setCheckable(True)
        Item.setCheckState(Qt.Checked if Selected else Qt.Unchecked)
        self.EngineModel.appendRow(Item)
        return Item

    def OnEngineCheckChanged(self, item):
        name = item.text().split(" ")[0]
        checked = item.checkState() == Qt.Checked
        config = ConfigManager()
        config.SetEngineField(name, "Selected", checked)
        config.Save()

    def ShowEngineContextMenu(self, Pos: QPoint):
        Index = self.EngineListWidget.indexAt(Pos)
        if not Index.isValid():
            return

        Menu = QtWidgets.QMenu(self)
        ActionEdit = Menu.addAction("编辑")
        ActionDelete = Menu.addAction("删除")
        Action = Menu.exec_(self.EngineListWidget.mapToGlobal(Pos))
        Row = Index.row()

        Config = ConfigManager()
        Engines = Config.GetEngines()

        if Action == ActionEdit:
            Current = Engines[Row]
            Dialog = AddEngineDialog([e["Name"] for i, e in enumerate(Engines) if i != Row], self)
            Dialog.SetInitialData(Current["Name"], Current["Path"], Current["SourceBuild"])
            if Dialog.exec_() == QtWidgets.QDialog.Accepted:
                NewData = Dialog.GetResult()
                Engines[Row] = NewData
                Config.SetEngines(Engines)
                Config.Save()
                self.EngineModel.item(Row).setText(f"{NewData['Name']} ({'源码版' if NewData['SourceBuild'] else 'Launcher'})")

        elif Action == ActionDelete:
            self.EngineModel.removeRow(Row)
            Config.RemoveEngine(Engines[Row]["Name"])
            Config.Save()

    def SaveGlobalCheckbox(self, Key: str, Checkbox: QtWidgets.QCheckBox):
        config = ConfigManager()
        config.Set(Key, Checkbox.isChecked())
        config.Save()

    def LoadGlobalSettings(self):
        config = ConfigManager()
        self.OutputEdit.setText(config.Get("OutputPath", os.path.join(os.getcwd(), "Packaged")))
        self.CbWin64.setChecked(config.Get("Platform.Win64", True))
        self.CbLinux.setChecked(config.Get("Platform.Linux", False))
        self.CbMac.setChecked(config.Get("Platform.Mac", False))
        for Label, Checkbox in self.FabOptions.items():
            Checkbox.setChecked(config.Get(f"FabSettings.{Label}", True))