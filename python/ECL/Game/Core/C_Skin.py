from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from configparser import ConfigParser
from pathlib import Path
from typing import Any

import requests

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from ...Core.logger import get_logger

logger = get_logger("skin")

SKIN_CACHE_DIR_NAME = "ECL_Libs/Cache/Skin"
_SKIN_DOWNLOAD_LOCK = threading.Lock()


def _get_project_root() -> Path:
    # 使用当前工作目录，与 launcher.py 保持一致
    return Path.cwd()


def _get_default_skin_path(skin_type: str) -> Path:
    """获取默认皮肤文件的路径"""
    # 优先从 ECL_Libs/Skins/ 目录获取
    ecl_libs_path = _get_project_root() / "ECL_Libs" / "Skins" / f"{skin_type}.png"
    if ecl_libs_path.exists():
        return ecl_libs_path

    # 如果不存在，尝试从 ui/dist/Skins/ 获取
    ui_dist_path = _get_project_root() / "ui" / "dist" / "Skins" / f"{skin_type}.png"
    if ui_dist_path.exists():
        return ui_dist_path

    # 如果还不存在，尝试从开发时的public目录获取
    dev_path = _get_project_root() / ".." / "EuoraCraft-UI" / "public" / "Skins" / f"{skin_type}.png"
    if dev_path.exists():
        return dev_path

    return ecl_libs_path


def _get_skin_cache_dir() -> Path:
    cache_dir = _get_project_root() / SKIN_CACHE_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_skin_index_path(type_name: str) -> Path:
    skin_dir = _get_skin_cache_dir()
    return skin_dir / f"Index{type_name}.ini"


def _load_skin_index(type_name: str) -> ConfigParser:
    path = _get_skin_index_path(type_name)
    parser = ConfigParser()
    parser.optionxform = str
    if path.exists():
        parser.read(path, encoding="utf-8")
    if "skins" not in parser.sections():
        parser["skins"] = {}
    return parser


def _save_skin_index(parser: ConfigParser, type_name: str) -> None:
    path = _get_skin_index_path(type_name)
    with path.open("w", encoding="utf-8") as f:
        parser.write(f)


def _get_cached_skin_address(uuid: str, type_name: str) -> str | None:
    uuid_key = uuid.lower()
    parser = _load_skin_index(type_name)
    return parser["skins"].get(uuid_key)


def _cache_skin_address(uuid: str, type_name: str, skin_url: str) -> None:
    uuid_key = uuid.lower()
    parser = _load_skin_index(type_name)
    parser["skins"][uuid_key] = skin_url
    _save_skin_index(parser, type_name)


def _cache_offline_avatar(uuid: str, skin_type: str, size: int) -> None:
    """缓存离线玩家或默认皮肤的头像数据"""
    cache_dir = _get_skin_cache_dir()
    filename = f"{uuid.lower()}-{skin_type}-{size}.png"
    file_path = cache_dir / filename
    
    # 如果缓存已存在，直接返回
    if file_path.exists():
        return
    
    # 生成头像并保存到缓存
    try:
        skin_path = _get_default_skin_path(skin_type)
        if not skin_path.exists():
            return
        
        with Image.open(skin_path) as skin_img:
            if skin_img.mode != 'RGBA':
                skin_img = skin_img.convert('RGBA')
            
            scale = max(1, skin_img.width // 64)
            head_x, head_y = 8 * scale, 8 * scale
            head_size = 8 * scale
            
            head_region = skin_img.crop((head_x, head_y, head_x + head_size, head_y + head_size))
            
            hair_x, hair_y = 40 * scale, 8 * scale
            if hair_x + head_size <= skin_img.width and hair_y + head_size <= skin_img.height:
                hair_region = skin_img.crop((hair_x, hair_y, hair_x + head_size, hair_y + head_size))
                if hair_region.getbbox() is not None:
                    head_region.paste(hair_region, (0, 0), hair_region)
            
            if size != head_size:
                head_region = head_region.resize((size, size), Image.NEAREST)
            
            head_region.save(file_path, 'PNG')
    except Exception as e:
        logger.warning(f"缓存离线头像失败 {uuid}: {e}")


def _build_skin_server_url(type_name: str, custom_server: str | None = None) -> str:
    type_clean = type_name.strip().lower()
    if type_clean in ("mojang", "ms", "microsoft"):
        return "https://sessionserver.mojang.com/session/minecraft/profile/"

    if type_clean == "nide":
        server = custom_server or os.environ.get("ECL_VERSION_SERVER_NIDE") or os.environ.get("ECL_NIDE_SERVER")
        if not server:
            raise ValueError("Nide 服务器地址未配置，请设置 ECL_VERSION_SERVER_NIDE 或 ECL_NIDE_SERVER")
        return f"https://auth.mc-user.com:233/{server.rstrip('/')}/sessionserver/session/minecraft/profile/"

    if type_clean == "auth":
        server = custom_server or os.environ.get("ECL_VERSION_SERVER_AUTH_SERVER") or os.environ.get("ECL_AUTH_SERVER")
        if not server:
            raise ValueError("Auth 服务器地址未配置，请设置 ECL_VERSION_SERVER_AUTH_SERVER 或 ECL_AUTH_SERVER")
        return f"{server.rstrip('/')}/sessionserver/session/minecraft/profile/"

    raise ValueError(f"皮肤地址种类无效：{type_name}")


def _fetch_profile_json(url: str, timeout: int = 10) -> dict[str, Any]:
    headers = {
        "User-Agent": "EuoraCraft Launcher",
        "Accept": "application/json"
    }
    
    # 调试：打印请求URL
    logger.debug(f"请求皮肤URL: {url}")
    
    response = requests.get(url, timeout=timeout, headers=headers)
    
    # 处理 204 No Content 响应（用户不存在）
    if response.status_code == 204:
        logger.debug("Mojang API 返回 204 No Content，用户不存在")
        raise ValueError("用户不存在或未设置皮肤")
    
    response.raise_for_status()
    
    # 调试：查看响应内容
    content = response.text
    logger.debug(f"响应状态码: {response.status_code}")
    logger.debug(f"响应内容前200字符: {content[:200]}")
    
    try:
        data = response.json()
        if not data:
            raise ValueError("皮肤返回值为空，可能是未设置自定义皮肤的用户")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        logger.error(f"完整响应内容: {content}")
        raise


def _parse_skin_url(profile_json: dict[str, Any]) -> str:
    properties = profile_json.get("properties")
    if not isinstance(properties, list):
        raise ValueError("皮肤返回值中不包含皮肤数据项，可能是未设置自定义皮肤的用户")

    texture_value = None
    for item in properties:
        if isinstance(item, dict) and item.get("name") == "textures":
            texture_value = item.get("value")
            break

    if not texture_value:
        raise ValueError("未从皮肤返回值中找到符合条件的 Property")

    try:
        decoded = base64.b64decode(texture_value)
        texture_json = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValueError("无法解析皮肤返回数据") from exc

    skin = texture_json.get("textures", {}).get("SKIN", {})
    skin_url = skin.get("url")
    if not skin_url:
        raise ValueError("用户未设置自定义皮肤")

    return skin_url.replace("http://", "https://") if "minecraft.net/" in skin_url else skin_url


def get_skin_address(uuid: str, type_name: str = "Mojang", custom_server: str | None = None) -> str:
    if not uuid:
        raise ValueError("UUID 为空。")

    if uuid.startswith("00000") and type_name.lower() != "auth":
        raise ValueError(f"离线 UUID 无正版皮肤文件：{uuid}")

    cached = _get_cached_skin_address(uuid, type_name)
    if cached:
        return cached

    server_url = _build_skin_server_url(type_name, custom_server)
    profile_json = _fetch_profile_json(f"{server_url}{uuid}")
    skin_url = _parse_skin_url(profile_json)
    _cache_skin_address(uuid, type_name, skin_url)
    return skin_url


def download_skin(address: str) -> Path:
    if not address:
        raise ValueError("皮肤地址不能为空")

    cache_dir = _get_skin_cache_dir()
    filename = f"{hashlib.md5(address.encode('utf-8')).hexdigest()}.png"
    file_path = cache_dir / filename
    tmp_path = cache_dir / (filename + ".tmp")

    with _SKIN_DOWNLOAD_LOCK:
        if file_path.exists():
            return file_path

        headers = {"User-Agent": "EuoraCraft Launcher"}
        response = requests.get(address, stream=True, timeout=15, headers=headers)
        response.raise_for_status()

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        tmp_path.replace(file_path)
        return file_path


def get_skin_sex(uuid: str) -> str:
    normalized = uuid.replace("-", "")
    if len(normalized) != 32:
        return "Steve"

    try:
        values = [int(normalized[i], 16) for i in (7, 15, 23, 31)]
    except ValueError:
        return "Steve"

    return "Alex" if (values[0] ^ values[1] ^ values[2] ^ values[3]) % 2 else "Steve"


def get_avatar_data_url(uuid: str, type_name: str = "Mojang", custom_server: str | None = None, size: int = 64, use_default_skin: bool = False) -> str:
    """
    获取玩家头像的 base64 data URL
    从皮肤中提取头部区域并缩放到指定尺寸
    
    Args:
        uuid: 玩家UUID
        type_name: 皮肤服务器类型 (Mojang, Nide, Auth)
        custom_server: 自定义服务器地址
        size: 头像尺寸
        use_default_skin: 是否强制使用默认皮肤（True: 使用默认皮肤，False: 尝试API获取）
    """
    if not HAS_PIL:
        raise ImportError("PIL (Pillow) 库未安装，无法处理头像")

    if not uuid:
        raise ValueError("UUID 为空")

    # 调试信息
    logger.debug(f"获取头像参数: uuid={uuid}, type_name={type_name}, use_default_skin={use_default_skin}")

    # 根据参数决定使用默认皮肤还是API获取
    if use_default_skin:
        # 强制使用默认皮肤
        skin_type = get_skin_sex(uuid)  # Steve 或 Alex
        skin_path = _get_default_skin_path(skin_type)
        logger.debug(f"强制使用默认皮肤路径: {skin_path}")
        if not skin_path.exists():
            raise FileNotFoundError(f"默认皮肤文件不存在: {skin_path}")
        # 缓存离线玩家皮肤
        _cache_offline_avatar(uuid, skin_type, size)
        logger.debug(f"强制使用默认皮肤: {uuid} -> {skin_type}")
    elif type_name.lower() in ("mojang", "ms", "microsoft"):
        # 使用 API 获取皮肤（Mojang正版用户和Microsoft账户）
        logger.debug(f"尝试API获取正版用户皮肤: {uuid}")
        try:
            skin_url = get_skin_address(uuid, type_name, custom_server)
            skin_path = download_skin(skin_url)
            logger.debug(f"成功获取正版用户在线皮肤: {uuid}")
        except Exception as e:
            # 如果获取失败，使用默认皮肤
            logger.warning(f"获取正版用户皮肤失败 {uuid}: {e}，使用默认皮肤")
            skin_type = get_skin_sex(uuid)
            skin_path = _get_default_skin_path(skin_type)
            if not skin_path.exists():
                raise FileNotFoundError(f"默认皮肤文件不存在: {skin_path}")
            # 缓存默认皮肤
            _cache_offline_avatar(uuid, skin_type, size)
    else:
        # 非Mojang服务器（如Nide、Auth等）使用默认皮肤
        skin_type = get_skin_sex(uuid)  # Steve 或 Alex
        skin_path = _get_default_skin_path(skin_type)
        logger.debug(f"非Mojang服务器使用默认皮肤路径: {skin_path}")
        if not skin_path.exists():
            raise FileNotFoundError(f"默认皮肤文件不存在: {skin_path}")
        # 缓存离线玩家皮肤
        _cache_offline_avatar(uuid, skin_type, size)
        logger.debug(f"非Mojang服务器使用默认皮肤: {uuid} -> {skin_type}")

    # 处理头像
    with Image.open(skin_path) as skin_img:
        # 确保是 RGBA 模式
        if skin_img.mode != 'RGBA':
            skin_img = skin_img.convert('RGBA')

        # 检测皮肤缩放比例（通常是 64x64 或更高）
        scale = max(1, skin_img.width // 64)

        # 提取头部区域 (8x8 像素，从位置 8,8 开始)
        head_x, head_y = 8 * scale, 8 * scale
        head_size = 8 * scale

        head_region = skin_img.crop((head_x, head_y, head_x + head_size, head_y + head_size))

        # 检查是否有头发层 (位置 40,8)
        hair_x, hair_y = 40 * scale, 8 * scale
        if hair_x + head_size <= skin_img.width and hair_y + head_size <= skin_img.height:
            hair_region = skin_img.crop((hair_x, hair_y, hair_x + head_size, hair_y + head_size))

            # 检查头发层是否透明或为空
            if hair_region.getbbox() is not None:  # 有非透明像素
                # 合并头发层到头部
                head_region.paste(hair_region, (0, 0), hair_region)

        # 缩放到目标尺寸
        if size != head_size:
            head_region = head_region.resize((size, size), Image.NEAREST)

        # 转换为 base64 data URL
        from io import BytesIO
        buffer = BytesIO()
        head_region.save(buffer, format='PNG')
        img_data = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return f"data:image/png;base64,{img_data}"