# 3. Skill 系统设计

## 3.1 Skill 定义规范

```python
class SkillSchema(BaseModel):
    """Skill 注册标准 Schema"""
    name: str              # 唯一标识, 如 "market.fetch_indices"
    description: str       # 自然语言描述, 供 LLM 理解用途
    category: Literal["data", "quant", "report", "communication", "memory"]
    input_schema: dict     # JSON Schema 定义输入参数
    output_schema: dict    # JSON Schema 定义输出格式
    timeout: int = 30      # 超时秒数
    retry: int = 1         # 重试次数
    cache_ttl: int = 300   # 缓存有效期秒数

class SkillResult(BaseModel):
    """Skill 执行结果"""
    success: bool
    data: Any = None
    error: str | None = None
    latency_ms: int
    tokens_used: int = 0
    cache_hit: bool = False
```

## 3.2 核心 Skill 清单

### Data Skills

| Skill 名称 | 功能 | 参数 | 复用现有代码 |
|------------|------|------|-------------|
| `data.fetch_kline` | 获取日 K 线 | stock_code, start_date, end_date, freq='D' | `providers/market_data.py` |
| `data.fetch_fundamentals` | 获取基本面 | stock_code, fields=['pe','pb','roe',...] | `providers/market_data.py` |
| `data.fetch_index` | 获取指数行情 | index_code='000001.SH', days=60 | `providers/market_data.py` |
| `data.fetch_money_flow` | 获取资金流向 | stock_code, days=5 | `providers/sources/eastmoney.py` |
| `data.fetch_sectors` | 获取行业板块 | date | `providers/sources/board_rank.py` |
| `data.fetch_hot_stocks` | 获取热榜 | limit=50 | `providers/sources/hot_rank.py` |
| `data.fetch_dragon_tiger` | 获取龙虎榜 | date | `providers/sources/lhb.py` |
| `data.refresh_stock_info` | 刷新股票基础信息 | stock_codes | `services/stock_populator.py` |
| `data.check_data_freshness` | 检查数据新鲜度 | date | `services/data_bus.py` |

### Quant Skills

| Skill 名称 | 功能 | 参数 | 复用现有代码 |
|------------|------|------|-------------|
| `quant.calculate_factors` | 计算多因子值 | stock_code, factor_list | `services/factor_farm.py` |
| `quant.hard_filter` | 18 条件硬过滤 | universe, date | `services/hard_filter.py` |
| `quant.factor_ranking` | 因子排名 | universe, factor_name | `services/factor_farm.py` |
| `quant.master_score` | 大师风格评分 | stock_code, master_name | `services/master_agents.py` |
| `quant.debate_analysis` | LLM 多空辩论 | stock_code, context | `services/debate_engine.py` |
| `quant.risk_score` | 风险评分 | stock_code | `services/risk_engine.py` |
| `quant.market_regime` | 市场状态诊断 | date | `services/market_perception.py` |
| `quant.screening_pipeline` | 完整选股漏斗 | style, universe, date | `services/screening/pipeline.py` |

### Report Skills

| Skill 名称 | 功能 | 参数 | 说明 |
|------------|------|------|------|
| `report.generate_markdown` | 生成 Markdown 报告 | data, template | 新增 |
| `report.generate_html` | 生成 HTML 报告 | markdown, css_theme | 新增 |
| `report.generate_pdf` | 生成 PDF 报告 | html | 使用 weasyprint |
| `report.generate_chart` | 生成图表图片 | chart_spec | ECharts 服务端渲染 |

### Communication Skills

| Skill 名称 | 功能 | 参数 | 说明 |
|------------|------|------|------|
| `comm.send_email` | 发送邮件 | to, subject, html_body | QQ 邮箱 SMTP |
| `comm.send_qq_mail` | QQ 邮箱快捷发送 | to, subject, html_body | 预设 SMTP 配置 |

### Memory Skills

| Skill 名称 | 功能 | 参数 | 说明 |
|------------|------|------|------|
| `memory.store_run` | 存储分析运行记录 | run_id, goal, result | 写入 AgentRun 表 |
| `memory.store_reflection` | 存储复盘结果 | date, predictions, actuals | 写入 Reflection 表 |
| `memory.retrieve_predictions` | 检索历史预测 | date_range | 查询 AgentRun + ScreenResult |
| `memory.get_similar_market` | 查找相似市场 | current_regime, top_k=3 | FAISS 向量检索 |

## 3.3 Skill 执行引擎

```python
class SkillExecutor:
    """Skill 执行引擎"""
    
    def __init__(self, cache: SkillCache, tracer: SkillTracer):
        self.cache = cache
        self.tracer = tracer
        self.registry: dict[str, Callable] = {}
    
    def register(self, skill: SkillSchema, handler: Callable):
        """注册 Skill"""
        self.registry[skill.name] = SkillWrapper(skill, handler)
    
    async def execute(self, name: str, params: dict) -> SkillResult:
        """执行 Skill, 含缓存/追踪/超时/重试"""
        wrapper = self.registry[name]
        # 1. 查缓存
        cache_key = f"{name}:{hash(frozenset(params.items()))}"
        if cached := await self.cache.get(cache_key):
            return SkillResult(success=True, data=cached, cache_hit=True)
        # 2. 执行, 含超时和重试
        start = time.time()
        with self.tracer.span(name) as span:
            result = await wrapper.execute(params)
        # 3. 写缓存
        await self.cache.set(cache_key, result.data, ttl=wrapper.schema.cache_ttl)
        return result
```

---

**上一节**: [02-agent-architecture.md](02-agent-architecture.md)
**下一节**: [04-workflow-engine.md](04-workflow-engine.md)
