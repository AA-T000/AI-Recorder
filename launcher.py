"""主程序入口。"""

import sys
import os

# 确保资源文件能找到（打包后路径不同）
if getattr(sys, 'frozen', False):
    # 打包成 exe 后，资源在 _MEIPASS 目录下
    os.environ['_MEIPASS'] = sys._MEIPASS
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config.settings import ensure_dirs
ensure_dirs()

from main import main

if __name__ == "__main__":
    main()
