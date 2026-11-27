import argparse
import signal
import sys
from pathlib import Path

from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.Packaging import BuildOptions, CancelGate, PackagingCancelled, RunPackaging, ValidateSelection
from Source.Logic.PackagingPaths import ValidateName


def _Print(Message, Stream=None):
    Stream = sys.stdout if Stream is None else Stream
    try:
        print(Message, file=Stream)
    except UnicodeEncodeError:
        Encoding = Stream.encoding or 'utf-8'
        print(Message.encode(Encoding, errors='backslashreplace').decode(Encoding), file=Stream)


def CmdEngines(Args, ProjectRoot):
    Engines = ConfigManager().Get('EngineList', [])
    if not Engines:
        print('尚未配置引擎，请先在图形界面添加。')
        return 0
    for Engine in Engines:
        Selected = '*' if Engine.get('Selected', True) else ' '
        Kind = '源码版' if Engine.get('SourceBuild', False) else '安装版'
        _Print(f'{Selected} {Engine["Name"]:<12} {Kind}  {Engine["Path"]}')
    return 0


def CmdPlugins(Args, ProjectRoot):
    Root = ProjectRoot / 'Plugins'
    _Print(f'项目插件（{Root}）：')
    if Root.is_dir():
        for Entry in sorted(Root.iterdir()):
            if (Entry / f'{Entry.name}.uplugin').is_file():
                _Print(f'  - {Entry.name}')
    return 0


def _SelectEngines(Args, Configured):
    if not Configured:
        raise ValueError('尚未配置引擎，请先在图形界面添加')
    Names = [ValidateName(Engine['Name']) for Engine in Configured]
    if len(Names) != len({Name.casefold() for Name in Names}):
        raise ValueError('配置中有重复或大小写别名引擎')
    if Args.all:
        return Configured
    if Args.engines is not None:
        Wanted = {ValidateName(Name.strip()) for Name in Args.engines.split(',')}
        Missing = Wanted - set(Names)
        if Missing:
            raise ValueError(f'找不到引擎：{", ".join(sorted(Missing))}')
        return [Engine for Engine in Configured if Engine['Name'] in Wanted]
    Selected = [Engine for Engine in Configured if Engine.get('Selected', True)]
    if not Selected:
        raise ValueError('没有勾选引擎，请用 --engines 或 --all 指定')
    return Selected


def CmdPackage(Args, ProjectRoot):
    ZipOnly = Args.command == 'zip'
    Options = Args.Options
    try:
        PluginName = ValidateName(Args.plugin)
        Configured = ConfigManager().Get('EngineList', [])
        Engines = _SelectEngines(Args, Configured)
        ValidateSelection(Engines, ZipOnly or Options.MakeZip)
        PluginPath = ProjectRoot / 'Plugins' / PluginName / f'{PluginName}.uplugin'
        if not ZipOnly and not PluginPath.is_file():
            raise ValueError(f'找不到插件清单：{PluginPath}')
    except (ValueError, KeyError, TypeError) as Error:
        _Print(f'参数或配置错误：{Error}', sys.stderr)
        return 2
    Output = Path(Args.output) if Args.output else ProjectRoot / 'PackagedPlugins'
    Gate = CancelGate()

    def Stop(Signum, Frame):
        if Gate.Stop():
            _Print('当前引擎已进入提交，将完成本次提交或回滚；后续引擎取消。', sys.stderr)

    Previous = signal.signal(signal.SIGINT, Stop)
    try:
        return _RunSelected(Engines, Configured, PluginName, PluginPath, Output, Options, ZipOnly, Gate)
    finally:
        signal.signal(signal.SIGINT, Previous)


def _RunSelected(Engines, Configured, PluginName, PluginPath, Output, Options, ZipOnly, Gate):
    Failed = []
    for Engine in Engines:
        if Gate.ShouldStop():
            break
        Name = Engine['Name']
        _Print(f'=== {Name} ===')
        try:
            Artifacts = RunPackaging(Engine, Configured, PluginName, PluginPath, Output, Options, ZipOnly=ZipOnly,
                                     Log=lambda Line: _Print(f'  | {Line}'), Gate=Gate)
            for Artifact in Artifacts:
                _Print(f'  产物：{Artifact}')
        except (KeyboardInterrupt, PackagingCancelled):
            _Print('用户中断，若保留事务目录请先检查其中的备份和提交记录。', sys.stderr)
            return 130
        except Exception as Error:
            Failed.append(Name)
            _Print(f'  {Name} 失败：{Error}', sys.stderr)
    if Gate.ShouldStop():
        _Print('已停止；已提交的产物保留，未开始的引擎已取消。', sys.stderr)
        return 130
    _Print(f'成功：{len(Engines) - len(Failed)} / {len(Engines)}')
    return int(bool(Failed))


def ParseArgs(Argv):
    Parser = argparse.ArgumentParser(prog='UEPluginPacker', description='UE 多版本插件打包器')
    Commands = Parser.add_subparsers(dest='command', required=True)
    Build = Commands.add_parser('build', help='构建所选引擎的插件')
    Zip = Commands.add_parser('zip', help='从已有正式产物生成源码 ZIP，不运行 UAT')
    for Command in (Build, Zip):
        Command.add_argument('plugin', help='插件名')
        Selection = Command.add_mutually_exclusive_group()
        Selection.add_argument('--engines', help='逗号分隔的引擎名，例如 UE_5.4,UE_5.7')
        Selection.add_argument('--all', action='store_true', help='选择全部已配置的引擎')
        Command.add_argument('--output', help='输出根目录，默认 PackagedPlugins')
        VersionOptions = Command.add_mutually_exclusive_group()
        VersionOptions.add_argument('--add-version', dest='add_version', action='store_true', default=None,
                                    help='在产物中写入目标引擎版本，覆盖格式化设置')
        VersionOptions.add_argument('--no-add-version', dest='add_version', action='store_false',
                                    help='不在产物中写入 EngineVersion，覆盖格式化设置')
        Command.set_defaults(Func=CmdPackage, Options=BuildOptions())
    Build.add_argument('--profile', choices=('fab', 'deploy'), help=argparse.SUPPRESS)
    ZipOptions = Build.add_mutually_exclusive_group()
    ZipOptions.add_argument('--zip', dest='make_zip', action='store_true', default=None, help='生成源码 ZIP')
    ZipOptions.add_argument('--no-zip', dest='make_zip', action='store_false', help='不生成源码 ZIP')
    Build.add_argument('--no-post', action='store_true', help='跳过可选整理')
    Build.add_argument('--keep-binaries', action='store_true', help='保留二进制（默认已保留，兼容旧命令）')
    OutputOptions = Build.add_mutually_exclusive_group()
    OutputOptions.add_argument('--delete-output-after-zip', dest='delete_output', action='store_true',
                               help='ZIP 校验成功后只保留 ZIP，删除该 ZIP 对应的引擎构建输出，不动原始源码')
    OutputOptions.add_argument('--keep-output', dest='delete_output', action='store_false',
                               help='保留构建输出目录（默认）')
    Commands.add_parser('engines', help='列出已配置的引擎').set_defaults(Func=CmdEngines)
    Commands.add_parser('plugins', help='列出项目插件').set_defaults(Func=CmdPlugins)
    Args = Parser.parse_args(Argv)
    if Args.command == 'build':
        try:
            Profile = Args.profile if Args.profile is not None or Args.no_post else 'deploy'
            Args.Options = BuildOptions(Profile, Args.make_zip, Args.no_post, Args.keep_binaries,
                                        DeleteOutput=Args.delete_output, AddVersion=Args.add_version)
        except ValueError as Error:
            Build.error(str(Error))
    elif Args.command == 'zip':
        Args.Options = BuildOptions(AddVersion=Args.add_version)
    return Args


def RunCli(Argv, ProjectRoot):
    Args = ParseArgs(Argv)
    return Args.Func(Args, Path(ProjectRoot))
