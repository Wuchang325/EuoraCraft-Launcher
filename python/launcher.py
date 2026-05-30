"""
EuoraCraft Launcher - pytauri entry point

Called from Rust (src-tauri/src/main.rs) via PyO3.
Initializes logging, then runs the Tauri app.
"""

import sys
from pathlib import Path

# Add backend to path
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "EuoraCraft-Launcher"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

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

    # Import and run the pytauri app
    from commands import main as run_app
    run_app()


if __name__ == "__main__":
    main()
