# AShare-X — 操作备忘录

## 启动方式

| 命令 | 用途 |
|------|------|
| `python launch.py` | 生产模式：构建前端 + 启动后端 + 开浏览器 |
| `python launch.py --dev` | 开发模式：启动后端 + 前端 dev server (5173) |
| `python launch.py --check` | 全组件检测 |
| `python main.py analyze 600519` | CLI 单股分析 |
| `python main.py serve` | 仅启动 API |
| `python main.py daily` | 日频分析 + 报告 |
| `python main.py screen` | 全市场选股 |
| `start.cmd` / `start_dev.cmd` | Windows 双击入口 |

**关键**: `launch.py` 通过 `uvicorn.run("server:app", ...)` 启动。`server.py` 负责 WebSocket + 静态文件 + 全部 API 路由注册。

## API 路由

全部注册于 `server.py`，13 个模块：`/api/{portfolio,risk,reports,signals,screening,analysis,tasks,favorites,logs,db,fusion,market,system}`。对应源文件在 `api/routes/` 下。

## 数据库模型 — 注意过渡状态

**模型文件**: `shared/models.py` 是统一的 ORM 模型定义文件。

## 前端

- Vue 3 + Element Plus + Vite + TypeScript
- build 输出到 `static/`（由 `vite.config.ts` 的 `outDir: '../static'` 控制）
- dev 时 `src/` 源码变更后 vite **自动热更新**前端（无需手动刷新或重启前端）
- API 代理：dev 模式下 `/api` 请求自动转发到 `127.0.0.1:8765`
- 构建命令：`npm run build:quick`（跳过类型检查，快速构建）

## 配置文件层级

`shared/config.py` 加载顺序：环境变量 > `.env` > `config/config.yaml` > `config.json`（旧格式回退）。
- **新配置源**: `config/config.yaml` + `config/.env`
- **旧配置源**: `config.json`（`providers/market_data.py`、`scripts/` 等仍直接读取）
- 修改配置时尽量更新 `config/config.yaml`，同时保持 `config.json` 兼容性

## 用到的 key 依赖

| 包 | 用途 |
|----|------|
| fastapi + uvicorn | API 服务器 |
| sqlalchemy | ORM |
| akshare / efinance | A股数据源 |
| rich | CLI 表格输出 |
| langgraph | 多 Agent 工作流 |
| skills.py + services/skill_engine.py | 技能框架 |
| multi_model_voter.py | 多模型集成 |

## 测试

```bash
pytest                           # 全量测试（含覆盖率）
pytest -m "not slow"             # 跳过慢测试
python tests/integration_test_api.py  # API 集成测试（需先启动 server）
```

dev dependencies: `pytest>=8.0`, `ruff>=0.11.0`, `mypy>=1.15`, `black>=24.0`, `isort>=6.0`, `pre-commit>=4.0`, `bandit>=1.8`。

## 代码检查

```bash
ruff check .                     # lint
ruff format --check .            # format check
mypy .                           # type check
```

pyproject.toml 已配置所有工具（ruff line-length=100, quote-style=double; mypy python_version=3.10 等）。

## 服务层（`services/`）

关键文件快速索引：
- `market.py` — 实时行情/指数/资金流
- `portfolio.py` — 持仓/交易记录
- `risk_engine.py` — 风险评估
- `stock_screener.py` — 选股器
- `quant_analyzers.py` — 量化指标
- `skill_engine.py` + `master_agents.py` — 融合架构引擎
- `data_mgmt.py` — 数据库备份/维护
- `backtest_loop.py` — 回测引擎

## 架构注意事项

- `shared/models.py`：统一的 ORM 模型定义
- `server.py`：生产入口，含 FastAPI app + WebSocket
- `config.json` vs `config/config.yaml`：项目在从 `config.json` 向 `config/config.yaml` 迁移中，两套共存
- API routes 混用 `from models import get_session` 和 `from shared.db_service import ...`，添加新路由时保持一致
- 前端构建产物在 `static/`（不是 `frontend/dist/`），`server.py` 从 `static/` 提供静态文件
