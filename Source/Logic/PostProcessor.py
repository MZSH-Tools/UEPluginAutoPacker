import os
import shutil
import json
import re
from Source.Logic.ConfigManager import ConfigManager

def ReplaceMarketplaceURL(FilePath):
    try:
        with open(FilePath, "r", encoding="utf-8") as f:
            Content = f.read()

        if '"MarketplaceURL"' in Content:
            NewContent = Content.replace('"MarketplaceURL"', '"FabURL"', 1)
            with open(FilePath, "w", encoding="utf-8") as f:
                f.write(NewContent)
            return "已原样替换 MarketplaceURL → FabURL"
        else:
            return "未发现 MarketplaceURL 字段，无需替换"
    except Exception as e:
        return f"❌ 替换失败：{str(e)}"

def RemoveCopyrightHeaderBlock(lines):
    comment_block_end = 0
    comment_block = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*") or stripped.endswith("*/"):
            comment_block.append(stripped.lower())
            comment_block_end = i + 1
        else:
            break

    contains_copyright = any(
        "copyright" in line or "all rights reserved" in line
        for line in comment_block
    )

    return lines[comment_block_end:] if contains_copyright else lines

def AddCopyrightHeaders(PluginDir, Author, Year="2025"):
    SourceDir = os.path.join(PluginDir, "Source")
    if not os.path.isdir(SourceDir):
        return ["⚠️ 未找到 Source 文件夹，跳过版权添加"]

    Logs = []
    Header = f"// Copyright (c) {Year} {Author}. All rights reserved."
    Logs.append(f"📄 正在插入版权声明：{Header}")
    ValidExts = [".h", ".cpp", ".Build.cs"]

    for root, _, files in os.walk(SourceDir):
        for fname in files:
            if not any(fname.endswith(ext) for ext in ValidExts):
                continue
            fpath = os.path.join(root, fname)

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    original = f.readlines()

                cleaned = RemoveCopyrightHeaderBlock(original)
                new_content = [Header, "\n"] + cleaned

                with open(fpath, "w", encoding="utf-8") as f:
                    f.writelines(new_content)

                rel_path = os.path.relpath(fpath, PluginDir)
                Logs.append(f"✔️ 已添加版权声明 → {rel_path}")
            except Exception as e:
                Logs.append(f"❌ 添加版权失败：{fpath}，原因：{str(e)}")

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

def GenerateFilterPluginIniContent(PluginDir: str) -> str:
    Entries = []
    ExcludedDirs = {"Binaries", "Intermediate", "Resources", "Source"}

    for entry in os.listdir(PluginDir):
        full_path = os.path.join(PluginDir, entry)

        if os.path.isdir(full_path):
            if entry not in ExcludedDirs:
                Entries.append(f"/{entry}/...")
        elif os.path.isfile(full_path):
            if not entry.endswith(".uplugin"):
                Entries.append(f"/{entry}")

    Entries.sort()
    return "[FilterPlugin]\n" + "\n".join(Entries) + "\n"

def RunPostProcess(PluginDir: str, ShouldStopCallback=None):
    Config = ConfigManager()
    Settings = Config.Get("FabSettings", {})
    Logs = []

    def ShouldStop():
        return ShouldStopCallback and ShouldStopCallback()

    def SafeCopy(Src, Dst):
        try:
            if os.path.isdir(Src):
                if os.path.exists(Dst):
                    shutil.rmtree(Dst)
                shutil.copytree(Src, Dst)
            else:
                os.makedirs(os.path.dirname(Dst), exist_ok=True)
                shutil.copy2(Src, Dst)
            Logs.append(f"已拷贝 {os.path.basename(Src)}")
        except Exception as e:
            Logs.append(f"❌ 拷贝失败：{Src} → {Dst}，原因：{str(e)}")

    def SafeDelete(Path):
        try:
            if os.path.exists(Path):
                shutil.rmtree(Path, ignore_errors=True)
                Logs.append(f"已删除 {os.path.basename(Path)} 文件夹")
        except Exception as e:
            Logs.append(f"❌ 删除失败：{Path}，原因：{str(e)}")

    if ShouldStop():
        Logs.append("⚠️ 整理被终止")
        return Logs

    if Settings.get("删除Binaries文件夹", False):
        SafeDelete(os.path.join(PluginDir, "Binaries"))
    if ShouldStop(): return Logs

    if Settings.get("删除Intermediate文件夹", False):
        SafeDelete(os.path.join(PluginDir, "Intermediate"))
    if ShouldStop(): return Logs

    if Settings.get("拷贝项目README文件到插件", False):
        Src = os.path.join(os.getcwd(), "README.md")
        Dst = os.path.join(PluginDir, "README.md")
        if os.path.isfile(Src):
            SafeCopy(Src, Dst)
        else:
            Logs.append("⚠️ 未找到 README.md")
    if ShouldStop(): return Logs

    if Settings.get("拷贝项目Docs文件夹到插件", False):
        Src = os.path.join(os.getcwd(), "Docs")
        Dst = os.path.join(PluginDir, "Docs")
        if os.path.isdir(Src):
            SafeCopy(Src, Dst)
        else:
            Logs.append("⚠️ 未找到 Docs 文件夹")
    if ShouldStop(): return Logs

    if Settings.get("转换MarketplaceURL为FabURL", False):
        for File in os.listdir(PluginDir):
            if File.endswith(".uplugin"):
                FilePath = os.path.join(PluginDir, File)
                Logs.append(ReplaceMarketplaceURL(FilePath))
                break
    if ShouldStop(): return Logs

    if Settings.get("自动生成FilterPlugin.ini", False):
        Dst = os.path.join(PluginDir, "Config", "FilterPlugin.ini")
        try:
            os.makedirs(os.path.dirname(Dst), exist_ok=True)
            content = GenerateFilterPluginIniContent(PluginDir)
            with open(Dst, "w", encoding="utf-8") as f:
                f.write(content)
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
