import os
import shutil
import subprocess

class BuildRunner:
    def __init__(self, RunUatPath: str, PluginPath: str, OutputDir: str, TargetPlatforms: str):
        self.RunUatPath = RunUatPath
        self.PluginPath = PluginPath
        self.OutputDir = OutputDir
        self.TargetPlatforms = TargetPlatforms

    def CleanOutputDir(self):
        if os.path.exists(self.OutputDir):
            shutil.rmtree(self.OutputDir)
        os.makedirs(self.OutputDir, exist_ok=True)

    def RunBuild(self):
        self.CleanOutputDir()
        Cmd = f'"{self.RunUatPath}" BuildPlugin -Plugin="{self.PluginPath}" -Package="{self.OutputDir}" -Rocket -TargetPlatforms={self.TargetPlatforms}'
        try:
            subprocess.run(Cmd, check=True, shell=True)
            return True, ""
        except subprocess.CalledProcessError as E:
            FailedLogPath = os.path.join(self.OutputDir, "Failed.log")
            with open(FailedLogPath, "w", encoding="utf-8") as LogFile:
                LogFile.write(str(E))
            return False, str(E)
