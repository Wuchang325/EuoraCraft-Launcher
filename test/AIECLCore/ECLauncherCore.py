from . import C_Libs, C_Downloader, C_FilesChecker
from typing import Callable, List, Dict, Union, Optional, Any
from shutil import rmtree
from pathlib import Path
import subprocess
import platform
from uuid import uuid4
import json
import re
import requests
from dataclasses import dataclass, field
from ..logger import get_logger

logger = get_logger("core")


@dataclass
class LaunchSettings:
    """游戏启动配置参数类"""
    java_path: Path
    game_path: Path
    version_name: str
    max_use_ram: int
    player_name: str
    user_type: str = "Legacy"
    auth_uuid: str = ""
    access_token: str = "None"
    first_set_lang: str = "zh_CN"
    set_lang: str = ""
    launcher_name: str = "ECL"
    launcher_version: str = "0.1145"
    default_version_type: bool = False
    custom_jvm_params: str = ""
    window_width: Union[int, str] = "${resolution_width}"
    window_height: Union[int, str] = "${resolution_height}"
    completes_file: bool = True
    download_max_thread: int = 64
    output_jvm_params: bool = False
    write_run_script: bool = False
    run_script_path: Path = Path(".")
    extra_jvm_args: List[str] = field(default_factory=list)
    extra_game_args: List[str] = field(default_factory=list)
    extra_jvm_args_before_default: bool = False
    extra_game_args_before_default: bool = False


class ECLauncherCore:
    """启动器核心类，负责游戏启动逻辑、参数拼接和进程管理"""
    
    def __init__(self):
        self.output_launcher_log = self.__default_output_log
        self.output_minecraft_instance = self.__default_output_log
        self.output_jvm_params = self.__default_output_log

        self.api_url = C_Libs.ApiUrl()
        self.downloader = C_Downloader.Downloader()
        self.files_checker = C_FilesChecker.FilesChecker(self.api_url, self.downloader)

        self.system_type = platform.system()
        self.instances: List[Dict[str, Union[str, bool, subprocess.Popen]]] = []
        
        self.default_uuid = "12340000000000123000000020260217"

    @staticmethod
    def __default_output_log(log):
        logger.info(str(log))

    def set_api_url(self, api_url_dict: dict):
        self.api_url.update_from_dict(api_url_dict)

    def set_output_launcher_log(self, output_function: Callable[[str], None]) -> None:
        self.output_launcher_log = output_function

    def set_output_minecraft_instance(self, output_function: Callable[[dict], None]) -> None:
        self.output_minecraft_instance = output_function

    def set_output_jvm_params(self, output_function: Callable[[str], None]) -> None:
        self.output_jvm_params = output_function

    def _validate_params(self, settings: LaunchSettings):
        """验证启动参数"""
        if re.search(r"[^a-zA-Z0-9\-_+.]", settings.player_name):
            raise ValueError("玩家名称包含非法字符")

        if settings.auth_uuid and not C_Libs.is_uuid3(settings.auth_uuid):
            raise ValueError("错误的 UUID, 必须是 UUID3")

        if not settings.java_path.is_file():
            raise FileNotFoundError(f"未找到 Java 可执行文件: {settings.java_path}")

        version_json_path = settings.game_path / "versions" / settings.version_name / f"{settings.version_name}.json"
        if not version_json_path.is_file():
            raise FileNotFoundError(f"未找到游戏版本配置文件: {version_json_path}")

    def _get_base_jvm_args(self, settings: LaunchSettings) -> List[str]:
        """获取基础 JVM 参数"""
        args = []
        if self.system_type == "Windows":
            args.append("-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump")
            if platform.release() == "10":
                args.append("-Dos.name=Windows 10")
                args.append("-Dos.version=10.0")
        elif self.system_type == "Darwin":
            args.append("-XstartOnFirstThread")

        max_ram = max(256, settings.max_use_ram)
        args.extend([
            "-Xms256M",
            f"-Xmx{max_ram}M",
            "-Dstderr.encoding=UTF-8",
            "-Dstdout.encoding=UTF-8",
            "-Dfile.encoding=COMPAT",
            "-XX:+UseG1GC",
            "-XX:-UseAdaptiveSizePolicy",
            "-XX:-OmitStackTraceInFastThrow",
            "-Dfml.ignoreInvalidMinecraftCertificates=True",
            "-Dfml.ignorePatchDiscrepancies=True",
            "-Dlog4j2.formatMsgNoLookups=true"
        ])

        if settings.custom_jvm_params:
            args.extend([p for p in settings.custom_jvm_params.split(" ") if p])
        
        return args

    def _is_forge_client_library(self, lib: Dict) -> bool:
        """检查是否为 Forge 的 client 分类器库"""
        name = lib.get("name", "")
        if ":client" in name and ("forge" in name.lower() or "neoforge" in name.lower()):
            downloads = lib.get("downloads", {})
            if not downloads or not downloads.get("artifact", {}).get("path"):
                return True
        return False

    def _process_libraries(self, libs: List[Dict], game_path: Path, class_path_list: List[str], 
                           natives_path_list: List[Path], asm_versions: List[Path]):
        """处理依赖库"""
        for lib in libs:
            if self._is_forge_client_library(lib):
                logger.debug(f"跳过 Forge client 库（类路径）: {lib.get('name')}")
                continue
            
            path_str = C_Libs.name_to_path(lib["name"])
            if not path_str:
                continue
            lib_path = (game_path / "libraries" / path_str).absolute()
            
            if str(lib_path) in class_path_list:
                continue
            
            if re.search(r"asm-\d+(?:\.\d+)*", lib_path.stem):
                asm_versions.append(lib_path)
                continue
            
            class_path_list.append(str(lib_path))
            
            if "classifiers" in lib.get("downloads", {}):
                for classifier in lib["downloads"]["classifiers"].values():
                    n_path = game_path / "libraries" / classifier["path"]
                    if n_path not in natives_path_list:
                        natives_path_list.append(n_path)

    def _handle_natives(self, settings: LaunchSettings, natives_path_list: List[Path]) -> Path:
        """解压 Natives 库"""
        natives_path = (settings.game_path / "versions" / settings.version_name / "natives").absolute()
        if natives_path.exists():
            rmtree(natives_path)
        natives_path.mkdir(parents=True, exist_ok=True)
        
        if natives_path_list:
            self.output_launcher_log(f"正在解压 Natives 库 ({len(natives_path_list)} 个)...")
            for n_lib in natives_path_list:
                C_Libs.unzip(n_lib, natives_path)
        return natives_path

    def _handle_language(self, settings: LaunchSettings):
        """设置游戏语言"""
        options_path = settings.game_path / "versions" / settings.version_name / "options.txt"
        if settings.set_lang or not options_path.exists():
            lang = settings.set_lang if settings.set_lang else settings.first_set_lang
            content = f"lang:{lang}"
            if options_path.is_file():
                old_content = options_path.read_text("utf-8")
                content = re.sub(r"^lang:\S+$", f"lang:{lang}", old_content, flags=re.MULTILINE)
            options_path.write_text(content, "utf-8")
            self.output_launcher_log(f"已设置游戏语言: {lang}")

    def _check_rules(self, rules: List[Dict], features: Dict[str, bool] = None) -> bool:
        """检查规则是否允许"""
        if not rules:
            return True
            
        features = features or {}
        allow = False
        
        for rule in rules:
            action = rule.get("action", "allow")
            os_rule = rule.get("os", {})
            features_rule = rule.get("features", {})
            
            os_match = True
            if os_rule:
                os_name = os_rule.get("name", "")
                if os_name == "windows" and self.system_type != "Windows":
                    os_match = False
                elif os_name == "osx" and self.system_type != "Darwin":
                    os_match = False
                elif os_name == "linux" and self.system_type != "Linux":
                    os_match = False
            
            features_match = True
            if features_rule:
                for feature, expected in features_rule.items():
                    if feature == "is_demo_user":
                        features_match = False
                        break
                    elif feature == "has_custom_resolution":
                        if features.get("has_custom_resolution") != expected:
                            features_match = False
                            break
                    elif feature.startswith(("has_quick_plays", "is_quick_play")):
                        features_match = False
                        break
            
            if os_match and features_match:
                if action == "allow":
                    allow = True
                elif action == "disallow":
                    return False
        
        return allow

    def _get_inherits_from(self, version_json: Dict) -> Optional[str]:
        """从 version.json 中获取继承的原版版本号"""
        inherits = version_json.get("inheritsFrom")
        if inherits:
            return inherits
        
        patches = version_json.get("patches", [])
        for patch in patches:
            if patch.get("id") in ["game", "minecraft"]:
                patch_inherits = patch.get("inheritsFrom") or patch.get("version")
                if patch_inherits:
                    return patch_inherits
            elif patch.get("id") in ["forge", "neoforge", "fabric", "quilt"]:
                patch_inherits = patch.get("inheritsFrom")
                if patch_inherits:
                    return patch_inherits
        
        version_id = version_json.get("id", "")
        if "-forge" in version_id.lower() or "-neoforge" in version_id.lower():
            match = re.match(r"(\d+\.\d+\.\d+)-", version_id)
            if match:
                inferred = match.group(1)
                logger.warning(f"未找到明确的 inheritsFrom，从版本名称推断原版为: {inferred}")
                return inferred
        
        return None

    def _download_vanilla_jar(self, game_path: Path, version_name: str, vanilla_version: str) -> Optional[Path]:
        """自动下载原版客户端 Jar"""
        try:
            logger.info(f"正在自动下载原版 {vanilla_version} 客户端 Jar...")
            
            manifest_url = f"{self.api_url.Meta}/mc/game/version_manifest.json"
            resp = requests.get(manifest_url, timeout=10)
            resp.raise_for_status()
            manifest = resp.json()
            
            version_info = next((v for v in manifest["versions"] if v["id"] == vanilla_version), None)
            if not version_info:
                logger.error(f"在官方清单中未找到版本: {vanilla_version}")
                return None
            
            version_detail_resp = requests.get(version_info["url"], timeout=10)
            version_detail_resp.raise_for_status()
            vanilla_json = version_detail_resp.json()
            
            client_download = vanilla_json.get("downloads", {}).get("client", {})
            if not client_download or not client_download.get("url"):
                logger.error("无法获取客户端下载链接")
                return None
            
            jar_path = game_path / "versions" / version_name / f"{vanilla_version}.jar"
            jar_path.parent.mkdir(parents=True, exist_ok=True)
            
            urls = [client_download["url"]]
            success = self.downloader.download_manager([(urls, str(jar_path))], 1)
            
            if success and jar_path.exists():
                logger.info(f"成功下载原版客户端 Jar: {jar_path}")
                return jar_path
            else:
                logger.error("下载原版客户端 Jar 失败")
                return None
                
        except Exception as e:
            logger.error(f"自动下载原版客户端失败: {e}")
            return None

    def _build_final_command(self, settings: LaunchSettings, jvm_args: List[str], class_path_list: List[str], 
                             version_json: Dict, version_jar: Path, asset_index_id: str, natives_path: Path) -> List[str]:
        """构建最终启动命令列表"""
        cp_delimiter = ";" if self.system_type == "Windows" else ":"
        
        if settings.user_type == "Legacy":
            if settings.auth_uuid and len(settings.auth_uuid.replace("-", "")) == 32:
                auth_uuid = settings.auth_uuid.replace("-", "")
            else:
                try:
                    auth_uuid = C_Libs.name_to_uuid(settings.player_name).hex
                except Exception as e:
                    logger.error(f"生成 UUID 失败: {e}")
                    auth_uuid = self.default_uuid
            
            if not auth_uuid or len(auth_uuid) != 32:
                logger.warning(f"UUID 无效 (长度: {len(auth_uuid) if auth_uuid else 0}), 使用备用值")
                auth_uuid = self.default_uuid
                
            access_token = auth_uuid
            user_type = "msa"
            has_custom_resolution = (settings.window_width != "${resolution_width}" and 
                                    settings.window_height != "${resolution_height}")
        else:
            auth_uuid = settings.auth_uuid.replace("-", "") if settings.auth_uuid else ""
            if not auth_uuid or len(auth_uuid) != 32:
                auth_uuid = self.default_uuid
            access_token = settings.access_token if settings.access_token else "None"
            user_type = settings.user_type
            has_custom_resolution = (settings.window_width != "${resolution_width}" and 
                                    settings.window_height != "${resolution_height}")

        replacements = {
            "${classpath}": cp_delimiter.join(class_path_list),
            "${library_directory}": str((settings.game_path / "libraries").absolute()),
            "${assets_root}": str((settings.game_path / "assets").absolute()),
            "${assets_index_name}": asset_index_id,
            "${natives_directory}": str(natives_path),
            "${game_directory}": str((settings.game_path / "versions" / settings.version_name).absolute()),
            "${launcher_name}": settings.launcher_name,
            "${launcher_version}": settings.launcher_version,
            "${version_type}": version_json.get("type", "release") if settings.default_version_type else settings.launcher_name,
            "${auth_player_name}": settings.player_name,
            "${user_type}": user_type,
            "${auth_uuid}": auth_uuid,
            "${auth_access_token}": access_token,
            "${user_properties}": "{}",
            "${classpath_separator}": cp_delimiter,
            "${primary_jar_name}": version_jar.name,
            "${version_name}": settings.version_name,
            "${resolution_width}": str(settings.window_width),
            "${resolution_height}": str(settings.window_height),
            "${clientid}": "",
            "${auth_xuid}": "",
            "${quickPlayPath}": "",
            "${quickPlaySingleplayer}": "",
            "${quickPlayMultiplayer}": "",
            "${quickPlayRealms}": "",
        }

        def replace_all(text: str) -> str:
            if not isinstance(text, str):
                return str(text)
            for k, v in replacements.items():
                text = text.replace(k, str(v))
            return text

        final_cmd = [str(settings.java_path.absolute())]
        
        if settings.extra_jvm_args and settings.extra_jvm_args_before_default:
            for arg in settings.extra_jvm_args:
                replaced = replace_all(arg)
                final_cmd.append(replaced)
                logger.debug(f"[手动JVM参数] 添加(前置): {replaced}")

        for arg in jvm_args:
            if isinstance(arg, str):
                replaced = replace_all(arg)
                final_cmd.append(replaced)
            elif isinstance(arg, dict):
                rules = arg.get("rules", [])
                features = {"has_custom_resolution": has_custom_resolution}
                if self._check_rules(rules, features):
                    value = arg.get("value", [])
                    if isinstance(value, list):
                        for v in value:
                            replaced = replace_all(v)
                            final_cmd.append(replaced)
                    else:
                        replaced = replace_all(value)
                        final_cmd.append(replaced)

        if settings.extra_jvm_args and not settings.extra_jvm_args_before_default:
            for arg in settings.extra_jvm_args:
                replaced = replace_all(arg)
                final_cmd.append(replaced)
                logger.debug(f"[手动JVM参数] 添加(后置): {replaced}")

        cmd_str = " ".join(final_cmd)
        
        # 确保类路径存在
        if "-cp" not in cmd_str and "-classpath" not in cmd_str and class_path_list:
            final_cmd.extend(["-cp", cp_delimiter.join(class_path_list)])
        
        # 确保 natives 路径存在
        if "-Djava.library.path" not in cmd_str:
            final_cmd.append(f"-Djava.library.path={str(natives_path)}")

        main_class = version_json["mainClass"]
        if main_class not in final_cmd:
            final_cmd.append(main_class)
        
        game_args = []
        
        if settings.extra_game_args and settings.extra_game_args_before_default:
            for arg in settings.extra_game_args:
                replaced = replace_all(arg)
                if replaced and replaced not in game_args:
                    game_args.append(replaced)
                    logger.debug(f"[手动Game参数] 添加(前置): {replaced}")

        def is_demo_related(arg_item) -> bool:
            if isinstance(arg_item, str):
                return arg_item == "--demo" or "--demo" in arg_item
            elif isinstance(arg_item, dict):
                value = arg_item.get("value", "")
                if value == "--demo" or (isinstance(value, list) and "--demo" in value):
                    return True
                rules = arg_item.get("rules", [])
                for rule in rules:
                    if rule.get("features", {}).get("is_demo_user", False):
                        return True
            return False

        if "arguments" in version_json and "game" in version_json["arguments"]:
            for arg in version_json["arguments"]["game"]:
                if is_demo_related(arg):
                    continue
                
                if isinstance(arg, str):
                    replaced = replace_all(arg)
                    if replaced and replaced != "--demo" and replaced not in game_args:
                        game_args.append(replaced)
                elif isinstance(arg, dict):
                    rules = arg.get("rules", [])
                    features = {"has_custom_resolution": has_custom_resolution}
                    if self._check_rules(rules, features):
                        value = arg.get("value", [])
                        if isinstance(value, list):
                            for v in value:
                                if v != "--demo" and v not in game_args:
                                    game_args.append(replace_all(v))
                        else:
                            if value != "--demo" and value not in game_args:
                                game_args.append(replace_all(value))
        elif "minecraftArguments" in version_json:
            old_args = replace_all(version_json["minecraftArguments"]).split(" ")
            for a in old_args:
                if a and a != "--demo" and a not in game_args:
                    game_args.append(a)

        if settings.extra_game_args and not settings.extra_game_args_before_default:
            for arg in settings.extra_game_args:
                replaced = replace_all(arg)
                if replaced and replaced not in game_args:
                    game_args.append(replaced)
                    logger.debug(f"[手动Game参数] 添加(后置): {replaced}")

        def set_or_replace_arg(args_list: List[str], key: str, value: str):
            existing_idx = -1
            for i, arg in enumerate(args_list):
                if arg == key:
                    existing_idx = i
                    break
            
            if existing_idx >= 0:
                if existing_idx + 1 < len(args_list):
                    args_list[existing_idx + 1] = value
                else:
                    args_list.append(value)
            else:
                args_list.extend([key, value])

        set_or_replace_arg(game_args, "--username", settings.player_name)
        set_or_replace_arg(game_args, "--version", settings.version_name)
        set_or_replace_arg(game_args, "--gameDir", str((settings.game_path / "versions" / settings.version_name).absolute()))
        set_or_replace_arg(game_args, "--assetsDir", str((settings.game_path / "assets").absolute()))
        set_or_replace_arg(game_args, "--assetIndex", asset_index_id)
        set_or_replace_arg(game_args, "--uuid", auth_uuid)
        set_or_replace_arg(game_args, "--accessToken", access_token)
        set_or_replace_arg(game_args, "--userType", user_type)

        for arg in game_args:
            if arg:
                if arg not in final_cmd:
                    final_cmd.append(arg)
        return final_cmd

    def launch_minecraft(self, java_path: str | Path, game_path: str | Path, version_name: str, max_use_ram: int, player_name: str,
                         user_type: str = "Legacy", auth_uuid: str = "", access_token: str = "None",
                         first_set_lang: str = "zh_CN", set_lang: str = "", launcher_name: str = "ECL",
                         launcher_version: str = "0.1145", default_version_type: bool = False,
                         custom_jvm_params: str = "", window_width: int | str = "${resolution_width}",
                         window_height: int | str = "${resolution_height}",
                         completes_file: bool = True, download_max_thread: int = 64,
                         output_jvm_params: bool = False, write_run_script: bool = False, run_script_path: str | Path = ".",
                         extra_jvm_args: List[str] = None,
                         extra_game_args: List[str] = None,
                         extra_jvm_args_before_default: bool = False,
                         extra_game_args_before_default: bool = False):
        """启动游戏主入口"""
        try:
            settings = LaunchSettings(
                java_path=Path(java_path).absolute(),
                game_path=Path(game_path).absolute(),
                version_name=version_name,
                max_use_ram=max_use_ram,
                player_name=player_name,
                user_type=user_type,
                auth_uuid=auth_uuid,
                access_token=access_token,
                first_set_lang=first_set_lang,
                set_lang=set_lang,
                launcher_name=launcher_name,
                launcher_version=launcher_version,
                default_version_type=default_version_type,
                custom_jvm_params=custom_jvm_params,
                window_width=window_width,
                window_height=window_height,
                completes_file=completes_file,
                download_max_thread=download_max_thread,
                output_jvm_params=output_jvm_params,
                write_run_script=write_run_script,
                run_script_path=Path(run_script_path),
                extra_jvm_args=extra_jvm_args or [],
                extra_game_args=extra_game_args or [],
                extra_jvm_args_before_default=extra_jvm_args_before_default,
                extra_game_args_before_default=extra_game_args_before_default
            )
            self._validate_params(settings)
            
            if settings.completes_file:
                self.output_launcher_log("正在检查文件完整性...")
                self.files_checker.check_files(settings.game_path, settings.version_name, settings.download_max_thread)

            jvm_args = self._get_base_jvm_args(settings)
            
            version_json_path = settings.game_path / "versions" / settings.version_name / f"{settings.version_name}.json"
            version_json = json.loads(version_json_path.read_text("utf-8"))

            if "arguments" in version_json and "jvm" in version_json["arguments"]:
                for arg in version_json["arguments"]["jvm"]:
                    if isinstance(arg, str):
                        jvm_args.append(arg)
                    elif isinstance(arg, dict):
                        jvm_args.append(arg)
            else:
                jvm_args.extend([
                    "-Djava.library.path=${natives_directory}",
                    "-cp",
                    "${classpath}"
                ])

            # 获取继承信息
            inherits_from = self._get_inherits_from(version_json)
            logger.debug(f"检测到继承版本: {inherits_from}")
            original_jar = None
            client_jar_candidates = []
            version_dir = settings.game_path / "versions" / settings.version_name
            
            # 判断是否为独立模式
            is_isolated = (version_json.get("_merged") == True or 
                          version_json.get("inheritsFrom") is None)

            if inherits_from:
                if is_isolated:
                    # 使用 {version_name}.jar
                    client_jar_candidates.append(version_dir / f"{version_name}.jar")
                    logger.debug(f"独立模式：优先查找 {version_name}.jar")
                
                # 备用查找路径
                client_jar_candidates.append(version_dir / f"{inherits_from}.jar")
                client_jar_candidates.append(version_dir / "client.jar")
                client_jar_candidates.append(settings.game_path / "versions" / inherits_from / f"{inherits_from}.jar")
                
                # 查找继承版本数据
                game_data = C_Libs.find_version(version_json, settings.game_path, current_version_name=settings.version_name)
                if game_data:
                    _, version_path = game_data
                    if version_path.name != inherits_from:
                        client_jar_candidates.append(version_path / f"{inherits_from}.jar")
                    client_jar_candidates.append(version_path / f"{version_path.name}.jar")

            # 找到第一个存在的原版 Jar
            logger.debug(f"查找原版客户端 Jar...")
            for candidate in client_jar_candidates:
                logger.debug(f"检查: {candidate} -> {'存在' if candidate.exists() else '不存在'}")
                if candidate.exists():
                    original_jar = candidate
                    logger.info(f"找到原版客户端 Jar: {original_jar.name}")
                    break

            main_class = version_json.get("mainClass", "").lower()
            is_forge = "forge" in main_class or "neoforge" in main_class
            
            if is_forge and (not original_jar or not original_jar.exists()):
                if is_isolated:
                    error_msg = (
                        f"独立模式下缺少原版客户端 Jar。请确保以下文件之一存在：\n"
                        f"  - {version_dir / version_name}.jar\n"
                        f"  - {version_dir / inherits_from}.jar\n"
                        f"独立模式下，安装器应将原版客户端 Jar 重命名为 {version_name}.jar 并放入版本目录。"
                    )
                    logger.error(error_msg)
                    raise FileNotFoundError(error_msg)
                else:
                    logger.warning(f"共享模式下缺少原版客户端 Jar，尝试自动下载 {inherits_from}...")
                    original_jar = self._download_vanilla_jar(settings.game_path, settings.version_name, inherits_from)
                    
                    if not original_jar or not original_jar.exists():
                        raise FileNotFoundError(f"无法下载原版客户端 Jar (版本: {inherits_from})")

            # 处理依赖库
            class_path_list, natives_path_list, asm_versions = [], [], []
            self._process_libraries(version_json.get("libraries", []), settings.game_path, class_path_list, natives_path_list, asm_versions)

            version_jar = settings.game_path / "versions" / settings.version_name / f"{settings.version_name}.jar"
            asset_index_id = version_json.get("assetIndex", {}).get("id", "")

            # 继承版本处理（
            if inherits_from:
                game_data = C_Libs.find_version(version_json, settings.game_path, current_version_name=settings.version_name)
                if game_data:
                    game_json, version_path = game_data

                    if "arguments" in game_json and "jvm" in game_json["arguments"]:
                        for arg in game_json["arguments"]["jvm"]:
                            if isinstance(arg, str):
                                jvm_args.append(arg)
                            elif isinstance(arg, dict):
                                jvm_args.append(arg)
                    
                    # 合并 Game 参数
                    if "arguments" in game_json and "game" in game_json["arguments"]:
                        if "arguments" not in version_json:
                            version_json["arguments"] = {}
                        if "game" not in version_json["arguments"]:
                            version_json["arguments"]["game"] = []
                        
                        existing_game_args = version_json["arguments"]["game"]
                        for arg in game_json["arguments"]["game"]:
                            if arg not in existing_game_args:
                                existing_game_args.append(arg)
                    
                    # 处理继承版本的库
                    self._process_libraries(game_json.get("libraries", []), settings.game_path, class_path_list, natives_path_list, asm_versions)
                    
                    if not asset_index_id:
                        asset_index_id = game_json.get("assetIndex", {}).get("id", "")

            if not asset_index_id:
                raise RuntimeError("缺少资源索引 ID")

            if original_jar and original_jar.exists():
                if is_forge:
                    logger.info(f"Forge 模式：原版 Jar 不加入类路径，仅通过 -Dfml.gameJarPath 指定")
                else:
                    original_jar_str = str(original_jar.absolute())
                    if original_jar_str not in class_path_list:
                        class_path_list.insert(0, original_jar_str)
                        logger.info(f"已将原版 Jar 加入类路径首位: {original_jar.name}")

            # 添加 ASM 库
            if asm_versions:
                def parse_version(path):
                    version_str = path.stem.replace("asm-", "")
                    try:
                        return tuple(int(x) for x in version_str.split('.'))
                    except ValueError:
                        return (0,)
                
                latest_asm = max(asm_versions, key=parse_version)
                class_path_list.append(str(latest_asm.absolute()))

            # 添加当前版本 Jar
            if version_jar.exists():
                class_path_list.append(str(version_jar.absolute()))
            else:
                logger.debug(f"当前版本 JAR 不存在，跳过类路径添加: {version_jar}")

            if is_forge:
                if original_jar and original_jar.exists():
                    game_jar_path = str(original_jar.absolute())
                    if not any("fml.gameJarPath" in str(arg) for arg in jvm_args):
                        jvm_args.append(f"-Dfml.gameJarPath={game_jar_path}")
                        logger.info(f"Forge 模式：设置 gameJarPath 指向原版 Jar: {original_jar.name}")
                else:
                    raise RuntimeError("Forge 启动失败：缺少原版客户端 Jar")

            elif "fabric" in main_class or "quilt" in main_class:
                # Fabric/Quilt 处理
                if not version_jar.exists() and game_data:
                    _, version_path = game_data
                    fallback_jar = version_path / f"{version_path.name}.jar"
                    if fallback_jar.exists():
                        version_jar = fallback_jar
                
                if not any("fabric.gameJarPath" in str(arg) for arg in jvm_args):
                    jvm_args.append(f"-Dfabric.gameJarPath={version_jar}")
                
            natives_path = self._handle_natives(settings, natives_path_list)
            self._handle_language(settings)

            final_cmd_list = self._build_final_command(settings, jvm_args, class_path_list, version_json, version_jar, asset_index_id, natives_path)
            
            if settings.write_run_script:
                suffix = ".bat" if self.system_type == "Windows" else (".command" if self.system_type == "Darwin" else ".sh")
                script_file = settings.run_script_path / f"run{suffix}"
                script_content = " ".join([f'"{a}"' if " " in a else a for a in final_cmd_list])
                script_file.write_text(script_content, "utf-8")
                self.output_launcher_log(f"启动脚本已生成: {script_file}")

            if settings.output_jvm_params:
                self.output_jvm_params(" ".join([f'"{a}"' if " " in a else a for a in final_cmd_list]))
            else:
                self.output_launcher_log("正在启动游戏进程...")
                instance_info = {
                    "Name": settings.version_name,
                    "ID": uuid4().hex,
                    "Type": "MinecraftClient",
                    "StdIn": False,
                    "Instance": subprocess.Popen(final_cmd_list, start_new_session=True, cwd=str((settings.game_path / "versions" / settings.version_name).absolute()))
                }
                self.instances.append(instance_info)
                self.output_minecraft_instance(instance_info)

        except Exception as e:
            self.output_launcher_log(f"启动失败: {str(e)}")
            raise
        
    def install_neoforge(self, minecraft_version: str, neoforge_version: str, 
                        game_path: Path, save_version_name: str = None) -> bool:
        """
        安装 NeoForge 到指定游戏目录
        
        Args:
            minecraft_version: Minecraft 版本号，如 "1.21.1"
            neoforge_version: NeoForge 版本号，如 "21.1.1"
            game_path: 游戏根目录 (.minecraft 目录)
            save_version_name: 自定义版本名称，None 则使用默认格式 "{mc_version}-neoforge-{neoforge_version}"
        
        Returns:
            是否安装成功
        """
        try:
            default_name = f"{minecraft_version}-neoforge-{neoforge_version}"
            version_name = save_version_name if save_version_name else default_name
            
            version_dir = game_path / "versions" / version_name
            version_dir.mkdir(parents=True, exist_ok=True)

            base_url = self.api_url.NeoForged.rstrip('/') + "/net/neoforged/neoforge"
            neoforge_path = f"{minecraft_version}-{neoforge_version}"
            universal_jar_name = f"neoforge-{neoforge_path}-universal.jar"
            universal_url = f"{base_url}/{neoforge_path}/{universal_jar_name}"
            universal_path = version_dir / f"{version_name}.jar"
            if not universal_path.exists():
                self.output_launcher_log(f"正在下载 NeoForge Universal JAR: {version_name}")
                success = self.downloader.download_manager([([universal_url], str(universal_path))], 1)
                if not success:
                    raise Exception("下载 NeoForge Universal JAR 失败")
            else:
                self.output_launcher_log(f"NeoForge Universal JAR 已存在: {universal_path}")

            client_json_name = f"neoforge-{neoforge_path}-client.json"
            json_url = f"{base_url}/{neoforge_path}/{client_json_name}"
            json_path = version_dir / f"{version_name}.json"
            if not json_path.exists():
                self.output_launcher_log(f"正在下载 NeoForge 客户端 JSON: {version_name}.json")
                success = self.downloader.download_manager([([json_url], str(json_path))], 1)
                if not success:
                    raise Exception("下载 NeoForge 客户端 JSON 失败")
                
                # 修改 JSON 中的 id 为自定义名称
                try:
                    json_content = json.loads(json_path.read_text(encoding="utf-8"))
                    json_content["id"] = version_name
                    json_path.write_text(json.dumps(json_content, indent=2), encoding="utf-8")
                except Exception as e:
                    logger.warning(f"修改版本名称失败: {e}")
            else:
                self.output_launcher_log(f"NeoForge 客户端 JSON 已存在: {json_path}")

            self.output_launcher_log(f"NeoForge {version_name} 安装成功！")
            return True
        except Exception as e:
            self.output_launcher_log(f"安装 NeoForge 失败: {str(e)}")
            return False