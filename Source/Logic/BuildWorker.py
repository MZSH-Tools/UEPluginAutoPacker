from PySide2.QtCore import QThread, Signal
from Source.Logic.BuildRunner import BuildRunner
import os

class BuildWorker(QThread):
    LogSignal = Signal(str, str)           # (文本, 等级)
    StatusSignal = Signal(int, str)        # (引擎索引, 状态)
    FinishedSignal = Signal()

    def __init__(self, EngineList, PluginName, PluginPath, OutputRoot, Platforms):
        super().__init__()
        self.EngineList = EngineList
        self.PluginName = PluginName
        self.PluginPath = PluginPath
        self.OutputRoot = OutputRoot
        self.Platforms = Platforms
        self.ShouldStop = False

    def Stop(self):
        self.ShouldStop = True

    def run(self):
        for Index, Engine in enumerate(self.EngineList):
            if self.ShouldStop:
                self.StatusSignal.emit(Index, "已取消")
                self.LogSignal.emit(f"[{Engine['Name']}] 已跳过打包", "warn")
                continue

            self.StatusSignal.emit(Index, "打包中")
            self.LogSignal.emit(f"[{Engine['Name']}] 开始打包...", "info")

            UatPath = os.path.join(Engine["Path"], "Engine", "Build", "BatchFiles", "RunUAT.bat")
            OutputDir = os.path.join(self.OutputRoot, self.PluginName, Engine["Name"])
            Runner = BuildRunner(UatPath, self.PluginPath, OutputDir, self.Platforms)

            Success, Err = Runner.RunBuild()

            if Success:
                self.StatusSignal.emit(Index, "✅ 成功")
                self.LogSignal.emit(f"[{Engine['Name']}] 打包成功", "success")
            else:
                self.StatusSignal.emit(Index, "❌ 失败")
                self.LogSignal.emit(f"[{Engine['Name']}] 打包失败：{Err}", "error")
        self.FinishedSignal.emit()
