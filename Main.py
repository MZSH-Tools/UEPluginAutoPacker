from PySide2 import QtWidgets
import os
from Source.UI.MainWindow import MainWindow
from Source.UI.Item.AddEngineDialog import AddEngineDialog
from Source.UI.BuildWindow import BuildWindow
from Source.Logic.ConfigManager import ConfigManager

def LaunchApp():
    app = QtWidgets.QApplication([])
    screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
    width, height = screen.width() // 2, screen.height() // 2

    Window = QtWidgets.QMainWindow()
    UI = MainWindow()
    Window.setCentralWidget(UI)
    Window.setGeometry(
        (screen.width() - width) // 2,
        (screen.height() - height) // 2,
        width, height
    )
    Window.setWindowTitle("UE 插件打包器")

    Config = ConfigManager()

    # 加载引擎列表
    for EngineData in Config.GetEngines():
        UI.AddEngineItem(EngineData)

    # 加载插件列表（默认使用当前项目插件路径）
    PluginRoot = os.path.join(os.getcwd(), "Plugins")
    if os.path.exists(PluginRoot):
        PluginList = [name for name in os.listdir(PluginRoot) if os.path.isdir(os.path.join(PluginRoot, name))]
        UI.PluginBox.addItems(PluginList)
        ProjectName = os.path.basename(os.getcwd())
        if ProjectName in PluginList:
            UI.PluginBox.setCurrentText(ProjectName)

    # 加载输出路径、平台与Fab设置
    UI.LoadGlobalSettings()

    # 添加引擎回调
    def OnAddEngine():
        Dialog = AddEngineDialog([e["Name"] for e in Config.GetEngines()], UI)
        if Dialog.exec_() == QtWidgets.QDialog.Accepted:
            Data = Dialog.GetResult()
            Config.AddEngine(Data)
            Config.Save()
            UI.AddEngineItem(Data)

    # 选择输出路径回调
    def OnChooseOutput():
        Path = QtWidgets.QFileDialog.getExistingDirectory(UI, "选择输出目录")
        if Path:
            UI.OutputEdit.setText(Path)
            Config.Set("OutputPath", Path)
            Config.Save()

    # 开始打包回调
    def OnBuild():
        SelectedEngines = [e for e in Config.GetEngines() if e.get("Selected", True)]
        if not SelectedEngines:
            QtWidgets.QMessageBox.warning(UI, "未选择引擎", "请至少勾选一个引擎进行打包。")
            return

        PluginName = UI.PluginBox.currentText()
        PluginPath = os.path.join(os.getcwd(), "Plugins", PluginName, f"{PluginName}.uplugin")
        OutputPath = UI.OutputEdit.text()
        if not os.path.isfile(PluginPath):
            QtWidgets.QMessageBox.critical(UI, "插件不存在", f"找不到插件文件：{PluginPath}")
            return
        if not os.path.isdir(OutputPath):
            QtWidgets.QMessageBox.critical(UI, "输出路径无效", "请指定有效的输出路径。")
            return

        Platforms = ",".join([
            k for k, cb in zip(["Win64", "Linux", "Mac"], [UI.CbWin64, UI.CbLinux, UI.CbMac]) if cb.isChecked()
        ])
        if not Platforms:
            QtWidgets.QMessageBox.warning(UI, "未选择平台", "请至少选择一个目标平台。")
            return

        Dialog = BuildWindow(SelectedEngines, PluginName, PluginPath, OutputPath, Platforms, UI)
        Dialog.exec_()

    # 绑定回调
    UI.BindCallbacks(OnAddEngine, OnBuild, OnChooseOutput)
    Window.show()
    app.exec_()

if __name__ == "__main__":
    LaunchApp()
