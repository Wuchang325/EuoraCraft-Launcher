##################################
#
#       EuoraCraft Launcher
#   基于Python开发的Minecraft启动器，支持多版本管理、跨平台运行。
#   ECLTeam 版权所有 2026
#
##################################
from ECL.launcher import EuoraCraftLauncher


def main() -> None:
    launcher = EuoraCraftLauncher()
    launcher.run()


if __name__ == "__main__":
    main()