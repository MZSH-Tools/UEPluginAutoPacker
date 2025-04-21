from PySide2 import QtWidgets
import os

class AddEngineDialog(QtWidgets.QDialog):
    def __init__(self, ExistingNames, Parent=None):
        super().__init__(Parent)
        self.setWindowTitle("添加引擎")
        self.setFixedSize(420, 180)
        self.ExistingNames = ExistingNames
        self.ResultData = None

        self.OriginalPath = ""
        self.OriginalName = ""

        self._BuildUI()

    def _BuildUI(self):
        Layout = QtWidgets.QVBoxLayout(self)

        # 路径选择优先
        PathRow = QtWidgets.QHBoxLayout()
        self.PathEdit = QtWidgets.QLineEdit()
        BtnBrowse = QtWidgets.QPushButton("选择")
        BtnBrowse.clicked.connect(self._BrowsePath)
        PathRow.addWidget(QtWidgets.QLabel("引擎路径："))
        PathRow.addWidget(self.PathEdit)
        PathRow.addWidget(BtnBrowse)
        Layout.addLayout(PathRow)

        # 名称
        NameRow = QtWidgets.QHBoxLayout()
        self.NameEdit = QtWidgets.QLineEdit()
        NameRow.addWidget(QtWidgets.QLabel("引擎名称："))
        NameRow.addWidget(self.NameEdit)
        Layout.addLayout(NameRow)

        # 源码版
        self.CbSource = QtWidgets.QCheckBox("此引擎为源码编译版本")
        Layout.addWidget(self.CbSource)

        # 按钮组
        BtnRow = QtWidgets.QHBoxLayout()
        BtnOk = QtWidgets.QPushButton("完成")
        BtnCancel = QtWidgets.QPushButton("取消")
        BtnOk.clicked.connect(self._OnConfirm)
        BtnCancel.clicked.connect(self.reject)
        BtnRow.addStretch()
        BtnRow.addWidget(BtnOk)
        BtnRow.addWidget(BtnCancel)
        Layout.addLayout(BtnRow)

    def _BrowsePath(self):
        NewPath = QtWidgets.QFileDialog.getExistingDirectory(self, "选择引擎路径")
        if NewPath:
            self.PathEdit.setText(NewPath)

            CurName = self.NameEdit.text().strip()
            OldPathName = os.path.basename(os.path.normpath(self.OriginalPath))

            # ✅ 如果当前名称为空 或 当前名称等于旧路径末尾 → 自动命名
            if not CurName or CurName == OldPathName:
                NewName = os.path.basename(os.path.normpath(NewPath))
                self.NameEdit.setText(NewName)

            self.OriginalPath = NewPath

    def _OnConfirm(self):
        Name = self.NameEdit.text().strip()
        Path = self.PathEdit.text().strip()
        IsSource = self.CbSource.isChecked()

        if not Name:
            QtWidgets.QMessageBox.warning(self, "名称不能为空", "请输入引擎名称。")
            return
        if Name in self.ExistingNames:
            QtWidgets.QMessageBox.warning(self, "名称重复", f"“{Name}” 已存在，请更换。")
            return
        if not Path or not os.path.isdir(Path):
            QtWidgets.QMessageBox.warning(self, "路径无效", "请选择有效的引擎目录。")
            return

        UatPath = os.path.join(Path, "Engine", "Build", "BatchFiles", "RunUAT.bat")
        if not os.path.isfile(UatPath):
            QtWidgets.QMessageBox.critical(self, "路径无效", "未在该路径中找到 RunUAT.bat，请检查是否为有效的引擎目录。")
            return

        self.ResultData = {
            "Name": Name,
            "Path": Path,
            "SourceBuild": IsSource
        }
        self.accept()

    def GetResult(self):
        return self.ResultData

    def SetInitialData(self, Name: str, Path: str, SourceBuild: bool):
        self.NameEdit.setText(Name)
        self.PathEdit.setText(Path)
        self.CbSource.setChecked(SourceBuild)
        self.OriginalName = Name
        self.OriginalPath = Path

# ✅ 自测试
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog = AddEngineDialog(["UE_5.3", "UE_5.4"])
    Dialog.SetInitialData("UE_5.3", "C:/Program Files/Epic Games/UE_5.3", False)
    if Dialog.exec_() == QtWidgets.QDialog.Accepted:
        print("添加成功：", Dialog.GetResult())
