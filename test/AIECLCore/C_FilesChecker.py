from pathlib import Path
from typing import Callable, List, Tuple, Optional, Dict, Any, Union
import json
import requests
import os
from . import C_Libs, C_Downloader
from ..logger import get_logger

logger = get_logger("checker")


class FilesChecker:
    """
    文件检查器，支持版本隔离（Version Isolation）
    """
    
    def __init__(self, api_url: C_Libs.ApiUrl | None = None, downloader: C_Downloader.Downloader | None = None):
        self.api_url = api_url if api_url else C_Libs.ApiUrl()
        self.downloader = downloader if downloader else C_Downloader.Downloader()
        self.output_log = self.__default_output_log
        self.isolation_mode = "shared"

    @staticmethod
    def __default_output_log(log: str):
        logger.info(log)

    def set_isolation_mode(self, mode: str):
        """设置版本隔离模式: 'isolated' (独立) 或 'shared' (共享)"""
        if mode not in ["isolated", "shared"]:
            raise ValueError("模式必须是 'isolated' 或 'shared'")
        self.isolation_mode = mode
        logger.info(f"版本隔离模式: {mode}")

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def __find_api(self, get_url: str, get_path: str) -> List[str]:
        """根据 URL 模式匹配对应的镜像源"""
        if not get_url: 
            return []
        
        mapping = {
            "libraries.minecraft.net": self.api_url.Libraries,
            "resources.download.minecraft.net": self.api_url.Assets,
            "launchermeta.mojang.com": self.api_url.Meta,
            "launcher.mojang.com": self.api_url.Data,
            "piston-data.mojang.com": self.api_url.Data,
            "piston-meta.mojang.com": self.api_url.Meta,
            "files.minecraftforge.net": self.api_url.Forge,
            "maven.fabricmc.net": self.api_url.Fabric,
            "meta.fabricmc.net": self.api_url.FabricMeta,
            "maven.neoforged.net": self.api_url.NeoForged,
            "maven.quiltmc.org": self.api_url.Quilt,
            "meta.quiltmc.org": self.api_url.QuiltMeta
        }
        
        urls = []
        
        if "resources.download.minecraft.net" in get_url:
            asset_hash = get_url.split("/")[-1]
            if len(asset_hash) >= 2:
                urls.append(f"{self.api_url.Assets}/{asset_hash[:2]}/{asset_hash}")
                urls.append(f"https://resources.download.minecraft.net/{asset_hash[:2]}/{asset_hash}")
                return urls
        
        for domain, mirror in mapping.items():
            if domain in get_url:
                urls.append(f"{mirror}/{get_path}")
                break
        
        if get_url not in urls:
            urls.append(get_url)
            
        return urls

    def __check_libraries(self, game_path: Path, version_json: dict) -> List[Tuple[List[str], str]]:
        """检查依赖库文件"""
        download_list = []
        libraries = version_json.get("libraries", [])
        
        for lib in libraries:
            lib_name = lib.get("name", "")
            downloads = lib.get("downloads", {})
            artifact = downloads.get("artifact", {})
            
            if artifact:
                path = artifact.get("path") or C_Libs.name_to_path(lib_name)
                if not path:
                    continue
                
                full_path = game_path / "libraries" / path
                
                need_download = False
                if not full_path.exists():
                    need_download = True
                elif artifact.get("sha1") and C_Libs.get_file_sha1(full_path) != artifact["sha1"]:
                    need_download = True
                    full_path.unlink(missing_ok=True)
                
                if need_download:
                    url = artifact.get("url", "")
                    if not url:
                        if "fabricmc" in lib_name:
                            url = f"https://maven.fabricmc.net/{path}"
                        elif "neoforged" in lib_name:
                            url = f"https://maven.neoforged.net/releases/{path}"
                        elif "net.minecraftforge" in lib_name:
                            url = f"https://maven.minecraftforge.net/{path}"
                        else:
                            url = f"https://libraries.minecraft.net/{path}"
                    
                    urls = self.__find_api(url, path)
                    download_list.append((urls, str(full_path)))
            
            elif lib_name:
                path = C_Libs.name_to_path(lib_name)
                if not path:
                    continue
                
                full_path = game_path / "libraries" / path
                if full_path.exists():
                    continue
                
                lib_url = lib.get("url", "https://libraries.minecraft.net")
                primary_url = f"{lib_url.rstrip('/')}/{path}"
                urls = self.__find_api(primary_url, path)
                download_list.append((urls, str(full_path)))

        return download_list

    def __check_assets(self, game_path: Path, version_json: dict) -> List[Tuple[List[str], str]]:
        """检查游戏资源文件（修复：不强制下载索引）"""
        download_list = []
        asset_index = version_json.get("assetIndex", {})
        
        if not asset_index: 
            return download_list

        index_id = asset_index["id"]
        index_path = game_path / "assets" / "indexes" / f"{index_id}.json"
        index_url = asset_index["url"]
        
        # 【关键修复】检查索引文件是否已存在且有效
        need_download_index = False
        if not index_path.exists():
            need_download_index = True
            logger.debug(f"索引文件不存在，需要下载: {index_id}.json")
        else:
            # 检查 SHA1（如果 JSON 中提供了）
            expected_sha1 = asset_index.get("sha1")
            if expected_sha1:
                actual_sha1 = C_Libs.get_file_sha1(index_path)
                if actual_sha1 != expected_sha1:
                    need_download_index = True
                    logger.debug(f"索引文件 SHA1 不匹配，重新下载")
                    index_path.unlink(missing_ok=True)
                else:
                    logger.debug(f"索引文件已存在且有效，跳过下载")
            else:
                # 没有 SHA1，检查文件大小或默认信任已存在的文件
                logger.debug(f"索引文件已存在（无 SHA1 校验），跳过下载")

        # 只在需要时下载索引
        if need_download_index:
            urls = self.__find_api(index_url, f"indexes/{index_id}.json")
            logger.debug(f"正在下载索引文件...")
            success = self.downloader.download_manager([(urls, str(index_path))], 1)
            if not success or not index_path.exists():
                logger.error("资源索引下载失败")
                return download_list
        else:
            logger.debug(f"使用现有索引文件")

        # 解析索引并检查资源文件
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
                objects = index_data.get("objects", {})
            
            total = len(objects)
            if total == 0:
                return download_list
                
            logger.debug(f"校验 {total} 个资源文件...")
            
            for name, info in objects.items():
                h = info["hash"]
                rel = f"objects/{h[:2]}/{h}"
                full = game_path / "assets" / rel
                
                if not full.exists():
                    official_url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"
                    urls = self.__find_api(official_url, rel)
                    download_list.append((urls, str(full)))
                elif C_Libs.get_file_sha1(full) != h:
                    full.unlink(missing_ok=True)
                    official_url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"
                    urls = self.__find_api(official_url, rel)
                    download_list.append((urls, str(full)))
                    
        except Exception as e:
            logger.error(f"[诊断 Assets] 解析资源失败: {e}")
            return download_list
            
        return download_list    

    def _download_vanilla_json(self, game_path: Path, version_id: str) -> Optional[dict]:
        """下载原版版本 JSON 并返回数据（不保存文件）"""
        try:
            manifest_url = f"{self.api_url.Meta}/mc/game/version_manifest.json"
            resp = requests.get(manifest_url, timeout=10).json()
            
            version_info = next((v for v in resp["versions"] if v["id"] == version_id), None)
            if not version_info:
                logger.error(f"未找到版本: {version_id}")
                return None
            
            vanilla_resp = requests.get(version_info["url"], timeout=10)
            return vanilla_resp.json()
            
        except Exception as e:
            logger.error(f"下载原版 JSON 失败: {e}")
            return None

    def check_files_isolated(self, game_path: Path, version_name: str) -> List[Tuple[List[str], str]]:
        """独立模式（版本隔离）"""
        download_list = []
        version_dir = game_path / "versions" / version_name
        json_path = version_dir / f"{version_name}.json"
        
        if not json_path.exists():
            raise FileNotFoundError(f"找不到版本配置文件: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            version_json = json.load(f)

        self.output_log(f"[独立模式] 检查: {version_name}")

        vanilla_version = version_json.get("_vanillaVersion")
        is_merged = version_json.get("_merged", False)
        logger.debug(f"_merged: {is_merged}, _vanillaVersion: {vanilla_version}")

        # 检查主 Jar
        main_jar = version_dir / f"{version_name}.jar"
        
        inherits_from = version_json.get("inheritsFrom")
        
        if inherits_from:
            logger.info(f"检测到继承原版: {inherits_from}，执行合并...")
            
            if not version_json.get("_merged"):
                vanilla_json = self._download_vanilla_json(game_path, inherits_from)
                if not vanilla_json:
                    raise RuntimeError(f"无法获取原版 {inherits_from} 配置")
                
                merged_json = C_Libs.merge_version_jsons(vanilla_json, version_json)
                merged_json["id"] = version_name
                merged_json["_merged"] = True
                merged_json["_vanillaVersion"] = inherits_from
                
                json_path.write_text(json.dumps(merged_json, indent=2), encoding="utf-8")
                logger.info(f"✓ 已合并为: {version_name}.json")
                
                version_json = merged_json
            
            if not main_jar.exists():
                logger.info(f"需要下载原版 Jar: {version_name}.jar")
                
                client_download = version_json.get("downloads", {}).get("client", {})
                if client_download:
                    url = client_download.get("url")
                    if url:
                        urls = self.__find_api(url, f"versions/{inherits_from}/{inherits_from}.jar")
                        download_list.append((urls, str(main_jar)))
            else:
                logger.info(f"Jar 文件已存在，跳过下载")
            
            download_list.extend(self.__check_libraries(game_path, version_json))
            
            if version_json.get("assetIndex"):
                download_list.extend(self.__check_assets(game_path, version_json))
        
        else:
            jar_download_version = vanilla_version if vanilla_version else version_name
            
            if not main_jar.exists():
                logger.info(f"需要下载 Jar（已合并模式）: {main_jar.name}")
                
                client_download = version_json.get("downloads", {}).get("client", {})
                if client_download:
                    url = client_download.get("url")
                    if url:
                        urls = self.__find_api(url, f"versions/{jar_download_version}/{jar_download_version}.jar")
                        download_list.append((urls, str(main_jar)))
            else:
                logger.info(f"Jar 文件已存在，跳过下载")

            download_list.extend(self.__check_libraries(game_path, version_json))
            
            if version_json.get("assetIndex"):
                asset_downloads = self.__check_assets(game_path, version_json)
                download_list.extend(asset_downloads)

        return download_list

    def check_files_shared(self, game_path: Path, version_name: str) -> List[Tuple[List[str], str]]:
        """共享模式（PCL 风格）"""
        download_list = []
        version_dir = game_path / "versions" / version_name
        json_path = version_dir / f"{version_name}.json"
        
        if not json_path.exists():
            raise FileNotFoundError(f"找不到版本配置文件: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            version_json = json.load(f)

        self.output_log(f"[共享模式] 检查: {version_name}")

        # 检查当前版本的 Jar
        main_jar = version_dir / f"{version_name}.jar"
        if not main_jar.exists():
            client_download = version_json.get("downloads", {}).get("client", {})
            if client_download:
                url = client_download.get("url")
                if url:
                    urls = self.__find_api(url, f"versions/{version_name}/{version_name}.jar")
                    download_list.append((urls, str(main_jar)))

        download_list.extend(self.__check_libraries(game_path, version_json))

        inherits_from = version_json.get("inheritsFrom")
        
        if inherits_from:
            logger.info(f"检测到依赖原版: {inherits_from}")
            
            shared_vanilla_dir = game_path / "versions" / inherits_from
            shared_vanilla_jar = shared_vanilla_dir / f"{inherits_from}.jar"
            shared_vanilla_json = shared_vanilla_dir / f"{inherits_from}.json"
            
            if shared_vanilla_jar.exists() and shared_vanilla_json.exists():
                logger.info(f"使用共享原版: {inherits_from}")
                try:
                    v_json = json.loads(shared_vanilla_json.read_text("utf-8"))
                    download_list.extend(self.__check_libraries(game_path, v_json))
                    if v_json.get("assetIndex"):
                        download_list.extend(self.__check_assets(game_path, v_json))
                except Exception as e:
                    logger.error(f"读取共享原版失败: {e}")
            else:
                logger.info(f"下载原版到共享目录: {inherits_from}")
                shared_vanilla_dir.mkdir(parents=True, exist_ok=True)
                
                vanilla_json = self._download_vanilla_json(game_path, inherits_from)
                if vanilla_json:
                    shared_vanilla_json.write_text(
                        json.dumps(vanilla_json, indent=2), encoding="utf-8"
                    )
                    client_download = vanilla_json.get("downloads", {}).get("client", {})
                    if client_download:
                        url = client_download.get("url")
                        if url:
                            urls = self.__find_api(url, f"versions/{inherits_from}/{inherits_from}.jar")
                            download_list.append((urls, str(shared_vanilla_jar)))
                    
                    download_list.extend(self.__check_libraries(game_path, vanilla_json))
                    if vanilla_json.get("assetIndex"):
                        download_list.extend(self.__check_assets(game_path, vanilla_json))
        
        else:
            if version_json.get("assetIndex"):
                download_list.extend(self.__check_assets(game_path, version_json))

        return download_list

    def check_files(self, game_path: str | Path, version_name: str, download_max_thread: int) -> bool:
        """主入口：根据隔离模式选择检查逻辑"""
        game_path = Path(game_path)
        
        # 自动检测已合并 JSON
        json_path = game_path / "versions" / version_name / f"{version_name}.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("_merged") and self.isolation_mode != "isolated":
                        logger.info(f"检测到已合并 JSON，自动切换到独立模式")
                        self.isolation_mode = "isolated"
            except:
                pass
        
        if self.isolation_mode == "isolated":
            download_list = self.check_files_isolated(game_path, version_name)
        else:
            download_list = self.check_files_shared(game_path, version_name)
        
        if download_list:
            logger.info(f"总共需要下载 {len(download_list)} 个文件")
            success = self.downloader.download_manager(download_list, download_max_thread)
            if not success:
                logger.error("部分文件下载失败")
            return success
        else:
            logger.info("所有文件已就绪，无需下载")
            return True