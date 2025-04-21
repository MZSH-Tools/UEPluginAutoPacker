from PySide2 import QtWidgets, QtCore, QtGui


class BuildWindow(QtWidgets.QDialog):
    StopClicked = QtCore.Signal()               # 用户点击“停止”

    def __init__(self, engineList, parent=None):
        super().__init__(parent)
        self.setWindowTitle("打包进度")
        self.setMinimumSize(800, 500)
        self.setModal(True)
        self._BuildUI(engineList)

    # ---------- UI ----------
    def _BuildUI(self, engineList):
        lay = QtWidgets.QVBoxLayout(self)

        # 状态表
        self.Table = QtWidgets.QTableWidget(len(engineList), 2)
        self.Table.setHorizontalHeaderLabels(["引擎名称", "当前状态"])
        self.Table.verticalHeader().setVisible(False)
        self.Table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.Table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)

        for i, e in enumerate(engineList):
            self.Table.setItem(i, 0, QtWidgets.QTableWidgetItem(e["Name"]))
            self.Table.setItem(i, 1, QtWidgets.QTableWidgetItem("排队中"))
        lay.addWidget(self.Table)

        # 日志
        self.LogBox = QtWidgets.QTextEdit(readOnly=True)
        lay.addWidget(self.LogBox)

        # 停止按钮
        self.BtnStop = QtWidgets.QPushButton("⏹ 停止打包")
        self.BtnStop.clicked.connect(self._onStop)
        lay.addWidget(self.BtnStop)

    # ---------- 公共接口 ----------
    def AppendLog(self, text: str, level: str):
        clr = dict(info="white", warn="orange", error="red", success="lime").get(level, "white")
        self.LogBox.append(f'<span style="color:{clr}">{text}</span>')

    def UpdateStatus(self, row: int, status: str):
        self.Table.setItem(row, 1, QtWidgets.QTableWidgetItem(status))

    def EnableStop(self, enable: bool):
        self.BtnStop.setEnabled(enable)

    # ---------- 内部 ----------
    def _onStop(self):
        self.EnableStop(False)
        self.BtnStop.setText("正在终止…")
        self.StopClicked.emit()
