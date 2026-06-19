import argparse
import os
import sys
from pathlib import Path
from typing import List

from Source.Logic.BuildRunner import BuildRunner
from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.PostProcessor import RunPostProcess


# ====================================================================
# 工具
# ====================================================================

def _FindPluginPath(ProjectRoot: Path, PluginName: str) -> Path:
    """在 ProjectRoot/Plugins/<Name>/<Name>.uplugin 找插件清单"""
    return ProjectRoot / "Plugins" / PluginName / f"{PluginName}.uplugin"


def _ListAvailablePlugins(ProjectRoot: Path) -> List[str]:
    Root = ProjectRoot / "Plugins"
    if not Root.exists():
        return []
    Result = []
    for Entry in Root.iterdir():
        if Entry.is_dir() and (Entry / f"{Entry.name}.uplugin").is_file():
            Result.append(Entry.name)
    return Result


# ====================================================================
# 子命令：engines（列出已配置的引擎）
# ====================================================================

def CmdEngines(Args, ProjectRoot: Path) -> int:
    Config = ConfigManager()
    Engines = Config.Get("EngineList", [])

    if not Engines:
        print("(尚未配置任何引擎，请先在 GUI 中添加)")
        return 0

    print(f"已配置引擎：{len(Engines)} 个")
    print(f"{'勾选':<6}{'名称':<12}{'源码版':<8}路径")
    print("-" * 80)
    for E in Engines:
        Mark = "✔" if E.get("Selected", True) else " "
        Src = "✔" if E.get("SourceBuild", False) else " "
        print(f"  {Mark:<4}{E['Name']:<12}  {Src:<6}{E['Path']}")
    return 0


# ====================================================================
# 子命令：plugins（列出项目下的插件）
# ====================================================================

def CmdPlugins(Args, ProjectRoot: Path) -> int:
    Plugins = _ListAvailablePlugins(ProjectRoot)

    if not Plugins:
        Root = ProjectRoot / "Plugins"
        print(f"(未在 {Root} 找到任何插件)")
        return 0

    print(f"项目下的插件（{ProjectRoot / 'Plugins'}）：")
    for P in Plugins:
        print(f"  - {P}")
    return 0


# ====================================================================
# 子命令：build（批量打包）
# ====================================================================

def CmdBuild(Args, ProjectRoot: Path) -> int:
    PluginPath = _FindPluginPath(ProjectRoot, Args.plugin)
    if not PluginPath.is_file():
        print(f"❌ 找不到插件清单：{PluginPath}", file=sys.stderr)
        print(f"   提示：运行 'UEPluginPacker.exe plugins' 查看可用插件", file=sys.stderr)
        return 2

    Config = ConfigManager()
    AllEngines = Config.Get("EngineList", [])
    if not AllEngines:
        print("❌ 尚未配置任何引擎，请先在 GUI 中添加", file=sys.stderr)
        return 2

    # 筛选引擎
    if Args.all:
        Engines = AllEngines
    elif Args.engines:
        Wanted = [X.strip() for X in Args.engines.split(",") if X.strip()]
        Engines = [E for E in AllEngines if E["Name"] in Wanted]
        Missing = set(Wanted) - set(E["Name"] for E in Engines)
        if Missing:
            print(f"❌ 找不到引擎：{', '.join(Missing)}", file=sys.stderr)
            print(f"   已配置：{', '.join(E['Name'] for E in AllEngines)}", file=sys.stderr)
            return 2
    else:
        Engines = [E for E in AllEngines if E.get("Selected", True)]
        if not Engines:
            print("❌ 配置中没有勾选的引擎，请用 --engines 或 --all 指定", file=sys.stderr)
            return 2

    OutputRoot = Path(Args.output).resolve() if Args.output else ProjectRoot / "PackagedPlugins"

    print(f"插件     : {Args.plugin}")
    print(f"清单     : {PluginPath}")
    print(f"输出根   : {OutputRoot}")
    print(f"目标引擎 : {', '.join(E['Name'] for E in Engines)}")
    print(f"后处理   : {'关闭（--no-post）' if Args.no_post else '启用'}")
    print(f"Binaries : {'保留（--keep-binaries）' if Args.keep_binaries else '按配置'}")
    print()

    Failed = []
    for Index, Engine in enumerate(Engines, 1):
        Name = Engine["Name"]
        OutDir = OutputRoot / Args.plugin / Name
        UatPath = Path(Engine["Path"]) / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"

        print(f"========== [{Index}/{len(Engines)}] {Name} ==========")
        print(f"  UAT     : {UatPath}")
        print(f"  Output  : {OutDir}")

        if not UatPath.is_file():
            print(f"  ❌ RunUAT.bat 不存在，跳过", file=sys.stderr)
            Failed.append(Name)
            continue

        Runner = BuildRunner(
            RunUatPath=str(UatPath),
            PluginPath=str(PluginPath),
            OutputDir=str(OutDir),
            UseRocket=not Engine.get("SourceBuild", False),
        )

        Success = False
        LogLines: List[str] = []

        try:
            for Line in Runner.RunBuild():
                if Line == "EXIT_SUCCESS":
                    Success = True
                    break
                if Line == "EXIT_FAILURE":
                    break
                if Line.startswith("ERROR::"):
                    Msg = Line[len("ERROR::"):]
                    LogLines.append(Msg)
                    print(f"  ERROR: {Msg}", file=sys.stderr)
                    break
                LogLines.append(Line)
                print(f"  | {Line}")
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断，正在终止构建…", file=sys.stderr)
            Runner.Terminate()
            return 130

        if Success:
            print(f"  ✅ 构建成功")
            if not Args.no_post:
                print(f"  运行后处理…")
                try:
                    for Line in RunPostProcess(str(OutDir), KeepBinaries=Args.keep_binaries):
                        print(f"    | {Line}")
                except Exception as E:
                    print(f"  ❌ 后处理异常：{E}", file=sys.stderr)
                    Failed.append(Name)
                    continue
            print(f"  🎉 {Name} 完成")
        else:
            print(f"  ❌ 构建失败", file=sys.stderr)
            Failed.append(Name)
            try:
                OutDir.mkdir(parents=True, exist_ok=True)
                (OutDir / "Failed.log").write_text("\n".join(LogLines), encoding="utf-8")
                print(f"  📁 失败日志：{OutDir / 'Failed.log'}")
            except Exception as E:
                print(f"  写入失败日志出错：{E}", file=sys.stderr)
        print()

    OkCount = len(Engines) - len(Failed)
    print(f"========== 汇总 ==========")
    print(f"  成功：{OkCount} / {len(Engines)}")
    if Failed:
        print(f"  失败：{', '.join(Failed)}")
        return 1
    return 0


# ====================================================================
# 入口
# ====================================================================

def RunCli(Argv: List[str], ProjectRoot: str) -> int:
    Parser = argparse.ArgumentParser(
        prog="UEPluginPacker",
        description="UE 多版本插件打包器 — CLI 模式",
    )
    Sub = Parser.add_subparsers(dest="command", required=True)

    Build = Sub.add_parser("build", help="对选定引擎批量打包插件")
    Build.add_argument("plugin", help="插件名（Plugins/<name>/<name>.uplugin）")
    Group = Build.add_mutually_exclusive_group()
    Group.add_argument("--engines", help="指定引擎名，逗号分隔，如 '5.2,5.5,5.7'")
    Group.add_argument("--all", action="store_true", help="打包所有已配置的引擎")
    Build.add_argument("--output", help="输出根目录（默认 <ProjectRoot>/PackagedPlugins）")
    Build.add_argument("--no-post", action="store_true", help="跳过 Fab 后处理（版权/FilterPlugin 等）")
    Build.add_argument("--keep-binaries", action="store_true", help="保留 Binaries（覆盖配置的删除Binaries，用于部署到安装版引擎，无需引擎重建模块）")
    Build.set_defaults(Func=CmdBuild)

    Engines = Sub.add_parser("engines", help="列出已配置的引擎")
    Engines.set_defaults(Func=CmdEngines)

    Plugins = Sub.add_parser("plugins", help="列出当前项目下的插件")
    Plugins.set_defaults(Func=CmdPlugins)

    Args = Parser.parse_args(Argv)
    return Args.Func(Args, Path(ProjectRoot).resolve())
