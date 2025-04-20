from PySide2 import QtWidgets
import os

class AddEngineDialog(QtWidgets.QDialog):
    def __init__(self, existingNames, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加引擎")
        self.setFixedSize(400, 180)
        self.resultData = None
        self.existingNames = existingNames

        layout = QtWidgets.QVBoxLayout(self)

        nameLayout = QtWidgets.QHBoxLayout()
        self.nameEdit = QtWidgets.QLineEdit()
        nameLayout.addWidget(QtWidgets.QLabel("引擎名称："))
        nameLayout.addWidget(self.nameEdit)
        layout.addLayout(nameLayout)

        pathLayout = QtWidgets.QHBoxLayout()
        self.pathEdit = QtWidgets.QLineEdit()
        btnBrowse = QtWidgets.QPushButton("选择")
        btnBrowse.clicked.connect(self.BrowsePath)
        pathLayout.addWidget(QtWidgets.QLabel("引擎路径："))
        pathLayout.addWidget(self.pathEdit)
        pathLayout.addWidget(btnBrowse)
        layout.addLayout(pathLayout)

        self.cbSourceBuild = QtWidgets.QCheckBox("此引擎为源码编译版本")
        layout.addWidget(self.cbSourceBuild)

        buttonLayout = QtWidgets.QHBoxLayout()
        btnOK = QtWidgets.QPushButton("完成")
        btnCancel = QtWidgets.QPushButton("取消")
        btnOK.clicked.connect(self.OnConfirm)
        btnCancel.clicked.connect(self.reject)
        buttonLayout.addStretch()
        buttonLayout.addWidget(btnOK)
        buttonLayout.addWidget(btnCancel)
        layout.addLayout(buttonLayout)

    def BrowsePath(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择引擎路径")
        if path:
            self.pathEdit.setText(path)

    def OnConfirm(self):
        name = self.nameEdit.text().strip()
        path = self.pathEdit.text().strip()
        isSource = self.cbSourceBuild.isChecked()

        if not name:
            QtWidgets.QMessageBox.warning(self, "无效名称", "请填写引擎名称。")
            return
        if name in self.existingNames:
            QtWidgets.QMessageBox.warning(self, "名称重复", f"引擎名称“{name}”已存在，请使用其他名称。")
            return
        if not path or not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "路径无效", "请设置有效的引擎路径。")
            return

        self.resultData = {
            "Name": name,
            "Path": path,
            "SourceBuild": isSource
        }
        self.accept()
