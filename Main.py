from PySide2 import QtWidgets, QtCore
import os
import sys
from Source.UI.MainWindow import MainWindow
from Source.UI.Item.AddEngineDialog import AddEngineDialog
from Source.UI.BuildWindow import BuildWindow
from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.PluginManager import PluginManager
from Source.Logic.BuildWorker import BuildWorker

# ========== 全局状态 ==========
EngineList = []
EngineKey = "EngineList"
Config = None
View = None

# ========== 引擎数据逻辑 ==========

def LoadEngineList():
    global EngineList
    EngineList = Config.Get(EngineKey, [])

def SaveEngineList():
    Config.Set(EngineKey, EngineList)
    Config.Save()

def RefreshEngineListUI():
    View.EngineView.ClearAll()
    for Engine in EngineList:
        View.AddEngineItem(Engine)

# ========== 引擎操作回调 ==========

def OnAddEngine():
    Names = [e["Name"] for e in EngineList]
    Dialog = AddEngineDialog(Names, View)
    if Dialog.exec_() == QtWidgets.QDialog.Accepted:
        Data = Dialog.GetResult()
        if any(e["Name"] == Data["Name"] for e in EngineList):
            QtWidgets.QMessageBox.warning(View, "重复名称", f"“{Data['Name']}” 已存在")
            return
        EngineList.append(Data)
        SaveEngineList()
        RefreshEngineListUI()

def OnEditEngine(Index):
    Current = EngineList[Index]
    Names = [e["Name"] for i, e in enumerate(EngineList) if i != Index]
    Dialog = AddEngineDialog(Names, View)
    Dialog.SetInitialData(Current["Name"], Current["Path"], Current["SourceBuild"])
    if Dialog.exec_() == QtWidgets.QDialog.Accepted:
        EngineList[Index] = Dialog.GetResult()
        SaveEngineList()
        RefreshEngineListUI()

def OnDeleteEngine(Index):
    if 0 <= Index < len(EngineList):
        del EngineList[Index]
        SaveEngineList()
        RefreshEngineListUI()

def OnEngineChecked(Name, Checked):
    for e in EngineList:
        if e["Name"] == Name:
            e["Selected"] = Checked
            break
    SaveEngineList()

def OnEngineReordered(NameList):
    global EngineList
    EngineList = [next(e for e in EngineList if e["Name"] == Name) for Name in NameList]
    SaveEngineList()
    RefreshEngineListUI()

# ========== Fab设置回调 ==========

def OnFabOptionChanged(Section: str, Patch: dict):
    Current = Config.Get(Section, {})
    Current.update(Patch)
    Config.Set(Section, Current)
    Config.Save()

# ========== 构建执行 ==========

def OnBuild():
    Selected = [e for e in EngineList if e.get("Selected", True)]
    if not Selected:
        QtWidgets.QMessageBox.warning(View, "未选择引擎", "请至少勾选一个引擎。")
        return

    PluginName = View.PluginBox.currentText()
    PluginPath = os.path.join(os.getcwd(), "Plugins", PluginName, f"{PluginName}.uplugin")
    if not os.path.isfile(PluginPath):
        QtWidgets.QMessageBox.critical(View, "插件不存在", f"找不到插件文件：\n{PluginPath}")
        return

    OutputRoot = os.path.join(os.getcwd(), "PackagedPlugins")
    Dialog = BuildWindow(Selected, View)

    Worker = BuildWorker(Selected, PluginName, PluginPath, OutputRoot, "")
    Worker.LogSignal.connect(Dialog.AppendLog)
    Worker.StatusSignal.connect(Dialog.UpdateStatus)
    Worker.FinishedSignal.connect(lambda: Dialog.EnableStop(True))
    Dialog.StopClicked.connect(Worker.Stop)

    Worker.start()
    Dialog.exec_()

# ========== 启动主界面 ==========

def LaunchApp():
    global Config, View
    os.chdir(r"D:\GitHub\UEPlugins\SimpleSSHTunnel")

    App = QtWidgets.QApplication([])
    Screen = QtWidgets.QApplication.primaryScreen().availableGeometry()

    Window = QtWidgets.QMainWindow()
    View = MainWindow()
    Window.setCentralWidget(View)
    Window.resize(900, 600)
    Window.move((Screen.width() - 900) // 2, (Screen.height() - 600) // 2)
    Window.setWindowTitle("UE 插件打包器")

    # 初始化配置
    Config = ConfigManager()
    LoadEngineList()
    RefreshEngineListUI()

    # 插件检测
    PluginRoot = os.path.join(os.getcwd(), "Plugins")
    if os.path.exists(PluginRoot):
        Items = [n for n in os.listdir(PluginRoot) if os.path.isdir(os.path.join(PluginRoot, n))]
        View.PluginBox.addItems(Items)
        ProjectName = os.path.basename(os.getcwd())
        if ProjectName in Items:
            View.PluginBox.setCurrentText(ProjectName)

    # Fab 选项初始化
    for Label, Checkbox in View.FabOptions.items():
        Checkbox.setChecked(Config.Get("FabSettings", {}).get(Label, True))

    # 信号连接
    View.AddEngineRequested.connect(OnAddEngine)
    View.EngineCheckedChanged.connect(OnEngineChecked)
    View.EngineOrderChanged.connect(OnEngineReordered)
    View.EngineEditRequested.connect(OnEditEngine)
    View.EngineDeleteRequested.connect(OnDeleteEngine)
    View.GlobalOptionChanged.connect(OnFabOptionChanged)
    View.BuildRequested.connect(OnBuild)

    Window.show()
    sys.exit(App.exec_())

# ========== 程序入口 ==========

if __name__ == "__main__":
    LaunchApp()
