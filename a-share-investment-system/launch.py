#!/usr/bin/env python3
"""AShare-X Launcher — double-click to run, auto-setup, always latest code.

使用方式:
    python launch.py              # 构建前端(如过期) + 启动 + 浏览器打开
    python launch.py --build      # 强制重建前端(跳过mtime检查)
    python launch.py --no-browser # 启动服务但不打开浏览器
    python launch.py --update     # 启动前执行 git pull --ff-only
    python launch.py --skip-build # 跳过前端构建检查
    python launch.py --port 8765  # 指定服务端口

参考: ai-hedge-fund (load_dotenv + argparse), daily_stock_analysis (setup_env + lazy imports)
"""

import argparse
import contextlib
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import warnings
import webbrowser

# 全局抑制第三方库噪音
warnings.filterwarnings("ignore", category=ResourceWarning)
os.environ.setdefault("TQDM_DISABLE", "1")

# SOCKS proxy 清理: 如果未安装 socksio, 清除 PROXY 环境变量防止网络请求阻塞
try:
    import socksio  # noqa: F401
except ImportError:
    for _key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "PROXY_URL",
        "ALL_PROXY",
    ):
        os.environ.pop(_key, None)

# Force IPv4 for outbound connections (Chinese financial APIs reject IPv6)
import socket as _socket  # noqa: E402

_old_gai = _socket.getaddrinfo


def _prefer_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    try:
        results = _old_gai(host, port, _socket.AF_INET, type, proto, flags)
        if results:
            return results
    except Exception as e:
        # IPv4 解析失败,回退到系统默认解析路径
        logger.debug("IPv4 gai failed, fallback: %s", e)
    return _old_gai(host, port, family, type, proto, flags)


with contextlib.suppress(Exception):
    _socket.getaddrinfo = _prefer_ipv4  # 如果 monkey-patch 失败也不阻断启动

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 确保标准输出在管道/重定向下也能及时刷新
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# 项目版本
try:
    sys.path.insert(0, ROOT)
    from shared.version import VERSION
except Exception:
    VERSION = "1.0.0"

# ════════════════════════════════════════════
#  Step 0: Python version check
# ════════════════════════════════════════════

if sys.version_info < (3, 10):  # noqa: UP036
    print("[ERROR] AShare-X requires Python 3.10+. Current:", sys.version)
    input("Press Enter to exit...")
    sys.exit(1)


# ════════════════════════════════════════════
#  Step 1: Python & environment detection
# ════════════════════════════════════════════


def find_venv_python() -> str | None:
    """查找项目内虚拟环境的 Python 解释器。"""
    for venv_dir in [".venv", "venv"]:
        py = os.path.join(ROOT, venv_dir, "Scripts", "python.exe")
        if os.path.exists(py):
            return os.path.abspath(py)
        py = os.path.join(ROOT, venv_dir, "bin", "python")
        if os.path.exists(py):
            return os.path.abspath(py)
    return None


def ensure_venv_python() -> str:
    """若存在虚拟环境且当前不是它，切换过去重新执行。"""
    venv_python = find_venv_python()
    if not venv_python:
        return sys.executable
    current = os.path.normcase(sys.executable)
    target = os.path.normcase(venv_python)
    if current == target:
        return sys.executable
    if not os.path.exists(target):
        return sys.executable
    logger.info("[SETUP] Switching to virtualenv Python: %s", venv_python)
    os.execv(target, [target, *sys.argv])  # noqa: S606
    return sys.executable  # unreachable, keeps linters happy


PYTHON = ensure_venv_python()
if not PYTHON:
    print("[ERROR] Python not found. Install Python 3.10+: https://python.org")
    input("Press Enter to exit...")
    sys.exit(1)

# 启动服务器和安装依赖统一使用 PYTHON
_EXECUTABLE = PYTHON

REQUIRED_DEPS = [
    "fastapi",
    "uvicorn",
    "rich",
    "pydantic",
    "sqlalchemy",
    "pandas",
    "numpy",
    "yaml",
    "requests",
    "httpx",
    "akshare",
    "tushare",
    "baostock",
    "langchain",
    "langgraph",
    "openai",
]


def check_deps() -> list[str]:
    """检查核心依赖是否已安装，返回缺失列表。"""
    missing: list[str] = []
    for dep in REQUIRED_DEPS:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)
    return missing


def install_deps():
    """安装必需依赖 — 优先使用 requirements.txt，回退到 pyproject.toml。"""
    logger.info("[SETUP] Installing dependencies...")
    req_file = os.path.join(ROOT, "requirements.txt")
    if os.path.exists(req_file):
        subprocess.run(  # noqa: S603
            [_EXECUTABLE, "-m", "pip", "install", "-r", req_file],
            cwd=ROOT,
            check=True,
        )
    else:
        subprocess.run(  # noqa: S603
            [_EXECUTABLE, "-m", "pip", "install", "-e", "."],
            cwd=ROOT,
            check=True,
        )
    logger.info("[SETUP] Dependencies installed")


def ensure_deps():
    """确保依赖存在，缺失时自动安装。"""
    missing = check_deps()
    if missing:
        logger.info("[SETUP] Missing deps: %s", ", ".join(missing))
        install_deps()
        missing = check_deps()
        if missing:
            logger.error("[SETUP] Still missing after install: %s", ", ".join(missing))
            sys.exit(1)


def ensure_dirs():
    """确保运行所需目录存在。"""
    for d in ["data", "logs", "reports", "static"]:
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)


def check_config() -> tuple[bool, list[str]]:
    """检查最小可运行配置，返回 (ok, messages)。"""
    messages: list[str] = []
    yaml_path = os.path.join(ROOT, "config", "config.yaml")
    if not os.path.exists(yaml_path):
        messages.append("WARN: config/config.yaml not found, using defaults")

    env_path = os.path.join(ROOT, "config", ".env")
    env_example = os.path.join(ROOT, "config", ".env.example")
    if not os.path.exists(env_path) and os.path.exists(env_example):
        messages.append("HINT: copy config/.env.example to config/.env and fill API keys")

    # 检查至少一个 LLM API key
    has_key = False
    providers = [
        "DEEPSEEK",
        "SILICONFLOW",
        "CHATANYWHERE",
        "OPENAI",
        "ANTHROPIC",
        "CHERRYIN",
        "JUGUANG",
    ]
    for provider in providers:
        if os.environ.get(f"{provider}_API_KEY"):
            has_key = True
            break

    if not has_key:
        try:
            cfg_path = os.path.join(ROOT, "config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                api_keys = cfg.get("api_keys", {})
                if any(v and not str(v).startswith("sk-xxx") for v in api_keys.values()):
                    has_key = True
        except Exception:
            pass

    if not has_key:
        messages.append("WARN: No LLM API key configured. LLM features will fail.")

    has_warnings = any(m.startswith("WARN") for m in messages)
    return not has_warnings, messages


# ════════════════════════════════════════════
#  Step 2: Frontend build (if stale)
# ════════════════════════════════════════════


def frontend_needs_build():
    """检查前端是否需要重建 — 基于 frontend/ (Vue3 + TypeScript)"""
    static_index = os.path.join(ROOT, "static", "index.html")
    if not os.path.exists(static_index):
        return True, "static/index.html not found"

    static_mtime = os.path.getmtime(static_index)

    frontend_dir = os.path.join(ROOT, "frontend", "src")
    if os.path.isdir(frontend_dir):
        for root, _, files in os.walk(frontend_dir):
            for f in files:
                if f.endswith((".vue", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss")):
                    fp = os.path.join(root, f)
                    if os.path.getmtime(fp) > static_mtime:
                        return True, f"{f} modified"

    return False, "up to date"


def build_frontend():
    """构建前端 — 先构建到临时目录，成功后再覆盖 static/，失败可回滚。"""
    frontend_dir = os.path.join(ROOT, "frontend")
    static_dir = os.path.join(ROOT, "static")

    if not os.path.isdir(frontend_dir) or not os.path.exists(
        os.path.join(frontend_dir, "package.json")
    ):
        logger.warning("[BUILD] No valid frontend directory found")
        return False

    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        logger.info("[SETUP] Installing frontend dependencies...")
        subprocess.run(
            ["npm", "install"],
            cwd=frontend_dir,
            check=True,
        )

    tmpdir = tempfile.mkdtemp(prefix="ashare_frontend_")
    try:
        env = os.environ.copy()
        env["DIST_DIR"] = tmpdir
        env["VITE_BUILD_OUTDIR"] = tmpdir

        result = None
        for script in ["build:quick", "build"]:
            result = subprocess.run(  # noqa: S603
                ["npm", "run", script],
                cwd=frontend_dir,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                break

        if result is None or result.returncode != 0:
            stderr = result.stderr[-800:] if result else "no npm script available"
            logger.warning("[BUILD] frontend build failed:\n%s", stderr)
            return False

        # 构建成功，安全覆盖 static/
        if os.path.isdir(static_dir):
            shutil.rmtree(static_dir, ignore_errors=True)
        shutil.copytree(tmpdir, static_dir)
        logger.info("[BUILD] Frontend built successfully -> static/")
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════
#  Step 3: Kill old process
# ════════════════════════════════════════════


def kill_port(port=8765):
    """关闭占用指定端口的旧进程(仅 Windows)。"""
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pid = parts[-1]
                    subprocess.run(  # noqa: S603
                        ["taskkill", "/F", "/PID", pid],
                        check=False,
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                    )
    except Exception:
        pass


# ════════════════════════════════════════════
#  Step 4: Git pull (optional)
# ════════════════════════════════════════════


def git_update():
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        return
    try:
        # 检查是否有远程跟踪分支
        branch_check = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if branch_check.returncode != 0:
            return  # 无远程跟踪分支,跳过 git pull

        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            logger.debug("[UPDATE] git pull failed: %s", result.stderr[:200])
        elif "Already up to date" not in result.stdout:
            logger.info("[UPDATE] Code updated, rebuilding frontend...")
            build_frontend()
    except Exception as e:
        logger.debug("[UPDATE] git skip: %s", e)


# ════════════════════════════════════════════
#  Step 5: Start server + open browser
# ════════════════════════════════════════════


def find_free_port(start=8765, count=10):
    for p in range(start, start + count):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def init_skills():
    """初始化技能引擎、大师Agent、Agent工作流 + 数据源探针。"""
    skills_count = 0
    agents_count = 0
    agent_wf_ready = False
    try:
        from services.skill_engine import get_skill_engine

        se = get_skill_engine()
        skills_count = len(se.skills)
    except Exception as e:
        logger.debug("[INIT] SkillEngine: %s", e)
    try:
        from services.master_agents import get_master_agents

        ma = get_master_agents()
        agents_count = len(ma.get_all_names())
    except Exception as e:
        logger.debug("[INIT] MasterAgents: %s", e)
    try:
        from services.agent_workflow import AgentWorkflow

        AgentWorkflow()
        agent_wf_ready = True
    except Exception as e:
        logger.debug("[INIT] AgentWorkflow: %s", e)
    return skills_count, agents_count, agent_wf_ready


def probe_data_sources():
    """探测数据源状态并返回可用源列表。"""
    try:
        from providers.market_data import MarketDataProvider

        p = MarketDataProvider()
        status = p.get_source_status()
        return [n for n, s in status.items() if s.get("available")], status
    except Exception:
        return [], {}


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """等待服务器健康检查通过。"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{url}/api/system/health", timeout=2) as resp:
                if resp.status == 200:
                    try:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data.get("status") in ("ok", "healthy"):
                            return True
                    except Exception:
                        # 健康检查响应异常按已启动处理
                        return True
        except Exception as e:
            logger.debug("health check connect failed: %s", e)
        time.sleep(1)
    return False


def start(open_browser=True, port=None):
    if port is None:
        port = find_free_port(8765)
    url = f"http://127.0.0.1:{port}"
    logger.info("[SERVER] Using port %s", port)
    kill_port(port)
    logger.info("[SERVER] Starting uvicorn in daemon thread...")

    def run_server():
        import uvicorn

        uvicorn.run("server:app", host="127.0.0.1", port=port, log_level="warning")

    threading.Thread(target=run_server, daemon=True).start()

    # 等待服务器就绪(健康检查 + 模块加载超时保护)
    logger.info("[SERVER] Waiting for health check...")
    ready = wait_for_server(url, timeout=30)
    logger.info("[SERVER] Health check result: %s", ready)
    if not ready:
        logger.warning("Server health-check failed after 30s, continuing anyway...")

    if open_browser:
        webbrowser.open(url)

    # 后台初始化技能引擎/大师Agent/数据源探针，避免阻塞主线程
    logger.info("[SERVER] Background init starting...")
    init_state = {"skills": 0, "agents": 0, "wf": False, "status": {}}

    def _background_init():
        s, a, w = init_skills()
        _, st = probe_data_sources()
        init_state.update(skills=s, agents=a, wf=w, status=st)

    threading.Thread(target=_background_init, daemon=True).start()
    time.sleep(0.5)  # 给后台线程一个启动窗口，不阻塞后续流程

    src_icons = (
        " ".join(
            f"{'+' if s.get('available') else '-'}{n[0].upper()}"
            for n, s in sorted(init_state["status"].items())
        )
        if init_state["status"]
        else "initializing..."
    )

    logger.info("[SERVER] Printing banner...")
    banner = f"""
+==================================================================+
|  AShare-X v{VERSION:<58}|
|  {url:<64}|
|  Skills: {init_state["skills"]:<3} Masters: {init_state["agents"]:<3} AgentWF: {"yes" if init_state["wf"] else "no":<5}                     |
|  Data sources: {src_icons:<52}|
|  Press Ctrl+C to stop                                            |
+==================================================================+
"""
    print(banner, flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown.")


# ════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AShare-X 启动器")
    parser.add_argument("--build", action="store_true", help="强制重建前端")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--update", action="store_true", help="启动前执行 git pull --ff-only")
    parser.add_argument("--skip-build", action="store_true", help="跳过前端构建检查")
    parser.add_argument("--port", type=int, default=8765, help="服务端口")
    args = parser.parse_args()

    logger.info("Python: %s", PYTHON)
    logger.info("Root: %s", ROOT)

    ensure_deps()
    ensure_dirs()
    ok, msgs = check_config()
    for msg in msgs:
        if msg.startswith("WARN"):
            logger.warning(msg)
        else:
            logger.info(msg)

    if args.update:
        git_update()

    need_build, reason = frontend_needs_build()
    if args.build or (need_build and not args.skip_build):
        logger.info("[BUILD] Triggered: %s", reason)
        build_frontend()
    elif args.skip_build:
        logger.info("[BUILD] Skipped by user")
    else:
        logger.info("[BUILD] Frontend up to date (%s)", reason)

    start(open_browser=not args.no_browser, port=args.port)
