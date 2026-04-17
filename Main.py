import os
import sys
from pathlib import Path

# 获取 exe/脚本 所在目录（兼容 PyInstaller 打包）
if getattr(sys, 'frozen', False):
    ProjectRoot = str(Path(sys.executable).parent.resolve())
else:
    ProjectRoot = str(Path(__file__).parent.resolve())


# ========== 入口分支：有参数 → CLI 模式（不加载 Qt） ==========

def _DispatchCli() -> int:
    # CLI 在 Windows 下默认用 GBK，输出 emoji / 中文符号会崩溃，强制 UTF-8
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        try:
            os.system("chcp 65001 >nul")
        except Exception:
            pass
    from Source.Logic.CliRunner import RunCli
    return RunCli(sys.argv[1:], ProjectRoot)


# ========== GUI 模式 ==========

def LaunchApp():
    from PySide2 import QtWidgets
    from Source.UI.MainWindow import MainWindow
    from Source.UI.Item.AddEngineDialog import AddEngineDialog
    from Source.UI.BuildWindow import BuildWindow
    from Source.Logic.ConfigManager import ConfigManager
    from Source.Logic.BuildWorker import BuildWorker

    # 局部状态（闭包共享）
    EngineList = []
    EngineKey = "EngineList"
    Config = ConfigManager()
    View = None

    def LoadEngineList():
        nonlocal EngineList
        EngineList = Config.Get(EngineKey, [])

    def SaveEngineList():
        Config.Set(EngineKey, EngineList)
        Config.Save()

    def RefreshEngineListUI():
        View.EngineView.ClearAll()
        for Engine in EngineList:
            View.AddEngineItem(Engine)

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
        nonlocal EngineList
        EngineList = [next(e for e in EngineList if e["Name"] == Name) for Name in NameList]
        SaveEngineList()
        RefreshEngineListUI()

    def OnFabOptionChanged(Section: str, Patch: dict):
        Current = Config.Get(Section, {})
        Current.update(Patch)
        Config.Set(Section, Current)
        Config.Save()

    def OnBuild():
        Selected = [e for e in EngineList if e.get("Selected", True)]
        if not Selected:
            QtWidgets.QMessageBox.warning(View, "未选择引擎", "请至少勾选一个引擎。")
            return

        PluginName = View.PluginBox.currentText()
        PluginPath = os.path.join(ProjectRoot, "Plugins", PluginName, f"{PluginName}.uplugin")
        if not os.path.isfile(PluginPath):
            QtWidgets.QMessageBox.critical(View, "插件不存在", f"找不到插件文件：\n{PluginPath}")
            return

        OutputRoot = os.path.join(ProjectRoot, "PackagedPlugins")
        Dialog = BuildWindow(Selected, View)

        Worker = BuildWorker(Selected, PluginName, PluginPath, OutputRoot)

        def OnLog(data, level):
            engineName, line = data
            Dialog.AppendLog(engineName, line)

            if level == "error" and "失败" in line:
                path = os.path.join(OutputRoot, PluginName, engineName, "Failed.log")
                if os.path.exists(path):
                    Dialog.AppendLog(engineName, f"📁 日志文件已保存至：{path}")

        def OnFinished():
            Dialog.EnableStop(True)
            Dialog.BtnStop.setText("关闭界面")

        Worker.LogSignal.connect(OnLog)
        Worker.StatusSignal.connect(Dialog.UpdateStatus)
        Worker.FinishedSignal.connect(OnFinished)
        Dialog.StopClicked.connect(Worker.Stop)

        Worker.start()
        Dialog.exec_()

    App = QtWidgets.QApplication([])
    Screen = QtWidgets.QApplication.primaryScreen().availableGeometry()

    Window = QtWidgets.QMainWindow()
    View = MainWindow()
    Window.setCentralWidget(View)
    Window.resize(900, 600)
    Window.move((Screen.width() - 900) // 2, (Screen.height() - 600) // 2)
    Window.setWindowTitle("UE 插件打包器")

    LoadEngineList()
    RefreshEngineListUI()

    # 插件检测
    PluginRoot = os.path.join(ProjectRoot, "Plugins")
    if os.path.exists(PluginRoot):
        Items = [n for n in os.listdir(PluginRoot) if os.path.isdir(os.path.join(PluginRoot, n))]
        View.PluginBox.addItems(Items)
        ProjectName = os.path.basename(ProjectRoot)
        if ProjectName in Items:
            View.PluginBox.setCurrentText(ProjectName)

    # Fab 选项初始化
    FabSettings = Config.Get("FabSettings", {})
    for Label, Checkbox in View.FabOptions.items():
        if Label in FabSettings:
            Checkbox.setChecked(FabSettings[Label])
        else:
            Checkbox.setChecked(False)

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
    if len(sys.argv) > 1:
        sys.exit(_DispatchCli())
    LaunchApp()
