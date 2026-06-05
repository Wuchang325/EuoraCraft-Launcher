"""
EuoraCraft Launcher - pytauri Commands

Replaces the old pywebview Api class.
All IPC handlers are registered here as pytauri commands,
called from the Vue frontend via `import { invoke } from '@tauri-apps/api/core'`.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import anyio
from anyio.from_thread import start_blocking_portal
from pydantic import BaseModel

from pytauri import (
    AppHandle,
    Commands,
    Emitter,
    Manager,
    builder_factory,
    context_factory,
    WebviewUrl,
)
from pytauri.ipc import InvokeException, WebviewWindow
from pytauri_plugins.dialog import (
    FileDialogBuilder,
    MessageDialogBuilder,
    MessageDialogKind,
    MessageDialogButtons,
    FilePath,
)

# ── Reuse existing ECL modules ────────────────────────
# python/ is the package root for ECL and other backend modules
_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from ECL.Core.logger import get_logger
from ECL.Core.config import ConfigManager
from ECL.Game.java import get_java_list as _get_java_list
from ECL.Game.AccountManager import get_account_manager
from ECL.Game.Core import ECLauncherCore, C_GetGames, InstancesManager
from ECL.Game.Core.C_Libs import is_uuid3

logger = get_logger("pytauri")
import sys
import os
# 强制stdout/stderr utf8，解决Windows控制台中文乱码
os.environ["PYTHONUTF8"] = "1"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


# ── Pydantic models for IPC ──────────────────────────

class EmptyResponse(BaseModel):
    success: bool = True
    message: str = "ok"

class ConfigResponse(BaseModel):
    success: bool = True
    data: Any = None
    message: str = "ok"

class PingResponse(BaseModel):
    status: str = "ok"
    message: str = "API连接正常"


# ── Commands ─────────────────────────────────────────

commands = Commands()

# Global state (managed internally; Commands uses State via Annotated)
_config_manager: ConfigManager | None = None
_app_handle: AppHandle | None = None
_launch_tasks: dict[str, dict[str, Any]] = {}


def init_config_manager() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


# ── Health ────────────────────────────────────────────

@commands.command()
async def ping() -> PingResponse:
    return PingResponse()


# ── Window Control ────────────────────────────────────

@commands.command()
async def minimize_window(webview_window: WebviewWindow) -> EmptyResponse:
    """最小化窗口"""
    try:
        webview_window.minimize()
        return EmptyResponse(message="窗口已最小化")
    except Exception as e:
        logger.error(f"最小化窗口失败: {e}")
        return EmptyResponse(success=False, message=str(e))


@commands.command()
async def close_window(webview_window: WebviewWindow) -> EmptyResponse:
    """关闭窗口"""
    try:
        webview_window.close()
        return EmptyResponse(message="窗口已关闭")
    except Exception as e:
        logger.error(f"关闭窗口失败: {e}")
        return EmptyResponse(success=False, message=str(e))


@commands.command()
async def toggle_maximize(webview_window: WebviewWindow) -> EmptyResponse:
    """切换最大化/还原"""
    try:
        if webview_window.is_maximized():
            webview_window.unmaximize()
        else:
            webview_window.maximize()
        return EmptyResponse()
    except Exception as e:
        logger.error(f"切换最大化失败: {e}")
        return EmptyResponse(success=False, message=str(e))


# ── Config ────────────────────────────────────────────

@commands.command()
async def get_launcher_config() -> ConfigResponse:
    cfg = init_config_manager().get_launcher_config()
    return ConfigResponse(data=cfg)


@commands.command()
async def get_game_config() -> ConfigResponse:
    cfg = init_config_manager().get_game_config()
    return ConfigResponse(data=cfg)


@commands.command()
async def update_game_config(body: str) -> EmptyResponse:
    data = json.loads(body)
    init_config_manager().update_game_config(data)
    return EmptyResponse(message="游戏配置更新成功")


@commands.command()
async def get_theme_config() -> ConfigResponse:
    cfg = init_config_manager().get_theme_config()
    return ConfigResponse(data=cfg)


@commands.command()
async def update_theme_config(body: str) -> EmptyResponse:
    data = json.loads(body)
    init_config_manager().update_theme_config(data)
    return EmptyResponse(message="主题配置更新成功")


@commands.command()
async def get_background_config() -> ConfigResponse:
    cfg = init_config_manager().get_background_config()
    return ConfigResponse(data=cfg)


@commands.command()
async def update_background_config(body: str) -> EmptyResponse:
    data = json.loads(body)
    init_config_manager().update_background_config(data)
    # 同步背景模糊值到主题配置，保持两处一致
    blur = data.get("blur")
    if blur is not None:
        cm = init_config_manager()
        theme = cm.get_theme_config()
        if theme.get("blur_amount") != blur:
            theme["blur_amount"] = blur
            cm.update_theme_config(theme)
    return EmptyResponse(message="背景配置更新成功")


@commands.command()
async def get_download_config() -> ConfigResponse:
    cfg = init_config_manager().get_download_config()
    return ConfigResponse(data=cfg)


@commands.command()
async def update_download_config(body: str) -> EmptyResponse:
    data = json.loads(body)
    init_config_manager().update_download_config(data)
    return EmptyResponse(message="下载配置更新成功")


@commands.command()
async def get_locale_config() -> ConfigResponse:
    cfg = init_config_manager().get_locale_config()
    return ConfigResponse(data=cfg)


@commands.command()
async def update_locale_config(body: str) -> EmptyResponse:
    data = json.loads(body)
    init_config_manager().update_locale_config(data.get("locale", "zh-CN"))
    return EmptyResponse(message="语言配置更新成功")


@commands.command()
async def get_mouse_effect_config() -> ConfigResponse:
    cfg = init_config_manager().get_mouse_effect_config()
    return ConfigResponse(data=cfg)


@commands.command()
async def update_mouse_effect_config(body: str) -> EmptyResponse:
    data = json.loads(body)
    init_config_manager().update_mouse_effect_config(data)
    return EmptyResponse(message="鼠标效果配置更新成功")

@commands.command()
async def get_background_image() -> ConfigResponse:
    cfg = init_config_manager().get_background_config()
    path_str = cfg.get("path", "")
    if not path_str:
        return ConfigResponse(success=False, message="未设置背景图", data=None)
    
    path = Path(path_str)
    if not path.exists():
        return ConfigResponse(success=False, message=f"文件不存在: {path_str}", data=None)
    
    image_bytes = path.read_bytes()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime = mime_map.get(path.suffix.lower(), "image/jpeg")
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    
    return ConfigResponse(data={
        "base64": data_url,
        "path": str(path.as_posix()),
        "type": cfg.get("type", "local"),
    })


# ── Background Image Upload ───────────────────────────

@commands.command()
async def update_background_image(body: str) -> EmptyResponse:
    """更新背景图片设置"""
    try:
        data = json.loads(body)
        img_type = data.get("type", "local")
        img_path = data.get("path", "")
        cm = init_config_manager()
        bg_cfg = cm.get_background_config()
        bg_cfg["type"] = img_type
        bg_cfg["path"] = img_path
        cm.update_background_config(bg_cfg)
        logger.info(f"背景图片已更新: type={img_type}, path={img_path}")
        return EmptyResponse(message="背景图片已更新")
    except Exception as e:
        logger.error(f"更新背景图片失败: {e}")
        return EmptyResponse(success=False, message=str(e))


@commands.command()
async def load_image_from_url(body: str) -> ConfigResponse:
    """从 URL 下载图片到本地缓存目录"""
    try:
        data = json.loads(body)
        url = data.get("url", "")
        if not url:
            return ConfigResponse(success=False, message="URL 不能为空")
        
        import requests
        from pathlib import Path
        from datetime import datetime
        
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        
        cache_dir = Path("./ECL_Libs/backgrounds").resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        ext = ".png"
        content_type = resp.headers.get("content-type", "")
        if "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "gif" in content_type:
            ext = ".gif"
        elif "webp" in content_type:
            ext = ".webp"
        
        filename = f"bg_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        local_path = cache_dir / filename
        local_path.write_bytes(resp.content)
        
        logger.info(f"图片已从 URL 下载: {url} -> {local_path}")
        return ConfigResponse(data={"path": str(local_path)}, message="图片下载成功")
    except Exception as e:
        logger.error(f"从 URL 加载图片失败: {e}")
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def select_local_image() -> ConfigResponse:
    try:
        files = await FileDialogBuilder()\
            .add_filter("图片", ["jpg", "jpeg", "png", "gif", "webp"])\
            .pick_file()
        if files:
            path = files[0] if isinstance(files, list) else files
            return ConfigResponse(data={"path": str(path)})
        return ConfigResponse(success=False, message="用户取消选择")
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


# ── Java ──────────────────────────────────────────────

@commands.command()
async def get_java_list() -> ConfigResponse:
    java_list = _get_java_list()
    if not java_list:
        return ConfigResponse(data=[], message="未找到Java安装")
    
    java_dicts = []
    for j in java_list:
        java_dicts.append({
            "path": str(j.path),
            "version": j.version,
            "major_version": j.major_version,
            "java_type": j.java_type,
            "arch": j.arch,
            "sources": j.sources,
        })
    return ConfigResponse(data=java_dicts, message=f"找到 {len(java_dicts)} 个Java安装")


# ── Directory / File Dialogs ──────────────────────────

@commands.command()
async def select_directory() -> ConfigResponse:
    try:
        dirs = await FileDialogBuilder().pick_folder()
        if dirs:
            path = dirs[0] if isinstance(dirs, list) else dirs
            return ConfigResponse(data={"path": str(path)})
        return ConfigResponse(success=False, message="用户取消选择")
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def select_java_executable() -> ConfigResponse:
    try:
        files = await FileDialogBuilder()\
            .add_filter("Java Executable", ["exe"])\
            .pick_file()
        if files:
            path = files[0] if isinstance(files, list) else files
            return ConfigResponse(data={"path": str(path)})
        return ConfigResponse(success=False, message="用户取消选择")
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


# ── Account Management ───────────────────────────────

@commands.command()
async def get_accounts() -> ConfigResponse:
    try:
        am = get_account_manager()
        accounts = am.get_all_accounts()
        current = am.get_current_account()
        return ConfigResponse(data={"accounts": accounts, "current": current})
    except Exception as e:
        return ConfigResponse(success=False, message=str(e), data={"accounts": [], "current": None})


@commands.command()
async def get_current_account() -> ConfigResponse:
    am = get_account_manager()
    current = am.get_current_account()
    return ConfigResponse(data=current)


@commands.command()
async def add_offline_account(body: str) -> ConfigResponse:
    data = json.loads(body)
    username = data.get("username", "")
    if not username:
        return ConfigResponse(success=False, message="用户名不能为空")
    try:
        am = get_account_manager()
        result = am.add_offline_account(username)
        return ConfigResponse(data=result, message=result.get("message", "添加成功"))
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def start_microsoft_login() -> ConfigResponse:
    try:
        am = get_account_manager()
        result = am.start_microsoft_login()
        return ConfigResponse(data=result, message=result.get("message", "请完成授权"))
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def complete_microsoft_login() -> ConfigResponse:
    try:
        am = get_account_manager()
        result = am.complete_microsoft_login()
        return ConfigResponse(data=result, message=result.get("message", "登录成功"))
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def poll_microsoft_login() -> ConfigResponse:
    """轮询微软登录状态"""
    try:
        am = get_account_manager()
        result = am.poll_microsoft_login()
        return ConfigResponse(data=result, message=result.get("message", ""))
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def switch_account(body: str) -> ConfigResponse:
    data = json.loads(body)
    account_id = data.get("accountId", "")
    if not account_id:
        return ConfigResponse(success=False, message="缺少 accountId")
    try:
        am = get_account_manager()
        result = am.switch_account(account_id)
        return ConfigResponse(data=result, message=result.get("message", "切换成功"))
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def remove_account(body: str) -> ConfigResponse:
    data = json.loads(body)
    account_id = data.get("accountId", "")
    if not account_id:
        return ConfigResponse(success=False, message="缺少 accountId")
    try:
        am = get_account_manager()
        result = am.remove_account(account_id)
        return ConfigResponse(data=result, message=result.get("message", "移除成功"))
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


# ── Version Scanning ─────────────────────────────────

def _get_game_path() -> Path:
    cfg = init_config_manager().get_game_config()
    paths = cfg.get("minecraft_paths", [{"path": "./.minecraft"}])
    first = paths[0] if isinstance(paths[0], dict) else {"path": paths[0]}
    return Path(first["path"]).resolve()


def _resolve_game_path(path_str: Optional[str] = None) -> Path:
    if path_str:
        return Path(path_str).resolve()
    cfg = init_config_manager().get_game_config()
    paths = cfg.get("minecraft_paths", [{"path": "./.minecraft"}])
    first = paths[0] if isinstance(paths[0], dict) else {"path": paths[0]}
    return Path(first["path"]).resolve()


@commands.command()
async def scan_versions_in_path(body: str = "{}") -> ConfigResponse:
    """扫描本地游戏目录中的已安装版本"""
    try:
        data = json.loads(body)
        requested_paths = data.get("paths", [])
        
        if requested_paths:
            # 使用前端传入的路径
            all_versions = []
            for p in requested_paths:
                gp = Path(p).resolve()
                get_games = C_GetGames.GetGames()
                versions = get_games.scan_local_versions(gp)
                all_versions.extend(versions)
            return ConfigResponse(data=[
                {"id": v["id"], "type": v.get("type", "release")}
                for v in all_versions
            ])
        else:
            # 回退到配置中的路径
            game_path = _get_game_path()
            get_games = C_GetGames.GetGames()
            versions = get_games.scan_local_versions(game_path)
            return ConfigResponse(data=versions)
    except Exception as e:
        logger.error(f"扫描版本失败: {e}")
        return ConfigResponse(success=False, message=str(e), data=[])


@commands.command()
async def get_minecraft_versions() -> ConfigResponse:
    try:
        get_games = C_GetGames.GetGames()
        versions = await anyio.to_thread.run_sync(get_games.get_minecraft_versions)
        if versions is None:
            return ConfigResponse(success=False, message="获取Minecraft版本失败", data=None)
        return ConfigResponse(data=versions)
    except Exception as e:
        logger.error(f"获取Minecraft版本失败: {e}")
        return ConfigResponse(success=False, message=str(e), data=None)


@commands.command()
async def get_fabric_versions(body: str = "{}") -> ConfigResponse:
    try:
        data = json.loads(body)
        game_version_id = data.get("gameVersionId")
        if not game_version_id:
            return ConfigResponse(data=[], message="未指定Minecraft版本，返回空列表")
        get_games = C_GetGames.GetGames()
        result = await anyio.to_thread.run_sync(get_games.get_fabric_versions, game_version_id)
        if not result or not isinstance(result, dict) or "All" not in result:
            return ConfigResponse(success=False, message="获取Fabric版本失败", data=None)
        versions = [item.get("LoaderVersion") for item in result.get("All", []) if isinstance(item, dict) and item.get("LoaderVersion")]
        return ConfigResponse(data=versions)
    except Exception as e:
        logger.error(f"获取Fabric版本失败: {e}")
        return ConfigResponse(success=False, message=str(e), data=None)


@commands.command()
async def launch_instance(body: str) -> ConfigResponse:
    data = json.loads(body)
    version = data.get("version")
    if not version:
        return ConfigResponse(success=False, message="缺少 version", data=None)

    game_path = _resolve_game_path(data.get("gamePath"))
    java_path = data.get("javaPath") or None
    max_memory = int(data.get("maxMemory", 4096))
    player_name = data.get("playerName", "Player")

    if not java_path:
        java_list = _get_java_list()
        if not java_list:
            return ConfigResponse(success=False, message="未找到可用Java", data=None)
        java_path = str(java_list[0].path)

    task_id = uuid.uuid4().hex
    _launch_tasks[task_id] = {
        "completed": False,
        "percent": 0,
        "stage": "准备启动",
        "message": "正在准备启动游戏",
        "error": None,
    }

    def _run_launch() -> None:
        try:
            _launch_tasks[task_id].update({
                "stage": "正在启动",
                "message": f"启动版本 {version}",
                "percent": 20,
            })

            core = ECLauncherCore.ECLauncherCore()
            core.launch_minecraft(
                java_path,
                game_path,
                version,
                max_memory,
                player_name,
            )

            _launch_tasks[task_id].update({
                "completed": True,
                "percent": 100,
                "stage": "已启动",
                "message": "游戏进程已启动",
            })
        except Exception as e:
            logger.error(f"启动实例失败: {e}")
            _launch_tasks[task_id].update({
                "completed": True,
                "percent": 100,
                "stage": "错误",
                "message": str(e),
                "error": str(e),
            })

    import threading
    thread = threading.Thread(target=_run_launch, daemon=True)
    thread.start()

    return ConfigResponse(data={"taskId": task_id}, message="启动任务已提交")


@commands.command()
async def get_launch_status(body: str) -> ConfigResponse:
    try:
        data = json.loads(body)
        task_id = data.get("taskId")
        if not task_id:
            return ConfigResponse(success=False, message="缺少 taskId", data=None)
        status = _launch_tasks.get(task_id)
        if status is None:
            return ConfigResponse(success=False, message=f"未找到任务 {task_id}", data=None)
        return ConfigResponse(data=status)
    except Exception as e:
        logger.error(f"查询启动状态失败: {e}")
        return ConfigResponse(success=False, message=str(e), data=None)


@commands.command()
async def uninstall_version(body: str) -> ConfigResponse:
    try:
        data = json.loads(body)
        version = data.get("version")
        if not version:
            return ConfigResponse(success=False, message="缺少 version", data=None)
        game_path = _resolve_game_path(data.get("gamePath"))
        version_dir = game_path / "versions" / version
        if not version_dir.exists():
            return ConfigResponse(success=False, message="版本不存在", data=None)
        shutil.rmtree(version_dir)
        return ConfigResponse(message=f"版本 {version} 已卸载")
    except Exception as e:
        logger.error(f"卸载版本失败: {e}")
        return ConfigResponse(success=False, message=str(e), data=None)


# ── Game Launch (simplified - will wire up fully) ───

@commands.command()
async def launch_game(body: str) -> ConfigResponse:
    """启动游戏"""
    try:
        params = json.loads(body)
        game_path = _get_game_path()
        version_name = params.get("versionId", "")
        java_path = params.get("javaPath", "")
        max_memory = params.get("maxMemory", 4096)
        player_name = params.get("playerName", "Player")
        
        if not version_name:
            return ConfigResponse(success=False, message="未指定游戏版本")
        
        core = ECLauncherCore.ECLauncherCore()
        
        # Launch in background via anyio
        async def _launch():
            core.launch_minecraft(
                java_path=java_path,
                game_path=game_path,
                version_name=version_name,
                max_use_ram=max_memory,
                player_name=player_name,
                user_type="legacy",
            )
        
        # Run the blocking launch in a thread
        await anyio.to_thread.run_sync(
            core.launch_minecraft,
            java_path, game_path, version_name, max_memory,
            player_name
        )
        
        return ConfigResponse(message="游戏启动成功")
    except Exception as e:
        logger.error(f"启动游戏失败: {e}")
        return ConfigResponse(success=False, message=str(e))


_in_game_instances: dict = {}  # instance_id -> subprocess info


@commands.command()
async def get_game_instances() -> ConfigResponse:
    """获取当前运行的 Minecraft 实例列表"""
    try:
        running = [
            {
                "id": inst_id,
                "name": info.get("Name", inst_id),
                "version": info.get("Version", "unknown"),
                "gamePath": info.get("GamePath", ""),
                "isRunning": info.get("Instance") is not None and (
                    info["Instance"].poll() is None
                ),
                "memory": info.get("Memory", {"min": 0, "max": 0}),
                "playTime": info.get("PlayTime", 0),
                "modCount": info.get("ModCount", 0),
                "lastPlayed": info.get("LastPlayed", ""),
                "createdAt": info.get("CreatedAt", ""),
            }
            for inst_id, info in _in_game_instances.items()
            if info.get("Instance") is None or info["Instance"].poll() is None
        ]
        return ConfigResponse(data=running, message=f"找到 {len(running)} 个实例")
    except Exception as e:
        logger.error(f"获取实例列表失败: {e}")
        return ConfigResponse(success=False, message=str(e), data=[])


@commands.command()
async def stop_instance(body: str) -> EmptyResponse:
    """停止一个运行中的 Minecraft 实例"""
    try:
        data = json.loads(body)
        inst_id = data.get("instanceId", "")
        if not inst_id or inst_id not in _in_game_instances:
            return EmptyResponse(success=False, message=f"实例 {inst_id} 未找到")
        
        info = _in_game_instances[inst_id]
        proc = info.get("Instance")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            logger.info(f"实例 {inst_id} 已停止")
        
        _in_game_instances.pop(inst_id, None)
        return EmptyResponse(message=f"实例 {inst_id} 已停止")
    except Exception as e:
        logger.error(f"停止实例失败: {e}")
        return EmptyResponse(success=False, message=str(e))


# ── Avatar ────────────────────────────────────────────

@commands.command()
async def get_avatar_data_url(body: str) -> str:
    """Get player avatar as base64 data URL."""
    try:
        params = json.loads(body)
        uuid = params.get("uuid", "")
        type_name = params.get("typeName", "Mojang")
        size = params.get("size", 64)
        use_default_skin = params.get("useDefaultSkin", False)
        
        from ECL.Game.Core.C_Skin import get_avatar_data_url as _get_avatar
        
        data_url = _get_avatar(uuid, type_name, None, size, use_default_skin)
        result = {"success": True, "data": {"dataUrl": data_url}, "message": "头像生成成功"}
        return json.dumps(result)
    except Exception as e:
        logger.error(f"获取头像失败: {e}")
        return json.dumps({"success": False, "message": str(e), "data": None})


# ── User Agreement ───────────────────────────────────

def _get_agreement_path() -> Path:
    return Path.cwd() / "ECL_Libs" / "user_agreement.json"


@commands.command()
async def get_user_agreement_status() -> ConfigResponse:
    path = _get_agreement_path()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return ConfigResponse(data={"accepted": data.get("accepted", False), "uuid": data.get("uuid", "")})
    return ConfigResponse(data={"accepted": False, "uuid": ""})


@commands.command()
async def save_user_agreement() -> ConfigResponse:
    path = _get_agreement_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"accepted": True, "uuid": str(uuid.uuid4())}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return ConfigResponse(data=data, message="用户协议已保存")


@commands.command()
async def clear_user_agreement() -> EmptyResponse:
    path = _get_agreement_path()
    if path.exists():
        path.unlink()
    return EmptyResponse(message="用户协议已清除")


@commands.command()
async def refresh_account_profile(body: str) -> ConfigResponse:
    try:
        data = json.loads(body)
        account_id = data.get("accountId", "")
        if not account_id:
            return ConfigResponse(success=False, message="缺少 accountId")
        am = get_account_manager()
        result = am.refresh_account_profile(account_id)
        return ConfigResponse(data=result, message=result.get("message", "刷新成功"))
    except Exception as e:
        logger.error(f"刷新账户档案失败: {e}")
        return ConfigResponse(success=False, message=str(e))


# ── Entry Point ──────────────────────────────────────

async def run_app() -> None:
    """Initialize and run the Tauri app."""
    global _app_handle

    try:
        # Initialize config
        cm = init_config_manager()
        
        # Initialize account manager
        am = get_account_manager()
        am.initialize()
        
        logger.info("EuoraCraft Launcher (pytauri) 初始化完成")

        # Determine frontend path
        dev_mode = cm.get_launcher_config().get("debug", False)
        ui_dist = _PYTHON_DIR.parent / "EuoraCraft-UI" / "dist"
        
        # cargo tauri dev sets this env var; let it manage the dev server
        is_tauri_dev = os.environ.get("TAURI_DEV") == "true"
        
        if is_tauri_dev:
            # Let the compiled context (tauri.conf.json) handle dev URL / dist
            logger.info("检测到 cargo tauri dev 模式，使用 Tauri CLI 管理的 dev server")
            no_server = None
            frontend_dist = None
        elif dev_mode and ui_dist.exists():
            # Development: serve from dist (or use dev server URL)
            frontend_dist = str(ui_dist)
            no_server = True
        elif dev_mode:
            # Development with Vite dev server (run separately)
            frontend_dist = "http://localhost:5173"
            no_server = False
        else:
            # Production: bundled
            frontend_dist = str(ui_dist)
            no_server = True

        # Create context and builder
        context = context_factory()
        if is_tauri_dev:
            builder = builder_factory()
        else:
            builder = builder_factory(
                no_server=no_server,
                frontend_dist_dir=frontend_dist if no_server else None,
                dev_url=None if no_server else frontend_dist,
            )

        # Generate invoke handler from registered commands
        logger.info(f"注册的命令: {len(commands.keys())} 个")
        for cmd in sorted(commands.keys()):
            logger.debug(f"  ─ {cmd}")

        with start_blocking_portal("asyncio") as portal:
            invoke_handler = commands.generate_handler(portal)
            app = builder.build(context, invoke_handler=invoke_handler)
            _app_handle = app.handle()

            logger.info("启动 Tauri 应用，并在后台线程运行主事件循环")
            app.run()
    except Exception as e:
        logger.error(f"应用运行时发生错误: {e}")
        raise
                    

def main() -> None:
    """Entry point called from Rust via PyO3."""
    anyio.run(run_app, backend="asyncio")
