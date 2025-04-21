from PySide2.QtCore import QThread, Signal
from Source.Logic.BuildRunner import BuildRunner
from Source.Logic.PostProcessor import RunPostProcess
import os

class BuildWorker(QThread):
    LogSignal = Signal(tuple, str)         # ((引擎名, 日志行), 等级)
    StatusSignal = Signal(int, str)        # (行号, 状态文字)
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
                self.LogSignal.emit((Name, "已跳过打包"), "warn")
                continue

            self.StatusSignal.emit(Index, "打包中")
            self.LogSignal.emit((Name, "开始打包..."), "info")

            UatPath = os.path.join(Engine["Path"], "Engine", "Build", "BatchFiles", "RunUAT.bat")
            OutputDir = os.path.join(self.OutputRoot, self.PluginName, Name)
            IsSourceBuild = Engine.get("SourceBuild", False)
            UseRocket = not IsSourceBuild

            Runner = BuildRunner(
                RunUatPath=UatPath,
                PluginPath=self.PluginPath,
                OutputDir=OutputDir,
                UseRocket=UseRocket
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
                    LogLines.append(Line)
                    self.LogSignal.emit((Name, Line), "info")

            self.CurrentRunner = None

            if self.ShouldStop:
                self.StatusSignal.emit(Index, "已取消")
                self.LogSignal.emit((Name, "打包被用户终止"), "warn")
                break

            if Success:
                self.StatusSignal.emit(Index, "整理中")
                self.LogSignal.emit((Name, "✅ 构建成功，开始整理插件..."), "info")
                try:
                    PostLogs = RunPostProcess(OutputDir, lambda: self.ShouldStop)
                    for line in PostLogs:
                        self.LogSignal.emit((Name, line), "info")
                except Exception as e:
                    self.LogSignal.emit((Name, f"整理插件时出错：{str(e)}"), "error")

                if self.ShouldStop:
                    self.StatusSignal.emit(Index, "已取消")
                    self.LogSignal.emit((Name, "整理被用户终止"), "warn")
                    break

                self.StatusSignal.emit(Index, "✅ 成功")
                self.LogSignal.emit((Name, "🎉 整理完成"), "success")
            else:
                self.StatusSignal.emit(Index, "❌ 失败")
                self.LogSignal.emit((Name, "❌ 构建失败"), "error")

                FailedLogPath = os.path.join(OutputDir, "Failed.log")
                os.makedirs(OutputDir, exist_ok=True)
                try:
                    with open(FailedLogPath, "w", encoding="utf-8") as f:
                        f.write("\n".join(LogLines))
                except Exception as e:
                    self.LogSignal.emit((Name, f"写入日志失败：{str(e)}"), "error")

        self.FinishedSignal.emit()

        if self.ShouldStop:
            for index in range(Index + 1, len(self.EngineList)):
                self.StatusSignal.emit(index, "已取消")
