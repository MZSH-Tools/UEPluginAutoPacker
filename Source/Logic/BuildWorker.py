from PySide2.QtCore import QThread, Signal
from Source.Logic.BuildRunner import BuildRunner
import os

class BuildWorker(QThread):
    LogSignal = Signal(str, str)           # (文本, 等级)
    StatusSignal = Signal(int, str)        # (引擎索引, 状态)
    FinishedSignal = Signal()

    def __init__(self, EngineList, PluginName, PluginPath, OutputRoot):
        super().__init__()
        self.EngineList = EngineList
        self.PluginName = PluginName
        self.PluginPath = PluginPath
        self.OutputRoot = OutputRoot
        self.ShouldStop = False
        self.CurrentRunner = None

    def Stop(self):
        self.ShouldStop = True
        if self.CurrentRunner:
            self.CurrentRunner.Terminate()

    def run(self):
        for Index, Engine in enumerate(self.EngineList):
            Name = Engine["Name"]

            if self.ShouldStop:
                self.StatusSignal.emit(Index, "已取消")
                self.LogSignal.emit(f"[{Name}] 已跳过打包", "warn")
                continue

            self.StatusSignal.emit(Index, "打包中")
            self.LogSignal.emit(f"[{Name}] 开始打包...", "info")

            UatPath = os.path.join(Engine["Path"], "Engine", "Build", "BatchFiles", "RunUAT.bat")
            OutputDir = os.path.join(self.OutputRoot, self.PluginName, Name)
            IsSourceBuild = Engine.get("SourceBuild", False)
            UseRocket = not IsSourceBuild

            Runner = BuildRunner(
                RunUatPath=UatPath,
                PluginPath=self.PluginPath,
                OutputDir=OutputDir,
                UseRocket=UseRocket  # ✅ 不再传 TargetPlatforms
            )

            self.CurrentRunner = Runner
            LogLines = []
            Success = False

            for Line in Runner.RunBuild():
                if Line == "EXIT_SUCCESS":
                    Success = True
                    break
                elif Line == "EXIT_FAILURE":
                    break
                elif Line.startswith("ERROR::"):
                    LogLines.append(Line[7:])
                    break
                else:
                    Prefixed = f"[{Name}] {Line}"
                    LogLines.append(Prefixed)
                    self.LogSignal.emit(Prefixed, "info")

            self.CurrentRunner = None

            if self.ShouldStop:
                self.StatusSignal.emit(Index, "已取消")
                self.LogSignal.emit(f"[{Name}] 被用户终止", "warn")
                break

            if Success:
                self.StatusSignal.emit(Index, "✅ 成功")
                self.LogSignal.emit(f"[{Name}] ✅ 构建成功", "success")
            else:
                self.StatusSignal.emit(Index, "❌ 失败")
                self.LogSignal.emit(f"[{Name}] ❌ 构建失败", "error")

                FailedLogPath = os.path.join(OutputDir, "Failed.log")
                os.makedirs(OutputDir, exist_ok=True)
                try:
                    with open(FailedLogPath, "w", encoding="utf-8") as f:
                        f.write("\n".join(LogLines))
                except Exception as e:
                    self.LogSignal.emit(f"[{Name}] 写入日志失败：{str(e)}", "error")

        self.FinishedSignal.emit()
