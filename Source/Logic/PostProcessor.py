import os
import sys
import shutil
import json
import chardet
from pathlib import Path
from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.PackagingPaths import CheckedPath, CopyToStage, EntryState, PinDirectories, WriteCheckedFile
from Source.Logic.PluginPayload import CompleteFabURL, JsonText, LocalEntries, ReadJson, TopExcluded

def _GetProjectRoot():
    if getattr(sys, 'frozen', False):
        return str(Path(sys.executable).parent.resolve())
    return str(Path(__file__).parent.parent.parent.resolve())

def ReplaceMarketplaceURL(FilePath):
    Manifest = Path(FilePath)
    with PinDirectories(Manifest.parent):
        Manifest = CheckedPath(Manifest)
        Original = EntryState(Manifest)
        Fields = ReadJson(Manifest.read_text(encoding='utf-8-sig'))
        if not CompleteFabURL(Fields):
            return '无需补齐 FabURL'
        WriteCheckedFile(Manifest, JsonText(Fields).encode('utf-8'), Original)
    return '已补齐 FabURL，保留 MarketplaceURL'

def RemoveCopyrightHeaderBlock(lines):
    BlockStart = 0
    while BlockStart < len(lines) and not lines[BlockStart].strip():
        BlockStart += 1

    if BlockStart >= len(lines):
        return lines

    FirstLine = lines[BlockStart].strip()
    BlockEnd = BlockStart
    if FirstLine.startswith("//"):
        while BlockEnd < len(lines) and lines[BlockEnd].strip().startswith("//"):
            BlockEnd += 1
    elif FirstLine.startswith("/*"):
        IsClosedBlock = False
        while BlockEnd < len(lines):
            CurrentLine = lines[BlockEnd].strip()
            BlockEnd += 1
            ClosingIndex = CurrentLine.find("*/")
            if ClosingIndex >= 0:
                if CurrentLine[ClosingIndex + 2:].strip():
                    return lines
                IsClosedBlock = True
                break
        if not IsClosedBlock:
            return lines
    else:
        return lines

    CommentBlock = [Line.strip().lower() for Line in lines[BlockStart:BlockEnd]]
    ContainsCopyright = any(
        "copyright" in Line or "all rights reserved" in Line
        for Line in CommentBlock
    )
    if not ContainsCopyright:
        return lines

    while BlockEnd < len(lines) and not lines[BlockEnd].strip():
        BlockEnd += 1
    return lines[BlockEnd:]

def DetectFileEncoding(FilePath: str) -> str:
    with open(FilePath, "rb") as File:
        Raw = File.read()

    if Raw.startswith(b"\xef\xbb\xbf"):
        Raw.decode("utf-8-sig")
        return "utf-8-sig"

    try:
        Raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    Result = chardet.detect(Raw)
    return Result.get("encoding") or "utf-8"

def AddCopyrightHeaders(PluginDir: str, Author: str, Year: str = "2025") -> list:
    SourceDir = os.path.join(PluginDir, "Source")
    if not os.path.isdir(SourceDir):
        return ["⚠️ 未找到 Source 文件夹，跳过版权添加"]

    Logs = []
    HeaderLine = f"// Copyright (c) {Year} {Author}. All rights reserved."
    Logs.append(f"📄 正在插入版权声明：{HeaderLine}")
    ValidExts = [".h", ".cpp", ".Build.cs"]

    for Root, Dirs, Files in os.walk(SourceDir):
        Dirs[:] = [Directory for Directory in Dirs if Directory.casefold() not in ('thirdparty', 'vendor')]

        for FileName in Files:
            if not any(FileName.endswith(Ext) for Ext in ValidExts):
                continue

            FilePath = Path(Root) / FileName

            try:
                Original = EntryState(CheckedPath(FilePath))
                if Original is None:
                    raise FileNotFoundError(FilePath)
                Encoding = DetectFileEncoding(FilePath)

                with open(FilePath, "r", encoding=Encoding, errors="strict", newline="") as File:
                    OriginalLines = File.readlines()

                CleanedLines = RemoveCopyrightHeaderBlock(OriginalLines)
                Newline = "\n"
                for Line in OriginalLines:
                    if Line.endswith("\r\n"):
                        Newline = "\r\n"
                        break
                    if Line.endswith("\n"):
                        break
                    if Line.endswith("\r"):
                        Newline = "\r"
                        break
                NewLines = [HeaderLine + Newline, Newline] + CleanedLines

                WriteCheckedFile(FilePath, ''.join(NewLines).encode(Encoding), Original)

                RelPath = os.path.relpath(FilePath, PluginDir)
                Logs.append(f"✔️ 已添加版权声明 → {RelPath}（编码：{Encoding}）")
            except Exception as E:
                Logs.append(f"❌ 添加版权失败：{FilePath}，原因：{str(E)}")

    return Logs

def GetPluginAuthor(PluginDir):
    for fname in os.listdir(PluginDir):
        if fname.endswith(".uplugin"):
            path = os.path.join(PluginDir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("CreatedBy", "Unknown Author")
            except Exception:
                return "Unknown Author"
    return "Unknown Author"

def GenerateFilterPluginIniContent(PluginDir: str, Existing: str = '') -> str:
    Entries = []
    ExcludedDirs = {"binaries", "resources", "source", "config", "content"} | TopExcluded

    for entry in os.listdir(PluginDir):
        if entry.casefold() in LocalEntries:
            continue
        full_path = os.path.join(PluginDir, entry)

        if os.path.isdir(full_path):
            if entry.casefold() not in ExcludedDirs:
                Entries.append(f"/{entry}/...")
        elif os.path.isfile(full_path):
            if not entry.endswith(".uplugin"):
                Entries.append(f"/{entry}")

    Entries.sort()
    if (Path(PluginDir) / 'Binaries/ThirdParty').is_dir():
        Entries.append('/Binaries/ThirdParty/...')
    Lines = Existing.splitlines()
    for Index, Line in enumerate(Lines):
        if Line.strip().casefold() == '[filterplugin]':
            Lines[Index + 1:Index + 1] = Entries
            break
    else:
        Lines[:0] = ['[FilterPlugin]', *Entries]
    return '\n'.join(Lines) + '\n'

def RunPostProcess(PluginDir: str, ShouldStopCallback=None, KeepBinaries: bool = False):
    Config = ConfigManager()
    Settings = Config.Get("FabSettings", {})
    Logs = []

    def ShouldStop():
        return ShouldStopCallback and ShouldStopCallback()

    def SafeCopy(Src, Dst):
        try:
            Target = Path(Dst)
            with PinDirectories(Target.parent, Create=True):
                Target = CheckedPath(Target)
                if os.path.isdir(Src):
                    if Target.exists():
                        shutil.rmtree(Target)
                    CopyToStage(CheckedPath(Src), Target, lambda Directory, Names: [
                        Name for Name in Names if Name.casefold() in LocalEntries])
                else:
                    Original = EntryState(Target)
                    WriteCheckedFile(Target, CheckedPath(Src).read_bytes(), Original)
            Logs.append(f"已拷贝 {os.path.basename(Src)}")
        except Exception as e:
            Logs.append(f"❌ 拷贝失败：{Src} → {Dst}，原因：{str(e)}")

    def SafeDelete(Path):
        try:
            with PinDirectories(os.path.dirname(Path)):
                Target = CheckedPath(Path)
                if Target.exists():
                    shutil.rmtree(Target)
                    Logs.append(f"已删除 {os.path.basename(Path)} 文件夹")
        except Exception as e:
            Logs.append(f"❌ 删除失败：{Path}，原因：{str(e)}")

    if ShouldStop():
        Logs.append("⚠️ 整理被终止")
        return Logs

    if Settings.get("删除Binaries文件夹", False):
        if KeepBinaries:
            Logs.append("保留 Binaries 文件夹（本次打包选项覆盖整理设置）")
        else:
            SafeDelete(os.path.join(PluginDir, "Binaries"))
    if ShouldStop(): return Logs

    if Settings.get("删除Intermediate文件夹", False):
        SafeDelete(os.path.join(PluginDir, "Intermediate"))
    if ShouldStop(): return Logs

    if Settings.get("拷贝项目README文件到插件", False):
        Src = os.path.join(_GetProjectRoot(), "README.md")
        Dst = os.path.join(PluginDir, "README.md")
        if os.path.isfile(Src):
            SafeCopy(Src, Dst)
        else:
            Logs.append("❌ 拷贝失败：找不到项目 README.md")
    if ShouldStop(): return Logs

    if Settings.get("拷贝项目Docs文件夹到插件", False):
        Src = os.path.join(_GetProjectRoot(), "Docs")
        Dst = os.path.join(PluginDir, "Docs")
        if os.path.isdir(Src):
            SafeCopy(Src, Dst)
        else:
            Logs.append("❌ 拷贝失败：找不到项目 Docs 文件夹")
    if ShouldStop(): return Logs

    if Settings.get("转换MarketplaceURL为FabURL", False):
        for File in os.listdir(PluginDir):
            if File.endswith(".uplugin"):
                FilePath = os.path.join(PluginDir, File)
                Logs.append(ReplaceMarketplaceURL(FilePath))
                break
    if ShouldStop(): return Logs

    if Settings.get("自动生成FilterPlugin.ini", False):
        Dst = Path(PluginDir) / 'Config' / 'FilterPlugin.ini'
        try:
            with PinDirectories(Dst.parent, Create=True):
                Original = EntryState(CheckedPath(Dst))
                Existing = Dst.read_text(encoding='utf-8-sig') if Original is not None else ''
                content = GenerateFilterPluginIniContent(PluginDir, Existing)
                WriteCheckedFile(Dst, content.encode('utf-8'), Original)
            Logs.append("✅ 已自动生成 FilterPlugin.ini 文件")
            Logs.append("📄 FilterPlugin.ini 内容如下：")
            for line in content.strip().splitlines():
                Logs.append("    " + line)
        except Exception as e:
            Logs.append(f"❌ 生成 FilterPlugin.ini 失败：{str(e)}")
    if ShouldStop(): return Logs

    if Settings.get("自动添加版权声明", False):
        Author = GetPluginAuthor(PluginDir)
        Logs += AddCopyrightHeaders(PluginDir, Author)
    if ShouldStop(): return Logs

    return Logs
