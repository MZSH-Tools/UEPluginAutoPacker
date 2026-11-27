# UE 多版本插件打包器

在 Windows 上为多个 Unreal Engine 版本构建同一个插件。支持安装版、源码版引擎和 `Win64` 目标，也能把已有产物整理成 Fab 源码 ZIP。

## 开始使用

1. 将 `UEPluginPacker.exe` 放到包含 `.uproject` 的项目根目录。插件描述符放在 `Plugins/<插件名>/<插件名>.uplugin`。
2. 双击打开图形界面，添加引擎根目录，按实际情况勾选「此引擎为源码编译版本」。构建需要 `Engine/Build/BatchFiles/RunUAT.bat`；构建和生成 ZIP 都需要该引擎的 `Engine/Build/Build.version`。
3. 选择插件、勾选引擎，然后点「开始打包」。需要 ZIP 时，勾选「构建完成后自动压缩」；只想保留 ZIP 时，再勾选下级的「压缩完成后删除源码」。

从源码运行时，先用 `conda env create -f environment.yml` 创建环境，再用 `conda run -n UEPluginAutoPacker python -m pip install -r requirements.txt` 安装依赖。双击 `Run.bat` 打开图形界面；传入参数会运行 CLI，例如 `Run.bat build --help`。

## 构建与 ZIP

图形界面只有一套构建流程，不需要选择用途。构建目录保留源码、资源和匹配引擎的 DLL，并核对模块清单与引擎 `BuildId`；不会自动安装到引擎。

「构建完成后自动压缩」默认不勾选。勾选后生成源码 ZIP，排除本插件可重建的 DLL、PDB 和缓存，保留必要的第三方依赖。

下级选项「压缩完成后删除源码」默认不勾选，只在自动压缩开启时可选。它只删除当前 ZIP 对应的引擎构建输出目录，例如 `PackagedPlugins/MyPlugin/UE_5.7/`，最终只保留该版 ZIP；项目 `Plugins` 下的原始源码、其他引擎版本目录和其他 ZIP 均不受影响。ZIP 写入、校验或提交失败时不删除原有输出。关闭自动压缩会同时取消删除选项。

清理前会核对已有输出的 `EngineVersion`。版本不符或缺失时保留目录并报错，不根据目录名猜测版本；可取消删除选项后重新构建。

CLI 默认与 GUI 走同一构建流程，保留源码和 DLL 并校验模块及 `BuildId`，默认不压缩。`--zip`、`--no-zip` 互斥。旧脚本的 `--profile` 参数仍可使用，但不再显示在帮助中：`deploy` 使用正常构建流程，`fab` 额外校验 Fab 元数据且默认生成 ZIP。它不能与 `--no-post` 同用，`fab` 也不能与 `--keep-binaries` 同用。`--no-post` 跳过可选整理，`--keep-binaries` 为旧命令保留。

构建使用源插件的临时副本。「Fab格式化整理」中的「自动添加版本信息」默认开启，从选中引擎读取主、次、补丁版本，写入构建目录及 ZIP 描述符的 `EngineVersion`；取消后两者均不写入该字段。Fab 上传建议保持开启。源码描述符不改写，源文件中显式声明的 `Installed`、`EnabledByDefault` 等标记会恢复到产物。其他整理选项可复制 README 和 Docs、清理中间文件、生成 `FilterPlugin.ini`、替换产物里的版权头；不会改写原插件或其版权。补齐 `FabURL` 时保留 `MarketplaceURL`，两个字段同时存在却不一致时会报错。

## 命令行

```bat
UEPluginPacker.exe engines
UEPluginPacker.exe plugins
UEPluginPacker.exe build MyPlugin
UEPluginPacker.exe build MyPlugin --all --zip
UEPluginPacker.exe build MyPlugin --engines UE_5.4,UE_5.7
UEPluginPacker.exe build MyPlugin --all --zip --delete-output-after-zip --add-version
UEPluginPacker.exe build MyPlugin --all --no-zip --keep-output --no-add-version
UEPluginPacker.exe build MyPlugin --all --no-post
UEPluginPacker.exe zip MyPlugin --engines UE_5.7 --output D:\temp\out
```

`--engines` 使用配置中的引擎名，以逗号分隔；`--all` 选择全部引擎。省略两者时使用图形界面勾选的引擎。`--output` 对构建和仅生成 ZIP 都表示产物根目录，默认 `PackagedPlugins`。退出码：`0` 全部成功，`1` 至少一个引擎失败，`2` 参数或选择配置有误，`130` 用户按下 Ctrl+C。

CLI 可自行选择 `--zip` / `--no-zip`、`--delete-output-after-zip` / `--keep-output`、`--add-version` / `--no-add-version`。删除选项必须同时生成 ZIP；默认保留构建目录。未传版本开关时读取保存的「自动添加版本信息」设置，缺省开启。图形界面不再提供「仅生成 ZIP」按钮；CLI 的 `zip` 子命令保留，用于复用已有产物，且不会删除已有目录。

## 产物与失败恢复

- 正式目录：`PackagedPlugins/<插件名>/<引擎名>/`。源码 ZIP 放在同一插件目录下，例如 `MyPlugin_UE_5.7_Source.zip`，按实际引擎主、次版本命名。同一批不能为两个相同主、次版本的引擎生成 ZIP。
- ZIP 内只有一个插件根。保留源码、配置、资源、内容、着色器及明确的第三方依赖（如 `ThirdParty`、`Vendor` 或 `FilterPlugin.ini` 明确纳入的库文件）；排除顶层 `Intermediate`、`HostProject`、`Saved`、`Tests`、版本控制及本机配置，以及可识别的本插件 DLL、PDB 和模块清单。`Source` 内的 `Tests` 不受影响。UAT 或后处理漏掉、修改了依赖，或遇到归属不明的二进制时，工具会报错。
- `zip` 不运行 UAT，不重跑整理，也不改正式目录。有合法同名描述符和实际载荷的旧产物，即使没有 `EngineVersion` 也可处理；版本字段只在 ZIP 副本中补齐。带 `Failed.log` 的旧目录、空壳或未完成事务不接受。不请求 ZIP 时，旧 ZIP 不读取、不替换，也不会列为本次产物。
- 工具在输出所在卷准备和校验产物，再替换正式目录与 ZIP。构建或整理失败时，日志写在正式引擎目录旁的 `.<引擎名>.failed-*.log`。若留下 `.<引擎名>.transaction`，先保留该目录和同级的 `.<引擎名>.transaction-*` 暂存件及备份；如有 `commit.json`，以其中的路径核对上次提交及回滚，再恢复产物。不要直接删除唯一备份。
- UAT 日志和临时文件写入本次事务目录，不沿用外部日志路径。源码版引擎仍可构建：Native UBT 可能向引擎的 `Intermediate`、`Binaries` 写入必要的生成物，工具不改引擎源代码。若留下 `running.json`，先确认本次 UAT 进程树已退出，再处理事务目录。
- 开始提交前可取消当前引擎；开始提交后，停止只取消后续引擎，当前提交会完成或回滚。
- 显式 `fab` 要求对应商品 UUID 的 Launcher 链接，两个 URL 字段可以互补；适用模块须明确声明平台范围。`deploy` 校验适用于 Win64 的模块、DLL 映射和所选引擎的清单 `BuildId`。这两项门禁不追溯到旧版产物的 `zip` 命令。
- 输出目录不能与源插件或任一已配置引擎根互相包含。路径使用实际拼写，不使用短路径、链接或 junction；工具不会覆盖归属不明的旧产物。

## 许可证

本项目采用 [MIT License](./LICENSE)。

## 联系方式

作者邮箱：**mengzhishanghun@outlook.com**
