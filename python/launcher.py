"""
EuoraCraft Launcher - pytauri entry point

Called from Rust (src-tauri/src/main.rs) via PyO3.
Initializes logging, then runs the Tauri app.
"""

import sys
from pathlib import Path

# pytauri package root (python/ contains ECL and other modules)
_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

import colorama
from ECL.Core.logger import get_logger, LoggerManager

# Initialize colorama on Windows
colorama.init()

logger = get_logger("launcher")


def main():
    """Main entry point - called by Rust binary."""
    logger.info("=" * 50)
    logger.info("EuoraCraft Launcher (pytauri) 启动中...")
    logger.info(f"Python 版本: {sys.version}")
    logger.info(f"工作目录: {Path.cwd()}")
    logger.info("=" * 50)

    # 初始化皮肤目录（从 resources/Skins/ 拷贝到 ECL_Libs/Skins/）
    _init_skins_directory()

    # Import and run the pytauri app
    from commands import main as run_app
    run_app()


def _init_skins_directory() -> None:
    """初始化默认皮肤目录"""
    import shutil

    work_dir = Path.cwd()
    possible_sources = [
        work_dir / "resources" / "Skins",
        work_dir.parent / "EuoraCraft-Launcher" / "resources" / "Skins",
    ]
    src = None
    for p in possible_sources:
        if p.exists() and p.is_dir():
            src = p
            break
    if not src:
        logger.warning("未找到默认皮肤源目录")
        return

    dst = work_dir / "ECL_Libs" / "Skins"
    if dst.exists() and list(dst.glob("*.png")):
        logger.info(f"皮肤目录已就绪: {dst}")
        return

    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.png"):
        shutil.copy2(f, dst / f.name)
    logger.info(f"已初始化皮肤目录: {src} -> {dst}")


if __name__ == "__main__":
    main()
