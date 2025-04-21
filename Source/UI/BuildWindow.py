from PySide2 import QtWidgets, QtCore, QtGui
from functools import partial

class BuildWindow(QtWidgets.QDialog):
    StopClicked = QtCore.Signal()

    def __init__(self, engineList, parent=None):
        super().__init__(parent)
        self.setWindowTitle("打包进度")
        self.setMinimumSize(1000, 600)
        self.setModal(True)
        self.EngineList = engineList
        self.ButtonMap = {}
        self.StatusMap = {}
        self.LogMap = {}
        self.CurrentName = None

        self._BuildUI()

    def _BuildUI(self):
        MainLayout = QtWidgets.QVBoxLayout(self)

        # -------- 三列横排 --------
        RowLayout = QtWidgets.QHBoxLayout()

        # 左列：引擎按钮
        LeftCol = QtWidgets.QVBoxLayout()
        for engine in self.EngineList:
            name = engine["Name"]
            btn = QtWidgets.QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setMinimumWidth(100)
            btn.clicked.connect(partial(self._SetCurrentEngine, name))
            self.ButtonMap[name] = btn
            LeftCol.addWidget(btn)
        RowLayout.addLayout(LeftCol, 1)

        # 中列：状态标签
        MidCol = QtWidgets.QVBoxLayout()
        for engine in self.EngineList:
            name = engine["Name"]
            lbl = QtWidgets.QLabel("等待中")
            lbl.setFixedHeight(40)
            lbl.setMinimumWidth(100)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("""
                QLabel {
                    border: 1px solid gray;
                    background-color: #eeeeee;
                    font-size: 13px;
                }
            """)
            self.StatusMap[name] = lbl
            MidCol.addWidget(lbl)
        RowLayout.addLayout(MidCol, 1)

        # 右列：日志框
        self.LogBox = QtWidgets.QTextEdit()
        self.LogBox.setReadOnly(True)
        self.LogBox.setStyleSheet("font-family: Consolas; font-size: 13px;")
        RowLayout.addWidget(self.LogBox, 3)

        MainLayout.addLayout(RowLayout)

        # -------- 停止按钮 --------
        self.BtnStop = QtWidgets.QPushButton("⏹ 停止打包")
        self.BtnStop.setMinimumHeight(36)
        self.BtnStop.clicked.connect(self._onStop)
        MainLayout.addWidget(self.BtnStop)

        # 初始化日志映射
        for engine in self.EngineList:
            self.LogMap[engine["Name"]] = []

        if self.EngineList:
            self._SetCurrentEngine(self.EngineList[0]["Name"])

    # -------- 公共接口 --------
    def AppendLog(self, engineName: str, line: str):
        self.LogMap.setdefault(engineName, []).append(line)
        if self.CurrentName == engineName:
            self.LogBox.append(line)

    def UpdateStatus(self, row: int, status: str):
        name = self.EngineList[row]["Name"]
        if name in self.StatusMap:
            self.StatusMap[name].setText(status)

    def EnableStop(self, enable: bool):
        self.BtnStop.setEnabled(enable)

    def _onStop(self):
        self.EnableStop(False)
        self.BtnStop.setText("正在终止…")
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

# ===== 自测试入口 =====
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)

    engines = [
        {"Name": "UE5.3"},
        {"Name": "UE5.4"},
        {"Name": "UE5.5"},
    ]

    win = BuildWindow(engines)
    win.AppendLog("[UE5.3] 正在打包...", "info")
    win.AppendLog("[UE5.3] ✅ 成功", "success")
    win.AppendLog("[UE5.4] 等待中...", "warn")
    win.UpdateStatus(0, "打包中")
    win.UpdateStatus(1, "等待中")
    win.UpdateStatus(2, "等待中")

    win.show()
    sys.exit(app.exec_())
