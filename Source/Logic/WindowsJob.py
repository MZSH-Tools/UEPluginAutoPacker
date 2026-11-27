import ctypes
import subprocess
import time
from ctypes import wintypes
from threading import RLock

from Source.Logic.WindowsHandles import Bind, Close, InvalidHandle


class ThreadEntry(ctypes.Structure):
    _fields_ = [('Size', wintypes.DWORD), ('Usage', wintypes.DWORD), ('ThreadId', wintypes.DWORD),
                ('Owner', wintypes.DWORD), ('BasePriority', wintypes.LONG),
                ('DeltaPriority', wintypes.LONG), ('Flags', wintypes.DWORD)]


class JobAccounting(ctypes.Structure):
    _fields_ = [('Times', ctypes.c_longlong * 4), ('PageFaults', wintypes.DWORD),
                ('TotalProcesses', wintypes.DWORD), ('ActiveProcesses', wintypes.DWORD),
                ('TerminatedProcesses', wintypes.DWORD)]


class JobProcessList(ctypes.Structure):
    _fields_ = [('Assigned', wintypes.DWORD), ('Listed', wintypes.DWORD), ('Ids', ctypes.c_size_t * 1)]


def _Check(Result):
    if not Result:
        raise ctypes.WinError(ctypes.get_last_error())
    return Result


def _InitialThread(ProcessId):
    Snapshot = Bind('CreateToolhelp32Snapshot', wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)(4, 0)
    if Snapshot == InvalidHandle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        Entry = ThreadEntry()
        Entry.Size = ctypes.sizeof(Entry)
        ArgumentTypes = (wintypes.HANDLE, ctypes.POINTER(ThreadEntry))
        First = Bind('Thread32First', wintypes.BOOL, *ArgumentTypes)
        Next = Bind('Thread32Next', wintypes.BOOL, *ArgumentTypes)
        Found = []
        Present = First(Snapshot, ctypes.byref(Entry))
        while Present:
            if Entry.Size >= ThreadEntry.Owner.offset + ctypes.sizeof(wintypes.DWORD) and Entry.Owner == ProcessId:
                Found.append(Entry.ThreadId)
            Entry.Size = ctypes.sizeof(Entry)
            Present = Next(Snapshot, ctypes.byref(Entry))
        if ctypes.get_last_error() != 18 or len(Found) != 1:
            raise RuntimeError(f'无法唯一确认挂起进程的初始线程：{ProcessId}')
        return _Check(Bind('OpenThread', wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)(
            0x802, False, Found[0]))
    finally:
        Close(Snapshot)


class WindowsJob:
    def __init__(self):
        self.Handle = _Check(Bind('CreateJobObjectW', wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCWSTR)(None, None))
        self.Lock = RLock()
        self.Process = None
        self.Assigned = False
        self.Confirmed = False

    def __enter__(self):
        return self

    def Launch(self, Command, **Options):
        CreateSuspended = 0x4
        Flags = Options.pop('creationflags', 0)
        self.Process = subprocess.Popen(Command, creationflags=Flags | CreateSuspended, **Options)
        Thread = _InitialThread(self.Process.pid)
        try:
            Owner = Bind('GetProcessIdOfThread', wintypes.DWORD, wintypes.HANDLE)
            if Owner(Thread) != self.Process.pid or self.Process.poll() is not None:
                raise RuntimeError('挂起线程不属于本次 UAT 进程')
            Assign = Bind('AssignProcessToJobObject', wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE)
            _Check(Assign(self.Handle, int(self.Process._handle)))
            self.Assigned = True
            Resume = Bind('ResumeThread', wintypes.DWORD, wintypes.HANDLE)
            if Resume(Thread) != 1:
                raise RuntimeError('无法恢复本次 UAT 的初始线程')
        finally:
            Close(Thread)
        return self.Process

    def _Empty(self):
        Query = Bind('QueryInformationJobObject', wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
                     wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID)
        Accounting = JobAccounting()
        _Check(Query(self.Handle, 1, ctypes.byref(Accounting), ctypes.sizeof(Accounting), None))
        if Accounting.ActiveProcesses:
            return False
        Processes = JobProcessList()
        _Check(Query(self.Handle, 3, ctypes.byref(Processes), ctypes.sizeof(Processes), None))
        return Processes.Assigned == Processes.Listed == 0

    def Wait(self, Process, Timeout=None, StopRequested=lambda: False):
        if Process is not self.Process:
            raise ValueError('不能等待不属于本 Job 的进程')
        Deadline = None if Timeout is None else time.monotonic() + Timeout
        Stopped = False
        while True:
            if not Stopped and StopRequested():
                self.Terminate()
                Stopped = True
                Deadline = time.monotonic() + 10 if Deadline is None else Deadline
            ExitCode = Process.poll() if Process is not None else None
            if (Process is None or ExitCode is not None) and self._Empty():
                break
            if Deadline is not None and time.monotonic() >= Deadline:
                raise RuntimeError('无法确认 UAT 进程树已退出')
            time.sleep(0.05)
        self.Confirmed = True
        return ExitCode

    def Terminate(self):
        with self.Lock:
            if self.Handle is None or self.Confirmed:
                return
            if self.Assigned:
                Terminate = Bind('TerminateJobObject', wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
                _Check(Terminate(self.Handle, 1))
            elif self.Process is not None:
                self.Process.terminate()

    def __exit__(self, ErrorType, Error, Traceback):
        if not self.Confirmed:
            self.Terminate()
            self.Wait(self.Process, Timeout=10)
        with self.Lock:
            Close(self.Handle)
            self.Handle = None
