"""
EuoraCraft Launcher - Dev runner (no Rust binary needed)

Usage:
    python run_dev.py

Requires: _pytauri_ext.pyd at python/euoracraft_launcher/_pytauri_ext.pyd
          (already compiled, no need to rebuild unless Rust code changes)
"""

import os
import sys

# Ensure we're in the project root
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Point pytauri at our extension module
os.environ["_PYTAURI_DIST"] = "euoracraft-launcher"

# Add python/ to path
sys.path.insert(0, os.path.join(os.getcwd(), "python"))

# Run the launcher
from commands import main

if __name__ == "__main__":
    print("=" * 50)
    print("EuoraCraft Launcher (dev mode - running via Python directly)")
    print(f"Python: {sys.version}")
    print(f"CWD: {os.getcwd()}")
    print("=" * 50)
    main()
