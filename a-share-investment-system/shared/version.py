"""项目版本 — 从 pyproject.toml 读取"""

import os

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from shared.logging import emit_log

try:
    _path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pyproject.toml",
    )
    with open(_path, "rb") as f:
        VERSION = tomllib.load(f)["project"]["version"]
except Exception as e:
    emit_log("WARNING", "version", f"Config fallback: {str(e)[:80]}")
    VERSION = "5.1.0"  # fallback
