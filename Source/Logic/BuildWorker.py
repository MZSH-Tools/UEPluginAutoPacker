from PySide2.QtCore import QThread, Signal

from Source.Logic.Packaging import BuildOptions, CancelGate, PackagingCancelled, RunPackaging


class BuildWorker(QThread):
    LogSignal = Signal(tuple, str)
    StatusSignal = Signal(int, str)
    FinishedSignal = Signal()

    def __init__(self, EngineList, PluginName, PluginPath, OutputRoot, *, AllEngines=None,
                 Options=None, ZipOnly=False):
        super().__init__()
        self.EngineList = EngineList
        self.AllEngines = EngineList if AllEngines is None else AllEngines
        self.PluginName = PluginName
        self.PluginPath = PluginPath
        self.OutputRoot = OutputRoot
        self.Options = Options or BuildOptions()
        self.ZipOnly = ZipOnly
        self.Gate = CancelGate()
        self.CurrentName = ''

    def Stop(self):
        if self.Gate.Stop():
            self.LogSignal.emit((self.CurrentName, '当前引擎已进入提交，将完成本次提交或回滚；后续引擎取消。'), 'warn')

    def run(self):
        try:
            for Index, Engine in enumerate(self.EngineList):
                Name = Engine['Name']
                self.CurrentName = Name
                if self.Gate.ShouldStop():
                    self.StatusSignal.emit(Index, '已取消')
                    continue
                self.StatusSignal.emit(Index, '打包中')
                try:
                    Artifacts = RunPackaging(
                        Engine, self.AllEngines, self.PluginName, self.PluginPath, self.OutputRoot, self.Options,
                        ZipOnly=self.ZipOnly, Log=lambda Line: self.LogSignal.emit((Name, Line), 'info'),
                        Gate=self.Gate)
                except PackagingCancelled as Error:
                    self.StatusSignal.emit(Index, '已取消')
                    self.LogSignal.emit((Name, str(Error)), 'warn')
                except Exception as Error:
                    self.StatusSignal.emit(Index, '❌ 失败')
                    self.LogSignal.emit((Name, f'失败：{Error}'), 'error')
                else:
                    self.StatusSignal.emit(Index, '✅ 成功')
                    for Artifact in Artifacts:
                        self.LogSignal.emit((Name, f'产物：{Artifact}'), 'success')
        finally:
            self.FinishedSignal.emit()
