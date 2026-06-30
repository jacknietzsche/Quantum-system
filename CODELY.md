# CODELY.md — AShare-X Workspace

## Project Overview

**AShare-X** is a multi-agent collaborative A-share (Chinese stock market) intelligent investment research system. It simulates a real investment institution's decision-making pipeline: 12 specialized AI agents (analysts → researchers → trader → risk team → portfolio manager) analyze stocks through multi-round bull-bear debates and three-way risk debates, ultimately producing actionable trading plans (entry price / stop-loss / take-profit / position sizing).

**Core principle**: Pure API-based (no local LLM deployment), using only free data sources, designed for zero additional runtime cost. The LLM backend is DeepSeek API (OpenAI-compatible SDK), costing approximately ¥46–74/month for daily analysis of 10 stocks.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+ / FastAPI |
| Workflow Orchestration | LangGraph (StateGraph with conditional routing) |
| LLM | DeepSeek API (OpenAI-compatible), Qwen / GLM as alternates |
| Database | SQLite + SQLAlchemy 2.0 |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Visualization | lightweight-charts (K-line), ReactFlow (agent flow) |
| Desktop Shell | Electron |
| Vector Store | ChromaDB (RAG / long-term memory) |
| Backtesting | vectorbt |
| Data Sources | AKShare / BaoStock / Tencent / Sina / EastMoney (all free) |
| MCP Server | mcp package (exposes tools to Claude Desktop / Cursor) |

### Architecture Overview

```
ashare-x/
├── main.py                 ← CLI: analyze / daily / screen / backtest / plan / schedule / serve
├── server.py               ← FastAPI entry, mounts all API routers + serves static frontend
├── launch.py               ← One-click launcher: start server + open browser
├── mcp_server.py           ← MCP server: exposes tools to external AI clients
├── pyproject.toml          ← Project config (ruff, mypy, pytest, dependencies)
├── core/                   ← Config (singleton + hot reload), State (AgentState TypedDict), LLMClient, exceptions, i18n
├── db/                     ← SQLAlchemy ORM, engine, migrations (SQLite)
├── providers/              ← Data provider adapters (circuit breaker + retry + pool) + DatabaseFirstDataBus
│   └── sources/            ← tencent, sina, akshare, baostock, eastmoney adapters
├── tools/                  ← Stock data, technical indicators, fundamentals, news, social sentiment, paper trading
├── agents/                 ← Agent factory + 12 agents across 5 roles
│   ├── analysts/           ← market, fundamentals, news, sentiment (+ quant_signals)
│   ├── researchers/        ← bull, bear, research manager (multi-round debate)
│   ├── risk_mgmt/          ← aggressive, conservative, neutral, portfolio manager (3-way risk debate)
│   ├── trader/             ← trader (generates trade proposal)
│   └── masters/            ← master_selector + master_review (optional expert review)
├── graph/                  ← LangGraph trading_graph + conditional_logic (debate routing)
├── skills/                 ← SkillEngine: auto-discovers SKILL.md files, injects into agent prompts
│   └── engine.py           ← 19+ skills (buffett, munger, taleb, livermore, turtle, etc.)
├── services/               ← backtest, daily_plan, screening, portfolio, risk_engine, factor_farm, etc.
├── api/routes/             ← FastAPI routers: analysis, backtest, data, portfolio, reports, screening, settings, trading_plan
├── memory/                 ← Decision log, layered memory (short/mid/long-term), reflection, vector store
├── config/                 ← config.yaml (committable) + user_config.yaml + .env (secrets, gitignored)
├── tests/                  ← pytest suite: unit/, integration/, backtest/ (conftest.py)
└── electron/               ← React/Vite/Tailwind frontend (builds to ../static/)
```

### Workflow Pipeline (LangGraph)

```
START → market_analyst → fundamentals_analyst → news_analyst → sentiment_analyst
  → bull_researcher ⟷ bear_researcher  (multi-round investment debate)
  → research_manager → trader
  → aggressive_analyst ⟷ conservative_analyst ⟷ neutral_analyst  (3-way risk debate)
  → portfolio_manager
  → [conditional] master_selector → master_review → END
```

- **Debate termination**: Controlled by `investment_debate_rounds` / `risk_debate_rounds` counters in `AgentState`, with max rounds configurable per run (fast mode = 1 round, full mode = 2 rounds).
- **Budget-aware**: If token budget exceeds threshold, debates auto-terminate (`should_fast_mode` flag in `budget_snapshot`).
- **Master review**: Optional, toggled via `config.features.enable_masters`. Selects relevant master agents (Buffett, Munger, Taleb, etc.) based on stock characteristics.

### Key Design Patterns

- **DB-first data pattern**: Read SQLite → if missing, fetch from provider chain (tencent → sina → akshare) → backfill DB → return. Orchestrated by `providers/data_bus.py`.
- **Agent factory** (`agents/base.py`): Each agent is created via `create_agent()`, which auto-gathers real-time data, injects skills, collects prior agent reports, and pulls layered memory before calling the LLM.
- **SkillEngine** (`skills/engine.py`): Auto-discovers `SKILL.md` files with YAML frontmatter. Skills are bound to specific agents via the `agents` field in metadata and injected into system prompts at runtime.
- **Config singleton** (`core/config.py`): Thread-safe, mtime-based hot reload. Priority: env vars > `config/config.yaml` > code defaults. ENV mapping: `ASHARE_X_FOO_BAR` → `foo.bar`, `DEEPSEEK_API_KEY` → `llm.deepseek.api_key`.
- **Layered memory** (`memory/layered.py`): Short-term (current session state), mid-term (recent decisions per ticker), long-term (RAG via ChromaDB vector store).

## Building and Running

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- DeepSeek API key (free tier: 5M tokens/day)

### Setup

```bash
cd ashare-x

# Python environment
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

# Environment variables
cp .env.example .env            # Fill in DEEPSEEK_API_KEY
```

### Running the Application

```bash
# One-click: start API server + open browser
python launch.py

# Start API server only
python main.py serve --port 8765

# Frontend dev (hot reload)
cd electron && npm install && npm run dev

# Build frontend to static/ (served by FastAPI)
cd electron && npm run build:static
```

### CLI Commands

```bash
python main.py analyze 600519              # Single stock analysis (full mode)
python main.py analyze 600519 --fast       # Fast mode (1 debate round, no masters)
python main.py analyze 600519 --masters    # Enable master agent review
python main.py daily                       # Daily data update
python main.py screen --style balanced     # Market screening (value/growth/momentum/balanced)
python main.py backtest 600519,000858      # Strategy backtest
python main.py plan                         # Generate daily trading plan
python main.py plan --show                 # Show today's plan without regenerating
python main.py schedule                    # Start daily scheduler (09:00 data, 09:30 screen, 15:10 plan)
```

### MCP Server (for external AI clients)

```bash
python mcp_server.py
# Configure in Claude Desktop's claude_desktop_config.json
```

## Linting, Type Checking, and Testing

```bash
cd ashare-x

# Lint
ruff check .

# Format
ruff format .

# Type check
mypy .

# Run all backend tests
pytest tests/ -v

# Run unit tests only
pytest tests/unit/ -v

# Run API contract tests (validates frontend/backend field compatibility)
pytest tests/integration/test_api_contract.py -v --no-cov

# Run integration tests
pytest tests/integration/ -v -m integration

# Run with coverage (50% gate enforced)
pytest tests/ -v --cov

# Frontend unit tests (Vitest + React Testing Library)
cd electron && npm run test

# E2E browser tests (Playwright — requires built frontend + running backend)
cd electron && npm run test:e2e

# Unified test runner (all layers in sequence)
python run_all_tests.py              # Full suite
python run_all_tests.py --skip-e2e  # Skip browser tests
python run_all_tests.py --backend   # Backend only
python run_all_tests.py --frontend  # Frontend only
```

### Test Markers

- `@pytest.mark.unit` — Unit tests (no external dependencies)
- `@pytest.mark.integration` — Integration tests
- `@pytest.mark.slow` — Slow tests
- `@pytest.mark.data` — Tests that fetch real market data (require network)

### Test Architecture (4 Layers)

| Layer | Framework | Location | What it tests |
|-------|-----------|----------|---------------|
| Backend Unit | pytest + mocks | `tests/unit/` | Individual modules (config, DB, providers, agents, services) |
| API Contract | pytest + TestClient | `tests/integration/test_api_contract.py` | Every API endpoint returns the exact fields the frontend expects |
| Frontend Unit | Vitest + React Testing Library | `electron/src/**/__tests__/` | Component rendering, user interactions, API call patterns |
| E2E Browser | Playwright | `electron/e2e/` | Real browser → backend → DB full-stack user flows |

**Frontend test setup**: `NODE_ENV=development` is required for npm install (devDependencies are skipped when `NODE_ENV=production`). The `vitest.config.js` uses jsdom environment with mocked `lightweight-charts`. API calls are mocked via `vi.hoisted()` pattern with matchers per endpoint. E2E tests use CSS selectors (not Chinese text) due to encoding differences in built output.

## Development Conventions

### Python

- **Python 3.10+ required**: Uses `match` statements, `X | Y` union types, `list[str]` lowercase generics.
- **Ruff** for both linting and formatting (not black/isort). Config in `pyproject.toml`:
  - `line-length = 100`
  - `quote-style = "double"`
  - `line-ending = "lf"`
  - `target-version = "py310"`
- **MyPy**: Progressive type checking (`disallow_untyped_defs = false`). Many third-party modules have `ignore_missing_imports = true`.
- **Suppressed rules** (intentional):
  - `PLR2004` (magic-value-comparison): Financial thresholds (PE ratios, risk percentages) are domain conventions.
  - `PLR0913` (too-many-arguments): Agent functions naturally have many parameters.
  - `RUF001/002/003` (ambiguous Unicode): Project uses Chinese text and full-width symbols extensively.
  - `PLC0415` (local import): Intentional lazy loading pattern.
- **Coverage gate**: `--cov-fail-under=50` in `pyproject.toml`.
- **Windows encoding**: `main.py` wraps stdout/stderr with UTF-8 to handle GBK console issues. SKILL.md parser strips UTF-8 BOM (PowerShell 5 artifact).

### Frontend

- React 18 + TypeScript, built with Vite.
- Tailwind CSS for styling.
- **NOT Vue3** — do not replace.
- ESLint with `--max-warnings 0` gate.
- Build output goes to `static/` (served by FastAPI at `/`).
- API types can be generated from OpenAPI schema: `npm run generate:types`.

### API Conventions

- All routes use `/api/` prefix. New routes go in `api/routes/` and register in `server.py`.
- WebSocket endpoints: `/ws/progress` and `/ws/progress` for real-time updates.
- CORS is enabled for all origins (`allow_origins=["*"]`).
- Server searches ports 8765–8775 for a free port on startup.

### Configuration

- **Config hierarchy** (high → low priority):
  1. Environment variables (`ASHARE_X_*`, `*_API_KEY`)
  2. `config/config.yaml` (committable, no secrets)
  3. Code defaults
- **`config.json`** (runtime, gitignored) — never commit; contains API keys.
- **`.env`** — secrets only, never committed.

### Data Sources

Primary chain: tencent → sina → eastmoney → tickflow → tushare → akshare → yfinance. Each provider wraps differently in `providers/sources/`. The `DatabaseFirstDataBus` ensures SQLite cache is always checked first. Circuit breaker (3 failures → 300s cooldown) and exponential backoff retry (3 attempts) protect against provider failures.

### Budget Management

- Budget tracked in **RMB monthly cost** (not token count). Token counting distinguishes `input` / `output` / `cached_input` separately.
- Default budget: ¥100/month (configurable via `ASHARE_X_MONTHLY_BUDGET_RMB`).
- Three-tier degradation: 80% warn → 100% auto-fast-mode → 120% halt non-urgent tasks.
- Full mode ≈ ¥74/month (10 stocks/day), fast mode ≈ ¥46/month (with 60% cache hit).

## Repository Structure

```
Trading agent and skill/
├── ashare-x/              ← Main application (Python + FastAPI + React)
├── quant-agents/          ← External quant AI projects (skill knowledge sources)
│   ├── a-share-skill/       ← 6 A-share trading skills
│   ├── buffett-skills/      ← Buffett investment framework
│   ├── munger-skill/        ← Munger mental models
│   ├── taleb-skill/         ← Taleb antifragile framework
│   ├── china-stock-research-skills/  ← 7 A-share research modules
│   ├── ai-hedge-fund/       ← 17 master agent analyzers
│   └── ...                  ← FinRobot, RD-Agent, TradingAgents, etc.
├── skill/                 ← Trading skill/knowledge resources (books & methods)
├── project-design/        ← 15 design documents (S01–S15)
├── experiments/           ← Prototyping experiments (exp1–exp14) with real data
├── deliverables/          ← Deliverables
└── AGENTS.md              ← Agent workspace quick reference
```

### Project Design Documents (`project-design/`)

15 modules covering the full system architecture: problem definition (S01), design philosophy (S02), system architecture (S03), agent system (S04), data layer (S05), workflow engine (S06), skill system (S07), risk management (S08), memory & learning (S09), frontend (S10), tech stack (S11), roadmap (S12), references (S13), API design (S14), LLM layer (S15).

### Experiments (`experiments/`)

14 experiments validating design decisions with real data: data layer, technical indicators, AKShare data, LangGraph workflow, LLM API, data pipeline, full workflow, SSE streaming, portfolio optimization, SQLite, report storage, medium/low defects, and **exp14** (real DeepSeek API pricing — the basis for all budget calculations).
