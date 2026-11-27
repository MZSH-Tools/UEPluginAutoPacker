import json
import re
import stat
import zipfile
from pathlib import PurePosixPath

from Source.Logic.PackagingPaths import CheckedPath, EntryState, PinDirectories, ValidateComponent, ValidateName, WalkTree


LocalEntries = {'.git', '.svn', '.hg', '.p4', '.p4config', '.codex', '.agents', '.claude', '.vs',
                '.idea', '.vscode', '.gitignore', '.gitattributes', '.gitmodules', '.p4ignore',
                '.editorconfig', '.env', '.ds_store', 'thumbs.db'}
TopExcluded = {'intermediate', 'hostproject', 'saved', 'tests'}
StandardDirs = {'source', 'config', 'resources', 'content', 'binaries', 'intermediate'}


def ReadJson(Text):
    def UniqueFields(Pairs):
        Fields = {}
        for Key, Value in Pairs:
            if Key in Fields:
                raise ValueError(f'JSON 字段重复：{Key}')
            Fields[Key] = Value
        return Fields

    Result = json.loads(Text, object_pairs_hook=UniqueFields)
    if not isinstance(Result, dict):
        raise ValueError('需要 JSON 对象')
    return Result


def JsonText(Fields):
    return json.dumps(Fields, ensure_ascii=False, indent=2) + '\n'


def ValidateDescriptor(Fields):
    Canonical = {'FileVersion', 'EngineVersion', 'Modules', 'Installed', 'EnabledByDefault'}
    Reserved = {Key.casefold() for Key in Canonical}
    if any(Key.casefold() in Reserved and Key not in Canonical for Key in Fields):
        raise ValueError('描述符包含大小写不规范的保留字段')
    Version = Fields.get('FileVersion')
    if type(Version) is not int or Version <= 0:
        raise ValueError('描述符 FileVersion 必须是正整数')
    Modules = Fields.get('Modules', [])
    if not isinstance(Modules, list) or not all(isinstance(Item, dict) for Item in Modules):
        raise ValueError('描述符 Modules 无效')
    Names = [ValidateName(Item.get('Name')).casefold() for Item in Modules]
    if len(Names) != len(set(Names)):
        raise ValueError('描述符模块名称重复')
    return set(Names)


def CompleteFabURL(Fields, AddMissing=True):
    Canonical = {'MarketplaceURL', 'FabURL'}
    Reserved = {Key.casefold() for Key in Canonical}
    if any(Key.casefold() in Reserved and Key not in Canonical for Key in Fields):
        raise ValueError('描述符包含大小写不规范的 URL 字段')
    if any(Key in Fields and not isinstance(Fields[Key], str) for Key in Canonical):
        raise ValueError('MarketplaceURL 和 FabURL 必须是字符串')
    if 'MarketplaceURL' in Fields and 'FabURL' in Fields:
        if Fields['FabURL'] != Fields['MarketplaceURL']:
            raise ValueError('MarketplaceURL 与 FabURL 不一致')
    elif AddMissing and 'MarketplaceURL' in Fields:
        Fields['FabURL'] = Fields['MarketplaceURL']
        return True
    return False


def PayloadMember(Parts, Modules):
    if len(Parts) < 2 or any(Part.casefold() in LocalEntries for Part in Parts):
        return False
    Top, Filename = Parts[0].casefold(), Parts[-1].casefold()
    if Top == 'content':
        return True
    if Top == 'source' and 'thirdparty' not in {Part.casefold() for Part in Parts[:-1]}:
        return Filename.endswith(('.build.cs', '.cpp', '.c', '.h', '.hpp', '.cc', '.cxx'))
    return OwnBinary(Parts, Modules) is not None and Filename.endswith('.dll')


def OwnBinary(Parts, Modules):
    if len(Parts) != 3 or Parts[0].casefold() != 'binaries' or Parts[1].casefold() != 'win64':
        return None
    Match = re.fullmatch(r'(?:(?:unrealeditor|ue4editor|unrealgame|ue4game)-)?(.+)\.(dll|pdb)',
                         Parts[-1].casefold())
    return Match[1] if Match and Match[1] in Modules else None


DependencyFilterNames = ('FilterPlugin.ini', 'FilterPluginWin64.ini')


def DependencyFilters(*FilterFiles):
    return [Rule for FilterFile in FilterFiles for Rule in _ReadDependencyFilter(FilterFile)]


def _ReadDependencyFilter(FilterFile):
    if FilterFile is None or EntryState(FilterFile) is None:
        return ()
    Filters = []
    InSection = False
    for Line in FilterFile.read_text(encoding='utf-8-sig').splitlines():
        Pattern = Line.strip()
        if Pattern.startswith('['):
            InSection = Pattern.casefold() == '[filterplugin]'
        if not InSection or not Pattern or Pattern[0] in '[;#':
            continue
        Include = not Pattern.startswith('-')
        Pattern = Pattern.lstrip('+-').lstrip('/').casefold()
        if not Pattern or '\\' in Pattern or '..' in Pattern.replace('...', ''):
            raise ValueError(f'{FilterFile.name} 路径规则无法解析：{Line}')
        Expression = re.escape(Pattern).replace(r'\.\.\.', '.*').replace(r'\*', '[^/]*').replace(r'\?', '[^/]')
        Filters.append((re.compile(Expression), Include))
    return Filters


def Dependency(Parts, Filters):
    Folded = tuple(Part.casefold() for Part in Parts)
    if {'thirdparty', 'vendor'} & set(Folded[:-1]):
        return True
    if not Folded[-1].endswith(('.dll', '.pdb', '.lib', '.a', '.so', '.dylib')):
        return False
    Included = False
    for Expression, Include in Filters:
        if Expression.fullmatch('/'.join(Folded)):
            Included = Include
    return Included


def InspectPlugin(Directory, PluginName):
    Files, Empty = {}, []
    for Parent, Dirs, Names in WalkTree(Directory):
        if not Dirs and not Names and Parent != Directory:
            Empty.append(Parent.relative_to(Directory).parts)
        for Name in Names:
            File = Parent / Name
            Files[File.relative_to(Directory).parts] = File
        if Parent == Directory and any(Name.casefold() == 'failed.log' for Name in Dirs + Names):
            raise ValueError(f'拒绝带 Failed.log 的正式产物：{Directory}')
    DescriptorName = f'{PluginName}.uplugin'
    Manifest = Files.get((DescriptorName,))
    Descriptors = [Parts for Parts in Files if Parts[-1].casefold().endswith('.uplugin')
                   and Parts[0].casefold() not in TopExcluded and Parts[0].casefold() not in LocalEntries]
    if Manifest is None or Descriptors != [(DescriptorName,)]:
        raise ValueError(f'目标归属不明：需要唯一的同名描述符 {Directory / DescriptorName}')
    Fields = ReadJson(Manifest.read_text(encoding='utf-8-sig'))
    Modules = ValidateDescriptor(Fields)
    if not any(File.stat().st_size > 0 and PayloadMember(Parts, Modules) for Parts, File in Files.items()):
        raise ValueError(f'插件没有实际源码、内容或模块载荷：{Directory}')
    return Fields, Modules, Files, Empty


def ZipMembers(Files, Empty, Modules):
    Keep, KeepEmpty = {}, []
    Filters = DependencyFilters(*(Files.get(('Config', Name)) for Name in DependencyFilterNames))
    for Parts, File in Files.items():
        Folded = tuple(Part.casefold() for Part in Parts)
        Explicit = Dependency(Parts, Filters) and OwnBinary(Parts, Modules) is None
        if set(Folded) & LocalEntries or Folded[0] in TopExcluded:
            if Explicit and Folded[0] in TopExcluded:
                raise ValueError(f'清理目录内含第三方依赖，无法安全判断：{File}')
            continue
        if not Explicit and Folded[0] == 'binaries':
            if OwnBinary(Parts, Modules) is not None:
                continue
            if len(Parts) == 3 and Folded[1] == 'win64' and Folded[-1] in (
                    'unrealeditor.modules', 'ue4editor.modules', 'unrealgame.modules', 'ue4game.modules'):
                Manifest = ReadJson(File.read_text(encoding='utf-8-sig')).get('Modules')
                if isinstance(Manifest, dict) and Manifest and all(
                    isinstance(Binary, str) and OwnBinary((*Parts[:-1], Binary), Modules) == Name.casefold()
                    and Parts[:-1] + (Binary,) in Files for Name, Binary in Manifest.items()
                ):
                    continue
            raise ValueError(f'无法判断 Binaries 文件是否可重建：{File}')
        if Folded[-1].endswith(('.dll', '.pdb', '.lib', '.a', '.so', '.dylib')) and not Explicit:
            raise ValueError(f'无法判断二进制依赖是否可重建：{File}')
        Keep[Parts] = File
    for Parts in Empty:
        Folded = tuple(Part.casefold() for Part in Parts)
        if (Folded[0] in (StandardDirs | {'shaders', 'thirdparty', 'vendor'}) and not set(Folded) & LocalEntries
                and Folded[0] not in TopExcluded and (Folded[0] != 'binaries' or {'thirdparty', 'vendor'} & set(Folded))):
            KeepEmpty.append(Parts)
    if not any(File.stat().st_size > 0 and PayloadMember(Parts, Modules) for Parts, File in Keep.items()):
        raise ValueError('移除可重建二进制后，ZIP 没有源码或内容载荷')
    return Keep, KeepEmpty


def ValidateZip(ZipPath, PluginName, Expected=None):
    Descriptor = (PluginName, f'{PluginName}.uplugin')
    with zipfile.ZipFile(ZipPath) as Archive:
        Seen, Members, Files = {}, set(), {}
        for Info in Archive.infolist():
            Name = Info.filename[:-1] if Info.is_dir() else Info.filename
            Parts = tuple(Name.split('/'))
            for Part in Parts:
                ValidateComponent(Part)
            if (Parts[0] != PluginName or (len(Parts) == 1 and not Info.is_dir())
                    or stat.S_ISLNK(Info.external_attr >> 16)
                    or Info.external_attr & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
                raise ValueError(f'ZIP 成员归属不明：{Info.filename}')
            for Length in range(1, len(Parts) + 1):
                Prefix = Parts[:Length]
                Key = tuple(Part.casefold() for Part in Prefix)
                if Seen.setdefault(Key, Prefix) != Prefix:
                    raise ValueError(f'ZIP 成员存在大小写别名：{Info.filename}')
            if Parts in Members:
                raise ValueError(f'ZIP 成员重复：{Info.filename}')
            Members.add(Parts)
            if not Info.is_dir():
                Files[Parts] = Info
        if any(Parts[:Length] in Files for Parts in Members for Length in range(1, len(Parts))):
            raise ValueError(f'ZIP 文件同时被用作目录：{ZipPath}')
        if ([Parts for Parts in Files if Parts[-1].casefold().endswith('.uplugin')] != [Descriptor]
                or any(Parts[1].casefold() == 'failed.log' for Parts in Files)):
            raise ValueError(f'ZIP 缺少唯一同名描述符或含 Failed.log：{ZipPath}')
        Fields = ReadJson(Archive.read(Files[Descriptor]).decode('utf-8-sig'))
        Modules = ValidateDescriptor(Fields)
        if not any(Info.file_size > 0 and PayloadMember(Parts[1:], Modules) for Parts, Info in Files.items()):
            raise ValueError(f'ZIP 无有效插件载荷：{ZipPath}')
        BadMember = Archive.testzip()
        if BadMember or (Expected is not None and sorted(Archive.namelist()) != sorted(Expected)):
            raise ValueError(f'ZIP 成员或 CRC 校验失败：{BadMember or ZipPath}')
        return Fields


def WriteSourceZip(Handle, PluginName, Inspected, EngineVersion):
    Fields, Modules, Files, Empty = Inspected
    Fields = dict(Fields)
    if EngineVersion is not None:
        Fields['EngineVersion'] = EngineVersion
    else:
        Fields.pop('EngineVersion', None)
    CompleteFabURL(Fields)
    Keep, KeepEmpty = ZipMembers(Files, Empty, Modules)
    Expected = []
    with zipfile.ZipFile(Handle, 'w', compression=zipfile.ZIP_DEFLATED) as Archive:
        for Parts in sorted(Keep):
            Member = str(PurePosixPath(PluginName, *Parts))
            if Parts == (f'{PluginName}.uplugin',):
                Archive.writestr(Member, JsonText(Fields))
            else:
                File = Keep[Parts]
                with PinDirectories(File.parent):
                    if EntryState(CheckedPath(File)) is None:
                        raise ValueError(f'ZIP 来源文件已消失：{File}')
                    Archive.write(File, Member)
            Expected.append(Member)
        for Parts in sorted(KeepEmpty):
            Member = str(PurePosixPath(PluginName, *Parts)) + '/'
            Archive.writestr(Member, b'')
            Expected.append(Member)
    return Expected
