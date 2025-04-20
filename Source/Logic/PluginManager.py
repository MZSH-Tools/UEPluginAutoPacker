import os
import glob

class PluginManager:
    _Instance = None

    def __new__(cls):
        if cls._Instance is None:
            cls._Instance = super().__new__(cls)
        return cls._Instance

    def __init__(self):
        if hasattr(self, "_Initialized"):
            return
        self._Initialized = True
        self.ProjectRoot = os.getcwd()

    def GetPluginList(self):
        Plugins = []
        PluginDir = os.path.join(self.ProjectRoot, "Plugins")
        if os.path.exists(PluginDir):
            for Root, _, Files in os.walk(PluginDir):
                for File in Files:
                    if File.endswith(".uplugin"):
                        Plugins.append(os.path.join(Root, File))
        return Plugins

    def GetDefaultPlugin(self):
        UprojectList = glob.glob(os.path.join(self.ProjectRoot, "*.uproject"))
        if UprojectList:
            ProjectName = os.path.splitext(os.path.basename(UprojectList[0]))[0]
            for Path in self.GetPluginList():
                if ProjectName in Path:
                    return Path
        return ""
