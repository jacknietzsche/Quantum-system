# 5. 数据库设计

## 5.1 核心表（精简至 8 张）

### 保留的现有表

**stock_info** — 股票主数据（50+ 字段, 详见 `shared/models/market.py`）
**kline_cache** — K 线数据缓存
**daily_nav** — 每日净值
**portfolio** — 持仓记录

### 新增表

#### agent_runs — Agent 运行记录

```sql
CREATE TABLE agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    goal TEXT NOT NULL,                    -- 用户原始意图
    plan_json TEXT NOT NULL,               -- ExecutionPlan JSON
    status TEXT NOT NULL DEFAULT 'pending',-- pending/running/completed/failed
    tokens_used INTEGER DEFAULT 0,
    cost_estimate REAL DEFAULT 0.0,
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### skill_executions — Skill 调用记录

```sql
CREATE TABLE skill_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    input_params TEXT,
    output_result TEXT,
    success BOOLEAN NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    cache_hit BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);
CREATE INDEX idx_skill_exec_run ON skill_executions(run_id);
CREATE INDEX idx_skill_exec_name ON skill_executions(skill_name);
```

#### daily_reports — 日频报告（重构）

```sql
CREATE TABLE daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL UNIQUE,
    market_summary TEXT,
    recommendations_json TEXT NOT NULL,
    report_markdown TEXT,
    report_html TEXT,
    report_pdf_path TEXT,
    email_sent BOOLEAN DEFAULT 0,
    email_to TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_reports_date ON daily_reports(report_date);
```

#### reflections — 复盘记录

```sql
CREATE TABLE reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    predictions_json TEXT NOT NULL,
    actuals_json TEXT NOT NULL,
    accuracy REAL,
    avg_return REAL,
    improvement_suggestions TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_reflections_date ON reflections(trade_date);
```

## 5.2 表关系

```
agent_runs (1) ──── (N) skill_executions
     │
     └─── (1:1) daily_reports

daily_reports (1) ──── (1) reflections (同一天)
```

---

**上一节**: [04-workflow-engine.md](04-workflow-engine.md)
**下一节**: [06-api-design.md](06-api-design.md)
