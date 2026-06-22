# Book Skills Integration Plan

## 4 Books to Process (livermore ✅ already done)

| # | Book | Integration Level |
|---|------|-----------------|
| 1 | Turtle Trading (海龟交易法则) | FULL: SKILL.md + QuantAnalyzer + MasterAgent + Pipeline + Config + Frontend |
| 2 | Candlestick Chart (蜡烛图技术) | MEDIUM: SKILL.md + QuantAnalyzer + MasterAgent |
| 3 | Trader Vic (专业投机原理) | MEDIUM: SKILL.md + QuantAnalyzer + MasterAgent |
| 4 | Fooled by Randomness (随机漫步的傻瓜) | LITE: SKILL.md + references (TalebAnalyzer exists) |

## Files to Create/Modify

### Task 1: SKILL.md for 4 Books
- `quant-agents/turtle-trading/SKILL.md` + `references/core-rules.md`
- `quant-agents/candlestick-chart/SKILL.md` + `references/patterns.md`
- `quant-agents/trader-vic/SKILL.md` + `references/123-rule.md`
- `quant-agents/fooled-by-randomness/SKILL.md`

### Task 2: QuantAnalyzers (3 new methods)
- `services/quant_analyzers.py`: `turtle_analyze()`, `candlestick_analyze()`, `trader_vic_analyze()`

### Task 3: MasterAgents (3 new agents)
- `services/master_agents.py`: `TurtleMaster`, `CandlestickMaster`, `TraderVicMaster`

### Task 4: Turtle Trading Full Pipeline
- `config/config.yaml`: add `turtle` screening style
- `services/stock_screener.py`: add `_run_turtle_pipeline()`
- `api/routes/screening.py`: add `turtle` to STYLES/enums
- `frontend/src/types/screening.ts`: add turtle style
