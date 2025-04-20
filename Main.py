from PySide2 import QtWidgets
import os
from Source.UI.MainWindow import MainWindow
from Source.UI.AddEngineDialog import AddEngineDialog
from Source.Logic.EngineManager import EngineManager
from Source.Logic.PluginManager import PluginManager
from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.BuildRunner import BuildRunner

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

    Engine = EngineManager()
    Plugin = PluginManager()
    Config = ConfigManager()

    # 加载引擎（✔ 使用 AddEngineItem 适配 QListView）
    for EngineData in Engine.GetEngines():
        UI.AddEngineItem(EngineData)

    # 加载插件列表
    PluginList = Plugin.GetPluginList()
    UI.PluginBox.addItems([os.path.basename(p) for p in PluginList])
    DefaultPath = Plugin.GetDefaultPlugin()
    if DefaultPath:
        UI.PluginBox.setCurrentText(os.path.basename(DefaultPath))

    # 输出目录
    UI.OutputEdit.setText(Config.Get("OutputPath", os.path.join(os.getcwd(), "Packaged")))

    # 添加引擎
    def OnAddEngine():
        Dialog = AddEngineDialog([e["Name"] for e in Engine.GetEngines()], UI)
        if Dialog.exec_() == QtWidgets.QDialog.Accepted:
            Data = Dialog.GetResult()
            Engine.AddEngine(Data)
            UI.AddEngineItem(Data)

    # 选择输出目录
    def OnChooseOutput():
        Path = QtWidgets.QFileDialog.getExistingDirectory(UI, "选择输出目录")
        if Path:
            UI.OutputEdit.setText(Path)
            Config.Set("OutputPath", Path)

    # 开始打包（占位）
    def OnBuild():
        QtWidgets.QMessageBox.information(UI, "TODO", "这里是打包功能的入口（待实现）")

    UI.BindCallbacks(OnAddEngine, OnBuild, OnChooseOutput)

    Window.show()
    app.exec_()

if __name__ == "__main__":
    LaunchApp()
