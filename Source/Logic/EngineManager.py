from Source.Logic.ConfigManager import ConfigManager

class EngineManager:
    _Instance = None

    def __new__(cls):
        if cls._Instance is None:
            cls._Instance = super().__new__(cls)
        return cls._Instance

    def __init__(self):
        if hasattr(self, "_Initialized"):
            return
        self._Initialized = True
        self.Config = ConfigManager()
        self.EngineList = self.Config.Get("Engines", [])

    def GetEngines(self):
        return self.EngineList

    def AddEngine(self, EngineData: dict):
        self.EngineList.append(EngineData)
        self.Save()

    def RemoveEngine(self, EngineName: str):
        self.EngineList = [e for e in self.EngineList if e["Name"] != EngineName]
        self.Save()

    def Save(self):
        self.Config.Set("Engines", self.EngineList)
