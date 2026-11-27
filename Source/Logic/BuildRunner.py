import os
import subprocess
from pathlib import Path
from contextlib import ExitStack
from queue import Empty, Full, Queue
from threading import Event, Thread

from Source.Logic.PackagingPaths import PinDirectories
from Source.Logic.WindowsJob import WindowsJob


def BuildEnvironment(Stage, Inherited):
    Work = Stage / 'uat-environment'
    Overrides = {'uebp_EngineSavedFolder': Work / 'saved', 'uebp_LogFolder': Work / 'logs',
                 'uebp_FinalLogFolder': Work / 'final-logs', 'uebp_CSVFile': Work / 'stats.csv',
                 'TMP': Work / 'temp', 'TEMP': Work / 'temp'}
    Removed = {Key.casefold() for Key in (*Overrides, 'uebp_LOCAL_ROOT')}
    Environment = {Key: Value for Key, Value in Inherited.items() if Key.casefold() not in Removed}
    with PinDirectories(Work, Create=True):
        for Directory in {Path(Value) for Key, Value in Overrides.items() if Key != 'uebp_CSVFile'}:
            Directory.mkdir()
    Environment.update({Key: str(Value) for Key, Value in Overrides.items()})
    return Environment


class BuildRunner:
    def __init__(self, RunUatPath: str, PluginPath: str, OutputDir: str, UseRocket: bool = True, *, StageDir):
        self.RunUatPath = RunUatPath
        self.PluginPath = PluginPath
        self.OutputDir = OutputDir
        self.UseRocket = UseRocket
        self.Stage = StageDir
        self.StopRequested = Event()

    def RunBuild(self):
        if self.StopRequested.is_set():
            yield 'EXIT_FAILURE'
            return
        Stage = self.Stage
        Environment = BuildEnvironment(Stage, os.environ)
        Command = f'"{self.RunUatPath}" BuildPlugin -Plugin="{self.PluginPath}" -Package="{self.OutputDir}"'
        if self.UseRocket:
            Command += ' -Rocket'
        Command += ' -TargetPlatforms=Win64'
        Running = Stage / 'running.json'
        with Running.open('x', encoding='utf-8') as Marker:
            Marker.write('{"state":"UAT process tree not confirmed empty"}\n')
            Marker.flush()
            os.fsync(Marker.fileno())
        Job = WindowsJob()
        try:
            with ExitStack() as Guards:
                for Key in ('uebp_EngineSavedFolder', 'uebp_LogFolder', 'uebp_FinalLogFolder', 'TMP'):
                    Guards.enter_context(PinDirectories(Environment[Key]))
                Guards.enter_context(Job)
                Process = Job.Launch(Command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding='utf-8', errors='replace', env=Environment,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                Lines = Queue(maxsize=256)
                ReaderDone = Event()

                def Enqueue(Value):
                    while not ReaderDone.is_set():
                        try:
                            Lines.put(Value, timeout=0.1)
                            return
                        except Full:
                            continue

                def ReadOutput():
                    try:
                        with Process.stdout as Output:
                            for Line in Output:
                                Enqueue(Line.strip())
                    except Exception as Error:
                        Enqueue(Error)
                    finally:
                        Enqueue(None)

                Thread(target=ReadOutput, daemon=True).start()
                try:
                    while not self.StopRequested.is_set():
                        try:
                            Line = Lines.get(timeout=0.1)
                        except Empty:
                            continue
                        if Line is None:
                            break
                        if isinstance(Line, Exception):
                            raise Line
                        yield Line
                    ExitCode = Job.Wait(Process, StopRequested=self.StopRequested.is_set)
                finally:
                    ReaderDone.set()
        finally:
            if Job.Confirmed and Job.Handle is None:
                Running.unlink()
        yield 'EXIT_SUCCESS' if ExitCode == 0 and not self.StopRequested.is_set() else 'EXIT_FAILURE'

    def Terminate(self):
        self.StopRequested.set()
