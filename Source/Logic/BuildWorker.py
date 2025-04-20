from PySide2.QtCore import QThread, Signal
from Source.Logic.BuildRunner import BuildRunner
import os

class BuildWorker(QThread):
    LogSignal = Signal(str, str)           # (文本, 等级)
    StatusSignal = Signal(int, str)        # (引擎索引, 状态)
    FinishedSignal = Signal()

    def __init__(self, EngineList, PluginName, PluginPath, OutputRoot, Platforms):
        super().__init__()
        self.EngineList = EngineList              # 多个引擎
        self.PluginName = PluginName              # 插件名
        self.PluginPath = PluginPath              # .uplugin 路径
        self.OutputRoot = OutputRoot              # 固定输出目录（如 PackagedPlugins）
        self.Platforms = Platforms                # "Win64,Linux"
        self.ShouldStop = False
        self.CurrentRunner = None                 # 当前执行的 BuildRunner

    def Stop(self):
        self.ShouldStop = True
        if self.CurrentRunner:
            self.CurrentRunner.Terminate()

    def run(self):
        for Index, Engine in enumerate(self.EngineList):
            if self.ShouldStop:
                self.StatusSignal.emit(Index, "已取消")
                self.LogSignal.emit(f"[{Engine['Name']}] 已跳过打包", "warn")
                continue

            self.StatusSignal.emit(Index, "打包中")
            self.LogSignal.emit(f"[{Engine['Name']}] 开始打包...", "info")

            # 构造路径
            UatPath = os.path.join(Engine["Path"], "Engine", "Build", "BatchFiles", "RunUAT.bat")
            OutputDir = os.path.join(self.OutputRoot, self.PluginName, Engine["Name"])

            # 判断是否为源码引擎
            IsSourceBuild = Engine.get("SourceBuild", False)
            UseRocket = not IsSourceBuild

            # 构建器
            Runner = BuildRunner(
                RunUatPath=UatPath,
                PluginPath=self.PluginPath,
                OutputDir=OutputDir,
                TargetPlatforms=self.Platforms,
                UseRocket=UseRocket
            )

            self.CurrentRunner = Runner
            Success, Err = Runner.RunBuild()
            self.CurrentRunner = None

            if self.ShouldStop:
                self.StatusSignal.emit(Index, "已取消")
                self.LogSignal.emit(f"[{Engine['Name']}] 被用户终止", "warn")
                break

            if Success:
                self.StatusSignal.emit(Index, "✅ 成功")
                self.LogSignal.emit(f"[{Engine['Name']}] 打包成功", "success")
            else:
                self.StatusSignal.emit(Index, "❌ 失败")
                self.LogSignal.emit(f"[{Engine['Name']}] 打包失败：{Err}", "error")

                FailedLogPath = os.path.join(OutputDir, "Failed.log")
                with open(FailedLogPath, "w", encoding="utf-8") as f:
                    f.write(Err or "Unknown Error")

        self.FinishedSignal.emit()
