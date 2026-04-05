# EuoraCraft Launcher (ECL) - Minecraft 启动器

# 版本信息 (从 Core 导入)
from .Core import __version__, __version_type__

# 导出核心组件，方便外部使用
from .Core import (
    get_logger,
    LoggerManager,
    ColoredFormatter,
    ConfigManager,
)

__all__ = [
    "__version__",
    "__version_type__",
    "get_logger",
    "LoggerManager",
    "ColoredFormatter",
    "ConfigManager",
]
