"""前端浏览器自动化测试（Playwright）。

启动 FastAPI 服务后，用无头 Chromium 访问 static/index.html，
验证关键页面元素和交互。
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def server_port() -> int:
    """找一个可用端口。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


@pytest.fixture(scope="session")
def server_url(server_port: int) -> Generator[str, None, None]:
    """启动后端服务并返回 base URL。"""
    project_root = Path(__file__).resolve().parents[2]
    proc = subprocess.Popen(
        [sys.executable, "-m", "main", "serve", "--port", str(server_port)],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 等待服务就绪
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect(("127.0.0.1", server_port))
            sock.close()
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("服务启动超时")

    yield f"http://127.0.0.1:{server_port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.integration
@pytest.mark.slow
class TestFrontend:
    """前端关键交互测试。"""

    def test_dashboard_loads(self, page, server_url: str):
        page.goto(server_url)
        assert page.title() == "AShare-X - AI智能投研系统"
        assert page.locator("text=控制台").first.is_visible()

    def test_navigate_to_trading_plan(self, page, server_url: str):
        page.goto(server_url)
        page.locator(".nav-item:has-text('交易计划')").click()
        assert page.locator("text=每日交易计划").first.is_visible()
        assert page.locator("button:has-text('运行每日分析')").first.is_visible()

    def test_navigate_to_settings(self, page, server_url: str):
        page.goto(server_url)
        page.locator(".nav-item:has-text('系统设置')").click()
        assert page.locator("text=模型接入").first.is_visible()
        assert page.locator("text=交易计划邮件推送").first.is_visible()

    def test_rebalance_button_exists(self, page, server_url: str):
        page.goto(f"{server_url}/#tradingplan")
        page.locator(".nav-item:has-text('交易计划')").click()
        btn = page.locator("button:has-text('再平衡')").first
        assert btn.is_visible()

    def test_history_table_exists(self, page, server_url: str):
        page.goto(server_url)
        page.locator(".nav-item:has-text('交易计划')").click()
        assert page.locator("text=历史计划").first.is_visible()
