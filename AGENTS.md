# AGENTS.md — AShare-X Workspace

## Quick Reference

```bash
# Start server + browser (recommended)
python launch.py

# Start only API backend
python main.py serve --port 8765

# Fusion component check (no server)
python launch.py --check

# Frontend dev (hot reload)
cd a-share-investment-system/electron && npm run dev

# Lint / Typecheck / Test
cd ashare-x
ruff check .                # lint
mypy .                     # typecheck
pytest tests/ -v            # all tests
pytest tests/unit/ -v       # unit tests only
```

## Repo Layout

```
Trading agent and skill/
├── ashare-x/                  ← Main app (Python + FastAPI + React)
│   ├── server.py              ← FastAPI entry, mounts all API routes
│   ├── launch.py              ← Launcher: auto-setup, git pull, build, start
│   ├── main.py                ← CLI entry: analyze/daily/screen/serve/schedule/backtest
│   ├── graph/                 ← LangGraph trading_graph + conditional logic
│   ├── agents/                ← analyst / researcher / trader / risk / master agents
│   ├── services/              ← screening, portfolio, risk, factor_farm, market_perception, quant_analyzers
│   ├── skills/                ← 19 SKILL.md (auto-discovered by SkillEngine)
│   ├── api/routes/            ← FastAPI routers (analysis, backtest, data, portfolio, reports, screening, settings, trading_plan)
│   ├── providers/             ← Data providers (akshare, sina, tencent, yfinance)
│   ├── db/                    ← SQLAlchemy ORM (SQLite)
│   ├── tools/                 ← Stock data, technical indicators, news search
│   ├── memory/                ← Decision log, layered memory, vector store
│   ├── electron/              ← React/Vite/Tailwind frontend
│   ├── static/                ← Built frontend output
│   ├── config/                ← .env, config.yaml, user_config.yaml
│   ├── data/                  ← SQLite DBs
│   ├── tests/                 ← pytest suite (unit/, integration/)
│   └── strategies/            ← YAML strategy definitions
└── quant-agents/              ← External quant AI projects (skill sources)
    ├── a-share-skill/           ← 6 A-share trading skills
    ├── buffett-skills/          ← Buffett investment framework (8 refs)
    ├── munger-skill/            ← Munger mental models
    ├── taleb-skill/             ← Taleb antifragile framework
    ├── china-stock-research-skills/  ← 7 A-share research modules
    ├── ai-hedge-fund/           ← 17 master agent analyzers
    └── ...                      ← daily_stock_analysis, FinRobot, RD-Agent, etc.
```

## Architecture (non-obvious)

- **Data pattern**: DB-first. Read SQLite → if missing, fetch from provider chain (akshare → baostock → tencent) → backfill DB → return. `services/data_bus.py` orchestrates this.
- **SkillEngine** (`services/skill_engine.py`): Auto-discovers SKILL.md files from `quant-agents/` at runtime. 23+ skills found across 9 source projects. Searches both `a-share-investment-system/quant-agents/` and `../quant-agents/`.
- **Frontend**: React/Vite in `electron/`, built to `static/` and served by FastAPI. NOT Vue3 — do not replace.
- **API prefix**: All routes use `/api/` prefix. New routes go in `api/routes/` and register in `server.py`.
- **WebSocket**: `/ws/progress` and `/ws/screening` for real-time updates. `server.py` has `ConnectionManager` class.
- **Config hierarchy**: `config.json` (gitignored, runtime) > `config/config.yaml` (backup/reference) > `config/.env` (secrets). `config.json` is never committed.

## Critical Conventions

- **Python 3.10+ required**. Uses `match` statements, `X | Y` union types, `list[str]` lowercase generics.
- **Ruff for lint+format** (not black/isort directly). Config in `pyproject.toml`: line-length=100, double quotes, LF endings.
- **Finance domain**: Magic numbers in thresholds (PE ratios, risk percentages) are intentional — `PLR2004` is suppressed.
- **Windows encoding**: `main.py` wraps stdout/stderr with UTF-8 to handle GBK console issues.
- **Port range**: Server searches 8765-8775 for free port. Kills old processes on startup.

## Gotchas

- `config.json` contains API keys — never commit it.
- `launch.py` auto-finds free port 8765-8775 and starts the FastAPI + browser.
- `pyproject.toml` has `--cov-fail-under=50` coverage gate.

## Data Sources

Primary chain: akshare → baostock → tencent. Each provider wraps differently in `providers/market_data.py`. The `DatabaseBackedDataBus` pattern ensures SQLite cache is always checked first.

## Testing

- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/` (marked with `@pytest.mark.integration`)
- Backtest tests: `tests/backtest/`
- Slow tests: marked with `@pytest.mark.slow`
- Data tests: marked with `@pytest.mark.data` (fetch real market data)
