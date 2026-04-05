import sys
import os
from pathlib import Path
import json
import requests
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ECL.Core.ECLauncherCore import ECLauncherCore
from ECL.Core.C_GetGames import GetGames
from ECL.logger import LoggerManager
import logging

LoggerManager().set_level(logging.INFO)

class TestTool:
    def __init__(self):
        self.launcher = ECLauncherCore()
        self.setup_mirrors()
        self.game_path = Path("./.minecraft")
        
    def setup_mirrors(self):
        self.launcher.set_api_url({
            "Meta": "https://bmclapi2.bangbang93.com",
            "Data": "https://bmclapi2.bangbang93.com",
            "Libraries": "https://bmclapi2.bangbang93.com/maven",
            "Assets": "https://bmclapi2.bangbang93.com/assets",
            "Forge": "https://bmclapi2.bangbang93.com/maven",
            "Fabric": "https://bmclapi2.bangbang93.com/maven",
            "NeoForged": "https://bmclapi2.bangbang93.com/maven"
        })
        
    def download_vanilla(self, version_id: str = "1.21.4"):
        print(f"\n[下载原版] {version_id}")
        try:
            meta_url = "https://bmclapi2.bangbang93.com/mc/game/version_manifest.json"
            manifest = requests.get(meta_url, timeout=15).json()
            
            version_info = None
            for v in manifest["versions"]:
                if v["id"] == version_id:
                    version_info = v
                    break
            
            if not version_info:
                print(f"未找到版本: {version_id}")
                return False
                
            version_dir = self.game_path / "versions" / version_id
            version_dir.mkdir(parents=True, exist_ok=True)
            
            version_json = requests.get(version_info["url"], timeout=15).json()
            json_path = version_dir / f"{version_id}.json"
            json_path.write_text(json.dumps(version_json, indent=2), encoding="utf-8")
            
            self.launcher.files_checker.check_files(
                game_path=self.game_path,
                version_name=version_id,
                download_max_thread=64
            )
            print(f"✓ 下载完成: {version_id}")
            return True
            
        except Exception as e:
            print(f"✗ 下载失败: {e}")
            return False
    
    def download_fabric(self, mc_version: str, loader_version: str = None):
        print(f"\n[下载 Fabric] MC {mc_version}")
        try:
            url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
            versions = requests.get(url, timeout=10).json()
            if not versions:
                print("未获取到 Fabric 版本列表")
                return False
            
            if loader_version is None:
                loader_version = versions[0]["loader"]["version"]
                
            fabric_id = f"fabric-loader-{loader_version}-{mc_version}"
            profile_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{loader_version}/profile/json"
            profile = requests.get(profile_url, timeout=15).json()
            
            version_dir = self.game_path / "versions" / fabric_id
            version_dir.mkdir(parents=True, exist_ok=True)
            
            json_path = version_dir / f"{fabric_id}.json"
            json_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            
            self.launcher.files_checker.check_files(
                game_path=self.game_path,
                version_name=fabric_id,
                download_max_thread=64
            )
            print(f"✓ Fabric 安装完成: {fabric_id}")
            return True
            
        except Exception as e:
            print(f"✗ 安装失败: {e}")
            return False
    
    def launch_game(self, version: str, java_path: str = None, player: str = "Player", ram: int = 4096):
        print(f"\n[启动游戏] {version}")
        
        if java_path is None:
            java_path = self._find_java()
            if not java_path:
                print("未找到 Java，请手动指定")
                return False
        
        try:
            self.launcher.launch_minecraft(
                java_path=java_path,
                game_path=self.game_path,
                version_name=version,
                max_use_ram=ram,
                player_name=player,
                completes_file=True,
                download_max_thread=32
            )
            
            if self.launcher.instances:
                instance = self.launcher.instances[-1]
                print(f"✓ 游戏已启动 PID: {instance['Instance'].pid}")
                return instance
            else:
                print("✗ 启动失败")
                return None
                
        except Exception as e:
            print(f"✗ 启动错误: {e}")
            return None
    
    def list_versions(self):
        print("\n[版本列表]")
        try:
            manifest = requests.get(
                "https://bmclapi2.bangbang93.com/mc/game/version_manifest.json",
                timeout=10
            ).json()
            
            releases = [v["id"] for v in manifest["versions"] if v["type"] == "release"][:10]
            print("正式版:", ", ".join(releases))
            return manifest
        except Exception as e:
            print(f"获取失败: {e}")
            return None
    
    def _find_java(self):
        possible_paths = [
            r"C:\Program Files\Java\jdk-21\bin\java.exe",
            r"C:\Program Files\Java\jdk-17\bin\java.exe",
            r"C:\Program Files\Java\jdk-11\bin\java.exe",
            r"C:\Program Files\Eclipse Adoptium\jdk-21\bin\java.exe",
        ]
        
        import shutil
        java_cmd = shutil.which("java")
        if java_cmd:
            return java_cmd
        
        for path in possible_paths:
            if Path(path).exists():
                return path
        return None


def main():
    tool = TestTool()
    
    while True:
        print("\n" + "=" * 50)
        print("  EuoraCraft 测试工具")
        print("=" * 50)
        print("1. 下载原版 Minecraft")
        print("2. 下载 Fabric")
        print("3. 启动游戏")
        print("4. 查看版本列表")
        print("5. 退出")
        print("=" * 50)
        
        choice = input("选择: ").strip()
        
        if choice == "1":
            version = input("版本 (默认 1.21.4): ").strip() or "1.21.4"
            tool.download_vanilla(version)
            
        elif choice == "2":
            mc_ver = input("MC 版本 (默认 1.21.4): ").strip() or "1.21.4"
            loader = input("Loader 版本 (留空自动): ").strip() or None
            tool.download_fabric(mc_ver, loader)
            
        elif choice == "3":
            version = input("版本名: ").strip()
            if not version:
                print("版本名不能为空")
                continue
            java = input("Java 路径 (留空自动): ").strip() or None
            player = input("玩家名 (默认 Player): ").strip() or "Player"
            ram = input("内存 MB (默认 4096): ").strip()
            ram = int(ram) if ram.isdigit() else 4096
            tool.launch_game(version, java, player, ram)
            
        elif choice == "4":
            tool.list_versions()
            
        elif choice == "5":
            break


if __name__ == "__main__":
    main()
