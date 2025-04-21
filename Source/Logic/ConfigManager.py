import os
import json

class ConfigManager:
    _Instance = None
    ConfigPath = os.path.join(os.getenv("LOCALAPPDATA"), "UEPluginPacker", "Config.json")

    def __new__(cls):
        if cls._Instance is None:
            cls._Instance = super().__new__(cls)
            cls._Instance._Data = {}
            cls._Instance._Load()
        return cls._Instance

    def _Load(self):
        if os.path.exists(self.ConfigPath):
            try:
                with open(self.ConfigPath, "r", encoding="utf-8") as File:
                    self._Data = json.load(File)
            except Exception:
                self._Data = {}
        else:
            self._Data = {}

    def Save(self):
        os.makedirs(os.path.dirname(self.ConfigPath), exist_ok=True)
        with open(self.ConfigPath, "w", encoding="utf-8") as File:
            json.dump(self._Data, File, indent=2, ensure_ascii=False)

    def Get(self, Key: str, Default=None):
        Keys = Key.split(".")
        Current = self._Data
        for K in Keys:
            if isinstance(Current, dict) and K in Current:
                Current = Current[K]
            else:
                return Default
        return Current

    def Set(self, Key: str, Value):
        Keys = Key.split(".")
        Current = self._Data
        for K in Keys[:-1]:
            if K not in Current or not isinstance(Current[K], dict):
                Current[K] = {}
            Current = Current[K]
        Current[Keys[-1]] = Value
