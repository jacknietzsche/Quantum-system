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
cd a-share-investment-system
ruff check .                # lint
mypy .                     # typecheck
pytest tests/ -v            # all tests
pytest tests/unit/ -v       # unit tests only
```

## Repo Layout

```
Trading agent and skill/
├── a-share-investment-system/   ← Main app (Python + React)
│   ├── server.py                ← FastAPI entry, mounts all API routes
│   ├── launch.py                ← Launcher: auto-setup, git pull, build, start
│   ├── main.py                  ← CLI entry: analyze/daily/screen/serve/schedule/backtest
│   ├── models.py                ← SQLAlchemy ORM (SQLite)
│   ├── workflow.py              ← LangGraph workflow (basic)
│   ├── super_workflow.py        ← LangGraph super-workflow (full fusion)
│   ├── skills.py                ← SkillRegistry + RiskFirewall base classes
│   ├── multi_model_voter.py     ← Multi-model voting
│   ├── advanced_tools.py        ← Look-ahead bias audit, strategy monitor
│   ├── optimizations.py         ← Fault-tolerant nodes, risk quadrant, stress test
│   ├── api/routes/              ← FastAPI routers (portfolio, risk, signals, screening, etc.)
│   ├── services/                ← Domain logic (29 modules)
│   ├── providers/               ← Data providers (market_data, llm, cache, email)
│   ├── electron/                ← React/Vite/Tailwind frontend
│   ├── static/                  ← Built frontend output (served by FastAPI)
│   ├── config.json              ← Runtime config (API keys, risk params) — gitignored
│   ├── config/                  ← .env, config.yaml, compat layer
│   ├── data/                    ← SQLite DBs (investment.db, factors.db)
│   ├── tests/                   ← pytest suite (unit/, integration/, backtest/)
│   └── strategies/              ← YAML strategy definitions
└── quant-agents/                ← 12+ external quant AI projects (skill sources)
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

- `config.json` contains API keys — never commit it. `config.json.backup` is also a config file (not a code backup).
- `start_dev.cmd` references Vue3/v4.0.0 — stale. Use `launch.py` instead.
- `super_workflow.py` is 2355 lines — the full fusion pipeline. `workflow.py` is the simpler LangGraph version.
- `skills.py` at root is the skill registry/base classes. `services/skill_engine.py` is the engine that loads SKILL.md files. Different modules.
- `decision_review.py` is imported by `workflow.py` and `super_workflow.py` — not redundant.
- `openclaw-skill/` contains runner scripts for the super workflow.
- Coverage threshold is 50% (`--cov-fail-under=50` in pyproject.toml).

## Data Sources

Primary chain: akshare → baostock → tencent. Each provider wraps differently in `providers/market_data.py`. The `DatabaseBackedDataBus` pattern ensures SQLite cache is always checked first.

## Testing

- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/` (marked with `@pytest.mark.integration`)
- Backtest tests: `tests/backtest/`
- Slow tests: marked with `@pytest.mark.slow`
- Data tests: marked with `@pytest.mark.data` (fetch real market data)
