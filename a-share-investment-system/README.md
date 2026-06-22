# A-Share Investment System

> **Warning: This project is under active development and NOT production-ready.**
> Many features are incomplete, unstable, or subject to breaking changes.
> Use at your own risk. This is NOT financial advice.

An AI-powered A-share (Chinese stock market) investment analysis system featuring multi-source data aggregation, multi-style stock screening, and LLM-driven analysis.

## Features

- **Multi-Source Data Chain**: Tencent, Sina, AKShare, Tushare, Baostock, EFinance, TickFlow with automatic failover and circuit breaker
- **Multi-Style Stock Screening**: Value, Momentum, Limit-Up, Hybrid styles with configurable thresholds
- **17 Investment Masters**: Buffett, Graham, Lynch, Taleb, Cathie Wood, Burry, Livermore, and more
- **LLM-Powered Analysis**: DeepSeek, SiliconFlow, and other LLM providers for stock analysis
- **Portfolio Management**: 3 independent portfolio modes with NAV tracking and trade records
- **Vue 3 Frontend**: Modern SPA with Element Plus, ECharts, and TypeScript
- **FastAPI Backend**: RESTful API with 14 route modules

## Project Status

| Module | Status | Notes |
|--------|--------|-------|
| Data Sources | Partial | Tencent/Sina stable; AKShare/Tushare flaky; Baostock/EFinance/TickFlow often unreachable |
| Screening Engine | Working | 4 styles functional, ~6000 stock universe |
| Master Agents | Working | 17 investment master analyzers |
| LLM Analysis | Working | Requires API key configuration |
| Portfolio | Working | 3 modes with trade tracking |
| Frontend | Working | Vue 3 SPA with dashboard, screening, portfolio views |
| Backtest | Incomplete | Basic framework exists, needs refinement |
| Risk Engine | Incomplete | Core logic present, not fully tested |
| Skill System | Experimental | 14 skills, discovery and injection framework |

## Tech Stack

- **Backend**: Python 3.10+ / FastAPI / SQLAlchemy 2.0 / SQLite
- **Frontend**: Vue 3 / Element Plus / Pinia / ECharts / TypeScript
- **Data Sources**: Tencent, AKShare, Baostock, EastMoney, Sina, EFinance, Tushare, TickFlow
- **LLM**: DeepSeek, SiliconFlow, ChatAnywhere, Juguang, Cherryin, OpenRouter

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- LLM API key (at least one provider)

### Setup

```bash
# Clone
git clone https://github.com/jacknietzsche/A-share-investment-system.git
cd A-share-investment-system

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp config/.env.example config/.env
# Edit config/.env with your API keys

# Initialize database
python -c "from shared.models import init_db; init_db()"

# Launch (auto git pull + frontend build + start)
python launch.py
```

### CLI Usage

```bash
python main.py analyze <code>   # Single stock deep analysis
python main.py screen           # Full market screening
python main.py daily            # Daily analysis + report
python main.py backtest         # Backtest
python main.py skills           # List skills and master agents
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

## Configuration

All configuration is in `config/config.yaml` (YAML) and `config/.env` (environment variables).

- **LLM keys**: Set in `config/.env` (DEEPSEEK_API_KEY, SILICONFLOW_API_KEY, etc.)
- **Screening thresholds**: Configure in `config/config.yaml` under `screening.styles`
- **Data source priority**: Adjustable in `providers/market_data.py`

## Architecture

```
a-share-investment-system/
├── api/routes/        # FastAPI endpoints (14 route files)
├── services/          # Core business logic (32 files)
├── core/              # New modular architecture (migration target)
├── providers/         # Data source adapters (12 sources)
├── shared/            # Shared models, config, DB
├── config/            # config.yaml + .env
├── frontend/          # Vue 3 SPA (Vite)
├── skills/            # 14 investment skill directories
├── workflows/         # LangGraph workflow nodes
└── tests/             # unit/ integration/ e2e/
```

## Testing

```bash
pytest tests/unit/ -v                            # Unit tests
pytest tests/integration/ -v                     # Integration tests
pytest tests/ -m "not slow"                      # Skip slow tests

# Lint
ruff check .
ruff format . --check
```

## Disclaimer

This project is for **educational and research purposes only**. It is NOT financial advice. The authors are not responsible for any investment decisions made based on this software. Always do your own research and consult qualified financial advisors before making investment decisions.

## License

This project is for personal learning and research. No license specified yet.
