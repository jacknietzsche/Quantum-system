"""pytest 全局 fixtures 与配置。

AShare-X 单元测试约定:
- 所有单测必须可离线运行（不触碰网络、不依赖 DEEPSEEK_API_KEY）。
- 需要网络/真实 API 的测试用 @pytest.mark.data 或 @pytest.mark.integration 标记。
- 临时配置/数据库走 pytest 的 tmp_path fixture，不污染 runtime/。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 确保 ashare-x/ 在 sys.path，使 `import core` / `import db` 可用
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """隔离环境: 清空相关 env，返回临时目录供测试写 config/.env/db。

    用法:
        def test_x(isolated_env):
            cfg = Config(config_path=isolated_env / "config.yaml")
    """
    for key in list(os.environ):
        if key.startswith("ASHARE_X_") or key.endswith("_API_KEY"):
            monkeypatch.delenv(key, raising=False)
    return tmp_path
