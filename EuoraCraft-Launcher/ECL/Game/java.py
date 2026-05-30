import os
import re
import sys
import subprocess
import platform
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from functools import cached_property

from ..Core.logger import get_logger

logger = get_logger("launcher")
sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class JavaInfo:
    path: Path
    version: str
    major_version: int
    java_type: str
    arch: str
    sources: list[str] = field(default_factory=list)

    @cached_property
    def _unique_key(self) -> str:
        java_home = self.path.parent.parent
        return f"{java_home.as_posix().lower()}_{self.major_version}"

    def __str__(self) -> str:
        return f"{self.java_type} {self.major_version} ({self.version}), {self.arch}, 来源:[{','.join(self.sources)}], 路径: {self.path}"


class JavaDetector:

    def __init__(self):
        self.java_list: list[JavaInfo] = []
        self._candidate_cache: dict[str, tuple[Path, str]] = {}
        self.is_windows = platform.system() == "Windows"
        self.is_macos = platform.system() == "Darwin"

    def detect_all(self) -> list[JavaInfo]:
        logger.debug("开始扫描 Java...")

        if self.is_windows:
            self._scan_registry()
        
        self._scan_environment()

        # Unix 系统额外扫描 which 和 update-alternatives
        if not self.is_windows:
            self._scan_unix_tools()

        self._validate_and_deduplicate()
        self.java_list.sort(key=lambda x: x.major_version, reverse=True)

        logger.info(f"扫描完成，共找到 {len(self.java_list)} 个有效 Java")
        return self.java_list

    def _add_candidate(self, path: Path, source: str) -> None:
        if not path.exists():
            return

        normalized = path.resolve()
        bin_dir = str(normalized.parent).lower()

        # Windows 优先 javaw，Unix 优先 java
        if bin_dir in self._candidate_cache:
            existing_path, _ = self._candidate_cache[bin_dir]
            if self.is_windows and "javaw" in normalized.name.lower():
                self._candidate_cache[bin_dir] = (normalized, source)
        else:
            self._candidate_cache[bin_dir] = (normalized, source)

    def _scan_registry(self) -> None:
        if not self.is_windows:
            return

        try:
            import winreg
        except ImportError:
            return

        logger.debug("正在读取注册表...")

        registry_configs = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Runtime Environment", "JRE"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Development Kit", "JDK"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK", "JDK"),
        ]

        if platform.machine().endswith('64'):
            registry_configs.extend([
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\Java Runtime Environment", "JRE"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\Java Development Kit", "JDK"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\JDK", "JDK"),
            ])

        for hkey, sub_path, java_type in registry_configs:
            try:
                with winreg.OpenKey(hkey, sub_path) as key:
                    index = 0
                    while True:
                        try:
                            version_name = winreg.EnumKey(key, index)
                            version_key_path = f"{sub_path}\\{version_name}"

                            with winreg.OpenKey(hkey, version_key_path) as version_key:
                                java_home, _ = winreg.QueryValueEx(version_key, "JavaHome")
                                if not java_home or not os.path.exists(java_home):
                                    index += 1
                                    continue

                                java_home_path = Path(java_home)
                                javaw = java_home_path / "bin" / "javaw.exe"
                                java = java_home_path / "bin" / "java.exe"

                                target = javaw if javaw.exists() else java
                                if target.exists():
                                    self._add_candidate(target, f"registry_{java_type}")
                            index += 1
                        except OSError:
                            break
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.error(f"注册表读取错误: {e}")

    def _scan_environment(self) -> None:
        logger.debug("正在检查环境变量...")

        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            base = Path(java_home) / "bin"
            for exe in ["javaw.exe", "java.exe"] if self.is_windows else ["java"]:
                if (full := base / exe).exists():
                    self._add_candidate(full, "env_java_home")
                    break

        path_env = os.environ.get("PATH", "")
        for path_dir in path_env.split(os.pathsep):
            path_dir = path_dir.strip('"')
            if not path_dir:
                continue
            for exe in ["javaw.exe", "java.exe"] if self.is_windows else ["java"]:
                if (full := Path(path_dir) / exe).exists():
                    self._add_candidate(full, "env_path")


    def _scan_unix_tools(self) -> None:
        """扫描 Unix 系统的 which 和 update-alternatives"""
        logger.debug("正在扫描 Unix 工具链...")

        # which java
        try:
            result = subprocess.run(
                ["which", "java"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and (path := Path(result.stdout.strip())).exists():
                # 解析符号链接找到真实路径
                real_path = path.resolve()
                self._add_candidate(real_path, "which_java")
        except Exception:
            pass

        # update-alternatives (Linux)
        if not self.is_macos:
            try:
                result = subprocess.run(
                    ["update-alternatives", "--list", "java"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line and (path := Path(line)).exists():
                            self._add_candidate(path.resolve(), "update_alternatives")
            except Exception:
                pass

    def _validate_and_deduplicate(self) -> None:
        logger.debug(f"发现 {len(self._candidate_cache)} 个唯一目录，开始验证...")

        validated: dict[str, JavaInfo] = {}

        for path, source in self._candidate_cache.values():
            info = self._validate_java(path, source)
            if not info:
                continue

            if info._unique_key in validated:
                validated[info._unique_key].sources.extend(info.sources)
            else:
                validated[info._unique_key] = info

        self.java_list = list(validated.values())

    def _validate_java(self, path: Path, source: str) -> Optional[JavaInfo]:
        # Windows 用 javaw 路径但验证时用 java
        exec_path = path.with_name("java.exe") if self.is_windows and "javaw" in path.name.lower() else path

        try:
            result = subprocess.run(
                [str(exec_path), "-version"],
                capture_output=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
        except Exception:
            return None

        output = result.stderr or result.stdout
        if not output:
            return None

        return self._parse_version_output(path, output, source, exec_path)

    def _is_jdk(self, java_home: Path, output: str) -> bool:
        if (java_home / "jmods").exists():
            return True
        if (java_home / "lib" / "tools.jar").exists():
            return True
        return "jdk" in output.lower() or "development" in output.lower()

    def _parse_version_output(self, path: Path, output: str, source: str, exec_path: Path) -> Optional[JavaInfo]:
        version_match = re.search(r'version\s+"(\d+[\.\d]*[_\+]?\d*)"', output, re.IGNORECASE)
        if not version_match:
            return None

        version_str = version_match.group(1)

        # 解析主版本号: 1.8.0_xxx -> 8, 17.0.1 -> 17
        major = int(version_str.split(".")[1]) if version_str.startswith("1.") else int(version_str.split(".")[0])

        java_home = exec_path.parent.parent
        java_type = "JDK" if self._is_jdk(java_home, output) else "JRE"

        # 架构检测
        arch = "64-bit"
        if any(x in output for x in ["32-Bit", "i586", "i686", "x86"]):
            arch = "32-bit"
        elif any(x in output for x in ["64-Bit", "amd64", "x86_64", "aarch64"]):
            arch = "64-bit"

        return JavaInfo(
            path=path,
            version=version_str,
            major_version=major,
            java_type=java_type,
            arch=arch,
            sources=[source]
        )

    def get_recommended_java(self, mc_version: str) -> Optional[JavaInfo]:
        if not self.java_list:
            return None

        parts = mc_version.split('.')
        if len(parts) < 2:
            return self.java_list[0]

        major = int(parts[1])
        minor = int(parts[2]) if len(parts) > 2 else 0

        # MC 1.20.5+ 需要 Java 21
        if major == 20 and minor >= 5:
            required = [21, 25]
        elif major >= 21:
            required = [21, 25]
        elif major >= 17:
            required = [17]
        elif major >= 12:
            required = [8]
        else:
            required = [8]

        for req in required:
            for java in self.java_list:
                if java.major_version == req:
                    return java

        logger.warning(f"未找到适合 MC {mc_version} 的 Java {required}，使用最新版本（可能不兼容！）")
        return self.java_list[0]


def get_java_list() -> Optional[list[JavaInfo]]:
    return JavaDetector().detect_all() or None


if __name__ == "__main__":
    get_java_list()