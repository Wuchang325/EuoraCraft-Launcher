import os
import sys
import base64
import json
import uuid
import requests
import webview
import ctypes
import threading
from datetime import datetime
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


def _get_project_root() -> Path:
    """获取项目根目录，与 C_Skin.py 中的实现保持一致"""
    return Path(__file__).resolve().parents[3]


def get_resource_path(relative_path: str) -> str:
    """返回字符串路径，兼容 PyWebView 等需要字符串的场景"""
    p = Path(getattr(sys, '_MEIPASS', Path.cwd())) / relative_path
    return str(p.resolve())


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
            'fetch_image_data_url',
            'get_avatar_data_url',
            'load_image_from_local',
            'select_local_image',
            'get_game_config',
            'update_game_config',
            'get_java_list',
            'get_theme_config',
            'update_theme_config',
            'get_download_config',
            'update_download_config',
            'get_mouse_effect_config',
            'update_mouse_effect_config',
            'get_locale_config',
            'update_locale_config',
            'select_directory',
            'select_java_executable',
            'scan_versions_in_path',
            'get_minecraft_versions',
            'get_fabric_versions',
            'install_version',
            'uninstall_version',
            'ping',
            # 用户协议 API
            'get_user_agreement_status',
            'save_user_agreement',
            'clear_user_agreement',
            # 账户管理 API
            'get_accounts',
            'get_current_account',
            'add_offline_account',
            'start_microsoft_login',
            'poll_microsoft_login',
            'complete_microsoft_login',
            'switch_account',
            'remove_account',
            'refresh_account_profile',
            # 实例管理 API
            'get_game_instances',
            'launch_instance',
            'get_launch_status',
            'stop_instance'
        ]

    def ping(self) -> dict[str, Any]:
        return {
            "success": True,
            "data": {"status": "ok", "message": "API连接正常"},
            "message": "Pong"
        }

    def get_user_agreement_status(self) -> dict[str, Any]:
        try:
            agreement_file = _get_project_root() / "ECL_Libs" / "user_agreement.json"
            if agreement_file.exists():
                with open(agreement_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return {
                    "success": True,
                    "data": {"accepted": data.get("accepted", False), "uuid": data.get("uuid", "")},
                    "message": "获取用户协议状态成功"
                }
            return {
                "success": True,
                "data": {"accepted": False, "uuid": ""},
                "message": "用户协议未同意"
            }
        except Exception as e:
            logger.error(f"获取用户协议状态失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def save_user_agreement(self) -> dict[str, Any]:
        try:
            agreement_file = _get_project_root() / "ECL_Libs" / "user_agreement.json"
            agreement_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "accepted": True,
                "uuid": str(uuid.uuid4())
            }
            with open(agreement_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {
                "success": True,
                "data": data,
                "message": "用户协议已保存"
            }
        except Exception as e:
            logger.error(f"保存用户协议失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def clear_user_agreement(self) -> dict[str, Any]:
        try:
            agreement_file = _get_project_root() / "ECL_Libs" / "user_agreement.json"
            if agreement_file.exists():
                agreement_file.unlink()
            return {
                "success": True,
                "message": "用户协议已清除"
            }
        except Exception as e:
            logger.error(f"清除用户协议失败: {e}")
            return {"success": False, "message": str(e)}

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
            
            if not path_str:
                return {"success": False, "message": "未设置背景图", "data": None}
            
            # 统一路径分隔符为系统分隔符
            path_str = path_str.replace('/', os.sep).replace('\\', os.sep)
            path = Path(path_str)
            
            if not path.exists():
                logger.error(f"[get_background_image] 文件不存在: {path}")
                return {"success": False, "message": f"背景图文件不存在: {path_str}", "data": None}
            
            try:
                image_data = path.read_bytes()
            except Exception as e:
                logger.error(f"[get_background_image] 读取文件失败: {e}")
                return {"success": False, "message": f"读取背景图文件失败: {e}", "data": None}
            
            mime_map = {
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg'
            }
            mime_type = mime_map.get(path.suffix.lower(), 'image/jpeg')
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            
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

    def fetch_image_data_url(self, url: str) -> dict[str, Any]:
        try:
            logger.info(f"[fetch_image_data_url] 开始下载图片: {url}")

            # 添加浏览器 User-Agent 和其他头，避免被 Cloudflare 误判为机器人
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }

            # 重试机制：最多重试 3 次
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.info(f"[fetch_image_data_url] 第 {attempt + 1} 次尝试")
                    response = requests.get(url, timeout=15, headers=headers)
                    response.raise_for_status()

                    content_type = response.headers.get('content-type', '')
                    logger.info(f"[fetch_image_data_url] Content-Type: {content_type}")

                    # 检查是否真的是图片
                    if not content_type.startswith('image/'):
                        # 如果是 HTML 响应（可能是 Cloudflare 错误页面），记录内容
                        if 'text/html' in content_type:
                            logger.warning(f"[fetch_image_data_url] 收到 HTML 响应，可能被 Cloudflare 拦截: {response.text[:200]}...")
                            if attempt < max_retries - 1:
                                logger.info(f"[fetch_image_data_url] {2 ** attempt} 秒后重试...")
                                import time
                                time.sleep(2 ** attempt)  # 指数退避
                                continue
                        return {"success": False, "message": f"URL不是图片类型: {content_type}", "data": None}

                    # 验证图片数据大小
                    if len(response.content) < 100:
                        logger.warning(f"[fetch_image_data_url] 图片数据过小: {len(response.content)} bytes")
                        if attempt < max_retries - 1:
                            logger.info(f"[fetch_image_data_url] {2 ** attempt} 秒后重试...")
                            import time
                            time.sleep(2 ** attempt)
                            continue
                        return {"success": False, "message": "图片数据不完整", "data": None}

                    data_url = f"data:{content_type};base64,{base64.b64encode(response.content).decode('utf-8')}"
                    logger.info(f"[fetch_image_data_url] 成功获取图片 ({len(response.content)} bytes)")
                    return {
                        "success": True,
                        "message": "图片代理获取成功",
                        "data": {"dataUrl": data_url}
                    }

                except requests.exceptions.HTTPError as http_err:
                    status_code = http_err.response.status_code if http_err.response else None
                    error_msg = str(http_err)
                    logger.warning(f"[fetch_image_data_url] HTTP 错误 {status_code}: {error_msg}")

                    # 检查是否为 5xx 错误（包括响应为 None 但错误信息中包含 5xx 的情况）
                    is_5xx_error = False
                    if status_code and 500 <= status_code < 600:
                        is_5xx_error = True
                    elif status_code is None and ('5' in error_msg and 'Server Error' in error_msg):
                        # 尝试从错误信息中提取状态码
                        import re
                        match = re.search(r'(\d{3})\s+Server Error', error_msg)
                        if match and 500 <= int(match.group(1)) < 600:
                            is_5xx_error = True

                    # 对于 5xx 错误，重试
                    if is_5xx_error:
                        if attempt < max_retries - 1:
                            logger.info(f"[fetch_image_data_url] 服务器错误，{2 ** attempt} 秒后重试...")
                            import time
                            time.sleep(2 ** attempt)
                            continue

                    # 对于其他错误，直接返回失败
                    return {"success": False, "message": f"HTTP 错误 {status_code}: {error_msg}", "data": None}

                except requests.exceptions.RequestException as req_err:
                    logger.warning(f"[fetch_image_data_url] 请求异常: {req_err}")
                    if attempt < max_retries - 1:
                        logger.info(f"[fetch_image_data_url] {2 ** attempt} 秒后重试...")
                        import time
                        time.sleep(2 ** attempt)
                        continue
                    return {"success": False, "message": f"网络请求失败: {str(req_err)}", "data": None}

            # 所有重试都失败了
            return {"success": False, "message": f"重试 {max_retries} 次后仍失败", "data": None}

        except Exception as e:
            logger.error(f"代理获取图片失败: {e}")
            return {"success": False, "message": str(e), "data": None}

    def get_avatar_data_url(self, uuid: str, type_name: str = "Mojang", custom_server: str | None = None, size: int = 64, use_default_skin: bool = False) -> dict[str, Any]:
        """
        获取玩家头像的 base64 data URL
        从皮肤中提取头部并处理为指定尺寸
        
        Args:
            uuid: 玩家UUID
            type_name: 皮肤服务器类型
            custom_server: 自定义服务器地址
            size: 头像尺寸
            use_default_skin: 是否使用默认皮肤（True: 使用默认皮肤，False: 尝试API获取）
        """
        try:
            from ..Game.Core import get_avatar_data_url as get_avatar_func
            
            # 由前端明确指定是否使用默认皮肤，不再通过UUID判断
            data_url = get_avatar_func(uuid, type_name, custom_server, size, use_default_skin)
            return {
                "success": True,
                "message": "头像生成成功",
                "data": {"dataUrl": data_url}
            }
        except ImportError as e:
            logger.error(f"[get_avatar_data_url] PIL 库未安装: {e}")
            return {"success": False, "message": "PIL (Pillow) 库未安装，无法处理头像", "data": None}
        except Exception as e:
            logger.error(f"[get_avatar_data_url] 生成头像失败: {e}")
            return {"success": False, "message": f"头像生成失败: {str(e)}", "data": None}

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
                    "path": str(java_info.path),
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

    def get_mouse_effect_config(self) -> dict[str, Any]:
        """获取鼠标点击效果配置"""
        try:
            self.__ensure_config_loaded()
            config = self._config_manager.get_mouse_effect_config()
            safe_config = make_json_safe(config)
            return {"success": True, "message": "鼠标点击效果配置获取成功", "data": safe_config}
        except Exception as e:
            logger.error(f"获取鼠标点击效果配置失败: {e}")
            return {"success": False, "message": f"获取鼠标点击效果配置失败: {str(e)}", "data": None}

    def update_mouse_effect_config(self, mouse_effect_config: dict[str, Any]) -> dict[str, Any]:
        """更新鼠标点击效果配置"""
        try:
            self.__ensure_config_loaded()
            self._config_manager.update_mouse_effect_config(mouse_effect_config)
            return {"success": True, "message": "鼠标点击效果配置已更新"}
        except Exception as e:
            logger.error(f"更新鼠标点击效果配置失败: {e}")
            return {"success": False, "message": f"更新鼠标点击效果配置失败: {str(e)}"}

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
        """【待对接】扫描本地游戏目录中的已安装版本"""
        return {"success": True, "message": "扫描版本功能待对接", "data": []}

    def get_minecraft_versions(self, filter_type: str = None) -> dict[str, Any]:
        """【待对接】获取官方 Minecraft 版本列表"""
        return {"success": True, "message": "版本列表功能待对接", "data": []}

    def get_fabric_versions(self) -> dict[str, Any]:
        """【待对接】获取 Fabric Loader 版本列表"""
        return {"success": True, "message": "Fabric 版本列表功能待对接", "data": []}

    def install_version(self, version_id: str, options: dict[str, Any] = None) -> dict[str, Any]:
        """【待对接】安装游戏版本"""
        return {"success": False, "message": "安装功能待对接", "data": None}

    def uninstall_version(self, version_id: str, game_path: str = None) -> dict[str, Any]:
        """卸载游戏版本"""
        try:
            from shutil import rmtree
            
            # 获取游戏路径
            if not game_path:
                config = self._config_manager.get_game_config()
                paths = config.get("minecraft_paths", ["./.minecraft"])
                game_path = paths[0] if isinstance(paths[0], str) else paths[0].get("path", "./.minecraft")
            
            game_path = Path(game_path)
            version_dir = game_path / "versions" / version_id
            
            if not version_dir.exists():
                return {"success": False, "message": "版本不存在"}
            
            # 删除版本目录
            rmtree(version_dir)
            logger.info(f"版本 {version_id} 已卸载")
            
            return {
                "success": True,
                "message": f"版本 {version_id} 已卸载"
            }
        except Exception as e:
            logger.error(f"卸载版本失败: {e}")
            return {"success": False, "message": str(e)}

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
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "添加成功")}
        except Exception as e:
            logger.error(f"添加离线账户失败: {e}")
            return {"success": False, "message": str(e)}

    def start_microsoft_login(self) -> dict[str, Any]:
        """开始微软账户登录流程，自动打开浏览器并复制授权码"""
        try:
            account_manager = get_account_manager()
            result = account_manager.start_microsoft_login()
            
            # 如果处于 pending 状态，自动打开浏览器并复制授权码
            if result.get("status") == "pending":
                verification_uri = result.get("verificationUri", "")
                user_code = result.get("userCode", "")
                
                # 自动复制授权码到剪贴板
                if user_code:
                    try:
                        import pyperclip
                        pyperclip.copy(user_code)
                        logger.info(f"授权码已自动复制: {user_code}")
                    except Exception as copy_err:
                        logger.warning(f"自动复制授权码失败: {copy_err}")
                
                # 自动打开浏览器
                if verification_uri:
                    try:
                        import webbrowser
                        webbrowser.open(verification_uri)
                        logger.info(f"已自动打开浏览器: {verification_uri}")
                    except Exception as open_err:
                        logger.warning(f"自动打开浏览器失败: {open_err}")
            
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "请完成授权")}
        except Exception as e:
            logger.error(f"启动微软登录失败: {e}")
            return {"success": False, "message": str(e)}

    def poll_microsoft_login(self) -> dict[str, Any]:
        """轮询检测微软登录状态"""
        try:
            account_manager = get_account_manager()
            result = account_manager.poll_microsoft_login()
            
            # 如果登录完成，自动置顶窗口
            if result.get("status") == "ready":
                try:
                    if webview.windows:
                        window = webview.windows[0]
                        # 恢复窗口（如果最小化）
                        window.restore()
                        # 激活窗口到前台
                        window.on_top = True
                        window.on_top = False
                        """try:
                            # Windows 平台特定方法
                            import ctypes
                            from ctypes import wintypes
                            
                            user32 = ctypes.windll.user32
                            
                            # 使用 FindWindow 找到窗口句柄（根据窗口标题）
                            hwnd = user32.FindWindowW(None, window.title)
                            if hwnd:
                                # 强制窗口到前台
                                user32.SetForegroundWindow(hwnd)
                                user32.BringWindowToTop(hwnd)
                        except Exception as platform_err:
                            logger.debug(f"平台特定置顶方法失败: {platform_err}")
                            # 备用方法：使用 pywebview 的 on_top
                            window.on_top = True
                            window.on_top = False"""
                        
                        logger.info("登录完成，窗口已置顶")
                except Exception as window_err:
                    logger.warning(f"窗口置顶失败: {window_err}")
            
            return make_json_safe(result)
        except Exception as e:
            logger.error(f"轮询微软登录状态失败: {e}")
            return {"success": False, "message": str(e)}

    def complete_microsoft_login(self) -> dict[str, Any]:
        """完成微软账户登录流程"""
        try:
            account_manager = get_account_manager()
            result = account_manager.complete_microsoft_login()
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "登录成功")}
        except Exception as e:
            logger.error(f"完成微软登录失败: {e}")
            return {"success": False, "message": str(e)}

    def switch_account(self, account_id: str) -> dict[str, Any]:
        """切换到指定账户"""
        try:
            account_manager = get_account_manager()
            result = account_manager.switch_account(account_id)
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "切换成功")}
        except Exception as e:
            logger.error(f"切换账户失败: {e}")
            return {"success": False, "message": str(e)}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        """移除指定账户"""
        try:
            account_manager = get_account_manager()
            result = account_manager.remove_account(account_id)
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "移除成功")}
        except Exception as e:
            logger.error(f"移除账户失败: {e}")
            return {"success": False, "message": str(e)}

    def refresh_account_profile(self, account_id: str) -> dict[str, Any]:
        """刷新账户档案信息"""
        try:
            account_manager = get_account_manager()
            result = account_manager.refresh_account_profile(account_id)
            return {"success": True, "data": make_json_safe(result), "message": result.get("message", "刷新成功")}
        except Exception as e:
            logger.error(f"刷新账户档案失败: {e}")
            return {"success": False, "message": str(e)}

    # ==================== 实例管理 API ====================

    def get_game_instances(self) -> dict[str, Any]:
        """获取所有正在运行的游戏进程列表"""
        try:
            from ..Game.Core.ECLauncherCore import ECLauncherCore
            core = ECLauncherCore()
            running_instances = core.instances_manager.get_instances_info()
            
            # 构建前端需要的格式
            instances = []
            for inst in running_instances:
                proc = inst.get("Instance")
                is_running = proc.poll() is None if proc else False
                instances.append({
                    "id": inst.get("ID"),
                    "name": inst.get("Name", "未知实例"),
                    "version": inst.get("Name", ""),
                    "isRunning": is_running,
                    "type": inst.get("Type", "MinecraftClient"),
                    "startTime": getattr(proc, '_start_time', None)
                })
            
            return {
                "success": True,
                "data": instances,
                "message": f"获取到 {len(instances)} 个运行中的进程"
            }
        except Exception as e:
            logger.error(f"获取运行中的进程列表失败: {e}")
            return {"success": False, "message": str(e), "data": []}

    def launch_instance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """【待对接】启动游戏实例"""
        return {"success": False, "message": "启动功能待对接", "data": None}

    def get_launch_status(self, task_id: str) -> dict[str, Any]:
        """【待对接】获取启动任务的进度状态"""
        return {"success": False, "message": "启动进度查询功能待对接", "data": None}

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        """停止实例"""
        try:
            from ..Game.Core.ECLauncherCore import ECLauncherCore
            core = ECLauncherCore()
            
            # 检查实例是否正在运行
            running_instances = core.instances_manager.get_instances_info()
            if not any(inst["ID"] == instance_id for inst in running_instances):
                return {"success": False, "message": "实例未在运行"}
            
            # 停止实例（强制终止）
            core.instances_manager.stop_instance(instance_id, terminate=True)
            
            return {"success": True, "message": "实例已停止"}
        except Exception as e:
            logger.error(f"停止实例失败: {e}")
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
    #html_path = get_resource_path("./ui/dist/index.html")
    
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