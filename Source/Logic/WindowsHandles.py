import ctypes
import os
import stat
from ctypes import wintypes


InvalidHandle = ctypes.c_void_p(-1).value
Kernel = ctypes.WinDLL('kernel32', use_last_error=True) if os.name == 'nt' else None


class PathIdentityChanged(ValueError):
    pass


def Bind(Name, Result, *Arguments):
    Function = getattr(Kernel, Name)
    Function.restype = Result
    Function.argtypes = Arguments
    return Function


class FileInformation(ctypes.Structure):
    _fields_ = [('Attributes', wintypes.DWORD), ('Created', wintypes.FILETIME),
                ('Accessed', wintypes.FILETIME), ('Written', wintypes.FILETIME),
                ('Volume', wintypes.DWORD), ('SizeHigh', wintypes.DWORD), ('SizeLow', wintypes.DWORD),
                ('Links', wintypes.DWORD), ('IndexHigh', wintypes.DWORD), ('IndexLow', wintypes.DWORD)]


class RenameInformation(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('RootDirectory', wintypes.HANDLE),
                ('NameLength', wintypes.DWORD), ('Name', wintypes.WCHAR * 1)]


def Close(Handle):
    Bind('CloseHandle', wintypes.BOOL, wintypes.HANDLE)(Handle)


def _OpenChecked(Pathname, Expected, Access):
    CreateFile = Bind('CreateFileW', wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    ShareRead = 1
    OpenExisting = 3
    OpenReparsePointAndBackupSemantics = 0x02200000
    Handle = CreateFile(str(Pathname), Access, ShareRead, None, OpenExisting,
                        OpenReparsePointAndBackupSemantics, None)
    if Handle == InvalidHandle:
        Error = ctypes.get_last_error()
        if Error in (2, 3):
            raise PathIdentityChanged(f'路径已消失：{Pathname}')
        raise ctypes.WinError(Error, f'无法保护路径：{Pathname}')
    try:
        Info = FileInformation()
        GetInfo = Bind('GetFileInformationByHandle', wintypes.BOOL, wintypes.HANDLE,
                       ctypes.POINTER(FileInformation))
        if not GetInfo(Handle, ctypes.byref(Info)):
            raise ctypes.WinError(ctypes.get_last_error())
        Identity = (Info.Volume, (Info.IndexHigh << 32) | Info.IndexLow)
        IsDirectory = bool(Info.Attributes & stat.FILE_ATTRIBUTE_DIRECTORY)
        if (IsDirectory != stat.S_ISDIR(Expected.st_mode) or not IsDirectory and Info.Links != 1
                or Info.Attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or not Identity[1] or Identity != (Expected.st_dev, Expected.st_ino)):
            raise PathIdentityChanged(f'拒绝 reparse、硬链接或路径身份变化：{Pathname}')
        return Handle
    except BaseException:
        Close(Handle)
        raise


def OpenDirectory(Pathname, Expected):
    return _OpenChecked(Pathname, Expected, 0x81)


def WriteLeaf(Pathname, Data, Expected):
    import msvcrt

    GenericWrite = 0x40000000
    Handle = _OpenChecked(Pathname, Expected, GenericWrite | 0x80)
    try:
        Descriptor = msvcrt.open_osfhandle(Handle, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        Close(Handle)
        raise
    try:
        Stream = os.fdopen(Descriptor, 'wb')
    except BaseException:
        os.close(Descriptor)
        raise
    with Stream:
        Stream.write(Data)
        Stream.truncate()


def RenameLeaf(From, NewName, Expected):
    DeleteAndReadAttributes = 0x10080
    Handle = _OpenChecked(From, Expected, DeleteAndReadAttributes)
    try:
        Native = ctypes.WinDLL('ntdll')
        Rename = Native.NtSetInformationFile
        Rename.argtypes = (wintypes.HANDLE, wintypes.LPVOID, wintypes.LPVOID, wintypes.ULONG, ctypes.c_int)
        Rename.restype = wintypes.LONG
        EncodeError = Native.RtlNtStatusToDosError
        EncodeError.argtypes = (wintypes.LONG,)
        EncodeError.restype = wintypes.ULONG
        Name = NewName.encode('utf-16-le')
        Offset = RenameInformation.Name.offset
        Buffer = ctypes.create_string_buffer(max(ctypes.sizeof(RenameInformation), Offset + len(Name) + 2))
        Info = RenameInformation.from_buffer(Buffer)
        Info.NameLength = len(Name)
        ctypes.memmove(ctypes.addressof(Buffer) + Offset, Name, len(Name))
        IoStatus = (ctypes.c_size_t * 2)()
        FileRenameInformation = 10
        Result = Rename(Handle, ctypes.byref(IoStatus), Buffer, len(Buffer), FileRenameInformation)
        if Result != 0:
            raise ctypes.WinError(EncodeError(Result))
    finally:
        Close(Handle)
