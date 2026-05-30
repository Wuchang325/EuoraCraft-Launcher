from typing import Callable, Optional, Dict, List
import requests
from pathlib import Path
import json
from . import C_Libs, C_Downloader, C_FilesChecker
from ..logger import get_logger

logger = get_logger("get_games")


class GetGames:
    """游戏版本管理，支持版本隔离和自定义版本名"""
    
    def __init__(self, api_url: C_Libs.ApiUrl | None = None, downloader: C_Downloader.Downloader | None = None, 
                 files_checker: C_FilesChecker.FilesChecker | None = None):
        self.api_url = api_url if api_url else C_Libs.ApiUrl()
        self.downloader = downloader if downloader else C_Downloader.Downloader()
        self.files_checker = files_checker if files_checker else C_FilesChecker.FilesChecker(self.api_url, self.downloader)
        self.output_log = self.__default_output_log

    @staticmethod
    def __default_output_log(log: str):
        logger.info(log)

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_api_url(self, api_url_dict: dict):
        self.api_url.update_from_dict(api_url_dict)
        self.files_checker.api_url.update_from_dict(api_url_dict)

    def get_version_list(self) -> Optional[Dict]:
        """获取 Minecraft 版本列表"""
        url = f"{self.api_url.Meta}/mc/game/version_manifest.json"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取版本列表失败: {e}")
            return None

    def download_minecraft(self, game_path: str | Path, version_id: str, download_file: bool = True, 
                           download_max_thread: int = 32, save_version_name: str | None = None) -> bool:
        """
        下载原版 Minecraft（支持自定义版本名）
        """
        game_path = Path(game_path)
        save_name = save_version_name if save_version_name else version_id
        
        save_json_path = game_path / "versions" / save_name / f"{save_name}.json"
        
        if save_json_path.exists():
            logger.info(f"版本 {save_name} 已存在")
            if download_file:
                return self.files_checker.check_files(game_path, save_name, download_max_thread)
            return True
        
        get_versions = self.get_version_list()
        if not get_versions: 
            return False
            
        get_version_info = None
        for version_info in get_versions["versions"]:
            if version_info["id"] == version_id:
                get_version_info = version_info
                try:
                    response = requests.get(version_info["url"], timeout=10)
                    response.raise_for_status()
                    save_json_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    json_data = response.json()
                    json_data["id"] = save_name
                    
                    save_json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
                    logger.info(f"已下载原版配置: {save_name}")
                    break
                except Exception as e:
                    logger.error(f"下载版本 JSON 失败: {e}")
                    return False
        
        if not get_version_info:
            logger.error(f"未找到版本: {version_id}")
            return False
            
        if download_file:
            return self.files_checker.check_files(game_path, save_name, download_max_thread)
            
        return True

    def download_fabric(self, game_path: str | Path, game_version_id: str, fabric_version: str, 
                        download_vanilla: bool = True, download_max_thread: int = 32, 
                        save_version_name: str | None = None,
                        isolation_mode: str = "shared",
                        merge_json: bool = True) -> bool:
        """
        下载 Fabric 版本（支持自定义版本名和版本隔离）
        """
        game_path = Path(game_path)
        default_name = f"fabric-loader-{fabric_version}-{game_version_id}"
        save_name = save_version_name if save_version_name else default_name
        
        version_dir = game_path / "versions" / save_name
        save_json_path = version_dir / f"{save_name}.json"
        
        if save_json_path.exists():
            logger.info(f"版本 {save_name} 已存在")
            self.files_checker.set_isolation_mode(isolation_mode)
            return self.files_checker.check_files(game_path, save_name, download_max_thread)
        
        version_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            url = f"{self.api_url.FabricMeta}/v2/versions/loader/{game_version_id}/{fabric_version}/profile/json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            fabric_json = response.json()
            
            if isolation_mode == "isolated":
                logger.info(f"隔离模式安装 Fabric: {save_name}")
                
                manifest = requests.get(f"{self.api_url.Meta}/mc/game/version_manifest.json", timeout=10).json()
                vanilla_info = next((v for v in manifest["versions"] if v["id"] == game_version_id), None)
                
                if not vanilla_info:
                    raise ValueError(f"未找到 Minecraft 版本: {game_version_id}")
                
                vanilla_json = requests.get(vanilla_info["url"], timeout=10).json()
                
                if merge_json:
                    merged = C_Libs.merge_version_jsons(vanilla_json, fabric_json)
                    merged["id"] = save_name
                    merged["_merged"] = True
                    merged["_vanillaVersion"] = game_version_id
                    save_json_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
                    logger.info(f"已合并 JSON: {save_name}.json")
                else:
                    fabric_json["id"] = save_name
                    save_json_path.write_text(json.dumps(fabric_json, indent=2), encoding="utf-8")
                    logger.info(f"已保存 Fabric JSON: {save_name}.json")
            else:
                logger.info(f"共享模式安装 Fabric: {save_name}")
                fabric_json["id"] = save_name
                save_json_path.write_text(json.dumps(fabric_json, indent=2), encoding="utf-8")
                
                if download_vanilla:
                    vanilla_dir = game_path / "versions" / game_version_id
                    if not (vanilla_dir / f"{game_version_id}.json").exists():
                        self.download_minecraft(game_path, game_version_id, True, download_max_thread, None)
            
        except Exception as e:
            logger.error(f"下载 Fabric 失败: {e}")
            return False        
            
        self.files_checker.set_isolation_mode(isolation_mode)
        return self.files_checker.check_files(game_path, save_name, download_max_thread)

    def download_neoforge(self, game_path: str | Path, mc_version: str, neoforge_version: str,
                          download_max_thread: int = 32,
                          save_version_name: str | None = None) -> bool:
        """
        下载 NeoForge 版本（支持自定义版本名）
        """
        game_path = Path(game_path)
        default_name = f"{mc_version}-neoforge-{neoforge_version}"
        save_name = save_version_name if save_version_name else default_name
        
        version_dir = game_path / "versions" / save_name
        version_dir.mkdir(parents=True, exist_ok=True)
        
        base_url = f"{self.api_url.NeoForged}/net/neoforged/neoforge"
        neoforge_path = f"{mc_version}-{neoforge_version}"
        
        try:
            universal_jar_name = f"neoforge-{neoforge_path}-universal.jar"
            universal_url = f"{base_url}/{neoforge_path}/{universal_jar_name}"
            universal_path = version_dir / f"{save_name}.jar"
            
            if not universal_path.exists():
                logger.info(f"下载 NeoForge Universal JAR...")
                success = self.downloader.download_manager([([universal_url], str(universal_path))], 1)
                if not success:
                    raise Exception("下载 Universal JAR 失败")
            
            client_json_name = f"neoforge-{neoforge_path}-client.json"
            json_url = f"{base_url}/{neoforge_path}/{client_json_name}"
            json_path = version_dir / f"{save_name}.json"
            
            if not json_path.exists():
                logger.info(f"下载 NeoForge 客户端 JSON...")
                success = self.downloader.download_manager([([json_url], str(json_path))], 1)
                if not success:
                    raise Exception("下载客户端 JSON 失败")
                
                json_content = json.loads(json_path.read_text(encoding="utf-8"))
                json_content["id"] = save_name
                json_path.write_text(json.dumps(json_content, indent=2), encoding="utf-8")
            
            logger.info(f"NeoForge {save_name} 安装成功")
            return self.files_checker.check_files(game_path, save_name, download_max_thread)
            
        except Exception as e:
            logger.error(f"下载 NeoForge 失败: {e}")
            return False