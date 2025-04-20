from PySide2 import QtWidgets, QtGui, QtCore
from Source.Logic.BuildWorker import BuildWorker

class BuildWindow(QtWidgets.QDialog):
    def __init__(self, EngineList, PluginName, PluginPath, OutputRoot, Platforms, Parent=None):
        super().__init__(Parent)
        self.setWindowTitle("打包进度")
        self.setMinimumSize(800, 500)
        self.setModal(True)

        self.EngineList = EngineList
        self.PluginName = PluginName
        self.PluginPath = PluginPath
        self.OutputRoot = OutputRoot
        self.Platforms = Platforms

        self._BuildUI()
        self._StartBuild()

    def _BuildUI(self):
        Layout = QtWidgets.QVBoxLayout(self)

        # 状态列表
        self.Table = QtWidgets.QTableWidget()
        self.Table.setColumnCount(2)
        self.Table.setHorizontalHeaderLabels(["引擎名称", "当前状态"])
        self.Table.setRowCount(len(self.EngineList))
        self.Table.verticalHeader().setVisible(False)
        self.Table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.Table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)

        for i, Engine in enumerate(self.EngineList):
            NameItem = QtWidgets.QTableWidgetItem(Engine["Name"])
            StatusItem = QtWidgets.QTableWidgetItem("排队中")
            self.Table.setItem(i, 0, NameItem)
            self.Table.setItem(i, 1, StatusItem)
        Layout.addWidget(self.Table)

        # 日志窗口
        self.LogBox = QtWidgets.QTextEdit()
        self.LogBox.setReadOnly(True)
        Layout.addWidget(self.LogBox)

        # 操作按钮
        self.BtnStop = QtWidgets.QPushButton("⏹ 停止打包")
        self.BtnStop.clicked.connect(self._OnStopClicked)
        Layout.addWidget(self.BtnStop)

    def _StartBuild(self):
        self.Worker = BuildWorker(
            self.EngineList, self.PluginName, self.PluginPath, self.OutputRoot, self.Platforms
        )
        self.Worker.LogSignal.connect(self._AppendLog)
        self.Worker.StatusSignal.connect(self._UpdateStatus)
        self.Worker.FinishedSignal.connect(self._OnBuildFinished)
        self.Worker.start()

    def _AppendLog(self, Text, Level):
        Color = {
            "info": "white",
            "warn": "orange",
            "error": "red",
            "success": "lime"
        }.get(Level, "white")
        self.LogBox.append(f'<span style="color:{Color}">{Text}</span>')

    def _UpdateStatus(self, Index, StatusText):
        self.Table.setItem(Index, 1, QtWidgets.QTableWidgetItem(StatusText))

    def _OnStopClicked(self):
        if self.Worker.isRunning():
            self.Worker.Stop()
            self.BtnStop.setEnabled(False)
            self.BtnStop.setText("正在终止...")

    def _OnBuildFinished(self):
        self.BtnStop.setEnabled(True)
        self.BtnStop.setText("✅ 打包完成")
        self.BtnStop.clicked.disconnect()
        self.BtnStop.clicked.connect(self.accept)
