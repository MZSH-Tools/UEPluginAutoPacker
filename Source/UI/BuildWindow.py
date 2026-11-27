from PySide2 import QtWidgets, QtCore, QtGui
from functools import partial

class BuildWindow(QtWidgets.QDialog):
    StopClicked = QtCore.Signal()

    IconMap = {
        "等待中": "⏳",
        "打包中": "🔵",
        "✅ 成功": "✅",
        "❌ 失败": "❌",
        "已取消": "➖"
    }

    def __init__(self, engineList, parent=None):
        super().__init__(parent)
        self.setWindowTitle("打包进度")
        self.setMinimumSize(1000, 600)
        self.setModal(True)
        self.EngineList = engineList

        self.ButtonMap = {}  # 引擎名 → 按钮
        self.LogMap = {}     # 引擎名 → 日志字符串列表
        self.CurrentName = None
        self.IsFinished = False

        self._BuildUI()

    def _BuildUI(self):
        Layout = QtWidgets.QVBoxLayout(self)

        # ---------- 书签栏 ----------
        self.TabBar = QtWidgets.QHBoxLayout()
        self.TabBar.setSpacing(4)
        for engine in self.EngineList:
            name = engine["Name"]
            btn = QtWidgets.QPushButton(f"{self.IconMap['等待中']} {name}")
            btn.setCheckable(True)
            btn.setMinimumHeight(36)
            btn.clicked.connect(partial(self._SetCurrentEngine, name))
            self.ButtonMap[name] = btn
            self.TabBar.addWidget(btn)
            self.LogMap[name] = []
        Layout.addLayout(self.TabBar)

        # ---------- 日志框 ----------
        self.LogBox = QtWidgets.QTextEdit()
        self.LogBox.setReadOnly(True)
        self.LogBox.setStyleSheet("font-family: Consolas; font-size: 13px;")
        Layout.addWidget(self.LogBox, 1)

        # ---------- 停止按钮 ----------
        self.BtnStop = QtWidgets.QPushButton("⏹ 停止打包")
        self.BtnStop.setMinimumHeight(36)
        self.BtnStop.clicked.connect(self._OnStop)
        Layout.addWidget(self.BtnStop)

        # 默认选中第一个
        if self.EngineList:
            self._SetCurrentEngine(self.EngineList[0]["Name"])

    # ---------- 公共方法 ----------
    def AppendLog(self, engineName: str, line: str):
        self.LogMap.setdefault(engineName, []).append(line)
        if self.CurrentName == engineName:
            self.LogBox.append(line)

    @QtCore.Slot(tuple, str)
    def AppendWorkerLog(self, Record, Level):
        self.AppendLog(*Record)

    def UpdateStatus(self, row: int, status: str):
        name = self.EngineList[row]["Name"]
        btn = self.ButtonMap.get(name)
        if btn:
            icon = self.IconMap.get(status, "⏳")
            btn.setText(f"{icon} {name}")

    def EnableStop(self, enable: bool):
        self.BtnStop.setEnabled(enable)

    def MarkFinished(self):
        self.IsFinished = True
        self.BtnStop.setText('关闭界面')
        self.EnableStop(True)

    def reject(self):
        if self.IsFinished:
            super().reject()
        elif self.BtnStop.isEnabled():
            self._OnStop()

    def closeEvent(self, Event):
        if self.IsFinished:
            super().closeEvent(Event)
        else:
            Event.ignore()
            self.reject()

    # ---------- 交互逻辑 ----------
    def _OnStop(self):
        if self.BtnStop.text() == "关闭界面":
            self.close()
        else:
            self.BtnStop.setText('正在停止…')
            self.EnableStop(False)
            self.StopClicked.emit()

    def _SetCurrentEngine(self, name: str):
        self.CurrentName = name
        self.LogBox.clear()
        for line in self.LogMap.get(name, []):
            self.LogBox.append(line)

        for n, btn in self.ButtonMap.items():
            btn.setChecked(n == name)
            if n == name:
                btn.setStyleSheet("background-color: #444488; color: white; font-weight: bold;")
            else:
                btn.setStyleSheet("")
