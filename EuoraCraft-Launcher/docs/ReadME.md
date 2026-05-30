# 介绍
EuoraCraft Launcher 是一个基于 Python 的跨平台 Minecraft 启动器

> 本文档属于开发文档，可能存在滞后性，请以实际代码为主

## 目录结构

```
EuoraCraft-Launcher/
├── main.py                 # 主启动文件
├── ECL/                    # EuoraCraft Launcher 核心模块
│   ├── __init__.py
│   ├── launcher.py         # 启动器主逻辑
│   ├── config.py           # 配置管理
│   ├── logger.py           # 日志管理
│   ├── ui/                 # UI相关模块
│   │   ├── __init__.py
│   │   └── ui.py
│   ├── Core/               # 核心功能模块
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── logger.py
│   └── Game/               # 游戏相关功能
│       ├── __init__.py
│       ├── java.py          # Java管理
│       ├── AccountManager.py # 账户管理
│       ├── MicrosoftAuth.py  # 微软认证
│       └── Core/             # 游戏核心功能
│           ├── __init__.py
│           ├── C_Downloader.py   # 下载器
│           ├── C_FilesChecker.py # 文件检查器
│           ├── C_GetGames.py     # 游戏获取
│           ├── C_Libs.py         # 库管理
│           └── ECLauncherCore.py # 核心启动器
├── docs/                   # 文档目录
│   └── ReadME.md
├── logs/                   # 日志目录
├── test/                   # 测试目录
├── ui/                     # 前端构建输出目录
├── .env.dev               # 开发环境配置
├── .gitignore
├── CHANGELOG.md
├── LICENSE
├── README.md
├── EuoraCraft-Launcher.spec # PyInstaller打包配置
├── pyproject.toml
├── requirements.txt
└── setting.json           # 应用设置
```

## 启动项目

推荐创建虚拟环境，以避免依赖冲突：
```bash
python -m venv venv
```

安装依赖：
```bash
pip install -r requirements.txt
```

在此之前，需要将前端项目构建到`ui/`目录下，并打开ECL/ui目录下的`ui.py`文件。找到
```python
#html_path = resource_path("./index.html")
```

将注释去掉
并注释
```python
html_path = "http://localhost:5173"
```

安装好依赖后，即可直接运行项目根目录下的`main.py`即可启动项目：
```bash
python main.py
```


## 构建项目
构建前请确保已安装 PyInstaller：
```bash
pip install pyinstaller
```
在项目根目录下运行以下命令进行构建：
```bash
pyinstaller EuoraCraft-Launcher.spec
```
构建完成后，生成的可执行文件位于`dist/EuoraCraft-Launcher/`目录下。