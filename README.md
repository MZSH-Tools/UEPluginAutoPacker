# UE 多版本插件打包器

一个用于 **一键打包多个 Unreal Engine 插件版本** 的工具，适用于插件开发者快速发布多个引擎版本的插件包。工具提供图形界面、打包日志查看、多引擎版本支持等功能。

---

## 🚀 工具特点

- 支持添加多个 Unreal Engine 引擎路径
- 每个引擎状态实时显示（图标式）：等待中、打包中、成功、失败、已取消
- 支持 Fab 规范整理（清理中间文件、复制 README / LICENSE / Docs 等）
- 打包日志实时显示，失败自动保存日志文件
- 图形界面简洁易用，点击即可切换查看每个引擎日志

---

## ⚙️ 使用方式

### ✅ 方法一：使用 `.exe` 可执行文件

1. 下载发布页中的 `UEPluginPacker.exe`
2. 将该文件放入你的 Unreal 项目根目录
3. 双击运行即可，无需配置其他参数

### 🧑‍💻 方法二：使用源码运行

1. 克隆本项目到本地
2. 安装 Python（建议使用 Miniconda）

#### 环境搭建

###### 方法1：使用Conda搭建虚拟环境(推荐)

```bash
conda env create -f environment.yml
conda activate UEPluginAutoPacker
pip install -r requirements.txt
```

##### 方法2：使用 requirements.txt 安装依赖

```bash
pip install -r requirements.txt
```

3. 运行主程序：

```bash
python Main.py
```

---

## ⚠️ 使用限制

- 当前版本仅支持打包 `Win64` 平台插件。

---


## 📁 打包输出路径

成功打包的插件会保存到：

```
PackagedPlugins / 插件名 / 引擎名 /
```

如果打包失败，会生成失败日志文件：

```
PackagedPlugins / 插件名 / 引擎名 / Failed.log
```

---

## 📄 许可证

本项目采用 MIT 开源许可证，详见 [LICENSE](./LICENSE)。

---

## 📬 联系方式

作者邮箱：**mengzhishanghun@outlook.com**

如有功能需求、定制开发或问题反馈，欢迎联系。