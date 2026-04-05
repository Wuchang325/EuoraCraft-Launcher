# ECL.Game.Core - 游戏核心模块
# 包含游戏启动、文件检查、下载等核心功能

from .C_Libs import (
    ApiUrl,
    name_to_path,
    name_to_uuid,
    is_uuid3,
    unzip,
    find_version,
    replace_last,
)
from .C_Downloader import Downloader
from .C_FilesChecker import FilesChecker
from .C_GetGames import GetGames
from .ECLauncherCore import ECLauncherCore

__all__ = [
    # Libs 工具类
    "ApiUrl",
    "name_to_path",
    "name_to_uuid",
    "is_uuid3",
    "unzip",
    "find_version",
    "replace_last",
    # 核心组件
    "Downloader",
    "FilesChecker",
    "GetGames",
    "ECLauncherCore",
]
