import sys
import colorama
from pathlib import Path

from .Core.logger import get_logger, LoggerManager
from .Core.config import ConfigManager
from .ui.ui import run_ui
from .Game.java import get_java_list


logger = get_logger("launcher")


class EuoraCraftLauncher:
    
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.config: dict | None = None
        self.debug_mode: bool = False
        self.system_type: str = sys.platform
        self.work_dir: Path = Path.cwd()
        self.program_dir: Path = Path(sys.executable).parent
        self.executable_path: Path = Path(sys.executable)
        self.java_list: list[dict] = []

    def __init_system_test(self) -> bool:
        logger.info(f"当前工作系统：{self.system_type}")
        platform_handlers = {
            "win32": lambda: (colorama.init(), logger.info("已初始化 colorama")),
            "linux": lambda: (logger.info("未支持Linux"), sys.exit(0)),
            "darwin": lambda: (logger.info("未支持macOS"), sys.exit(0)),
        }
        if self.system_type in platform_handlers:
            platform_handlers[self.system_type]()
            return self.system_type == "win32"
        logger.warning(f"未知平台：{self.system_type}")
        return False

    def __handle_version_info(self) -> None:
        launcher_cfg = self.config_manager.get_launcher_config()
        version = launcher_cfg.get("version", "未知")
        version_type = launcher_cfg.get("version_type", "unknown")
        logger.info(f"启动器版本: v{version}")
        logger.info(f"启动器版本类型: {version_type}")
        version_messages = {
            "dev": ("warning", "当前为开发版本，可能存在不稳定因素，请谨慎使用！"),
            "beta": ("info", "当前为测试版本，可能存在部分问题，请注意反馈！"),
            "release": ("info", "当前为正式版本，祝您使用愉快！"),
        }
        if version_type in version_messages:
            level, msg = version_messages[version_type]
            getattr(logger, level)(msg)
        else:
            logger.warning(f"未知的版本类型：{version_type}, 请移除配置文件并重启启动器")

    def __check_game_paths(self) -> None:
        logger.info("检查游戏目录...")
        
        game_config = self.config_manager.get_game_config()
        paths = game_config.get("minecraft_paths", [])
        
        has_default = any(
            (p.get("path", "") if isinstance(p, dict) else p) == "./.minecraft"
            for p in paths
        )
        
        if not has_default:
            logger.info("默认路径 ./.minecraft 不在配置中，自动添加")
            self.config_manager.update_game_config({
                "minecraft_paths": [{"name": "默认路径", "path": "./.minecraft", "protected": True}] + paths
            })
        
        path_status = self.config_manager.check_game_paths_exist()
        
        for status in path_status:
            if status["exists"]:
                logger.info(f"游戏目录已就绪: {status['name']} ({status['path']})")
            else:
                if status["raw_path"] == "./.minecraft":
                    logger.info(f"默认游戏目录不存在，正在创建: {status['raw_path']}")
                    self.config_manager.init_game_paths()
                    logger.info(f"默认游戏目录已创建: {status['path']}")
                else:
                    logger.warning(f"自定义游戏目录不存在: {status['name']} ({status['raw_path']})")

    def init_launcher(self) -> bool:
        logger.info("EuoraCraft Launcher 启动中...")
        
        try:
            self.__init_system_test()
            logger.info(f"当前工作目录：{self.work_dir}")
            logger.info(f"执行文件路径：{self.executable_path}")
            logger.info(f"程序目录：{self.program_dir}")
            
            self.config = self.config_manager.load()
            error = self.config_manager.validate()
            if error:
                logger.error(f"配置校验失败: {error}")
                sys.exit(1)
            
            self.__handle_version_info()
            self.__check_game_paths()
            
            launcher_cfg = self.config_manager.get_launcher_config()
            self.debug_mode = bool(launcher_cfg.get("debug", False))
            logger.info(f"调试模式: {self.debug_mode}")
            
            if self.debug_mode:
                LoggerManager().set_level(10)  # logging.DEBUG
                logger.debug("调试模式已启用")
                import json
                logger.debug(f"完整配置内容：\n{json.dumps(self.config, ensure_ascii=False, indent=2)}")
            
            self.java_list = get_java_list() or []
            if not self.java_list:
                logger.warning("未找到任何 Java 安装")
            logger.debug(f"Java 列表: {self.java_list}")
            
            return True
            
        except Exception as e:
            logger.error(f"初始化启动器时出错: {e}")
            return False

    def run(self) -> None:
        if not self.init_launcher():
            sys.exit(1)
        run_ui(self.config, self.debug_mode, self.config_manager)