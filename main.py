"""主程序入口。"""

import logging
import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """默认启动 CLI 模式。"""
    if len(sys.argv) > 1:
        # 有命令行参数，交给 CLI 处理
        from cli import main as cli_main
        cli_main()
    else:
        # 无参数，启动托盘模式
        from tray import TrayIcon
        logger.info("启动 AI Recorder 系统托盘模式...")
        TrayIcon().run()


if __name__ == "__main__":
    main()
