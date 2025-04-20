from PySide2 import QtWidgets
from PySide2.QtCore import Qt, QPoint
from PySide2.QtGui import QStandardItemModel, QStandardItem
from Source.UI.Item.AddEngineDialog import AddEngineDialog
from Source.UI.Item.EngineListView import EngineListView
from Source.Logic.ConfigManager import ConfigManager

class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.Layout = QtWidgets.QGridLayout(self)
        self.EngineListWidget = EngineListView()
        self.EngineListWidget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.EngineListWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.EngineModel = QStandardItemModel()
        self.EngineListWidget.setModel(self.EngineModel)
        self.EngineModel.itemChanged.connect(self.OnEngineCheckChanged)
        self.EngineListWidget.OrderChanged.connect(self.UpdateEngineOrder)
        self.EngineListWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.EngineListWidget.customContextMenuRequested.connect(self.ShowEngineContextMenu)

        self.PluginBox = QtWidgets.QComboBox()
        self.CbWin64 = QtWidgets.QCheckBox("Win64")
        self.CbLinux = QtWidgets.QCheckBox("Linux")
        self.CbMac = QtWidgets.QCheckBox("Mac")
        self.BtnBuild = QtWidgets.QPushButton("🚀 开始打包")
        self.FabOptions = {}

        self._BuildUI()

    def _BuildUI(self):
        LeftLayout = QtWidgets.QVBoxLayout()
        LeftLayout.addWidget(self.EngineListWidget)
        BtnAddEngine = QtWidgets.QPushButton("➕ 添加引擎")
        BtnAddEngine.clicked.connect(self.OnAddEngineClicked)
        LeftLayout.addWidget(BtnAddEngine)
        self.Layout.addLayout(LeftLayout, 0, 0)

        RightLayout = QtWidgets.QVBoxLayout()
        RightLayout.setSpacing(8)
        RightLayout.setAlignment(Qt.AlignTop)

        PluginRow = QtWidgets.QHBoxLayout()
        PluginRow.addWidget(QtWidgets.QLabel("插件选择："))
        PluginRow.addWidget(self.PluginBox)
        RightLayout.addLayout(PluginRow)

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

        self.Layout.addLayout(RightLayout, 0, 1)

        BottomLayout = QtWidgets.QHBoxLayout()
        BottomLayout.setContentsMargins(10, 10, 10, 10)
        BottomLayout.addWidget(self.BtnBuild)
        self.BtnBuild.setMinimumWidth(240)
        self.BtnBuild.setMinimumHeight(40)
        self.BtnBuild.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.Layout.addLayout(BottomLayout, 1, 0, 1, 2)

    def BindCallbacks(self, OnAddEngine=None, OnBuild=None, OnChooseOutput=None):
        self.OnAddEngine = OnAddEngine
        self.BtnBuild.clicked.connect(OnBuild)

    def AddEngineItem(self, EngineData) -> QStandardItem:
        name = EngineData["Name"]
        tag = "源码版" if EngineData.get("SourceBuild", False) else "Launcher"
        item = QStandardItem(f"{name} ({tag})")
        item.setEditable(False)
        item.setCheckable(True)
        item.setCheckState(Qt.Checked if EngineData.get("Selected", True) else Qt.Unchecked)
        self.EngineModel.appendRow(item)
        return item

    def OnAddEngineClicked(self):
        if self.OnAddEngine:
            self.OnAddEngine()

    def OnEngineCheckChanged(self, item: QStandardItem):
        name = item.text().split(" ")[0]
        checked = item.checkState() == Qt.Checked
        config = ConfigManager()
        config.SetEngineField(name, "Selected", checked)
        config.Save()

    def ShowEngineContextMenu(self, Pos: QPoint):
        index = self.EngineListWidget.indexAt(Pos)
        if not index.isValid():
            return
        row = index.row()
        item = self.EngineModel.item(row)
        name = item.text().split(" ")[0]
        config = ConfigManager()
        engines = config.GetEngines()

        menu = QtWidgets.QMenu(self)
        actionEdit = menu.addAction("编辑")
        actionDelete = menu.addAction("删除")
        selected = menu.exec_(self.EngineListWidget.mapToGlobal(Pos))

        if selected == actionEdit:
            current = engines[row]
            dialog = AddEngineDialog([e["Name"] for i, e in enumerate(engines) if i != row], self)
            dialog.SetInitialData(current["Name"], current["Path"], current["SourceBuild"])
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                data = dialog.GetResult()
                engines[row] = data
                config.SetEngines(engines)
                config.Save()
                item.setText(f"{data['Name']} ({'源码版' if data['SourceBuild'] else 'Launcher'})")

        elif selected == actionDelete:
            self.EngineModel.removeRow(row)
            config.RemoveEngine(name)
            config.Save()

    def SaveGlobalCheckbox(self, Key: str, Checkbox: QtWidgets.QCheckBox):
        config = ConfigManager()
        config.Set(Key, Checkbox.isChecked())
        config.Save()

    def LoadGlobalSettings(self):
        config = ConfigManager()
        for key, cb in zip(["Win64", "Linux", "Mac"], [self.CbWin64, self.CbLinux, self.CbMac]):
            cb.setChecked(config.Get(f"Platform.{key}", key == "Win64"))
        for label, cb in self.FabOptions.items():
            cb.setChecked(config.Get(f"FabSettings.{label}", True))

    def UpdateEngineOrder(self, *args):
        config = ConfigManager()
        allEngines = config.GetEngines()

        NewOrderNames = []
        for row in range(self.EngineModel.rowCount()):
            item = self.EngineModel.item(row)
            name = item.text().split(" ")[0]
            NewOrderNames.append(name)

        SortedEngines = []
        for name in NewOrderNames:
            for engine in allEngines:
                if engine.get("Name") == name:
                    SortedEngines.append(engine)
                    break

        config.SetEngines(SortedEngines)
        config.Save()
