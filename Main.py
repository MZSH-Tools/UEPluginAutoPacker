from PySide2 import QtWidgets
import os
from Source.UI.MainWindow import MainWindow
from Source.UI.AddEngineDialog import AddEngineDialog
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

    # 添加引擎
    def OnAddEngine():
        Dialog = AddEngineDialog([e["Name"] for e in Config.GetEngines()], UI)
        if Dialog.exec_() == QtWidgets.QDialog.Accepted:
            Data = Dialog.GetResult()
            Config.AddEngine(Data)
            Config.Save()
            UI.AddEngineItem(Data)

    # 选择输出路径
    def OnChooseOutput():
        Path = QtWidgets.QFileDialog.getExistingDirectory(UI, "选择输出目录")
        if Path:
            UI.OutputEdit.setText(Path)
            Config.Set("OutputPath", Path)
            Config.Save()

    # 开始打包（待实现）
    def OnBuild():
        QtWidgets.QMessageBox.information(UI, "提示", "打包逻辑尚未实现")

    UI.BindCallbacks(OnAddEngine, OnBuild, OnChooseOutput)
    Window.show()
    app.exec_()

if __name__ == "__main__":
    LaunchApp()
