import os
import re
import shutil
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path

from Source.Logic.WindowsHandles import Close, OpenDirectory, PathIdentityChanged, RenameLeaf, WriteLeaf


def ValidateName(Name):
    if not isinstance(Name, str) or Name != Name.strip() or Name.startswith('.'):
        raise ValueError(f'非法插件或引擎名：{Name!r}')
    ValidateComponent(Name)
    return Name


def ValidateComponent(Name):
    if (not Name or Name in ('.', '..') or Name.endswith(('.', ' ')) or len(Name.encode('utf-16-le')) > 510
            or any(Character in '<>:/\\|?*' or ord(Character) < 32 or ord(Character) == 34 for Character in Name)
            or re.fullmatch(r'CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³]',
                            Name.split('.')[0].rstrip().upper())):
        raise ValueError(f'不安全的路径名称：{Name!r}')


def EntryState(Pathname):
    try:
        Info = Pathname.lstat()
    except FileNotFoundError:
        return None
    if (stat.S_ISLNK(Info.st_mode)
            or getattr(Info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
        raise ValueError(f'拒绝链接、junction 或 reparse 路径：{Pathname}')
    if (stat.S_ISREG(Info.st_mode) and Info.st_nlink == 1) or stat.S_ISDIR(Info.st_mode):
        return Info
    raise ValueError(f'拒绝特殊文件或硬链接：{Pathname}')


def _AbsolutePath(Value):
    Candidate = Path(Value)
    if ('..' in Candidate.parts or (Candidate.anchor and not Candidate.is_absolute())
            or Candidate.anchor.startswith(('\\\\?\\', '\\\\.\\'))):
        raise ValueError(f'不安全的路径：{Value}')
    return Path.cwd() / Candidate


def CheckedPath(Value):
    Candidate = _AbsolutePath(Value)
    Current = Path(Candidate.anchor)
    ParentState = EntryState(Current)
    for Part in Candidate.parts[1:]:
        ValidateComponent(Part)
        Next = Current / Part
        if ParentState is not None:
            if not stat.S_ISDIR(ParentState.st_mode):
                raise ValueError(f'目标的上级不是目录：{Current}')
            Aliases = [Name for Name in os.listdir(Current) if Name.casefold() == Part.casefold()]
            ParentState = EntryState(Next)
            if Aliases not in ([], [Part]) or (ParentState is not None and not Aliases):
                raise ValueError(f'拒绝大小写或短文件名别名：{Next}')
        Current = Next
    return Current


@contextmanager
def PinDirectories(Value, *, Create=False):
    Candidate = _AbsolutePath(Value)
    with ExitStack() as Handles:
        for Directory in (*reversed(Candidate.parents), Candidate):
            if Directory != Path(Directory.anchor):
                ValidateComponent(Directory.name)
                Aliases = [Name for Name in os.listdir(Directory.parent)
                           if Name.casefold() == Directory.name.casefold()]
                if Aliases not in ([], [Directory.name]):
                    raise ValueError(f'拒绝大小写别名：{Directory}')
            else:
                Aliases = [Directory.name]
            State = EntryState(Directory)
            if State is None and Create and not Aliases:
                Directory.mkdir()
                State = EntryState(Directory)
                Aliases = [Directory.name]
            if State is None or not stat.S_ISDIR(State.st_mode) or not Aliases:
                raise ValueError(f'无法保护目录或路径为短文件名别名：{Directory}')
            if os.name == 'nt':
                Handles.callback(Close, OpenDirectory(Directory, State))
        yield Candidate


def StateIdentity(Info):
    return None if Info is None else (Info.st_dev, Info.st_ino, Info.st_mode, Info.st_mtime_ns, Info.st_size)


def WriteCheckedFile(Value, Data, Expected):
    Target = _AbsolutePath(Value)
    with PinDirectories(Target.parent):
        Target = CheckedPath(Target)
        if Expected is None:
            with Target.open('xb') as Stream:
                Stream.write(Data)
        elif not stat.S_ISREG(Expected.st_mode):
            raise ValueError(f'不是可覆盖的普通文件：{Target}')
        elif os.name == 'nt':
            WriteLeaf(Target, Data, Expected)
        else:
            Descriptor = os.open(Target, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(Descriptor, 'wb') as Stream:
                Info = os.fstat(Stream.fileno())
                if Info.st_nlink != 1 or StateIdentity(Info) != StateIdentity(Expected):
                    raise PathIdentityChanged(f'写入目标身份变化：{Target}')
                Stream.write(Data)
                Stream.truncate()


def RenameSibling(From, To, ExpectedIdentity=None):
    From, To = _AbsolutePath(From), _AbsolutePath(To)
    if From.parent.parts != To.parent.parts:
        raise ValueError(f'受保护的重命名要求同一父目录：{From} → {To}')
    with PinDirectories(From.parent):
        try:
            Expected = EntryState(CheckedPath(From))
            Destination = EntryState(CheckedPath(To))
        except ValueError as Error:
            raise PathIdentityChanged(f'提交或回滚路径状态变化：{From} → {To}') from Error
        if (Expected is None or Destination is not None
                or ExpectedIdentity is not None and StateIdentity(Expected) != ExpectedIdentity):
            raise PathIdentityChanged(f'提交或回滚路径状态变化：{From} → {To}')
        if os.name == 'nt':
            try:
                RenameLeaf(From, To.name, Expected)
            except FileExistsError as Error:
                raise PathIdentityChanged(f'重命名目标已出现：{To}') from Error
        else:
            os.rename(From, To)


def CheckOverlap(Output, Protected):
    def Identity(Pathname):
        Info = EntryState(Pathname)
        return (Info.st_dev, Info.st_ino) if Info is not None and Info.st_ino else None

    OutputParts = tuple(Part.casefold() for Part in Output.parts)
    OutputIdentity = Identity(Output)
    OutputAncestors = {Identity(Ancestor) for Ancestor in Output.parents}
    for Original in Protected:
        OriginalParts = tuple(Part.casefold() for Part in Original.parts)
        Shared = min(len(OutputParts), len(OriginalParts))
        OriginalIdentity = Identity(Original)
        if (OutputParts[:Shared] == OriginalParts[:Shared]
                or OriginalIdentity is not None and OriginalIdentity in OutputAncestors | {OutputIdentity}
                or OutputIdentity is not None and any(Identity(Ancestor) == OutputIdentity
                                                       for Ancestor in Original.parents)):
            raise ValueError(f'输出与源插件或引擎根重叠：{Output} ↔ {Original}')


def WalkTree(Root):
    def RaiseError(Error):
        raise Error

    Info = EntryState(Root)
    if Info is None or not stat.S_ISDIR(Info.st_mode):
        raise ValueError(f'不是有效目录：{Root}')
    for Directory, Dirs, Files in os.walk(Root, onerror=RaiseError):
        Parent = Path(Directory)
        Seen = set()
        for Name in Dirs + Files:
            ValidateComponent(Name)
            if Name.casefold() in Seen:
                raise ValueError(f'目录中存在大小写别名：{Parent / Name}')
            Seen.add(Name.casefold())
            if EntryState(Parent / Name) is None:
                raise ValueError(f'扫描时文件消失：{Parent / Name}')
        yield Parent, Dirs, Files


def CopyToStage(Source, Destination, Ignore=lambda Directory, Names: ()):
    with PinDirectories(Destination.parent, Create=True):
        Destination.mkdir()
        for Directory, Dirs, Files in WalkTree(Source):
            Skip = set(Ignore(Directory, Dirs + Files))
            Dirs[:] = [Name for Name in Dirs if Name not in Skip]
            Target = Destination / Directory.relative_to(Source)
            with PinDirectories(Target):
                for Name in Dirs:
                    (Target / Name).mkdir()
                for Name in Files:
                    if Name not in Skip:
                        with CheckedPath(Directory / Name).open('rb') as Original, (Target / Name).open('xb') as Copy:
                            shutil.copyfileobj(Original, Copy)


@contextmanager
def TargetLock(Parent):
    with PinDirectories(Parent) as Parent, _LockPinnedTarget(Parent):
        yield


@contextmanager
def _LockPinnedTarget(Parent):
    LockPath = CheckedPath(Parent / '.uepluginpacker.lock')
    Marker = b'UEPluginPacker lock v1\n'
    try:
        with LockPath.open('xb') as Created:
            Created.write(Marker)
    except FileExistsError:
        pass
    with LockPath.open('r+b') as Handle:
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(Handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(Handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as Error:
            raise RuntimeError(f'打包目标锁被占用：{LockPath}') from Error
        Handle.seek(1)
        if Handle.read(len(Marker)) != Marker[1:]:
            raise ValueError(f'锁文件归属不明：{LockPath}')
        yield
