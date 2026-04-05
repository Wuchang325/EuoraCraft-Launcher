import json
import re
from pathlib import Path
from typing import Any, Optional
from ..Core.logger import get_logger
from ..Core import __version__, __version_type__

logger = get_logger("config")

class ConfigManager:
    DEFAULT_CONFIG = [
        {
            "launcher": {
                "version": __version__,
                "version_type": __version_type__,
                "debug": False
            },
            "ui": {
                "width": 900,
                "height": 600,
                "title": "EuoraCraft Launcher",
                "locale": "zh-CN",
                "background": {
                    "type": "default",
                    "path": "",
                    "opacity": 0.8,
                    "blur": 0
                }
            },
            "game": {
                "minecraft_paths": ["./.minecraft"],
                "java_auto": True,
                "java_path": "",
                "memory_auto": True,
                "memory_size": 4096
            },
            "download": {
                "mirror_source": "official",
                "download_threads": 4
            },
            "theme": {
                "mode": "system",
                "primary_color": "#0078d4",
                "blur_amount": 6
            }
        }
    ]

    def __init__(self, config_path: str = "setting.json"):
        # 直接使用 Path 对象，不再担心递归问题
        self._config_path = Path(config_path).resolve()
        self._env_path = self._find_env_file()
        self.config: list[dict[str, Any]] = []
        logger.debug("ConfigManager初始化完成，配置文件路径: %s", str(self._config_path))
    
    @property
    def config_path(self) -> Path:
        return self._config_path
    
    @property
    def env_path(self) -> Optional[Path]:
        return self._env_path

    def _find_env_file(self) -> Path | None:
        for env_name in [".env.dev", ".env"]:
            try:
                path = Path(env_name).resolve()
                if path.exists():
                    logger.debug(f"找到环境配置文件: {path}")
                    return path
            except Exception:
                pass
        return None

    def _load_env(self) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        if not self.env_path or not self.env_path.exists():
            return env_vars
        
        logger.info(f"检测到环境配置文件 {self.env_path}，正在读取...")
        try:
            with open(self.env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
        except Exception as e:
            logger.error(f"读取 .env 文件失败: {e}")
        return env_vars

    def _apply_env_overrides(self, config: list[dict[str, Any]]) -> None:
        env_vars = self._load_env()
        if not env_vars or not config:
            return

        for env_key, env_val in env_vars.items():
            if not env_key.startswith("ECL_"):
                continue
            
            parts = env_key.split("_")
            if len(parts) < 3:
                continue
            
            section = parts[1].lower()
            key = "_".join(parts[2:]).lower()
            
            if section not in config[0] or key not in config[0][section]:
                continue
                
            original_val = config[0][section][key]
            if isinstance(original_val, bool):
                new_val = env_val.lower() in ("true", "1", "yes")
            elif isinstance(original_val, int):
                try:
                    new_val = int(env_val)
                except ValueError:
                    continue
            else:
                new_val = env_val
            
            config[0][section][key] = new_val
            logger.info(f"环境变量覆盖配置: [{section}][{key}] -> {new_val}")

    def load(self) -> list[dict[str, Any]]:
        if not self.config_path.exists():
            logger.warning("配置文件不存在，正在生成默认配置...")
            self.config = self.DEFAULT_CONFIG.copy()
            self.save(self.config)
            logger.info(f"默认配置文件已生成：{self.config_path}")
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                logger.info("配置文件读取完成")
            except Exception as e:
                logger.error(f"读取配置文件失败: {e}")
                raise
        self._apply_env_overrides(self.config)
        return self.config

    def save(self, config: list[dict[str, Any]]) -> None:
        try:
            safe_config = self._make_config_safe_for_json(config)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(safe_config, f, ensure_ascii=False, indent=2)
            logger.debug(f"配置已保存到: {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            raise
    
    def _make_config_safe_for_json(self, obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, dict):
            return {k: self._make_config_safe_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._make_config_safe_for_json(item) for item in obj]
        return obj

    def validate(self) -> str | None:
        if not self.config or not isinstance(self.config, list) or len(self.config) == 0:
            return "配置结构错误：配置应为非空列表"

        try:
            launcher_cfg = self.config[0].get("launcher", {})
            version = launcher_cfg.get("version")
            if not version or not re.match(r"^\d+\.\d+\.\d+$", version):
                return f"版本号格式错误: '{version}'，应为数字.数字.数字（如 1.0.0）"
        except Exception as e:
            return f"配置校验异常: {e}"
        
        return None

    # 配置获取方法
    def get_launcher_config(self) -> dict[str, Any]:
        return self.config[0].get("launcher", {}) if self.config else {}

    def get_ui_config(self) -> dict[str, Any]:
        return self.config[0].get("ui", {}) if self.config else {}

    def get_locale_config(self) -> dict[str, str]:
        ui_config = self.get_ui_config()
        return {"locale": ui_config.get("locale", "zh-CN")}

    def update_locale_config(self, locale: str) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        if "ui" not in self.config[0]:
            self.config[0]["ui"] = {}
        self.config[0]["ui"]["locale"] = locale
        self.save(self.config)
        logger.info(f"语言配置已更新: {locale}")

    def get_background_config(self) -> dict[str, Any]:
        ui_config = self.get_ui_config()
        return ui_config.get("background", {"type": "default", "path": "", "opacity": 0.8, "blur": 0})

    def update_background_config(self, background_config: dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        if "ui" not in self.config[0]:
            self.config[0]["ui"] = {}
        self.config[0]["ui"]["background"] = background_config
        self.save(self.config)
        logger.info(f"背景图配置已更新: {background_config.get('type', 'unknown')}")

    def _resolve_game_path(self, path: str) -> Path:
        path_obj = Path(path)
        if not path_obj.is_absolute():
            path_obj = Path.cwd() / path_obj
        return path_obj.resolve()

    def _init_single_path(self, path: str) -> None:
        path_obj = self._resolve_game_path(path)
        if path_obj.exists():
            return
        try:
            (path_obj / "versions").mkdir(parents=True, exist_ok=True)
            (path_obj / "assets").mkdir(exist_ok=True)
            (path_obj / "libraries").mkdir(exist_ok=True)
            logger.info(f"新游戏目录已创建: {path_obj}")
        except Exception as e:
            logger.error(f"创建游戏目录失败 {path}: {e}")

    def init_game_paths(self) -> None:
        game_config = self.config[0].get("game", {})
        paths = game_config.get("minecraft_paths", ["./.minecraft"])
        for path in paths:
            if isinstance(path, dict):
                path = path.get("path", "./.minecraft")
            self._init_single_path(path)

    def check_game_paths_exist(self) -> list[dict[str, Any]]:
        game_config = self.config[0].get("game", {})
        paths = game_config.get("minecraft_paths", ["./.minecraft"])
        results = []
        for p in paths:
            if isinstance(p, dict):
                path_str = p.get("path", "./.minecraft")
                name = p.get("name", "未命名路径")
            else:
                path_str = p
                name = "默认路径"
            resolved_path = self._resolve_game_path(path_str)
            results.append({"name": name, "path": str(resolved_path), "raw_path": path_str, "exists": resolved_path.exists()})
        return results

    def get_game_config(self, auto_init: bool = False) -> dict[str, Any]:
        game_config = self.config[0].get("game", {"minecraft_paths": ["./.minecraft"]})
        if "minecraft_path" in game_config and "minecraft_paths" not in game_config:
            game_config["minecraft_paths"] = [game_config.pop("minecraft_path")]
        elif "minecraft_paths" not in game_config:
            game_config["minecraft_paths"] = ["./.minecraft"]
        if auto_init:
            self.init_game_paths()
        return game_config

    def _ensure_default_minecraft_path(self, paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for p in paths:
            path_str = p.get("path", "") if isinstance(p, dict) else p
            if path_str != "./.minecraft":
                continue
            if isinstance(p, dict):
                p["protected"] = True
                p["name"] = "默认路径"
            return paths
        paths.insert(0, {"name": "默认路径", "path": "./.minecraft", "protected": True})
        return paths

    def update_game_config(self, game_config: dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        current_game_config = self.config[0].get("game", {})
        updated_config = {**current_game_config, **game_config}
        if "minecraft_path" in updated_config and isinstance(updated_config["minecraft_path"], str):
            updated_config["minecraft_paths"] = [{"name": "默认路径", "path": updated_config.pop("minecraft_path"), "protected": True}]
        elif "minecraft_paths" not in updated_config:
            updated_config["minecraft_paths"] = [{"name": "默认路径", "path": "./.minecraft", "protected": True}]
        updated_config["minecraft_paths"] = self._ensure_default_minecraft_path(updated_config["minecraft_paths"])
        old_paths = {p.get("path", "") if isinstance(p, dict) else p for p in current_game_config.get("minecraft_paths", [])}
        new_paths = [p.get("path", "") if isinstance(p, dict) else p for p in updated_config["minecraft_paths"] if (p.get("path", "") if isinstance(p, dict) else p) and (p.get("path", "") if isinstance(p, dict) else p) not in old_paths]
        self.config[0]["game"] = updated_config
        self.save(self.config)
        logger.info("游戏配置已更新")
        for path in new_paths:
            self._init_single_path(path)

    def get_theme_config(self) -> dict[str, Any]:
        return self.config[0].get("theme", {"mode": "system", "primary_color": "#87CEEB", "blur_amount": 6})

    def update_theme_config(self, theme_config: dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        self.config[0]["theme"] = {
            "mode": theme_config.get("mode", "system"),
            "primary_color": theme_config.get("primary_color", "#87CEEB"),
            "blur_amount": theme_config.get("blur_amount", 6)
        }
        self.save(self.config)
        logger.info("主题配置已更新")

    def get_download_config(self) -> dict[str, Any]:
        return self.config[0].get("download", {"mirror_source": "official", "download_threads": 4})

    def update_download_config(self, download_config: dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        self.config[0]["download"] = download_config
        self.save(self.config)
        logger.info("下载配置已更新")

    def __repr__(self) -> str:
        return f"ConfigManager(config_path='{str(self.config_path)}')"