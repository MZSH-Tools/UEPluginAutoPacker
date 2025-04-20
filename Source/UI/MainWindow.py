from PySide2 import QtWidgets
from PySide2.QtCore import Qt, QPoint
from Source.UI.AddEngineDialog import AddEngineDialog
import os

class MainPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setLayout(QtWidgets.QHBoxLayout())

        # 左侧：引擎列表
        self.engineList = QtWidgets.QListWidget()
        self.engineList.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.engineList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.engineList.customContextMenuRequested.connect(self.ShowContextMenu)
        self.layout().addWidget(self.engineList, 2)

        leftBtn = QtWidgets.QPushButton("➕ 添加引擎")
        leftBtn.clicked.connect(self.OnAddEngine)
        self.layout().addWidget(leftBtn, 0, Qt.AlignTop)

        # 右侧：设置区域
        right = QtWidgets.QVBoxLayout()

        # 插件选择
        pluginRow = QtWidgets.QHBoxLayout()
        self.pluginBox = QtWidgets.QComboBox()
        pluginRow.addWidget(QtWidgets.QLabel("插件选择："))
        pluginRow.addWidget(self.pluginBox)
        right.addLayout(pluginRow)

        # 输出路径
        outputRow = QtWidgets.QHBoxLayout()
        self.outputEdit = QtWidgets.QLineEdit()
        outputBtn = QtWidgets.QPushButton("选择输出")
        outputBtn.clicked.connect(self.SelectOutput)
        outputRow.addWidget(QtWidgets.QLabel("输出目录："))
        outputRow.addWidget(self.outputEdit)
        outputRow.addWidget(outputBtn)
        right.addLayout(outputRow)

        # 平台选择
        right.addWidget(QtWidgets.QLabel("目标平台："))
        self.cbWin64 = QtWidgets.QCheckBox("Win64")
        self.cbLinux = QtWidgets.QCheckBox("Linux")
        self.cbMac = QtWidgets.QCheckBox("Mac")
        self.cbWin64.setChecked(True)
        right.addWidget(self.cbWin64)
        right.addWidget(self.cbLinux)
        right.addWidget(self.cbMac)

        # 打包按钮
        buildBtn = QtWidgets.QPushButton("开始打包")
        buildBtn.clicked.connect(self.StartBuild)
        right.addWidget(buildBtn)

        right.addStretch()
        self.layout().addLayout(right, 3)

    def OnAddEngine(self):
        existing = [self.engineList.item(i).text().split(" ")[0] for i in range(self.engineList.count())]
        dialog = AddEngineDialog(existing, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            data = dialog.resultData
            tag = "源码版" if data["SourceBuild"] else "Launcher"
            displayName = f"{data['Name']} ({tag})"
            self.engineList.addItem(displayName)

    def ShowContextMenu(self, pos: QPoint):
        item = self.engineList.itemAt(pos)
        if not item:
            return
        menu = QtWidgets.QMenu(self)
        actionRename = menu.addAction("重命名")
        actionDelete = menu.addAction("删除")
        action = menu.exec_(self.engineList.mapToGlobal(pos))
        row = self.engineList.row(item)
        if action == actionRename:
            newName, ok = QtWidgets.QInputDialog.getText(self, "重命名", "新的名称：")
            if ok and newName:
                base = newName.strip()
                tag = "源码版" if "源码版" in item.text() else "Launcher"
                item.setText(f"{base} ({tag})")
        elif action == actionDelete:
            self.engineList.takeItem(row)

    def SelectOutput(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.outputEdit.setText(path)

    def StartBuild(self):
        QtWidgets.QMessageBox.information(self, "TODO", "这里将执行打包流程")

def LaunchApp():
    app = QtWidgets.QApplication([])
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("UE 插件打包器")
    window.setCentralWidget(MainPanel())
    window.resize(1000, 600)
    window.show()
    app.exec_()
