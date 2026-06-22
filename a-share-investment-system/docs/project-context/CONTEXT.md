# AShare-X 智能投研系统 — 项目上下文摘要

## 项目简述

A股智能投资决策系统，多Agent多Skill协同框架，提供全市场选股、多风格策略评分、LLM驱动分析、组合管理、风险控制和交易执行的一站式量化投研能力。

## 技术栈

**前端**: Vue 3 + TypeScript + Element Plus + ECharts + Pinia + Vue Router 4 + Vite 5 + Axios + SCSS  
**后端**: Python 3.10+ / FastAPI / SQLAlchemy 2.0 / SQLite / Rich CLI / Uvicorn  
**核心库**: pandas, numpy, akshare, efinance, baostock, tushare (13个A股数据源)  
**LLM**: 6家Provider (DeepSeek/SiliconFlow/ChatAnywhere/Juguang/Cherryin/OpenRouter)  
**工具链**: Ruff, MyPy, Pytest 8.x, pre-commit, Bandit  

## 关键架构约定

- **4层分离**: API层(api/routes/)→ 业务逻辑层(services/)→ 数据提供层(providers/)→ 持久化层(shared/models/)。API层不做业务计算, Service层通过ServiceResult模式返回`{status, data, errors}`。
- **选股Pipeline**: 4阶段漏斗 (Stage1量化硬过滤→ Stage2四维评分→ Stage3大师Agent深度分析→ Stage4可选的LLM Agent分析), 由ScreeningPipeline统一编排。
- **数据源合并链**: 13个适配器按优先级(10→60)依次尝试, 增量合并直到STOCK_REQUIRED_FIELDS填满, 每个适配器有独立断路器。
- **DB优先缓存**: DatabaseBackedDataBus先读MarketSnapshot DB缓存, 再调用API回填。
- **配置分层**: 环境变量 > config/.env > config/config.yaml > config.json。
- **市场市值公约**: total_market_cap/float_market_cap 统一以亿元(100M CNY)存储。

## 核心数据模型速查

**ORM (17表)**: StockInfo(57字段,股票主数据), KlineCache(10字段), MarketSnapshot(type,data_json), FundMetricHist(40+字段,财务时序), DragonTiger(龙虎榜), Portfolio(持仓), TradeRecord, DailyReport, Watchlist(自选股), DailyNAV(净值), Order(订单), Trade(成交), SystemLog, AnalysisTask(任务), StyleSignal(风格信号), ScreenResult(选股运行), MigrationVersion(迁移版本)  
**Pydantic (25+模型)**: AnalysisOut, FavoriteItem/ListOut/CheckOut, TaskItem/ListOut/DetailOut/QueueOut, ReportItem/ListOut/DetailOut, SystemStatusOut/DatabaseHealthOut/SourceDetailOut/SourceHealthOut, DbStatsOut, KlineItem/Out, HotStockItem/Out, IndustryItem/DistOut, MarketStateOut, AgentHealthEntry/Out, MemoryDayOut/CalendarOut, SimilarDayOut/MarketsOut, StockInfoOut/ListOut, AddStockIn/EditStockIn, TradeRecord/TradeOutcome, EmailSettings  
**TypeScript (12接口)**: Recommendation, ScreeningData, Stage4Analysis, PipelineStats, ScreenStyle, Position, PortfolioSummary, PortfolioHoldings, NavPoint, StyleConfig, PortfolioConfig, LogEntry

## 核心API速查 (120+端点)

**选股**: GET /api/screening/run[?style] (触发后台异步), GET /api/screening/run/stream (SSE流式), GET /api/screening/status, POST /api/screening/abort, POST /api/screening/generate-plan, GET /api/screening/daily-summary  
**分析**: GET /api/analysis/{code} (→AnalysisOut), GET /api/analysis/v2/{code}[?analysts], GET /api/analysis/daily-review  
**持仓**: GET /api/portfolio/holdings[?type], POST /api/portfolio/holdings, PUT /api/portfolio/holdings/{code}/sell, GET /api/portfolio/nav, GET /api/portfolio/trades, POST /api/portfolio/nav/record  
**风险**: GET /api/risk/status, GET /api/risk/alerts, POST /api/risk/assess-stock, GET /api/risk/portfolio-var, GET /api/risk/stress-test  
**数据库**: GET /api/db/stats (→DbStatsOut), GET /api/db/stockinfo[search,page], POST /api/db/stockinfo (AddStockIn), POST /api/db/refresh, GET /api/db/hot-stocks, GET /api/db/kline/{code}, GET /api/db/data-by-date, GET /api/db/industry-distribution  
**报告/任务**: GET /api/reports, GET /api/reports/{id} (→ReportDetailOut), POST /api/tasks, GET /api/tasks, POST /api/tasks/{id}/cancel  
**AI/Quant**: GET /api/ai/market-state (→MarketStateOut), GET /api/ai/agent-health, GET /api/ai/memory/calendar, POST /api/quant-agent/daily-cycle, GET /api/quant-agent/daily-cycle/stream  
**工作流记忆**: GET /api/workflow/memory/trades, GET /api/workflow/memory/reflections, GET /api/workflow/memory/performance  
**绩效/因子**: GET /api/performance/metrics, GET /api/performance/nav-curve, POST /api/factor-validation/run  
**系统**: GET /api/system/status (→SystemStatusOut), GET /api/system/health, GET /api/logs/recent, GET /api/settings/email  
**WS**: /ws/logs (实时日志推送)
