import os
import sys
import base64
import requests
import webview
import ctypes
from ctypes import wintypes
from pathlib import Path
from tkinter import Tk, filedialog
from typing import Any

from ..Core.logger import get_logger
from ..Game import java
from ..Game import ECLauncherCore
from ..Game.AccountManager import get_account_manager


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


logger = get_logger("ui")


def get_resource_path(relative_path: str) -> Path:
    # PyInstaller 打包后资源位于 _MEIPASS 临时目录，开发时直接用当前工作目录
    return Path(getattr(sys, '_MEIPASS', Path.cwd())) / relative_path


def make_json_safe(obj: Any) -> Any:
    # webview 的 js_api 要求返回 JSON 可序列化数据，Path 对象、set/tuple 等需要转换
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, (set, tuple)):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        # 自定义对象直接转字符串，避免序列化失败导致前端收不到响应
        return str(obj)


class Api:
    
    def __init__(self, config_manager) -> None:
        self._config_manager = config_manager
        self.__ensure_config_loaded()
    
    def __ensure_config_loaded(self) -> None:
        # 配置管理器延迟加载设计：首次访问时才读取文件，避免启动时阻塞
        try:
            if not self._config_manager.config:
                self._config_manager.load()
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    
    def __dir__(self) -> list[str]:
        # 显式列出暴露给前端的方法，webview 通过反射获取可用 API 列表
        return [
            'minimize_window',
            'close_window',
            'get_window_position',
            'set_window_position',
            'get_launcher_config',
            'get_background_config',
            'get_background_image',
            'update_background_config',
            'update_background_image',
            'load_image_from_url',
            'load_image_from_local',
            'select_local_image',
            'get_game_config',
            'update_game_config',
            'get_java_list',
            'get_theme_config',
            'update_theme_config',
            'get_download_config',
            'update_download_config',
            'get_locale_config',
            'update_locale_config',
            'select_directory',
            'select_java_executable',
            'scan_versions_in_path',
            'get_minecraft_versions',
            'get_fabric_versions',
            'install_version',
            'ping',
            # 账户管理 API
            'get_accounts',
            'get_current_account',
            'add_offline_account',
            'start_microsoft_login',
            'complete_microsoft_login',
            'switch_account',
            'remove_account',
            'refresh_account_profile'
        ]

    def ping(self) -> dict[str, Any]:
        return {
            "success": True,
            "data": {"status": "ok", "message": "API连接正常"},
            "message": "Pong"
        }

    def minimize_window(self) -> dict[str, Any]:
        try:
            if webview.windows:
                webview.windows[0].minimize()
                return {"success": True, "message": "窗口已最小化"}
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error(f"最小化窗口失败: {e}")
            return {"success": False, "message": str(e)}
        
    def close_window(self) -> dict[str, Any]:
        try:
            if webview.windows:
                webview.windows[0].destroy()
                return {"success": True, "message": "窗口已关闭"}
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error(f"关闭窗口失败: {e}")
            return {"success": False, "message": str(e)}

    def get_window_position(self) -> dict[str, Any]:
        try:
            if webview.windows:
                window = webview.windows[0]
                return {
                    "success": True,
                    "data": {
                        "x": window.x,
                        "y": window.y,
                        "width": window.width,
                        "height": window.height
                    },
                    "message": "获取窗口位置成功"
                }
            return {"success": False, "message": "窗口未找到", "data": None}
        except Exception as e:
            logger.error(f"获取窗口位置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def set_window_position(self, x: int, y: int) -> dict[str, Any]:
        try:
            if webview.windows:
                webview.windows[0].move(x, y)
                return {
                    "success": True,
                    "message": f"窗口位置已设置为 ({x}, {y})"
                }
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error(f"设置窗口位置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_launcher_config(self) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_launcher_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回启动器配置: {safe_config}")
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error(f"获取启动器配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_background_config(self) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_background_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回背景图配置: {safe_config}")
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error(f"获取背景图配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_background_image(self) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_background_config()
            path_str = config.get("path", "")
            logger.info(f"[get_background_image] 配置中的路径: {path_str}")
            
            if not path_str:
                return {"success": False, "message": "未设置背景图", "data": None}
            
            # 统一路径分隔符为系统分隔符
            path_str = path_str.replace('/', os.sep).replace('\\', os.sep)
            path = Path(path_str)
            logger.info(f"[get_background_image] 解析后的路径: {path}")
            
            if not path.exists():
                logger.error(f"[get_background_image] 文件不存在: {path}")
                return {"success": False, "message": f"背景图文件不存在: {path_str}", "data": None}
            
            try:
                image_data = path.read_bytes()
                logger.info(f"[get_background_image] 读取成功: {len(image_data)} bytes")
            except Exception as e:
                logger.error(f"[get_background_image] 读取文件失败: {e}")
                return {"success": False, "message": f"读取背景图文件失败: {e}", "data": None}
            
            # 前端 img 标签要求完整的 data URI scheme，不同格式的 MIME 类型必须准确声明
            mime_map = {
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg'
            }
            mime_type = mime_map.get(path.suffix.lower(), 'image/jpeg')
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            logger.info(f"[get_background_image] Base64 长度: {len(base64_data)}")
            
            return {
                "success": True,
                "data": {
                    "base64": f"data:{mime_type};base64,{base64_data}",
                    "path": str(path).replace('\\', '/'),
                    "type": config.get("type", "local")
                },
                "message": "获取成功"
            }
        except Exception as e:
            logger.error(f"[get_background_image] 异常: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_background_config(self, background_config: dict[str, Any]) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            
            # 前端多次读取本地文件会有权限问题，后端一次性转 base64 后前端直接用内存数据渲染
            if background_config.get("type") == "local" and background_config.get("path"):
                path = Path(background_config["path"])
                if path.exists():
                    background_config["image_base64"] = base64.b64encode(path.read_bytes()).decode("utf-8")
            
            self._config_manager.update_background_config(background_config)
            logger.info(f"背景图配置已更新: {background_config.get('type')}")
            
            # 背景模糊值同时影响主题 CSS 变量，两处配置必须同步避免显示不一致
            if "blur" in background_config:
                current_theme = self._config_manager.get_theme_config()
                current_theme["blur_amount"] = background_config["blur"]
                self._config_manager.update_theme_config(current_theme)
                logger.info(f"同步背景模糊值到主题配置: {background_config['blur']}")
            
            return {"success": True, "message": "背景图更新成功"}
        except Exception as e:
            logger.error(f"更新背景图配置失败: {e}")
            return {"success": False, "message": str(e)}

    def update_background_image(self, image_type: str, image_path: str) -> dict[str, Any]:
        return self.update_background_config({
            "type": image_type,
            "path": image_path,
            "opacity": 0.8,
            "blur": 0
        })

    def load_image_from_url(self, url: str) -> dict[str, Any]:
        try:
            logger.info(f"[load_image_from_url] 开始下载图片: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '')
            logger.info(f"[load_image_from_url] Content-Type: {content_type}")
            if not content_type.startswith('image/'):
                return {"success": False, "message": "URL不是图片类型", "data": None}
            
            ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
            
            # 确定应用数据目录
            if getattr(sys, 'frozen', False):
                # PyInstaller 打包模式：使用可执行文件所在目录
                app_dir = Path(sys.executable).parent
            else:
                # 开发模式：使用当前工作目录
                app_dir = Path.cwd()
            
            background_dir = app_dir / "backgrounds"
            background_dir.mkdir(exist_ok=True)
            logger.info(f"[load_image_from_url] 背景图目录: {background_dir}")
            
            # URL 可能包含特殊字符或过长，直接用 hash 生成短文件名避免文件系统限制
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            file_path = background_dir / f"bg_{url_hash}.{ext}"
            logger.info(f"[load_image_from_url] 保存路径: {file_path}")
            
            file_path.write_bytes(response.content)
            
            # 验证文件确实已写入
            if not file_path.exists():
                logger.error(f"[load_image_from_url] 文件保存失败，路径不存在: {file_path}")
                return {"success": False, "message": "图片保存失败", "data": None}
            
            # 返回绝对路径（使用正斜杠，避免 Windows 反斜杠问题）
            abs_path = str(file_path.resolve()).replace('\\', '/')
            logger.info(f"[load_image_from_url] 成功: {abs_path} ({len(response.content)} bytes)")
            
            return {
                "success": True,
                "data": {"path": abs_path},
                "message": "图片下载成功"
            }
        except Exception as e:
            logger.error(f"加载网络图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def load_image_from_local(self, file_path: str) -> dict[str, Any]:
        try:
            path_obj = Path(file_path)
            if not path_obj.exists():
                return {"success": False, "message": f"文件不存在: {file_path}", "data": None}
            
            valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            if path_obj.suffix.lower() not in valid_extensions:
                return {"success": False, "message": f"不支持的图片格式: {path_obj.suffix}", "data": None}
            
            return {
                "success": True,
                "data": {"path": str(path_obj.absolute())},
                "message": "图片验证成功"
            }
        except Exception as e:
            logger.error(f"验证本地图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def select_local_image(self) -> dict[str, Any]:
        try:
            window = webview.windows[0] if webview.windows else None
            if not window:
                return {"success": False, "message": "窗口未找到", "data": None}
            
            result = window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Image files (*.jpg;*.jpeg;*.png;*.gif;*.webp)', 'All files (*.*)')
            )
            
            if result and isinstance(result, (list, tuple)) and len(result) > 0:
                return self.load_image_from_local(str(result[0]))
            elif result and isinstance(result, str):
                return self.load_image_from_local(result)
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error(f"选择本地图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_game_config(self) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_game_config()
            
            # 旧版本只存单个路径字符串，新版本改为多路径列表结构，需要自动迁移避免配置丢失
            if "minecraft_paths" not in config:
                if "minecraft_path" in config and isinstance(config["minecraft_path"], str):
                    config["minecraft_paths"] = [{"name": "默认路径", "path": config.pop("minecraft_path"), "protected": True}]
                else:
                    config["minecraft_paths"] = [{"name": "默认路径", "path": "./.minecraft", "protected": True}]
            
            # 前端期望统一为字典格式包含 name 字段，历史数据可能是纯字符串路径需要转换
            formatted_paths = []
            for i, p in enumerate(config["minecraft_paths"]):
                if isinstance(p, dict):
                    path_obj = {"name": p.get("name", f"路径{i+1}"), "path": p.get("path", "")}
                else:
                    path_obj = {"name": f"路径{i+1}", "path": p}
                
                if path_obj["path"] == "./.minecraft":
                    path_obj["name"] = "默认路径"
                
                formatted_paths.append(path_obj)
            
            config["minecraft_paths"] = formatted_paths
            
            safe_config = make_json_safe(config)
            logger.debug(f"返回游戏配置: {safe_config}")
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error(f"获取游戏配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_game_config(self, game_config: dict[str, Any]) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            
            # 默认路径是程序运行的基础依赖，用户误删会导致后续逻辑崩溃，必须强制保留
            if "minecraft_paths" in game_config:
                paths = game_config["minecraft_paths"]
                has_default = any(
                    (p.get("path", "") if isinstance(p, dict) else p) == "./.minecraft"
                    for p in paths
                )
                if not has_default:
                    logger.warning("检测到默认路径被删除，自动恢复")
                    paths.insert(0, {"name": "默认路径", "path": "./.minecraft", "protected": True})
            
            self._config_manager.update_game_config(game_config)
            return {"success": True, "message": "游戏配置更新成功"}
        except Exception as e:
            logger.error(f"更新游戏配置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_java_list(self) -> dict[str, Any]:
        try:
            java_list = java.get_java_list()
            
            if java_list is False or not java_list:
                return {
                    "success": True,
                    "data": [],
                    "message": "未找到Java安装"
                }
            
            java_dicts = []
            for java_info in java_list:
                java_dicts.append({
                    "path": java_info.path,
                    "version": java_info.version,
                    "major_version": java_info.major_version,
                    "java_type": java_info.java_type,
                    "arch": java_info.arch,
                    "sources": java_info.sources
                })
            
            return {
                "success": True,
                "data": java_dicts,
                "message": f"找到 {len(java_dicts)} 个Java安装"
            }
        except Exception as e:
            logger.error(f"获取Java列表失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_theme_config(self) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_theme_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回主题配置: {safe_config}")
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error(f"获取主题配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_theme_config(self, theme_config: dict[str, Any]) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            self._config_manager.update_theme_config(theme_config)
            return {"success": True, "message": "主题配置更新成功"}
        except Exception as e:
            logger.error(f"更新主题配置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_download_config(self) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_download_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回下载配置: {safe_config}")
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error(f"获取下载配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_download_config(self, download_config: dict[str, Any]) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            self._config_manager.update_download_config(download_config)
            return {"success": True, "message": "下载配置更新成功"}
        except Exception as e:
            logger.error(f"更新下载配置失败: {e}")
            return {"success": False, "message": str(e)}

    def get_locale_config(self) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_locale_config()
            safe_config = make_json_safe(config)
            logger.debug(f"返回语言配置: {safe_config}")
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error(f"获取语言配置失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def update_locale_config(self, locale: str) -> dict[str, Any]:
        try:
            self.__ensure_config_loaded()
            self._config_manager.update_locale_config(locale)
            return {"success": True, "message": "语言配置更新成功"}
        except Exception as e:
            logger.error(f"更新语言配置失败: {e}")
            return {"success": False, "message": str(e)}

    def select_directory(self) -> dict[str, Any]:
        try:
            root = Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            selected_dir = filedialog.askdirectory(title="选择目录")
            root.destroy()
            
            if selected_dir:
                return {
                    "success": True,
                    "data": {"path": selected_dir},
                    "message": "目录选择成功"
                }
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error(f"选择目录失败: {e}")
            return {"success": False, "message": str(e), "data": None}
    
    def select_java_executable(self) -> dict[str, Any]:
        try:
            window = webview.windows[0] if webview.windows else None
            if not window:
                return {"success": False, "message": "窗口未找到", "data": None}
            
            result = window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Java Executable (java.exe;java)', 'All files (*.*)')
            )
            
            if result and isinstance(result, (list, tuple)) and len(result) > 0:
                return {
                    "success": True,
                    "data": {"path": str(result[0])},
                    "message": "Java 路径选择成功"
                }
            elif result and isinstance(result, str):
                return {
                    "success": True,
                    "data": {"path": result},
                    "message": "Java 路径选择成功"
                }
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error(f"选择 Java 路径失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def scan_versions_in_path(self, path: str | list[str] | list[dict[str, str]]) -> dict[str, Any]:
        try:
            # 前端组件库可能传递多层嵌套结构，需要递归解包直到拿到实际字符串路径
            actual_path = path
            while isinstance(actual_path, list) and len(actual_path) > 0:
                first = actual_path[0]
                if isinstance(first, dict) and "path" in first:
                    actual_path = first["path"]
                    break
                actual_path = first
            
            if isinstance(actual_path, list):
                if len(actual_path) == 0:
                    return {"success": False, "message": "路径列表为空", "data": None}
                actual_path = actual_path[0]
            
            if not isinstance(actual_path, (str, Path)):
                actual_path = str(actual_path)
            
            if not actual_path or not isinstance(actual_path, (str, Path)):
                return {"success": False, "message": f"无效的路径类型: {type(actual_path)}", "data": None}

            core = ECLauncherCore()
            versions = core.scan_versions_in_path(actual_path)
            safe_versions = make_json_safe(versions)
            logger.debug(f"在路径 {actual_path} 中扫描到 {len(versions)} 个版本")
            return {
                "success": True,
                "data": safe_versions,
                "message": f"扫描完成，共找到 {len(versions)} 个版本"
            }
        except Exception as e:
            logger.error(f"扫描版本失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_minecraft_versions(self, filter: dict[str, Any] = None) -> dict[str, Any]:
        try:
            versions = ECLauncherCore.get_version_list()
            version_list = []
            for v in versions:
                version_list.append({
                    "id": v.get("id", ""),
                    "type": v.get("type", "release"),
                    "releaseTime": v.get("releaseTime", ""),
                    "url": v.get("url", "")
                })
            return {
                "success": True,
                "data": version_list,
                "message": f"获取到 {len(version_list)} 个版本"
            }
        except Exception as e:
            logger.error(f"获取 Minecraft 版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": []}

    def get_fabric_versions(self) -> dict[str, Any]:
        try:
            versions = ECLauncherCore.get_fabric_loader_list()
            return {
                "success": True,
                "data": versions[:20] if versions else [],
                "message": f"获取到 {len(versions)} 个 Fabric 版本"
            }
        except Exception as e:
            logger.error(f"获取 Fabric 版本列表失败: {e}")
            return {"success": False, "message": str(e), "data": []}

    def install_version(self, version_id: str, options: dict[str, Any] = None) -> dict[str, Any]:
        try:
            options = options or {}
            game_path = options.get("gamePath")
            loader = options.get("loader", "")
            loader_version = options.get("loaderVersion", "")
            
            config = self._config_manager.get_game_config()
            if not game_path:
                game_path = config.get("minecraft_path", "./.minecraft")
            
            core = ECLauncherCore(game_path)
            
            if loader == "fabric":
                result = core.install(version_id, "fabric", loader_version or None)
            else:
                result = core.install(version_id)
            
            return {
                "success": result,
                "data": {"version": version_id, "loader": loader or "vanilla"},
                "message": "安装任务已启动" if result else "安装失败"
            }
        except Exception as e:
            logger.error(f"安装版本失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    # ==================== 账户管理 API ====================

    def get_accounts(self) -> dict[str, Any]:
        """获取所有账户列表"""
        try:
            account_manager = get_account_manager()
            accounts = account_manager.get_all_accounts()
            current = account_manager.get_current_account()
            return {
                "success": True,
                "data": {
                    "accounts": accounts,
                    "current": current
                },
                "message": f"获取到 {len(accounts)} 个账户"
            }
        except Exception as e:
            logger.error(f"获取账户列表失败: {e}")
            return {"success": False, "message": str(e), "data": {"accounts": [], "current": None}}

    def get_current_account(self) -> dict[str, Any]:
        """获取当前账户信息"""
        try:
            account_manager = get_account_manager()
            current = account_manager.get_current_account()
            return {
                "success": True,
                "data": current,
                "message": "获取当前账户成功" if current else "未选择账户"
            }
        except Exception as e:
            logger.error(f"获取当前账户失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def add_offline_account(self, username: str) -> dict[str, Any]:
        """添加离线账户"""
        try:
            account_manager = get_account_manager()
            result = account_manager.add_offline_account(username)
            return make_json_safe(result)
        except Exception as e:
            logger.error(f"添加离线账户失败: {e}")
            return {"success": False, "message": str(e)}

    def start_microsoft_login(self) -> dict[str, Any]:
        """开始微软账户登录流程"""
        try:
            account_manager = get_account_manager()
            result = account_manager.start_microsoft_login()
            return make_json_safe(result)
        except Exception as e:
            logger.error(f"启动微软登录失败: {e}")
            return {"success": False, "message": str(e)}

    def complete_microsoft_login(self) -> dict[str, Any]:
        """完成微软账户登录流程"""
        try:
            account_manager = get_account_manager()
            result = account_manager.complete_microsoft_login()
            return make_json_safe(result)
        except Exception as e:
            logger.error(f"完成微软登录失败: {e}")
            return {"success": False, "message": str(e)}

    def switch_account(self, account_id: str) -> dict[str, Any]:
        """切换到指定账户"""
        try:
            account_manager = get_account_manager()
            result = account_manager.switch_account(account_id)
            return make_json_safe(result)
        except Exception as e:
            logger.error(f"切换账户失败: {e}")
            return {"success": False, "message": str(e)}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        """移除指定账户"""
        try:
            account_manager = get_account_manager()
            result = account_manager.remove_account(account_id)
            return make_json_safe(result)
        except Exception as e:
            logger.error(f"移除账户失败: {e}")
            return {"success": False, "message": str(e)}

    def refresh_account_profile(self, account_id: str) -> dict[str, Any]:
        """刷新账户档案信息"""
        try:
            account_manager = get_account_manager()
            result = account_manager.refresh_account_profile(account_id)
            return make_json_safe(result)
        except Exception as e:
            logger.error(f"刷新账户档案失败: {e}")
            return {"success": False, "message": str(e)}


def on_closed():
    logger.info("窗口已关闭")
    
def on_loaded():
    logger.info("窗口已加载完成")
    if webview.windows:
        webview.windows[0].show()

def run_ui(config=None, debug=False, config_manager=None):
    if config_manager:
        try:
            if not config_manager.config:
                config_manager.load()
                logger.info("配置已加载")
        except Exception as e:
            logger.error(f"启动时加载配置失败: {e}")
    
    ui_config = config[0].get("ui", {}) if config else {}
    width = ui_config.get("width", 1000)
    height = ui_config.get("height", 700)
    title = ui_config.get("title", "EuoraCraft Launcher")
    
    api = Api(config_manager)
    
    html_path = "http://localhost:5173"
    #html_path = resource_path("./index.html")
    
    window = webview.create_window(
        title,
        url=html_path,
        js_api=api,
        width=width, 
        height=height,
        frameless=True, 
        easy_drag=False,
        hidden=True, 
        shadow=True,
        text_select=False
    )
    
    window.events.minimized += lambda: logger.info("窗口已最小化")
    window.events.restored += lambda: logger.info("窗口已还原")
    window.events.loaded += on_loaded
    window.events.closed += on_closed
    
    webview.start(debug=debug)
    logger.info('程序已退出')