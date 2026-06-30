"""一键启动脚本。"""

from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def main():
    print("AShare-X 启动中...")

    # 启动后端
    print("启动API服务器...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8766"],
        cwd=str(Path(__file__).parent),
    )

    # 等待启动
    time.sleep(3)

    # 打开浏览器
    print("打开浏览器...")
    webbrowser.open("http://127.0.0.1:8766")

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n停止服务...")
        proc.terminate()


if __name__ == "__main__":
    main()
