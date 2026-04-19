from typing import Callable
from pathlib import Path
import requests
import json
import xml.etree.ElementTree as ET
import re

from . import C_Libs, C_FilesChecker


class GetGames:
    def __init__(self, files_checker: C_FilesChecker.FilesChecker | None = None):
        self.files_checker = files_checker or C_FilesChecker.FilesChecker()
        self.output_log: Callable[[str], None] = print

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_api_url(self, api_url_dict: dict):
        self.files_checker.api_url.update_from_dict(api_url_dict)

    VERSION_REGEX = re.compile(r'^\d+\.\d+(?:\.\d+)*(?:-\w+)?$')  # NeoForged版本号正则

    def get_minecraft_versions(self):  # 获取官方版本列表
        try:
            get_versions = requests.get(f"{self.files_checker.api_url.Meta}/mc/game/version_manifest_v2.json").json()
        except requests.exceptions.RequestException:
            return None
        snapshot = []
        release = []
        fool_days = []
        beta = []
        alpha = []
        for version_info in get_versions["versions"]:
            if version_info["type"] == "release": 
                release.append(version_info)
            elif version_info["type"] == "snapshot":
                if "-04-01" in version_info["releaseTime"] or version_info["id"] == "1.RV-Pre1":
                    fool_days.append(version_info)  # 愚人节版本
                else:
                    snapshot.append(version_info)
            elif "beta" in version_info["type"]: 
                beta.append(version_info)
            elif "alpha" in version_info["type"]: 
                alpha.append(version_info)
        return {
            "Latest": get_versions["latest"],  # 最新版本{"release": "", "snapshot": ""}
            "All": get_versions["versions"],  # 所有版本
            "Snapshot": snapshot,  # 快照版
            "Release": release,  # 正式版
            "FoolDays": fool_days,  # 愚人节版
            "Beta": beta,  # Beta版
            "Alpha": alpha  # Alpha版
        }

    def download_minecraft(self, game_path: str | Path, version_id: str, download_file: bool = True,  # 下载原版
                           download_max_thread: int = 32, save_version_name: str | None = None,
                           get_versions: dict | None = None) -> bool:
        game_path = Path(game_path)
        save_version_name = save_version_name if save_version_name else version_id
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        get_versions = get_versions if get_versions else self.get_minecraft_versions()
        if not get_versions: 
            return False
        get_version_info = {}
        not_find = True
        for version_info in get_versions["All"]:
            if version_info["id"] == version_id:
                get_version_info = version_info
                try:
                    response = requests.get(f'{self.files_checker.api_url.Meta}/v1/packages/{version_info["sha1"]}/{version_id}.json')
                    response.raise_for_status()
                    save_json_path.parent.mkdir(parents=True, exist_ok=True)
                    save_json_path.write_text(response.text, encoding="utf-8")
                    not_find = False
                    break
                except requests.exceptions.RequestException:
                    return False
        if not_find: 
            return False
        (game_path / "versions" / "Manifest.json").write_text(
            json.dumps(get_versions, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file(): 
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update({
            version_id: {"Type": "Vanilla", "Version": version_id, "VanillaType": get_version_info["type"]}
        })
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        if download_file:
            self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        return True

    def get_fabric_versions(self, game_version_id: str) -> dict[str, list[dict[str, str | bool]]] | None:  # 获取Fabric版本
        try:
            get_versions = requests.get(f"{self.files_checker.api_url.FabricMeta}/v1/versions/loader/{game_version_id}").json()
            if len(get_versions) <= 0: 
                return None
        except requests.exceptions.RequestException:
            return None
        all_versions = []
        stable_versions = []
        not_stable_versions = []
        for version_info in get_versions:
            the_info = {
                "GameVersion": version_info["mappings"]["gameVersion"],
                "LoaderVersion": version_info["loader"]["version"],
                "Stable": version_info["loader"]["stable"]
            }
            all_versions.append(the_info)
            if version_info["loader"]["stable"]:
                stable_versions.append(the_info)
            else:
                not_stable_versions.append(the_info)
        return {"All": all_versions, "Stable": stable_versions, "NotStable": not_stable_versions}

    def download_fabric(self, game_path: str | Path, game_version_id: str, fabric_version: str,  # 下载Fabric
                        download_vanilla: bool = True, download_max_thread: int = 32,
                        save_version_name: str | None = None) -> bool:
        game_path = Path(game_path)
        save_version_name = save_version_name if save_version_name else f"fabric-loader-{fabric_version}-{game_version_id}"
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        try:
            response = requests.get(f'{self.files_checker.api_url.FabricMeta}/v2/versions/loader/{game_version_id}/{fabric_version}/profile/json')
            response.raise_for_status()
            version_json = response.json()
            save_json_path.parent.mkdir(parents=True, exist_ok=True)
            save_json_path.write_text(response.text, encoding="utf-8")
        except requests.exceptions.RequestException:
            return False
        get_versions = self.get_minecraft_versions()
        if not get_versions: 
            return False
        not_find = True
        for version_info in get_versions["All"]:
            if version_info["id"] == game_version_id: 
                not_find = False
        if not_find: 
            return False
        versions_info = {}
        versions_info_path = game_path / "versions" / "VersionsInfo.json"
        if versions_info_path.is_file(): 
            versions_info = json.loads(versions_info_path.read_text("utf-8"))
        versions_info.update({
            version_json: {"Type": "Fabric", "Version": fabric_version, "VanillaType": version_info["type"], "VanillaVersion": game_version_id}
        })
        versions_info_path.write_text(json.dumps(versions_info, ensure_ascii=False, indent=4), encoding="utf-8")
        if download_vanilla:
            self.download_minecraft(game_path, game_version_id, False, download_max_thread, None, get_versions)
        self.files_checker.check_files(game_path, save_version_name, download_max_thread)
        return True

    def get_forge_versions(self, mc_version: str) -> dict[str, list[str]] | None:  # 获取Forge版本列表
        try:
            if mc_version in ["1.12.2", "1.11.2", "1.10.2", "1.9.4", "1.8.9", "1.7.10"]:
                url = f"{self.files_checker.api_url.Forge}/net/minecraftforge/forge/maven-metadata.xml"
            else:
                url = f"{self.files_checker.api_url.Forge}/net/minecraftforge/forge/{mc_version}/maven-metadata.xml"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            versions = []
            for version_elem in root.findall(".//version"):
                version = version_elem.text
                if mc_version in version: 
                    versions.append(version)
            recommended = []
            latest = []
            stable = []
            for v in versions:
                if "-recommended" in v or v.endswith(".0"): 
                    recommended.append(v)
                else: 
                    stable.append(v)
            if versions: 
                latest = [versions[-1]]
            return {"All": versions, "Latest": latest, "Recommended": recommended, "Stable": stable}
        except Exception as e:
            self.output_log(f"获取 Forge 版本列表失败: {e}")
            return None

    def download_forge(self, game_path: str | Path, mc_version: str, forge_version: str,  # 下载Forge
                       download_vanilla: bool = True, download_max_thread: int = 32,
                       save_version_name: str | None = None) -> bool:
        game_path = Path(game_path)
        if "-" not in forge_version:
            full_version = f"{mc_version}-{forge_version}"
        else:
            full_version = forge_version
            mc_version = full_version.split("-")[0]
        save_version_name = save_version_name or f"{mc_version}-forge-{full_version.split('-')[1]}"
        version_dir = game_path / "versions" / save_version_name
        try:
            installer_url = f"{self.files_checker.api_url.Forge}/net/minecraftforge/forge/{full_version}/forge-{full_version}-installer.jar"
            installer_path = version_dir / "installer.jar"
            self.output_log(f"下载 Forge Installer: {full_version}")
            response = requests.get(installer_url, timeout=60)
            response.raise_for_status()
            version_dir.mkdir(parents=True, exist_ok=True)
            installer_path.write_bytes(response.content)
            import zipfile
            with zipfile.ZipFile(installer_path) as zf:
                if "version.json" in zf.namelist():
                    version_json = json.loads(zf.read("version.json"))
                elif f"forge-{full_version}.json" in zf.namelist():
                    version_json = json.loads(zf.read(f"forge-{full_version}.json"))
                else:
                    return self._install_forge_legacy(game_path, mc_version, full_version, save_version_name)
                install_profile = None
                if "install_profile.json" in zf.namelist():
                    install_profile = json.loads(zf.read("install_profile.json"))
            version_json["id"] = save_version_name
            version_json_path = version_dir / f"{save_version_name}.json"
            version_json_path.write_text(json.dumps(version_json, indent=2), encoding="utf-8")
            if download_vanilla:
                self.download_minecraft(game_path, mc_version, False, download_max_thread, None, None)
            self.files_checker.check_files(game_path, save_version_name, download_max_thread)
            self.output_log(f"Forge {full_version} 安装成功")
            return True
        except Exception as e:
            self.output_log(f"安装 Forge 失败: {e}")
            return False

    def _install_forge_legacy(self, game_path: Path, mc_version: str, full_version: str, save_version_name: str) -> bool:  # 旧版Forge安装
        try:
            base_url = f"{self.files_checker.api_url.Forge}/net/minecraftforge/forge/{full_version}"
            json_url = f"{base_url}/forge-{full_version}.json"
            response = requests.get(json_url, timeout=30)
            response.raise_for_status()
            version_dir = game_path / "versions" / save_version_name
            version_dir.mkdir(parents=True, exist_ok=True)
            version_json = response.json()
            version_json["id"] = save_version_name
            version_json_path = version_dir / f"{save_version_name}.json"
            version_json_path.write_text(json.dumps(version_json, indent=2), encoding="utf-8")
            universal_url = f"{base_url}/forge-{full_version}-universal.jar"
            response = requests.get(universal_url, timeout=60)
            response.raise_for_status()
            jar_path = version_dir / f"{save_version_name}.jar"
            jar_path.write_bytes(response.content)
            return True
        except Exception as e:
            self.output_log(f"安装旧版 Forge 失败: {e}")
            return False

    def get_neoforge_versions(self) -> dict | None:  # 获取NeoForged版本列表,使用正则分类
        try:
            url = f"{self.files_checker.api_url.NeoForged}/net/neoforged/neoforge/maven-metadata.xml"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            all_versions = []
            for version_elem in root.findall(".//version"):
                v = version_elem.text
                if self.VERSION_REGEX.match(v): 
                    all_versions.append(v)
            legacy = []
            new_scheme = []
            for v in all_versions:
                m = re.match(r'^(\d+)\.', v)
                if m:
                    year = int(m.group(1))
                    if year >= 26: 
                        new_scheme.append(v)
                    else: 
                        legacy.append(v)
            by_mc = {}
            for v in all_versions:
                mc_ver = C_Libs.parse_neoforge_version(v)
                if mc_ver: 
                    by_mc.setdefault(mc_ver, []).append(v)
            snapshots = [v for v in all_versions if re.search(r'-(?:beta|snapshot|rc|alpha)', v, re.I)]
            stable = [v for v in all_versions if not re.search(r'-(?:beta|snapshot|rc|alpha)', v, re.I)]
            return {
                "All": all_versions,
                "ByMCVersion": by_mc,
                "Legacy": legacy,
                "NewScheme": new_scheme,  # 26.x新命名方案
                "Latest": [all_versions[-1]] if all_versions else [],
                "LatestStable": [stable[-1]] if stable else [],
                "LatestSnapshot": [snapshots[-1]] if snapshots else [],
            }
        except Exception as e:
            self.output_log(f"获取 NeoForged 版本列表失败: {e}")
            return None

    def get_neoforge_versions_for_mc(self, mc_version: str) -> list[str]:
        all_versions = self.get_neoforge_versions()
        if not all_versions: 
            return []
        if mc_version in all_versions["ByMCVersion"]:
            return all_versions["ByMCVersion"][mc_version]
        return [
            v for v in all_versions["All"]
            if C_Libs.parse_neoforge_version(v) == mc_version
        ]

    def download_neoforge(self, game_path: str | Path, neoforge_version: str,  # 下载NeoForged,支持26.x新格式
                          download_vanilla: bool = True, download_max_thread: int = 32,
                          save_version_name: str | None = None) -> bool:
        game_path = Path(game_path)
        version_info = C_Libs.get_neoforge_version_info(neoforge_version)
        mc_version = version_info["mc_version"]
        if not mc_version:
            self.output_log(f"无法解析 NeoForged 版本: {neoforge_version}")
            return False
        is_new_scheme = version_info["is_new_scheme"]
        save_version_name = save_version_name or f"neoforge-{neoforge_version}"
        version_dir = game_path / "versions" / save_version_name
        try:
            base_url = f"{self.files_checker.api_url.NeoForged}/net/neoforged/neoforge/{neoforge_version}"
            installer_url = f"{base_url}/neoforge-{neoforge_version}-installer.jar"
            installer_path = version_dir / "installer.jar"
            if is_new_scheme:
                self.output_log(f"下载 NeoForged {neoforge_version} (Minecraft {mc_version}, 新命名方案)")
                self.output_log("注意:此版本需要 Java 25")
            else:
                self.output_log(f"下载 NeoForged {neoforge_version} (Minecraft {mc_version})")
            response = requests.get(installer_url, timeout=60)
            response.raise_for_status()
            version_dir.mkdir(parents=True, exist_ok=True)
            installer_path.write_bytes(response.content)
            import zipfile
            with zipfile.ZipFile(installer_path) as zf:
                if "install_profile.json" not in zf.namelist():
                    raise ValueError("Installer 中未找到 install_profile.json")
                install_profile = json.loads(zf.read("install_profile.json"))
                version_json = {}
                if "version.json" in zf.namelist():
                    version_json = json.loads(zf.read("version.json"))
            data = install_profile.get("data", {})
            processed_data = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    client_val = value.get("client", "")
                    if client_val.startswith("[") and client_val.endswith("]"):
                        coord = client_val[1:-1]
                        processed_data[key] = self._resolve_maven_path(game_path, coord)
                    elif client_val.startswith("/"):
                        processed_data[key] = str(version_dir / client_val.lstrip("/"))
                    else:
                        processed_data[key] = client_val
                else:
                    processed_data[key] = value
            libraries = install_profile.get("libraries", [])
            processors = install_profile.get("processors", [])
            for processor in processors:  # 下载processor依赖
                jar_coord = processor.get("jar", "")
                classpath = processor.get("classpath", [])
                if jar_coord: 
                    self._download_maven_artifact(game_path, jar_coord)
                for dep in classpath: 
                    self._download_maven_artifact(game_path, dep)
            main_class = version_json.get("mainClass", "net.minecraft.launchwrapper.Launch")
            if "launcherMeta" in version_json:
                launcher_meta = version_json["launcherMeta"]
                if "mainClass" in launcher_meta:
                    mc_info = launcher_meta["mainClass"]
                    main_class = mc_info.get("client", main_class) if isinstance(mc_info, dict) else mc_info
            final_version = {
                "id": save_version_name,
                "inheritsFrom": mc_version,
                "type": "release",
                "mainClass": main_class,
                "arguments": version_json.get("arguments", {}),
                "libraries": libraries + version_json.get("libraries", []),
                "jar": version_json.get("jar", mc_version)
            }
            if is_new_scheme:  # 26.x特殊标记
                final_version["neoForgeFeatures"] = {"newVersionScheme": True, "requiresJava25": True}
            version_json_path = version_dir / f"{save_version_name}.json"
            version_json_path.write_text(json.dumps(final_version, indent=2), encoding="utf-8")
            if download_vanilla:
                self.output_log(f"下载原版 Minecraft {mc_version}")
                self.download_minecraft(game_path, mc_version, False, download_max_thread, None, None)
            self.files_checker.check_files(game_path, save_version_name, download_max_thread)
            self.output_log(f"NeoForged {neoforge_version} 安装成功")
            return True
        except Exception as e:
            self.output_log(f"安装 NeoForged 失败: {e}")
            return False

    def _resolve_maven_path(self, game_path: Path, coord: str) -> str:  # 解析Maven坐标为本地路径
        if "@" in coord:
            coord, ext = coord.rsplit("@", 1)
        else:
            ext = "jar"
        parts = coord.split(":")
        if len(parts) == 3:
            group, artifact, version = parts
            classifier = None
        elif len(parts) == 4:
            group, artifact, version, classifier = parts
        else:
            return ""
        group_path = group.replace(".", "/")
        artifact_path = f"{group_path}/{artifact}/{version}/{artifact}-{version}"
        if classifier: 
            artifact_path += f"-{classifier}"
        artifact_path += f".{ext}"
        return str(game_path / "libraries" / artifact_path)

    def _download_maven_artifact(self, game_path: Path, coord: str) -> bool:  # 下载Maven构件
        try:
            local_path = self._resolve_maven_path(game_path, coord)
            if Path(local_path).exists(): 
                return True
            if "@" in coord:
                coord, ext = coord.rsplit("@", 1)
            else:
                ext = "jar"
            parts = coord.split(":")
            if len(parts) < 3: 
                return False
            group, artifact, version = parts[0], parts[1], parts[2]
            classifier = parts[3] if len(parts) > 3 else None
            group_url = group.replace(".", "/")
            url = f"{self.files_checker.api_url.NeoForged}/{group_url}/{artifact}/{version}/{artifact}-{version}"
            if classifier: 
                url += f"-{classifier}"
            url += f".{ext}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            Path(local_path).write_bytes(response.content)
            return True
        except Exception as e:
            self.output_log(f"下载 Maven 构件失败 {coord}: {e}")
            return False

    def get_quilt_versions(self, mc_version: str) -> dict[str, list[dict[str, str | bool]]] | None:  # 获取Quilt版本列表
        try:
            url = f"{self.files_checker.api_url.QuiltMeta}/v3/versions/loader/{mc_version}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            versions = []
            for item in data:
                loader_info = item.get("loader", {})
                version_info = {
                    "GameVersion": mc_version,
                    "LoaderVersion": loader_info.get("version", ""),
                    "Stable": loader_info.get("stable", False),
                    "Maven": loader_info.get("maven", "")
                }
                versions.append(version_info)
            return {"All": versions, "Stable": [v for v in versions if v["Stable"]], "NotStable": [v for v in versions if not v["Stable"]]}
        except Exception as e:
            self.output_log(f"获取 Quilt 版本列表失败: {e}")
            return None

    def download_quilt(self, game_path: str | Path, mc_version: str, quilt_version: str,  # 下载Quilt
                       download_vanilla: bool = True, download_max_thread: int = 32,
                       save_version_name: str | None = None) -> bool:
        game_path = Path(game_path)
        save_version_name = save_version_name or f"quilt-loader-{quilt_version}-{mc_version}"
        save_json_path = game_path / "versions" / save_version_name / f"{save_version_name}.json"
        try:
            url = f"{self.files_checker.api_url.QuiltMeta}/v3/versions/loader/{mc_version}/{quilt_version}/profile/json"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            version_json = response.json()
            save_json_path.parent.mkdir(parents=True, exist_ok=True)
            save_json_path.write_text(json.dumps(version_json, indent=2), encoding="utf-8")
            if download_vanilla:
                self.download_minecraft(game_path, mc_version, False, download_max_thread, None, None)
            self.files_checker.check_files(game_path, save_version_name, download_max_thread)
            self.output_log(f"Quilt {quilt_version} 安装成功")
            return True
        except Exception as e:
            self.output_log(f"安装 Quilt 失败: {e}")
            return False