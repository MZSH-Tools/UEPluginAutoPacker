# ✅ ConfigManager.py（合并引擎管理逻辑）

import os
import json

class ConfigManager:
    _instance = None
    CONFIG_PATH = os.path.join(os.getenv("LOCALAPPDATA"), "UEPluginPacker", "Config.json")

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
            cls._instance._Load()
        return cls._instance

    def _Load(self):
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def Save(self):
        os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def Get(self, key: str, default=None):
        keys = key.split(".")
        current = self._data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current

    def Set(self, key: str, value):
        keys = key.split(".")
        current = self._data
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    # === 引擎管理功能 ===

    def GetEngines(self):
        return self._data.get("EngineList", [])

    def SetEngines(self, engineList):
        self._data["EngineList"] = engineList

    def AddEngine(self, engine):
        if "EngineList" not in self._data:
            self._data["EngineList"] = []
        self._data["EngineList"].append(engine)

    def RemoveEngine(self, name):
        self._data["EngineList"] = [e for e in self.GetEngines() if e.get("Name") != name]

    def SetEngineField(self, name, key, value):
        for engine in self._data.get("EngineList", []):
            if engine.get("Name") == name:
                engine[key] = value
                break

    def GetEngineField(self, name, key, default=None):
        for engine in self._data.get("EngineList", []):
            if engine.get("Name") == name:
                return engine.get(key, default)
        return default