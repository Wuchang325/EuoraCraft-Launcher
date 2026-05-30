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
    WebviewWindow,
    builder_factory,
    context_factory,
    WebviewUrl,
)
from pytauri.ipc import InvokeException
from pytauri_plugins.dialog import ask, confirm, message, open_file, save_file

# ── Reuse existing ECL modules ────────────────────────
# Add the backend directory to sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "EuoraCraft-Launcher"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from ECL.Core.logger import get_logger
from ECL.Core.config import ConfigManager
from ECL.Game.java import get_java_list as _get_java_list
from ECL.Game.AccountManager import get_account_manager
from ECL.Game.Core import ECLauncherCore, C_GetGames, InstancesManager
from ECL.Game.Core.C_Libs import is_uuid3

logger = get_logger("pytauri")


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
    webview_window.minimize()
    return EmptyResponse(message="窗口已最小化")


@commands.command()
async def close_window(webview_window: WebviewWindow) -> EmptyResponse:
    webview_window.close()
    return EmptyResponse(message="窗口已关闭")


@commands.command()
async def toggle_maximize(webview_window: WebviewWindow) -> EmptyResponse:
    if webview_window.is_maximized():
        webview_window.unmaximize()
    else:
        webview_window.maximize()
    return EmptyResponse()


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


# ── Background Image ──────────────────────────────────

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


@commands.command()
async def select_local_image() -> ConfigResponse:
    try:
        files = await open_file(
            multiple=False,
            filters=[{
                "name": "图片",
                "extensions": ["jpg", "jpeg", "png", "gif", "webp"],
            }],
        )
        if files:
            return ConfigResponse(data={"path": str(files[0])})
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
        dirs = await open_file(multiple=False, directory=True)
        if dirs:
            return ConfigResponse(data={"path": str(dirs[0])})
        return ConfigResponse(success=False, message="用户取消选择")
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@commands.command()
async def select_java_executable() -> ConfigResponse:
    try:
        files = await open_file(
            multiple=False,
            filters=[{
                "name": "Java Executable",
                "extensions": ["exe"],
            }],
        )
        if files:
            return ConfigResponse(data={"path": str(files[0])})
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


@commands.command()
async def scan_versions_in_path() -> ConfigResponse:
    """扫描本地游戏目录中的已安装版本"""
    try:
        game_path = _get_game_path()
        get_games = C_GetGames.GetGames()
        versions = get_games.scan_local_versions(game_path)
        return ConfigResponse(data=[
            {"id": v["id"], "type": v.get("type", "release")}
            for v in versions
        ])
    except Exception as e:
        logger.error(f"扫描版本失败: {e}")
        return ConfigResponse(success=False, message=str(e), data=[])


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
        
        # Import the skin module from the backend
        sys.path.insert(0, str(_BACKEND_DIR))
        from ECL.Game.Core.C_Skin import get_avatar_data_url as _get_avatar
        
        data_url = _get_avatar(uuid, type_name, None, size, use_default_skin)
        result = {"success": True, "data": {"dataUrl": data_url}, "message": "头像生成成功"}
        return json.dumps(result)
    except Exception as e:
        logger.error(f"获取头像失败: {e}")
        return json.dumps({"success": False, "message": str(e), "data": None})


# ── User Agreement ───────────────────────────────────

def _get_agreement_path() -> Path:
    return _BACKEND_DIR.parent / "ECL_Libs" / "user_agreement.json"


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
        ui_dist = _BACKEND_DIR.parent / "EuoraCraft-UI" / "dist"
        
        if dev_mode and ui_dist.exists():
            # Development: serve from dist (or use dev server URL)
            frontend_dist = str(ui_dist)
            no_server = True
        elif dev_mode:
            # Development with Vite dev server
            frontend_dist = "http://localhost:5173"
            no_server = False
        else:
            # Production: bundled
            frontend_dist = str(ui_dist)
            no_server = True

        # Create context and builder
        context = context_factory()
        builder = builder_factory(
            no_server=no_server,
            frontend_dist_dir=frontend_dist if no_server else None,
            dev_url=None if no_server else frontend_dist,
        )

        # Generate invoke handler from registered commands
        async with anyio.create_task_group() as tg:
            with start_blocking_portal("asyncio") as portal:
                invoke_handler = commands.generate_handler(portal)
                app = builder.build(context, invoke_handler=invoke_handler)
                _app_handle = app.handle()

                # Run app (blocks until exit)
                app.run()

    except Exception as e:
        logger.critical(f"启动器运行失败: {e}")
        raise


def main() -> None:
    """Entry point called from Rust via PyO3."""
    anyio.run(run_app, backend="asyncio")
