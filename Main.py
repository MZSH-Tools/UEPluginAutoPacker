from PySide2 import QtWidgets, QtCore
import os
import sys
from Source.UI.MainWindow import MainWindow
from Source.UI.Item.AddEngineDialog import AddEngineDialog
from Source.UI.BuildWindow import BuildWindow
from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.PluginManager import PluginManager
from Source.Logic.BuildWorker import BuildWorker

# ======================= 引擎增删改查 =========================

EngineKey = "EngineList"

def GetEngines(Config):
    return Config.Get(EngineKey, [])

def SetEngines(Config, EngineList):
    Config.Set(EngineKey, EngineList)
    Config.Save()

def AddEngine(Config, EngineData):
    EngineList = GetEngines(Config)
    EngineList.append(EngineData)
    SetEngines(Config, EngineList)

def RemoveEngine(Config, Name):
    EngineList = [E for E in GetEngines(Config) if E.get("Name") != Name]
    SetEngines(Config, EngineList)

def SetEngineField(Config, Name, Key, Value):
    EngineList = GetEngines(Config)
    for Engine in EngineList:
        if Engine.get("Name") == Name:
            Engine[Key] = Value
            break
    SetEngines(Config, EngineList)

# ======================== 主函数逻辑 ==========================

def LaunchApp():
    os.chdir(r"D:\GitHub\UEPlugins\SimpleSSHTunnel")  # ✅ 启动调试目录

    App = QtWidgets.QApplication([])
    Screen = QtWidgets.QApplication.primaryScreen().availableGeometry()

    Window = QtWidgets.QMainWindow()
    View = MainWindow()
    Window.setCentralWidget(View)
    Window.resize(900, 600)
    Window.move((Screen.width() - 900) // 2, (Screen.height() - 600) // 2)
    Window.setWindowTitle("UE 插件打包器")

    Config = ConfigManager()
    Plugin = PluginManager()

    # 加载引擎到界面
    for EngineData in GetEngines(Config):
        View.AddEngineItem(EngineData)

    # 加载插件列表
    PluginRoot = os.path.join(os.getcwd(), "Plugins")
    if os.path.exists(PluginRoot):
        PluginList = [Name for Name in os.listdir(PluginRoot)
                      if os.path.isdir(os.path.join(PluginRoot, Name))]
        View.PluginBox.addItems(PluginList)
        ProjectName = os.path.basename(os.getcwd())
        if ProjectName in PluginList:
            View.PluginBox.setCurrentText(ProjectName)

    # 加载 Fab 整理设置
    for Label, Checkbox in View.FabOptions.items():
        Checkbox.setChecked(Config.Get(f"FabSettings.{Label}", True))

    # 信号绑定
    View.AddEngineRequested.connect(lambda: OnAddEngine(View, Config))
    View.EngineCheckedChanged.connect(lambda Name, Checked: SetEngineField(Config, Name, "Selected", Checked))
    View.EngineOrderChanged.connect(lambda Order: OnReorderEngines(Config, Order))
    View.EngineEditRequested.connect(lambda Row: OnEditEngine(View, Config, Row))
    View.EngineDeleteRequested.connect(lambda Row: OnDeleteEngine(View, Config, Row))
    View.GlobalOptionChanged.connect(lambda Key, Val: OnGlobalOptionChanged(Config, Key, Val))
    View.BuildRequested.connect(lambda: OnBuild(View, Config))

    Window.show()
    sys.exit(App.exec_())

# ======================== 回调逻辑 ==========================

def OnAddEngine(View, Config):
    Dialog = AddEngineDialog([E["Name"] for E in GetEngines(Config)], View)
    if Dialog.exec_() == QtWidgets.QDialog.Accepted:
        Data = Dialog.GetResult()
        AddEngine(Config, Data)
        View.AddEngineItem(Data)

def OnEditEngine(View, Config, Row):
    EngineList = GetEngines(Config)
    Current = EngineList[Row]
    Dialog = AddEngineDialog(
        [E["Name"] for I, E in enumerate(EngineList) if I != Row], View
    )
    Dialog.SetInitialData(Current["Name"], Current["Path"], Current["SourceBuild"])
    if Dialog.exec_() == QtWidgets.QDialog.Accepted:
        EngineList[Row] = Dialog.GetResult()
        SetEngines(Config, EngineList)
        Updated = EngineList[Row]
        View.EngineModel.item(Row).setText(
            f"{Updated['Name']} ({'源码版' if Updated['SourceBuild'] else 'Launcher'})"
        )

def OnDeleteEngine(View, Config, Row):
    Name = View.EngineModel.item(Row).text().split(" ")[0]
    View.EngineModel.removeRow(Row)
    RemoveEngine(Config, Name)

def OnReorderEngines(Config, NewOrder):
    AllEngines = GetEngines(Config)
    Sorted = []
    for Name in NewOrder:
        for Engine in AllEngines:
            if Engine.get("Name") == Name:
                Sorted.append(Engine)
                break
    SetEngines(Config, Sorted)

def OnGlobalOptionChanged(Config, Key, Value):
    Config.Set(Key, Value)
    Config.Save()

def OnBuild(View, Config):
    SelectedEngines = [E for E in GetEngines(Config) if E.get("Selected", True)]
    if not SelectedEngines:
        QtWidgets.QMessageBox.warning(View, "未选择引擎", "请至少勾选一个引擎。")
        return

    PluginName = View.PluginBox.currentText()
    PluginPath = os.path.join(os.getcwd(), "Plugins", PluginName, f"{PluginName}.uplugin")
    if not os.path.isfile(PluginPath):
        QtWidgets.QMessageBox.critical(View, "插件不存在", f"找不到插件文件：\n{PluginPath}")
        return

    OutputRoot = os.path.join(os.getcwd(), "PackagedPlugins")

    Dialog = BuildWindow(SelectedEngines, View)
    Worker = BuildWorker(SelectedEngines, PluginName, PluginPath, OutputRoot, "")
    Worker.LogSignal.connect(Dialog.AppendLog)
    Worker.StatusSignal.connect(Dialog.UpdateStatus)
    Worker.FinishedSignal.connect(lambda: Dialog.EnableStop(True))
    Dialog.StopClicked.connect(Worker.Stop)
    Worker.start()
    Dialog.exec_()

# ======================== 启动程序 ==========================

if __name__ == "__main__":
    LaunchApp()
