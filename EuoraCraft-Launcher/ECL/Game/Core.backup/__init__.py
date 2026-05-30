# ECL.Game.Core - 游戏核心模块

from .C_Libs import (
    ApiUrl,
    name_to_path,
    name_to_uuid,
    is_uuid3,
    unzip,
    find_version,
    replace_last,
    parse_neoforge_version,
    normalize_neoforge_version,
    is_neoforge_snapshot_version,
    get_neoforge_version_info,
    NEOFORGE_VERSION_PATTERN,
)
from .C_Downloader import Downloader
from .C_FilesChecker import FilesChecker
from .C_GetGames import GetGames
from .C_Skin import get_skin_address, download_skin, get_skin_sex, get_avatar_data_url
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
    "parse_neoforge_version",
    "normalize_neoforge_version",
    "is_neoforge_snapshot_version",
    "get_neoforge_version_info",
    "NEOFORGE_VERSION_PATTERN",
    "get_skin_address",
    "download_skin",
    "get_skin_sex",
    # 核心组件
    "Downloader",
    "FilesChecker",
    "GetGames",
    "ECLauncherCore",
]