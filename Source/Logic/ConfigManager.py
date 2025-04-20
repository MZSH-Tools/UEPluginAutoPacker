import os
import json

class ConfigManager:
    _Instance = None

    def __new__(cls):
        if cls._Instance is None:
            cls._Instance = super().__new__(cls)
        return cls._Instance

    def __init__(self):
        if hasattr(self, "_Initialized"):
            return
        self._Initialized = True

        LocalAppData = os.getenv("LOCALAPPDATA")
        self.ConfigDir = os.path.join(LocalAppData, "UEPluginPacker")
        self.ConfigPath = os.path.join(self.ConfigDir, "settings.json")
        self.ConfigData = {}
        self.Load()

    def Load(self):
        if os.path.exists(self.ConfigPath):
            with open(self.ConfigPath, "r", encoding="utf-8") as F:
                self.ConfigData = json.load(F)

    def Get(self, Key: str, Default=None):
        return self.ConfigData.get(Key, Default)

    def Set(self, Key: str, Value):
        self.ConfigData[Key] = Value
        self.Save()

    def Save(self):
        os.makedirs(self.ConfigDir, exist_ok=True)
        with open(self.ConfigPath, "w", encoding="utf-8") as F:
            json.dump(self.ConfigData, F, indent=2, ensure_ascii=False)
