from dataclasses import dataclass, fields, asdict
from pathlib import Path
from uuid import UUID
import hashlib
import zipfile
import json
import os
import re


def replace_last(text: str, old: str, new: str) -> str:  # 替换字符串最后一个匹配项, NeoForged的-p参数需要
    return new.join(text.rsplit(old, 1))


def name_to_path(name: str) -> str | None:  # 将Maven坐标转换为文件路径
    at_index = name.find("@")
    if at_index != -1:
        suffix = name[at_index + 1:]
        name = name[0:at_index]
    else:
        suffix = "jar"
    parts = name.split(":")
    if len(parts) == 4:
        return f"{parts[0].replace('.', '/')}/{parts[1]}/{parts[2]}/{parts[1]}-{parts[2]}-{parts[3]}.{suffix}"
    elif len(parts) == 3:
        return f"{parts[0].replace('.', '/')}/{parts[1]}/{parts[2]}/{parts[1]}-{parts[2]}.{suffix}"
    else:
        return None


def name_to_uuid(name: str) -> UUID:  # 将玩家昵称转换为UUID3(离线模式)
    return UUID(bytes=hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest()[:16], version=3)


def is_uuid3(uuid_string: str) -> bool:  # 检测字符串是否为UUID3格式
    try:
        return UUID(uuid_string, version=3).version == 3
    except ValueError:
        return False


def unzip(zip_path: str | Path, unzip_path: str | Path) -> None:  # 解压natives文件
    try:
        with zipfile.ZipFile(zip_path) as zip_object:
            for file in zip_object.namelist():
                zip_object.extract(file, unzip_path)
    except (zipfile.BadZipFile, FileNotFoundError):
        pass


def get_file_sha1(file_path: str | Path) -> str:  # 计算文件SHA1用于校验
    sha1 = hashlib.sha1()
    if os.path.isfile(file_path):
        with open(file_path, "rb") as open_file:
            for file_part in iter(lambda: open_file.read(8192), b""):
                sha1.update(file_part)
    return sha1.hexdigest()


def find_version(version_json: dict, game_path: Path) -> tuple[dict, Path] | None:  # 查找继承的原版版本
    if "inheritsFrom" in version_json:  # 若有Mod加载器则寻找原版游戏
        inherits_from = version_json["inheritsFrom"]
        for version_path in (game_path / "versions").iterdir():  # 通过版本Json内的id键查找,而非文件夹名
            if not version_path.is_dir(): 
                continue
            game_json_path = version_path / f"{version_path.name}.json"
            if not game_json_path.is_file(): 
                continue
            game_json = json.loads(game_json_path.read_text("utf-8"))
            if game_json["id"] != inherits_from: 
                continue
            return game_json, version_path
        version_path = game_path / "versions" / inherits_from
        if (version_path / f"{inherits_from}.json").is_file():  # 直接查找inheritsFrom对应版本
            return json.loads((version_path / f"{inherits_from}.json").read_text("utf-8")), version_path
        return None
    return None



NEOFORGE_VERSION_PATTERN = re.compile(
    r'^(?P<year>\d+)\.(?P<major>\d+)(?:\.(?P<hotfix>\d+))?(?:\.(?P<build>\d+))?(?P<suffix>-[\w.]+)?$'
)


def parse_neoforge_version(neoforge_version: str) -> str | None:  # 解析NeoForged版本号
    clean = neoforge_version.split("-")[0]
    m = NEOFORGE_VERSION_PATTERN.match(clean)
    if not m: 
        return None
    year = int(m.group("year"))
    major = int(m.group("major"))
    if year >= 26:  # 2026新命名方案
        return f"{year}.{major}"
    if year == 21:  # 旧方案
        return "1.21" if major == 0 else f"1.21.{major}"
    if year == 20:
        return f"1.20.{major}"
    return None


def normalize_neoforge_version(neoforge_version: str) -> str:  # 移除版本后缀
    return neoforge_version.split("-")[0]


def is_neoforge_snapshot_version(neoforge_version: str) -> bool:  # 判断是否为快照/预发布版本
    if re.match(r'^\d{2,}\.', neoforge_version):
        year = int(neoforge_version.split(".")[0])
        if year >= 26: 
            return True
    return bool(re.search(r'-(?:beta|snapshot|rc|alpha|pre)', neoforge_version, re.I))


def get_neoforge_version_info(neoforge_version: str) -> dict[str, str | bool | int | None]:  # 获取NeoForged版本详细信息
    normalized = normalize_neoforge_version(neoforge_version)
    m = NEOFORGE_VERSION_PATTERN.match(normalized)
    if not m:
        return {"raw": neoforge_version, "valid": False, "mc_version": None}
    year = int(m.group("year"))
    major = int(m.group("major"))
    hotfix = m.group("hotfix")
    build = m.group("build")
    suffix = m.group("suffix")
    is_new_scheme = year >= 26
    return {
        "raw": neoforge_version,
        "normalized": normalized,
        "valid": True,
        "year": year,
        "major": major,
        "hotfix": int(hotfix) if hotfix else None,
        "build": int(build) if build else None,
        "suffix": suffix,
        "is_new_scheme": is_new_scheme,
        "is_legacy": not is_new_scheme,
        "mc_version": parse_neoforge_version(neoforge_version),
        "is_snapshot": is_neoforge_snapshot_version(neoforge_version)
    }


@dataclass
class ApiUrl:  # API地址数据结构
    Meta: str = "https://launchermeta.mojang.com"
    Data: str = "https://launcher.mojang.com"
    Libraries: str = "https://libraries.minecraft.net"
    Assets: str = "https://resources.download.minecraft.net"
    Forge: str = "https://files.minecraftforge.net/maven"
    Fabric: str = "https://maven.fabricmc.net"
    FabricMeta: str = "https://meta.fabricmc.net"
    NeoForged: str = "https://maven.neoforged.net/releases"
    Quilt: str = "https://maven.quiltmc.org"
    QuiltMeta: str = "https://meta.quiltmc.org"

    def get(self, key_name: str) -> dict[str, str] | None:
        return getattr(self, key_name, None)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, api_url_dict: dict):
        kw = {}
        for api_name in fields(cls):
            if api_name.name in api_url_dict:
                kw.update({api_name.name: api_url_dict[api_name.name].strip("/")})
        return cls(**kw)

    def update_from_dict(self, api_url_dict: dict):
        for api_name in fields(self):
            if api_name.name in api_url_dict:
                setattr(self, api_name.name, api_url_dict[api_name.name].strip("/"))