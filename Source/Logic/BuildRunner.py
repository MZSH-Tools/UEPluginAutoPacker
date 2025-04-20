import os
import shutil
import subprocess
import signal
import sys

class BuildRunner:
    def __init__(self, RunUatPath: str, PluginPath: str, OutputDir: str, TargetPlatforms: str, UseRocket: bool = True):
        self.RunUatPath = RunUatPath
        self.PluginPath = PluginPath
        self.OutputDir = OutputDir
        self.TargetPlatforms = TargetPlatforms
        self.UseRocket = UseRocket
        self.Process = None

    def CleanOutputDir(self):
        if os.path.exists(self.OutputDir):
            shutil.rmtree(self.OutputDir)
        os.makedirs(self.OutputDir, exist_ok=True)

    def RunBuild(self):
        self.CleanOutputDir()
        Cmd = f'"{self.RunUatPath}" BuildPlugin -Plugin="{self.PluginPath}" -Package="{self.OutputDir}"'
        if self.UseRocket:
            Cmd += " -Rocket"
        Cmd += f" -TargetPlatforms={self.TargetPlatforms}"

        try:
            self.Process = subprocess.Popen(
                Cmd,
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            self.Process.wait()
            return self.Process.returncode == 0, ""
        except Exception as e:
            return False, str(e)

    def Terminate(self):
        if self.Process and self.Process.poll() is None:
            if sys.platform == "win32":
                # ✅ 使用 taskkill 强制终止整个子进程树，避免 Y/N 提示
                subprocess.call(f"taskkill /PID {self.Process.pid} /T /F", shell=True)
            else:
                self.Process.terminate()
