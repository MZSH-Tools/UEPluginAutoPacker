import hashlib
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Optional

from Source.Logic.BuildRunner import BuildRunner
from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.PackagingPaths import (CheckOverlap, CheckedPath, CopyToStage, EntryState, PinDirectories,
                                         RenameSibling, StateIdentity, TargetLock, ValidateName, WalkTree,
                                         WriteCheckedFile)
from Source.Logic.PluginPayload import (CompleteFabURL, Dependency, DependencyFilterNames, DependencyFilters,
                                        InspectPlugin, JsonText, LocalEntries, OwnBinary, ReadJson, TopExcluded,
                                        ValidateDescriptor, ValidateZip, WriteSourceZip)
from Source.Logic.PostProcessor import RunPostProcess
from Source.Logic.WindowsHandles import PathIdentityChanged


@dataclass(frozen=True)
class BuildOptions:
    Profile: Optional[str] = None
    Zip: Optional[bool] = None
    NoPost: bool = False
    KeepBinaries: bool = False
    DeleteOutput: bool = False
    AddVersion: Optional[bool] = None

    def __post_init__(self):
        if self.Profile not in (None, 'fab', 'deploy'):
            raise ValueError(f'未知打包用途：{self.Profile}')
        if self.Profile and self.NoPost:
            raise ValueError('--profile 与 --no-post 不可同时使用；跳过后处理请省略 --profile')
        if self.Profile == 'fab' and self.KeepBinaries:
            raise ValueError('--profile fab 与 --keep-binaries 不可同时使用')
        if self.DeleteOutput and not self.MakeZip:
            raise ValueError('删除构建输出必须同时生成 ZIP，请使用 --zip')

    @property
    def MakeZip(self):
        return self.Profile == 'fab' if self.Zip is None else self.Zip


class PackagingCancelled(Exception):
    pass


class CancelGate:
    def __init__(self):
        self.Lock = RLock()
        self.Cancelled = False
        self.Committing = False
        self.Runner = None

    def Stop(self):
        with self.Lock:
            self.Cancelled = True
            if self.Runner is not None:
                self.Runner.Terminate()
            return self.Committing

    def SetRunner(self, Runner):
        with self.Lock:
            self.Runner = Runner
            if Runner is not None and self.Cancelled:
                Runner.Terminate()

    def ShouldStop(self):
        return self.Cancelled

    @contextmanager
    def Commit(self):
        with self.Lock:
            self.Committing = True
            if self.Cancelled:
                self.Committing = False
                raise PackagingCancelled('打包已取消，未提交产物')
        try:
            yield
        finally:
            with self.Lock:
                self.Committing = False


def ReadEngineVersion(EngineRoot):
    VersionFile = CheckedPath(Path(EngineRoot) / 'Engine/Build/Build.version')
    Fields = ReadJson(VersionFile.read_text(encoding='utf-8-sig'))
    Parts = [Fields.get(Key) for Key in ('MajorVersion', 'MinorVersion', 'PatchVersion')]
    if any(type(Value) is not int or Value < 0 for Value in Parts) or Parts[0] == 0:
        raise ValueError(f'引擎版本字段无效：{VersionFile}')
    return '.'.join(map(str, Parts))


def ZipVersion(Version):
    return Version.rsplit('.', 1)[0]


def CheckArtifactVersion(Fields, Version):
    if 'EngineVersion' not in Fields:
        return
    Recorded = Fields['EngineVersion']
    if (not isinstance(Recorded, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', Recorded)
            or Recorded.split('.')[:2] != Version.split('.')[:2]):
        raise ValueError(f'产物引擎版本不匹配：{Recorded!r}，当前选择 {Version}')


def ValidateSelection(Engines, MakeZip):
    Versions = {}
    for Engine in Engines:
        ValidateName(Engine['Name'])
        if not MakeZip:
            continue
        try:
            Version = ZipVersion(ReadEngineVersion(Engine['Path']))
        except (OSError, ValueError):
            continue
        if Version in Versions:
            raise ValueError(f'{Versions[Version]} 与 {Engine["Name"]} 对应同一 ZIP 版本 {Version}，请分开选择')
        Versions[Version] = Engine['Name']


def _CheckSourceOptions(Name, Source, Root, AllEngines, Engine):
    Names = set()
    Roots = []
    for Configured in AllEngines:
        Key = ValidateName(Configured['Name']).casefold()
        if Key in Names:
            raise ValueError(f'配置中有重复或别名引擎：{Configured["Name"]}')
        Names.add(Key)
        if not Path(Configured['Path']).is_absolute():
            raise ValueError(f'引擎路径必须是绝对路径：{Configured["Path"]}')
        Roots.append(CheckedPath(Configured['Path']))
    if Engine not in AllEngines:
        raise ValueError('选中引擎不在配置中')
    if Source.name != f'{Name}.uplugin' or Source.parent.name != Name:
        raise ValueError(f'插件与源描述符名称不一致：{Source}')
    CheckOverlap(Root, [Source.parent.parent, *Roots])


def ArtifactIdentity(Target):
    return _FileIdentity(CheckedPath(Target))


def _FileIdentity(Target):
    return StateIdentity(EntryState(Target))


def _WriteJournal(Journal, Moves):
    with Journal.open('x', encoding='utf-8') as Handle:
        Handle.write(JsonText({'ordered_moves': [[str(From), str(To)] for From, To, _ in Moves]}))
        Handle.flush()
        os.fsync(Handle.fileno())


def CommitArtifacts(Stage, Items, *, ExpectedNew=None, Retire=None):
    with PinDirectories(Stage):
        _CommitPinned(Stage, Items, ExpectedNew, Retire)


def _CommitPinned(Stage, Items, ExpectedNew, Retire):
    if any(len({New.parent, Target.parent, Backup.parent}) != 1 for New, Target, Backup, _ in Items):
        raise ValueError('暂存件、正式目标和备份必须位于同一父目录')
    Backups, Publishes = [], []
    if Retire is not None:
        Target, Backup, Original = Retire
        if (Target.parent != Stage.parent or Backup.parent != Stage.parent or Target == Backup
                or any(Target in Item[:3] or Backup in Item[:3] for Item in Items)
                or ArtifactIdentity(Target) != Original or ArtifactIdentity(Backup) is not None):
            raise PathIdentityChanged('待删除输出或备份位置已变化，未提交 ZIP')
        if Original is not None:
            Backups.append((Target, Backup, Original))
    for New, Target, Backup, Original in Items:
        CurrentPending = ArtifactIdentity(New)
        Pending = CurrentPending if ExpectedNew is None else ExpectedNew.get(New)
        if ExpectedNew is not None and (Pending is None or Pending != CurrentPending):
            raise PathIdentityChanged(f'暂存件身份变化，未提交产物：{New}')
        if Pending is None or ArtifactIdentity(Target) != Original or ArtifactIdentity(Backup) is not None:
            raise ValueError('正式目标或暂存件已变化，未提交产物')
        if Original is not None:
            Backups.append((Target, Backup, Original))
        Publishes.append((New, Target, Pending))
    Moves = Backups + Publishes
    Journal = Stage / 'commit.json'
    _WriteJournal(Journal, Moves)
    Done = []

    def CheckRetired():
        if Retire is not None:
            Target, Backup, Original = Retire
            if ArtifactIdentity(Target) is not None or ArtifactIdentity(Backup) != Original:
                raise PathIdentityChanged('待删除输出位置被占用或备份身份变化，已保留事务')

    try:
        for From, To, Identity in Moves:
            if (From, To, Identity) in Publishes:
                CheckRetired()
            RenameSibling(From, To, Identity)
            Done.append((From, To, Identity))
        CheckRetired()
        for _, Target, Identity in Publishes:
            if ArtifactIdentity(Target) != Identity:
                raise PathIdentityChanged(f'已提交产物身份变化：{Target}')
    except Exception as Error:
        try:
            for From, To, Identity in reversed(Done):
                RenameSibling(To, From, Identity)
            if not isinstance(Error, PathIdentityChanged):
                Journal.unlink()
        except Exception as RollbackError:
            raise RuntimeError(f'回滚失败，保留事务和备份：{Stage}；{RollbackError}') from RollbackError
        raise


def _RemoveStage(Stage, Parent, Expected):
    Actual = ArtifactIdentity(Stage)
    if Actual is None:
        return
    if Stage.parent != Parent or Actual[:3] != Expected[:3]:
        raise ValueError(f'阶段目录身份改变，已保留：{Stage}')
    for _ in WalkTree(Stage):
        pass
    shutil.rmtree(Stage)


def _CleanTransaction(Stage, Parent, StageIdentity, Owned):
    for Target, (Expected, IsDirectory) in Owned.items():
        if IsDirectory:
            _RemoveStage(Target, Parent, Expected)
        else:
            Actual = ArtifactIdentity(Target)
            if Actual is None:
                continue
            if Target.parent != Parent or Actual[:3] != Expected[:3]:
                raise ValueError(f'暂存文件身份改变，已保留：{Target}')
            Target.unlink()
    _RemoveStage(Stage, Parent, StageIdentity)


def _CopySource(Source, Destination, Modules):
    Dependencies, Stale = set(), set()
    Filters = DependencyFilters(*(CheckedPath(Source / 'Config' / Name) for Name in DependencyFilterNames))
    for Parent, _, Files in WalkTree(Source):
        for Name in Files:
            File = Parent / Name
            Parts = File.relative_to(Source).parts
            Folded = tuple(Part.casefold() for Part in Parts)
            if any(Part in LocalEntries for Part in Folded):
                continue
            if Dependency(Parts, Filters) and OwnBinary(Parts, Modules) is None:
                if Folded[0] in TopExcluded:
                    raise ValueError(f'依赖位于排除目录：{File}')
                Dependencies.add(Parts)
            elif Folded[0] not in TopExcluded and Folded[-1].endswith(('.dll', '.pdb', '.lib', '.a', '.so', '.dylib')):
                if Folded[:2] == ('binaries', 'win64') and len(Folded) == 3 and (
                        OwnBinary(Parts, Modules) or re.fullmatch(
                            r'(?:unrealeditor|ue4editor|unrealgame|ue4game)-[^.]+\.(?:dll|pdb)', Folded[-1])):
                    Stale.add(Parts)
                else:
                    raise ValueError(f'无法确认源二进制依赖归属，请检查 FilterPlugin.ini：{File}')

    def Ignore(Directory, Names):
        Parts = Path(Directory).relative_to(Source).parts
        Excluded = LocalEntries | (TopExcluded - {'tests'} if Path(Directory) == Source else set())
        return [Name for Name in Names if Name.casefold() in Excluded
                or (*Parts, Name) in Stale
                or (tuple(Part.casefold() for Part in Parts) == ('binaries', 'win64')
                    and Name.casefold() in ('unrealeditor.modules', 'unrealgame.modules',
                                            'ue4editor.modules', 'ue4game.modules'))]

    CopyToStage(Source, Destination, Ignore)
    return {Parts: _Digest(Destination.joinpath(*Parts)) for Parts in Dependencies}


def _Digest(File):
    Digest = hashlib.sha256()
    with File.open('rb') as Handle:
        for Chunk in iter(lambda: Handle.read(1024 * 1024), b''):
            Digest.update(Chunk)
    return Digest.digest()


def _VerifyDependencies(Inspected, Dependencies):
    Files = Inspected[2]
    Missing = [str(Path(*Parts)) for Parts, Digest in Dependencies.items()
               if Parts not in Files or _Digest(Files[Parts]) != Digest]
    if Missing:
        raise ValueError(f'UAT 或后处理未完整保留依赖，请检查 FilterPlugin.ini：{", ".join(sorted(Missing))}')


def _Platforms(Module, Key):
    Legacy = 'WhitelistPlatforms' if Key == 'PlatformAllowList' else 'BlacklistPlatforms'
    if Key in Module and Legacy in Module:
        raise ValueError(f'模块 {Module["Name"]} 同时声明 {Key} 与 {Legacy}')
    if Key not in Module and Legacy not in Module:
        return None
    Values = Module.get(Key, Module.get(Legacy))
    if not isinstance(Values, list) or any(not isinstance(Value, str) or not Value for Value in Values):
        raise ValueError(f'模块 {Module["Name"]} 的 {Key} 无效')
    return Values


def _Win64Modules(Fields, CheckFab=False):
    Result = {}
    for Module in Fields.get('Modules', []):
        Allowed = _Platforms(Module, 'PlatformAllowList')
        Denied = _Platforms(Module, 'PlatformDenyList')
        if ((Allowed is not None or Module.get('HasExplicitPlatforms')) and 'Win64' not in (Allowed or ())
                or 'Win64' in (Denied or ())):
            continue
        if CheckFab and not (Allowed or Denied):
            raise ValueError(f'Fab 模块 {Module["Name"]} 必须声明 Win64 平台范围')
        Result[Module['Name'].casefold()] = Module
    return Result


def _VerifyFab(Fields):
    CompleteFabURL(Fields, AddMissing=True)
    if 'MarketplaceURL' not in Fields and 'FabURL' in Fields:
        Fields['MarketplaceURL'] = Fields['FabURL']
    if not re.fullmatch(r'com\.epicgames\.launcher://ue/(?:Fab|marketplace)/product/'
                        r'(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
                        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', Fields.get('FabURL', '')):
        raise ValueError('Fab 需要带商品 UUID 的 Launcher 链接（FabURL 或 MarketplaceURL）')
    _Win64Modules(Fields, CheckFab=True)


def _VerifyDeploy(Inspected, EngineRoot):
    Fields, Declared, Files, _ = Inspected
    Applicable = _Win64Modules(Fields)
    Modules = set(Applicable)
    if not Modules:
        return
    Built, EditorBuilt = set(), set()
    for Parts, File in Files.items():
        if len(Parts) != 3 or tuple(Part.casefold() for Part in Parts[:2]) != ('binaries', 'win64'):
            continue
        if Parts[-1].casefold() not in ('unrealeditor.modules', 'unrealgame.modules',
                                      'ue4editor.modules', 'ue4game.modules'):
            continue
        Manifest = ReadJson(File.read_text(encoding='utf-8-sig'))
        EngineManifest = CheckedPath(EngineRoot / 'Engine/Binaries/Win64' / Parts[-1])
        if not EngineManifest.is_file():
            raise ValueError(f'缺少用于核对 BuildId 的引擎清单：{EngineManifest}')
        BuildId = Manifest.get('BuildId')
        if (not isinstance(BuildId, str) or not BuildId.strip()
                or BuildId != ReadJson(EngineManifest.read_text(encoding='utf-8-sig')).get('BuildId')):
            raise ValueError(f'Win64 模块清单 BuildId 与选中引擎不匹配：{File}')
        Mapping = Manifest.get('Modules')
        if not isinstance(Mapping, dict) or not Mapping:
            raise ValueError(f'Win64 模块映射无效：{File}')
        Seen = set()
        for Name, Binary in Mapping.items():
            Key = Name.casefold()
            Target = Files.get((*Parts[:-1], Binary)) if isinstance(Binary, str) else None
            if (Key in Seen or Target is None or not Binary.casefold().endswith('.dll')
                    or OwnBinary((*Parts[:-1], Binary), Declared) != Key or Target.stat().st_size == 0):
                raise ValueError(f'Win64 模块映射没有匹配的 DLL：{Name} → {Binary}')
            Seen.add(Key)
        Built.update(Seen)
        if Parts[-1].casefold() in ('unrealeditor.modules', 'ue4editor.modules'):
            EditorBuilt.update(Seen)
    NeedEditor = {Name for Name, Module in Applicable.items()
                  if Module.get('Type', 'Runtime') not in ('CookedOnly', 'Program')
                  and ('Editor' in Module.get('TargetAllowList', []) or not Module.get('TargetAllowList', []))
                  and 'Editor' not in Module.get('TargetDenyList', [])}
    if not NeedEditor <= EditorBuilt:
        raise ValueError(f'部署产物缺少 Win64 Editor 模块映射：{", ".join(sorted(NeedEditor - EditorBuilt))}')
    Sources = {Parts[-1].casefold()[:-len('.build.cs')] for Parts, File in Files.items()
               if Parts[0].casefold() == 'source' and Parts[-1].casefold().endswith('.build.cs')
               and File.stat().st_size > 0}
    if not Modules <= (Built & Sources):
        raise ValueError(f'部署产物缺少与模块匹配的 Source 或 Win64 DLL：{", ".join(sorted(Modules - (Built & Sources)))}')


def _BuildInto(Engine, Uat, Source, Stage, Package, PluginName, Version, Options, Emit, ShouldStop, OnRunner):
    SourceCopy = Stage / 'input' / PluginName
    for Pathname in (Uat, SourceCopy, Package):
        if any(Character in str(Pathname) for Character in '%!^&|<>"\r\n'):
            raise ValueError(f'路径含 RunUAT shell 不安全字符：{Pathname}')
    Original = ReadJson(Source.read_text(encoding='utf-8-sig'))
    Modules = ValidateDescriptor(Original)
    CompleteFabURL(Original, AddMissing=False)
    Dependencies = _CopySource(Source.parent, SourceCopy, Modules)
    Descriptor = SourceCopy / Source.name
    with PinDirectories(SourceCopy), PinDirectories(Package):
        if 'EngineVersion' in Original:
            Unpinned = {Key: Value for Key, Value in Original.items() if Key != 'EngineVersion'}
            WriteCheckedFile(Descriptor, JsonText(Unpinned).encode('utf-8'), EntryState(Descriptor))
        Filters = {}
        for Name in DependencyFilterNames:
            Filter = CheckedPath(SourceCopy / 'Config' / Name)
            if EntryState(Filter) is not None:
                Filters[Name] = Filter.read_bytes()
        _RunUat(Engine, Uat, Descriptor, Package, Stage, Emit, ShouldStop, OnRunner)
        _RestoreSourceFilters(Package, Filters)
        Inspected = _PrepareOutput(Uat, Package, PluginName, Version, Options, Emit, ShouldStop, Original, Dependencies)
    return Package, Inspected


def _RestoreSourceFilters(Package, Filters):
    if not Filters:
        return
    with PinDirectories(Package / 'Config', Create=True) as Config:
        General, Win64 = DependencyFilterNames
        if General in Filters and Win64 not in Filters and DependencyFilters(CheckedPath(Config / Win64)):
            raise ValueError(f'UAT 新增的平台过滤规则可能覆盖源规则：{Config / Win64}')
        for Name, Content in Filters.items():
            Filter = CheckedPath(Config / Name)
            Original = EntryState(Filter)
            if Original is None or Filter.read_bytes() != Content:
                WriteCheckedFile(Filter, Content, Original)


def _RunUat(Engine, Uat, Descriptor, Package, Stage, Emit, ShouldStop, OnRunner):
    if ShouldStop():
        raise PackagingCancelled('打包已取消')
    Runner = BuildRunner(RunUatPath=str(Uat), PluginPath=str(Descriptor), OutputDir=str(Package),
                         UseRocket=not Engine.get('SourceBuild', False), StageDir=Stage)
    OnRunner(Runner)
    Output = Runner.RunBuild()
    try:
        Success = False
        for Line in Output:
            if ShouldStop():
                raise PackagingCancelled('构建已取消')
            if Line == 'EXIT_SUCCESS':
                Success = True
                break
            if Line == 'EXIT_FAILURE' or Line.startswith('ERROR::'):
                Emit(Line)
                break
            Emit(Line)
        if not Success:
            raise RuntimeError('UAT 构建失败')
    except BaseException:
        Runner.Terminate()
        raise
    finally:
        try:
            Close = getattr(Output, 'close', None)
            if Close is not None:
                Close()
        finally:
            OnRunner(None)


def _PrepareOutput(Uat, Package, PluginName, Version, Options, Emit, ShouldStop, Original, Dependencies):
    Descriptor = Package / f'{PluginName}.uplugin'
    DescriptorState = EntryState(Descriptor)
    Inspected = InspectPlugin(CheckedPath(Package), PluginName)
    _VerifyDependencies(Inspected, Dependencies)
    Fields = Inspected[0]
    if Options.AddVersion:
        Fields['EngineVersion'] = Version
    else:
        Fields.pop('EngineVersion', None)
    for Key, Value in Original.items():
        if Key in ('Installed', 'EnabledByDefault') or (type(Value) is bool and Key not in Fields):
            Fields[Key] = Value
        elif Key in ('MarketplaceURL', 'FabURL'):
            if Key not in Fields or (Options.Profile == 'fab' and Fields[Key] == '' and Value):
                Fields[Key] = Value
            elif Fields[Key] != Value:
                raise ValueError(f'UAT 产物的 {Key} 与源描述符不一致')
    if Options.Profile == 'fab':
        if 'FabURL' in Original and 'MarketplaceURL' not in Original and Fields.get('MarketplaceURL') == '':
            del Fields['MarketplaceURL']
        _VerifyFab(Fields)
    else:
        CompleteFabURL(Fields, AddMissing=False)
    if (Options.Profile or Options.MakeZip) and any(Dependency(Parts, ()) and Parts[0].casefold() in TopExcluded
                                                   for Parts in Inspected[2]):
        raise ValueError(f'清理目录内含第三方依赖，无法安全判断：{Package}')
    WriteCheckedFile(Descriptor, JsonText(Fields).encode('utf-8'), DescriptorState)
    if not Options.NoPost:
        for Line in RunPostProcess(str(Package), ShouldStop, KeepBinaries=(Options.KeepBinaries
                                   or Options.Profile is not None or Options.MakeZip)):
            Emit(Line)
            if Line.startswith('❌'):
                raise RuntimeError(Line)
    Inspected = InspectPlugin(Package, PluginName)
    _VerifyDependencies(Inspected, Dependencies)
    if Options.Profile == 'deploy':
        _VerifyDeploy(Inspected, Uat.parents[3])
    return Inspected


def RunPackaging(Engine, AllEngines, PluginName, PluginPath, OutputRoot, Options, *, ZipOnly=False,
                 Log=print, Gate=None):
    if ZipOnly and Options.DeleteOutput:
        raise ValueError('仅压缩命令不删除已有目录；请通过构建流程选择压缩后删除输出')
    if Options.AddVersion is None:
        Options = replace(Options, AddVersion=ConfigManager().Get('FabSettings', {}).get('自动添加版本信息', True))
    Gate = Gate if Gate is not None else CancelGate()
    ShouldStop = Gate.ShouldStop
    PluginName = ValidateName(PluginName)
    EngineName = ValidateName(Engine['Name'])
    Root = CheckedPath(OutputRoot)
    Source = CheckedPath(PluginPath)
    _CheckSourceOptions(PluginName, Source, Root, AllEngines, Engine)
    EngineRoot = CheckedPath(Engine['Path'])
    Version = ReadEngineVersion(EngineRoot)
    Uat = None
    if not ZipOnly:
        Uat = CheckedPath(EngineRoot / 'Engine/Build/BatchFiles/RunUAT.bat')
        if not Source.is_file() or not Uat.is_file():
            raise ValueError(f'找不到源插件描述符或 RunUAT.bat：{Source}；{Uat}')
    Parent = CheckedPath(Root / PluginName)
    Final = CheckedPath(Parent / EngineName)
    MakeZip = ZipOnly or Options.MakeZip
    Archive = CheckedPath(Parent / f'{PluginName}_UE_{ZipVersion(Version)}_Source.zip') if MakeZip else None
    Stage = CheckedPath(Parent / f'.{EngineName}.transaction')
    Package = Parent / f'{Stage.name}-new-package'
    NewZip = Parent / f'{Stage.name}-new.zip'
    OldPackage = Parent / f'{Stage.name}-old-package'
    OldZip = Parent / f'{Stage.name}-old.zip'
    if Archive is not None and Final.name.casefold() == Archive.name.casefold():
        raise ValueError(f'引擎目录名与 ZIP 文件名冲突：{Final}')

    ValidatedZip = None

    def Preflight():
        nonlocal ValidatedZip
        _CheckSourceOptions(PluginName, CheckedPath(Source), CheckedPath(Root), AllEngines, Engine)
        FinalState = ArtifactIdentity(Final)
        Existing = InspectPlugin(Final, PluginName) if FinalState else None
        if Options.DeleteOutput and Existing is not None:
            if 'EngineVersion' not in Existing[0]:
                raise ValueError(f'无法确认已有输出的引擎版本，已保留目录，请取消删除选项：{Final}')
            CheckArtifactVersion(Existing[0], Version)
        if ZipOnly:
            if Existing is None:
                raise ValueError(f'找不到正式产物：{Final}')
            CheckArtifactVersion(Existing[0], Version)
        ZipState = ArtifactIdentity(Archive) if Archive is not None else None
        if ZipState and ZipState != ValidatedZip:
            CheckArtifactVersion(ValidateZip(Archive, PluginName), Version)
            ValidatedZip = ZipState
        return FinalState, ZipState, Existing

    def CheckTransactions():
        if Parent.is_dir():
            for Entry in Parent.iterdir():
                if Entry.name.startswith('.') and Entry.name.casefold().endswith('.transaction'):
                    raise RuntimeError(f'存在未完成事务，禁止继续：{Entry}')

    CheckTransactions()
    Preflight()
    with PinDirectories(Parent, Create=True), TargetLock(Parent):
        CheckTransactions()
        OriginalFinal, OriginalZip, Inspected = Preflight()
        ZipOnlySnapshot = ({Parts: _FileIdentity(File) for Parts, File in Inspected[2].items()}
                           if ZipOnly else None)
        if ShouldStop():
            raise PackagingCancelled('打包已取消')
        Private = (() if ZipOnly else (Package, OldPackage)) + ((NewZip, OldZip) if MakeZip else ())
        for Target in Private:
            if ArtifactIdentity(Target) is not None:
                raise ValueError(f'已有未知暂存件，拒绝覆盖：{Target}')
        CheckedPath(Stage).mkdir()
        StageIdentity = ArtifactIdentity(Stage)
        LogLines = []
        Owned = {}

        def Emit(Line):
            LogLines.append(Line)
            Log(Line)

        try:
            with PinDirectories(Stage):
                Items = []
                ValidatedNew = {}
                Retire = (Final, OldPackage, OriginalFinal) if Options.DeleteOutput else None
                if not ZipOnly:
                    Package.mkdir()
                    Owned[Package] = (ArtifactIdentity(Package), True)
                    Package, Inspected = _BuildInto(Engine, Uat, Source, Stage, Package, PluginName, Version, Options,
                                                     Emit, ShouldStop, Gate.SetRunner)
                    if not Options.DeleteOutput:
                        Items.append((Package, Final, OldPackage, OriginalFinal))
                if MakeZip:
                    Emit('正在生成并校验源码 ZIP…')
                    with NewZip.open('xb') as Handle:
                        Owned[NewZip] = (StateIdentity(os.fstat(Handle.fileno())), False)
                        ExpectedMembers = WriteSourceZip(Handle, PluginName, Inspected,
                                                         Version if Options.AddVersion else None)
                    ZipIdentity = ArtifactIdentity(NewZip)
                    ValidateZip(NewZip, PluginName, ExpectedMembers)
                    if ArtifactIdentity(NewZip) != ZipIdentity:
                        raise PathIdentityChanged(f'ZIP 在校验期间发生变化：{NewZip}')
                    ValidatedNew[NewZip] = ZipIdentity
                    Items.append((NewZip, Archive, OldZip, OriginalZip))
                CurrentFinal, CurrentZip, Current = Preflight()
                if (CurrentFinal, CurrentZip) != (OriginalFinal, OriginalZip):
                    raise RuntimeError('正式目标在打包期间发生变化，未提交')
                if ZipOnly and {Parts: _FileIdentity(File) for Parts, File in Current[2].items()} != ZipOnlySnapshot:
                    raise RuntimeError('待压缩的正式文件在打包期间发生变化，未提交 ZIP')
                if ArtifactIdentity(Stage)[:3] != StageIdentity[:3]:
                    raise RuntimeError(f'阶段目录身份改变：{Stage}')
                ExpectedNew = {}
                for New, _, _, _ in Items:
                    Identity = ArtifactIdentity(New)
                    if Identity is None or Identity[:3] != Owned[New][0][:3]:
                        raise RuntimeError(f'暂存件身份改变：{New}')
                    if New in ValidatedNew and Identity != ValidatedNew[New]:
                        raise PathIdentityChanged(f'已校验 ZIP 的身份变化：{New}')
                    ExpectedNew[New] = Identity
                with Gate.Commit():
                    CommitArtifacts(Stage, Items, ExpectedNew=ExpectedNew, Retire=Retire)
                if not ZipOnly and OriginalFinal is not None:
                    Owned[OldPackage] = (OriginalFinal, True)
                if MakeZip and OriginalZip is not None:
                    Owned[OldZip] = (OriginalZip, False)
        except KeyboardInterrupt:
            Log(f'中断时已保留事务目录：{Stage}')
            raise
        except Exception as Error:
            if isinstance(Error, PathIdentityChanged) or any(
                    os.path.lexists(Stage / Name) for Name in ('commit.json', 'running.json')):
                Emit(f'事务未确认结束，已保留：{Stage}')
            else:
                try:
                    _CleanTransaction(Stage, Parent, StageIdentity, Owned)
                except (OSError, ValueError) as CleanupError:
                    Emit(f'无法安全清理阶段目录，已保留 {Stage}：{CleanupError}')
            if not isinstance(Error, PackagingCancelled):
                try:
                    CheckedPath(Parent)
                    with tempfile.NamedTemporaryFile(mode='w', prefix=f'.{EngineName}.failed-', suffix='.log',
                                                     dir=Parent, delete=False, encoding='utf-8') as FailedLog:
                        FailedLog.write('\n'.join([*LogLines, str(Error)]) + '\n')
                    Emit(f'失败日志：{FailedLog.name}')
                except (OSError, ValueError) as LogError:
                    Emit(f'无法写入失败日志：{LogError}')
            raise
        try:
            _CleanTransaction(Stage, Parent, StageIdentity, Owned)
        except (OSError, ValueError) as Error:
            raise RuntimeError(f'产物已提交，但无法安全清理备份，已保留 {Stage}：{Error}') from Error
    return tuple(Target for _, Target, _, _ in Items)
