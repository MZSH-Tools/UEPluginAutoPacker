# 🎮 UE 多版本插件打包器

一个用于 **一键打包多个 Unreal Engine 插件版本** 的图形化工具，适用于插件开发者快速构建多个引擎版本的插件安装包。
支持打包日志查看、Fab 规范整理、自动化过滤文件等功能，极大提升插件打包效率与一致性。

---

## 🚀 功能亮点

- 支持添加多个 Unreal Engine 安装路径（Launcher 或源码版）
- 每个引擎状态图标显示：等待中、打包中、✅ 成功、❌ 失败、➖ 已取消
- 图形界面简洁直观，支持日志实时查看，点击切换引擎日志
- 可选的 Fab 插件整理操作：清理中间文件、拷贝文档、生成 FilterPlugin.ini 等
- 支持读取 `.uplugin` 中的作者信息，自动为每个源文件添加版权声明

---

## ⚙️ 使用方法

### ✅ 方式一：使用 `.exe`（推荐）
1. 前往 Releases 页面下载 `UEPluginPacker.exe`
2. 放置到你的 Unreal 项目根目录（即包含 `.uproject` 的目录）
3. 双击运行即可，无需命令行和环境配置

### 🧑‍💻 方式二：源码运行
1. 克隆本仓库
2. 安装 Python 3.8+（建议使用 Miniconda）
3. 安装依赖并运行：

```bash
conda env create -f environment.yml
conda activate UEPluginAutoPacker
pip install -r requirements.txt
python Main.py
```

---

## 💡 每个功能的作用

| 功能项                      | 用途说明 |
|-----------------------------|----------|
| 添加引擎路径               | 注册多个 UE 引擎用于打包 |
| 插件选择                   | 自动检测项目中的 `.uplugin` |
| 转换 MarketplaceURL        | 修改 `.uplugin` 字段为 `FabURL` |
| 删除 Binaries / Intermediate | 清理冗余中间产物 |
| 拷贝 README / Docs         | 将工程文档复制到插件目录 |
| 自动生成 FilterPlugin.ini  | 自动扫描插件根目录下的文件/文件夹，生成用于发布的 `.ini` 过滤配置 |
| 自动添加版权声明           | 插入版权声明（从 `.uplugin` 中读取作者），替换旧注释，覆盖所有 `.h/.cpp/.Build.cs` 文件 |

每项操作均可单独勾选与组合使用，结果将在日志中详细显示，包括生成的版权文本与 ini 内容。

---

## 📤 打包输出说明

- 插件将被打包到 `PackagedPlugins/插件名/引擎名/` 中
- 如启用自动整理，插件中会包含清理后的文件与自动生成的配置
- 如果打包失败，会在对应目录生成 `Failed.log`

---

## ⚠️ 当前限制

- 仅支持构建 Windows 平台插件（Win64）
- 暂不支持 Mac / Linux
- 插件目录需规范，必须包含 `.uplugin` 文件

---

## 📄 许可证

本项目采用 [MIT License](./LICENSE) 协议开源，欢迎自由使用、修改和分发。

---

## 📬 联系方式

作者邮箱：**mengzhishanghun@outlook.com**  
如有定制功能或合作需求，欢迎联系！