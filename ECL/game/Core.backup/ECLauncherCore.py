from . import C_Libs, C_Downloader, C_FilesChecker, InstancesManager
from typing import Callable
from shutil import rmtree
from pathlib import Path
import subprocess
import platform
import json
import re
import requests
from ...Core.logger import get_logger

logger = get_logger("ECLauncherCore")


class ECLauncherCore:
    def __init__(self):
        self.output_launcher_log: Callable[[str], None] = self.__default_output_log
        self.output_minecraft_instance: Callable[[dict[str, str | bool | subprocess.Popen]], None] = self.__default_output_log
        self.output_jvm_params: Callable[[str], None] = self.__default_output_log

        self.api_url = C_Libs.ApiUrl()
        self.downloader = C_Downloader.Downloader()
        self.files_checker = C_FilesChecker.FilesChecker(self.api_url, self.downloader)
        self.instances_manager = InstancesManager.InstancesManager()

        self.system_type = platform.system()  # 获取系统类型

    def set_api_url(self, api_url_dict: dict): 
        self.api_url.update_from_dict(api_url_dict)

    def set_output_launcher_log(self, output_function: Callable[[str], None]) -> None:
        self.output_launcher_log = output_function

    @staticmethod
    def __default_output_log(log):
        logger.info(log)


    def set_output_jvm_params(self, output_function: Callable[[str], None]) -> None:
        self.output_jvm_params = output_function

    def launch_minecraft(self, java_path: str | Path, game_path: str | Path, version_name: str, max_use_ram: int, player_name: str,
                         user_type: str = "legacy", auth_uuid: str = "", access_token: str = "None",
                         first_set_lang: str = "zh_CN", set_lang: str = "", launcher_name: str = "ECL",
                         launcher_version: str = "0.1145", default_version_type: bool = False,
                         custom_jvm_params: list[str] = None, window_width: int | str = "${resolution_width}",
                         window_height: int | str = "${resolution_width}",
                         completes_file: bool = True, download_max_thread: int = 32,
                         output_jvm_params: bool = False, write_run_script: bool = False, run_script_path: str | Path = ".") -> str:
        if re.search(r"[^a-zA-Z0-9\-_+. ]", player_name):  # 检测用户名是否合法
            error_meg = "玩家名称不能包含数字、减号、下划线、加号或英文句号(小数点)以外的字符"
            self.output_launcher_log(error_meg)
            raise ValueError(error_meg)

        if auth_uuid != "" and not C_Libs.is_uuid3(auth_uuid):  # 检测UUID3是否合法
            error_msg = "错误的 UUID, UUID 必须是 UUID3"
            self.output_launcher_log(error_msg)
            raise ValueError(error_msg)

        java_path = Path(java_path)
        game_path = Path(game_path)
        version_json = game_path / "versions" / version_name / f"{version_name}.json"

        if not java_path.is_file():
            error_msg = f"未找到 Java 可执行文件 {java_path}"
            self.output_launcher_log(error_msg)
            raise FileExistsError(error_msg)

        if not version_json.is_file():
            error_msg = f"未找到游戏 {version_name}"
            self.output_launcher_log(error_msg)
            raise FileExistsError(error_msg)

        if max_use_ram < 256: 
            max_use_ram = 256

        if completes_file: 
            self.files_checker.check_files(game_path, version_name, download_max_thread)

        jvm_params_list = []
        cp_delimiter = ":"  # ClassPath分隔符
        run_script_suffix = ".sh"
        self.output_launcher_log(f"系统平台 {self.system_type}")

        if self.system_type == "Windows":  # Windows平台
            run_script_suffix = ".bat"
            cp_delimiter = ";"
            jvm_params_list.append("-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump")
        elif self.system_type == "Darwin":  # macOS平台
            run_script_suffix = ".command"
            jvm_params_list.append("-XstartOnFirstThread")

        jvm_params_list.extend([
            "-Xms256M",
            f"-Xmx{max_use_ram}M",
            "-Dstderr.encoding=UTF-8",
            "-Dstdout.encoding=UTF-8",
            "-Dfile.encoding=UTF-8",
            "-XX:+UseG1GC",
            "-XX:-UseAdaptiveSizePolicy",
            "-XX:-OmitStackTraceInFastThrow",
            "-Dlog4j2.formatMsgNoLookups=true",
            "-Dfml.ignoreInvalidMinecraftCertificates=True",
            "-Dfml.ignorePatchDiscrepancies=True",
            "-cp ${classpath}",  # 添加classpath占位符
            "${main_class}"  # 添加主类占位符
        ])

        if custom_jvm_params: 
            jvm_params_list.extend(custom_jvm_params)  # 添加自定义Jvm参数

        version_json = json.loads(version_json.read_text("utf-8"))

        if "arguments" in version_json:
            if "jvm" in version_json["arguments"]:
                for arguments_jvm in version_json["arguments"]["jvm"]:  # 遍历Json中的Jvm参数
                    if type(arguments_jvm) is not str: 
                        continue
                    if "${classpath_separator}" in arguments_jvm:  # 针对NeoForged的-p参数加双引号
                        jvm_params_list.append(f"\"{arguments_jvm.replace(' ', '')}\"")
                    else:
                        jvm_params_list.append(arguments_jvm.replace(" ", ""))
            if "game" in version_json["arguments"]:
                for arguments_game in version_json["arguments"]["game"]:  # 遍历游戏参数
                    if type(arguments_game) is not str: 
                        continue
                    jvm_params_list.append(arguments_game.replace(" ", ""))
        elif "minecraftArguments" in version_json:
            # 旧版格式：添加游戏参数（不包含-cp和主类，因为已在前面添加）
            jvm_params_list.extend([
                "-Djava.library.path=${natives_directory}",
                version_json["minecraftArguments"]
            ])

        if window_width != "${resolution_width}" != window_height:
            jvm_params_list.append(f"--width {window_width} --height {window_height}")

        class_path_list = []
        asm_versions = []  # Fuck ASM!!!
        natives_path_list = []

        for libraries in version_json["libraries"]:  # 遍历依赖构建ClassPath
            libraries_path = game_path / "libraries" / C_Libs.name_to_path(libraries["name"])
            if str(libraries_path) in class_path_list: 
                continue  # 防重复
            if re.search(r"asm-\d+(?:\.\d+)*", libraries_path.stem):  # Fuck ASM!!!
                asm_versions.append(libraries_path)
                continue
            class_path_list.append(str(libraries_path))
            if "classifiers" not in libraries.get("downloads", {}): 
                continue  # 查找natives
            for classifiers in libraries["downloads"]["classifiers"].values():
                natives_path = game_path / "libraries" / classifiers["path"]
                if natives_path in natives_path_list: 
                    continue  # 防重复
                natives_path_list.append(natives_path)

        version_jar = game_path / "versions" / version_name / f"{version_name}.jar"
        
        # 检查版本jar是否存在
        if not version_jar.is_file():
            error_msg = f"版本jar文件不存在: {version_jar}"
            self.output_launcher_log(error_msg)
            raise FileNotFoundError(error_msg)
        
        asset_index_id = ""

        if "id" in version_json.get("assetIndex", {}):
            asset_index_id = version_json["assetIndex"]["id"]

        game_json = C_Libs.find_version(version_json, game_path)

        if game_json:  # 处理继承版本
            game_json, version_path = game_json
            if "arguments" in game_json:
                if "jvm" in game_json["arguments"]:
                    for arguments_jvm in game_json["arguments"]["jvm"]:
                        if type(arguments_jvm) is not str: 
                            continue
                        arguments_jvm = arguments_jvm.replace(" ", "")
                        if arguments_jvm in jvm_params_list: 
                            continue  # 防重复
                        jvm_params_list.append(arguments_jvm)
                if "game" in game_json["arguments"]:
                    for arguments_game in game_json["arguments"]["game"]:
                        if type(arguments_game) is not str: 
                            continue
                        arguments_game = arguments_game.replace(" ", "")
                        if arguments_game in jvm_params_list: 
                            continue
                        jvm_params_list.append(arguments_game)
            elif "minecraftArguments" not in version_json and "minecraftArguments" in game_json:
                # 继承版本的旧版格式：只添加缺失的游戏参数
                jvm_params_list.extend([
                    "-Djava.library.path=${natives_directory}",
                    game_json["minecraftArguments"]
                ])

            for libraries in game_json["libraries"]:
                libraries_path = game_path / "libraries" / C_Libs.name_to_path(libraries["name"])
                if str(libraries_path) in class_path_list: 
                    continue
                if re.search(r"asm-\d+(?:\.\d+)*", libraries_path.stem) and libraries_path not in asm_versions:  # Fuck ASM!!!
                    asm_versions.append(libraries_path)
                    continue
                class_path_list.append(str(libraries_path))
                if "classifiers" not in libraries.get("downloads", {}): 
                    continue
                for classifiers in libraries["downloads"]["classifiers"].values():
                    natives_path = game_path / "libraries" / classifiers["path"]
                    if natives_path in natives_path_list: 
                        continue
                    natives_path_list.append(natives_path)

            if not version_jar.is_file(): 
                version_jar = version_path / f"{version_path.name}.jar"
            if not asset_index_id: 
                asset_index_id = game_json["assetIndex"]["id"]

        asm_version = 0
        asm_path = ""

        for get_asm in asm_versions:  # 选择最高版本ASM
            get_asm_version = float(get_asm.stem.replace("asm-", ""))
            if get_asm_version > asm_version:
                asm_version = get_asm_version
                asm_path = str(get_asm)
        if asm_path: 
            class_path_list.append(asm_path)

        class_path_list.append(str(version_jar))
        main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")
        
        self.output_launcher_log(f"Classpath包含 {len(class_path_list)} 个文件")
        self.output_launcher_log(f"主类: {main_class}")
        natives_path = game_path / "versions" / version_name / "natives"
        is_set_lang = False

        if natives_path.is_dir():  # 清理旧natives
            rmtree(natives_path)
            natives_path.mkdir(parents=True, exist_ok=True)
        else:
            is_set_lang = True
            natives_path.mkdir(parents=True, exist_ok=True)

        self.output_launcher_log(f"需要解压 {len(natives_path_list)} 个文件")
        for a_natives in natives_path_list:
            C_Libs.unzip(a_natives, natives_path)

        if is_set_lang or set_lang:  # 设置游戏语言
            lang = f"lang:{set_lang}" if set_lang else f"lang:{first_set_lang}"
            options_contents = lang
            options_path = game_path / "versions" / version_name / "options.txt"
            if options_path.is_file():
                options_contents = options_path.read_text("utf-8")
                options_contents = re.sub(r"^lang:\S+$", lang, options_contents, flags=re.MULTILINE)
            options_path.write_text(options_contents, "utf-8")
            self.output_launcher_log(f"设置游戏语言为 {lang}")

        if user_type == "legacy":  # 离线模式生成UUID3
            auth_uuid = C_Libs.name_to_uuid(player_name).hex
            self.output_launcher_log(f"未设置 UUID, 生成 UUID 为 {auth_uuid}")

        # 构建完整启动命令
        jvm_cmd = f'"{java_path}" {" ".join(jvm_params_list)}'
        # 替换classpath和主类（先替换这两个，因为其他替换可能包含路径）
        jvm_cmd = jvm_cmd.replace("${classpath}", f'"{cp_delimiter.join(class_path_list)}"')
        jvm_cmd = jvm_cmd.replace("${main_class}", main_class)
        # 替换其他变量
        jvm_cmd = jvm_cmd.replace("${library_directory}", f'"{game_path / "libraries"}"')
        jvm_cmd = jvm_cmd.replace("${assets_root}", f'"{game_path / "assets"}"')
        jvm_cmd = jvm_cmd.replace("${assets_index_name}", asset_index_id)
        jvm_cmd = jvm_cmd.replace("${natives_directory}", f'"{natives_path}"')
        jvm_cmd = jvm_cmd.replace("${game_directory}", f'"{game_path / "versions" / version_name}"')
        jvm_cmd = jvm_cmd.replace("${launcher_name}", f'"{launcher_name}"')
        jvm_cmd = jvm_cmd.replace("${launcher_version}", f'"{launcher_version}"')
        jvm_cmd = jvm_cmd.replace("${version_type}", f'"{version_json.get("type", launcher_name)}"' if default_version_type else f'"{launcher_name}"')
        jvm_cmd = jvm_cmd.replace("${auth_player_name}", f'"{player_name}"')
        jvm_cmd = jvm_cmd.replace("${user_type}", user_type)
        jvm_cmd = jvm_cmd.replace("${auth_uuid}", auth_uuid)
        jvm_cmd = jvm_cmd.replace("${auth_access_token}", access_token)
        jvm_cmd = jvm_cmd.replace("${user_properties}", "{}")
        jvm_cmd = jvm_cmd.replace("${classpath_separator}", cp_delimiter)
        jvm_cmd = jvm_cmd.replace("${library_directory}", f'{game_path/ "libraries"}')
        jvm_params = C_Libs.replace_last(jvm_cmd, "${version_name}", f'"{version_name}"')

        if write_run_script:
            run_script_path = Path(run_script_path) / f"run{run_script_suffix}"
            self.output_launcher_log(f"生成的启动脚本在 {run_script_path}")
            run_script_path.write_text(jvm_params, "utf-8")

        if output_jvm_params:
            self.output_launcher_log("输出启动参数")
            self.output_jvm_params(jvm_params)
            return ""
        else:
            self.output_launcher_log(f"正在启动游戏 [{version_name}]")
            # 输出完整启动命令用于调试
            # self.output_launcher_log(f"启动命令: {jvm_params}")
            instance_id = self.instances_manager.create_instance(
                instance_name=version_name,
                instance_type="MinecraftClient",
                args=jvm_params,
                cwd=(game_path / "versions" / version_name),
                only_stdout=True
            )  # 启动游戏
            return instance_id

    def scan_versions_in_path(self, base_path: str | Path) -> list[dict]:  # 扫描路径中的游戏版本
        base_path = Path(base_path)
        if not base_path.is_dir():
            logger.warning("扫描路径不存在或不是目录: %s", base_path)
            return []
        versions_dir = base_path / "versions"
        if not versions_dir.is_dir():
            logger.debug("路径 %s 中没有 versions 目录", base_path)
            return []
        results = []
        for child in versions_dir.iterdir():
            if not child.is_dir(): 
                continue
            folder_name = child.name
            json_file = child / f"{folder_name}.json"
            if not json_file.exists():
                json_files = list(child.glob("*.json"))
                if not json_files: 
                    continue
                json_file = json_files[0]
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loader_type = data.get("type", "Unknown")
                version = data.get("id", "Unknown")
                results.append({"folder": folder_name, "status": "success", "loader_type": loader_type, "version": version, "error": None})
            except Exception as e:
                results.append({"folder": folder_name, "status": "failure", "loader_type": None, "version": None, "error": f"解析JSON失败: {e}"})
        return results

    @staticmethod
    def get_version_list() -> list[dict]:  # 获取官方版本列表
        try:
            url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("versions", [])
        except Exception as e:
            logger.error("获取 Minecraft 版本列表失败: %s", e)
            return []

    @staticmethod
    def get_fabric_loader_list() -> list[str]:  # 获取Fabric加载器版本列表
        try:
            url = "https://meta.fabricmc.net/v2/versions/loader"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            versions = [item.get("version", "") for item in data if item.get("version")]
            return versions
        except Exception as e:
            logger.error("获取 Fabric Loader 版本列表失败: %s", e)
            return []

    def install(self, version_id: str | None = None, loader: str | None = None,  # 安装游戏版本入口
                loader_version: str | None = None, game_path: str | Path | None = None) -> bool:
        try:
            if game_path is None:
                game_path = Path("./.minecraft")
            else:
                game_path = Path(game_path)
            
            if not loader or loader == "vanilla":
                if not version_id:
                    logger.error("安装原版需要提供 version_id")
                    return False
                return self._install_vanilla(game_path, version_id)
            if loader == "fabric": 
                return self._install_fabric(game_path, version_id, loader_version)
            if loader == "forge": 
                return self._install_forge(game_path, version_id, loader_version)
            if loader == "neoforged": 
                return self._install_neoforged(game_path, version_id, loader_version)
            if loader == "quilt": 
                return self._install_quilt(game_path, version_id, loader_version)
            logger.error(f"不支持的加载器类型: {loader}")
            return False
        except Exception as e:
            logger.error("安装版本失败: %s", e)
            return False

    def _install_vanilla(self, game_path: Path, version_id: str) -> bool:  # 安装原版
        version_dir = game_path / "versions" / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        versions = self.get_version_list()
        version_info = None
        for v in versions:
            if v.get("id") == version_id:
                version_info = v
                break
        if not version_info:
            logger.error("未找到版本 %s", version_id)
            return False
        version_url = version_info.get("url")
        if not version_url: 
            return False
        response = requests.get(version_url, timeout=30)
        response.raise_for_status()
        version_json = response.json()
        vanilla_json_path = version_dir / f"{version_id}.json"
        vanilla_json_path.write_text(json.dumps(version_json, indent=2), encoding="utf-8")
        logger.info("原版版本 %s 安装成功", version_id)
        return True

    def _install_fabric(self, game_path: Path, mc_version: str | None, fabric_version: str | None) -> bool:  # 安装Fabric
        from .C_GetGames import GetGames
        getter = GetGames()
        getter.set_api_url(self.api_url.to_dict())
        if not mc_version:
            logger.error("安装 Fabric 需要提供 mc_version")
            return False
        if not fabric_version:
            fabric_versions = self.get_fabric_loader_list()
            if not fabric_versions: 
                return False
            fabric_version = fabric_versions[0]
        fabric_version_name = f"fabric-loader-{fabric_version}-{mc_version}"
        fabric_dir = game_path / "versions" / fabric_version_name
        try:
            fabric_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{fabric_version}/profile/json"
            fabric_response = requests.get(fabric_url, timeout=30)
            fabric_response.raise_for_status()
            fabric_json = fabric_response.json()
            fabric_dir.mkdir(parents=True, exist_ok=True)
            fabric_json_path = fabric_dir / f"{fabric_version_name}.json"
            fabric_json_path.write_text(json.dumps(fabric_json, indent=2), encoding="utf-8")
            logger.info("Fabric 版本 %s 安装成功", fabric_version_name)
            return True
        except Exception as e:
            logger.error("下载 Fabric 版本失败: %s", e)
            return False

    def _install_forge(self, game_path: Path, mc_version: str | None, forge_version: str | None) -> bool:  # 安装Forge
        from .C_GetGames import GetGames
        getter = GetGames()
        getter.set_api_url(self.api_url.to_dict())
        if not mc_version:
            logger.error("安装 Forge 需要提供 mc_version")
            return False
        if not forge_version:
            versions = getter.get_forge_versions(mc_version)
            if not versions or not versions.get("All"):
                logger.error("未找到 Forge 版本列表")
                return False
            forge_version = versions["All"][-1].split("-")[-1] if versions["All"] else None
            if not forge_version: 
                return False
        return getter.download_forge(game_path=game_path, mc_version=mc_version, forge_version=forge_version, download_vanilla=False)

    def _install_neoforged(self, game_path: Path, mc_version: str | None,  # 安装NeoForged,支持26.x新格式
                           neoforge_version: str | None) -> bool:
        from .C_GetGames import GetGames
        getter = GetGames()
        getter.set_api_url(self.api_url.to_dict())
        if not neoforge_version:
            versions = getter.get_neoforge_versions()
            if not versions:
                logger.error("未找到 NeoForged 版本列表")
                return False
            if versions.get("NewFormat"):
                neoforge_version = versions["NewFormat"][-1]
                logger.info(f"使用最新 NeoForged 版本(新格式): {neoforge_version}")
            else:
                neoforge_version = versions["All"][-1]
                logger.info(f"使用最新 NeoForged 版本: {neoforge_version}")
        version_info = C_Libs.get_neoforge_version_info(neoforge_version)
        inferred_mc = version_info["mc_version"]
        if version_info["is_new_scheme"]:
            logger.info("检测到 NeoForged 新格式版本(对应 MC 1.21.12+)")
        if not mc_version: 
            mc_version = inferred_mc
        elif inferred_mc and inferred_mc != mc_version:
            logger.warning(f"版本不匹配: 指定 {mc_version},但 {neoforge_version} 对应 {inferred_mc}")
        if mc_version: 
            logger.info(f"安装 NeoForged {neoforge_version} for Minecraft {mc_version}")
        return getter.download_neoforge(game_path=game_path, neoforge_version=neoforge_version, download_vanilla=True, download_max_thread=32)

    def _install_quilt(self, game_path: Path, mc_version: str | None, quilt_version: str | None) -> bool:  # 安装Quilt
        from .C_GetGames import GetGames
        getter = GetGames()
        getter.set_api_url(self.api_url.to_dict())
        if not mc_version:
            logger.error("安装 Quilt 需要提供 mc_version")
            return False
        if not quilt_version:
            versions = getter.get_quilt_versions(mc_version)
            if not versions or not versions.get("All"):
                logger.error("未找到 Quilt 版本列表")
                return False
            quilt_version = versions["All"][0]["LoaderVersion"] if versions["All"] else None
            if not quilt_version: 
                return False
        return getter.download_quilt(game_path=game_path, mc_version=mc_version, quilt_version=quilt_version, download_vanilla=False)