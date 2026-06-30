import os
import shutil
import subprocess
import signal
import sys

class BuildRunner:
    def __init__(self, RunUatPath: str, PluginPath: str, OutputDir: str, UseRocket: bool = True):
        self.RunUatPath = RunUatPath
        self.PluginPath = PluginPath
        self.OutputDir = OutputDir
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
        Cmd += " -TargetPlatforms=Win64"

        try:
            self.Process = subprocess.Popen(
                Cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",   # 显式 UTF-8，避免按系统 GBK 解码 UE 输出
                errors="replace",   # 个别非法字节用占位符替代，绝不因解码异常崩溃
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            FullLog = []
            while True:
                Line = self.Process.stdout.readline()
                if Line == '' and self.Process.poll() is not None:
                    break
                if Line:
                    FullLog.append(Line)
                    yield Line.strip()
            Success = self.Process.returncode == 0
            yield "EXIT_SUCCESS" if Success else "EXIT_FAILURE"
        except Exception as e:
            yield f"ERROR::{str(e)}"

    def Terminate(self):
        if self.Process and self.Process.poll() is None:
            if sys.platform == "win32":
                subprocess.call(f"taskkill /PID {self.Process.pid} /T /F", shell=True)
            else:
                self.Process.terminate()
