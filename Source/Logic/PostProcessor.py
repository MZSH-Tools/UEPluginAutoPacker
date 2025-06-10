import os
import shutil
import json
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

    # 删除 Binaries
    if Settings.get("删除Binaries文件夹", False):
        SafeDelete(os.path.join(PluginDir, "Binaries"))
    if ShouldStop(): return Logs

    # 删除 Intermediate
    if Settings.get("删除Intermediate文件夹", False):
        SafeDelete(os.path.join(PluginDir, "Intermediate"))
    if ShouldStop(): return Logs

    # 拷贝 README.md
    if Settings.get("拷贝项目README文件到插件", False):
        Src = os.path.join(os.getcwd(), "README.md")
        Dst = os.path.join(PluginDir, "README.md")
        if os.path.isfile(Src):
            SafeCopy(Src, Dst)
        else:
            Logs.append("⚠️ 未找到 README.md")
    if ShouldStop(): return Logs

    # 拷贝 LICENSE
    if Settings.get("拷贝项目LICENSE文件到插件", False):
        Src = os.path.join(os.getcwd(), "LICENSE")
        Dst = os.path.join(PluginDir, "LICENSE")
        if os.path.isfile(Src):
            SafeCopy(Src, Dst)
        else:
            Logs.append("⚠️ 未找到 LICENSE")
    if ShouldStop(): return Logs

    # 拷贝 Docs 文件夹
    if Settings.get("拷贝项目Docs文件夹到插件", False):
        Src = os.path.join(os.getcwd(), "Docs")
        Dst = os.path.join(PluginDir, "Docs")
        if os.path.isdir(Src):
            SafeCopy(Src, Dst)
        else:
            Logs.append("⚠️ 未找到 Docs 文件夹")
    if ShouldStop(): return Logs

    # 替换 uplugin 中 MarketplaceURL → FabURL（保留格式）
    if Settings.get("转换MarketplaceURL为FabURL", False):
        for File in os.listdir(PluginDir):
            if File.endswith(".uplugin"):
                FilePath = os.path.join(PluginDir, File)
                Logs.append(ReplaceMarketplaceURL(FilePath))
                break
    if ShouldStop(): return Logs

    # 生成 FilterPlugin.ini（读取自定义内容）
    if Settings.get("生成自定义FilterPlugin.ini文件", False):
        Dst = os.path.join(PluginDir, "Config", "FilterPlugin.ini")
        try:
            os.makedirs(os.path.dirname(Dst), exist_ok=True)
            Text = Config.Get("FabSettings.FilterPluginText", "/Docs/...\n/LICENSE\n/README.md").strip()
            FinalContent = "[FilterPlugin]\n" + Text + "\n"
            with open(Dst, "w", encoding="utf-8") as f:
                f.write(FinalContent)
            Logs.append("已生成 FilterPlugin.ini 文件")
        except Exception as e:
            Logs.append(f"❌ 写入 FilterPlugin.ini 失败：{str(e)}")

    return Logs
