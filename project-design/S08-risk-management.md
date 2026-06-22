# S8 — 风险管理框架

## 8.1 三层风险体系

| 层级 | 监控内容 | 检测方法 | 处置 |
|------|----------|----------|------|
| **L1 市场风险** | 市场状态（牛市/熊市/恐慌/过热） | 指数涨跌+涨跌家数+成交量+北向资金 | 自适应仓位上限 |
| **L2 个股风险** | 个股波动率、流动性、止损信号 | 历史波动率+日均成交额+持仓亏损 | 个股仓位限制 |
| **L3 组合风险** | 集中度、相关性、压力测试 | 相关性矩阵+行业暴露+VaR | 组合层面限制 |

## 8.2 市场状态检测算法

### 输入数据

| 指标 | 来源 | 周期 | 说明 |
|------|------|------|------|
| 上证指数涨跌幅 | 腾讯/AKShare | 20日 | 中期趋势 |
| 涨跌家数比 | AKShare | 当日 | 市场广度 |
| 成交量比率 | 腾讯 | 20日均值 | 活跃度 |
| 北向资金净流入 | AKShare | 5日累计 | 外资态度 |

### 检测算法

```python
def detect_market_state(indices_data: dict) -> str:
    """
    市场状态检测:
    1. 上证20日涨跌幅
    2. 涨跌家数比
    3. 成交量/20日均量
    4. 北向资金5日净流入
    综合评分 → 市场状态
    """
    sh_change_20d = indices_data.get("sh_change_20d", 0)
    advance_count = indices_data.get("advance_count", 0)
    decline_count = indices_data.get("decline_count", 0)
    volume = indices_data.get("volume", 0)
    volume_ma20 = indices_data.get("volume_ma20", volume)
    north_flow_5d = indices_data.get("north_flow_5d", 0)

    total = advance_count + decline_count
    advance_ratio = advance_count / total if total > 0 else 0.5
    volume_ratio = volume / volume_ma20 if volume_ma20 > 0 else 1.0

    score = 0
    # 趋势
    if sh_change_20d > 0.05: score += 2
    elif sh_change_20d > 0: score += 1
    elif sh_change_20d < -0.05: score -= 2
    elif sh_change_20d < 0: score -= 1

    # 广度
    if advance_ratio > 0.65: score += 1
    elif advance_ratio < 0.35: score -= 1

    # 活跃度
    if volume_ratio > 1.5: score += 1
    elif volume_ratio < 0.5: score -= 1

    # 外资
    if north_flow_5d > 50: score += 1    # 50亿以上净流入
    elif north_flow_5d < -50: score -= 1

    # 映射到状态
    if score >= 4: return "BULL"
    if score >= 1: return "NEUTRAL"
    if score >= -1: return "NEUTRAL"
    if score >= -4: return "BEAR"
    return "PANIC"
```

### 市场状态与仓位上限

```python
def get_position_cap(state: str) -> float:
    caps = {
        "PANIC": 0.10,    # 恐慌：最多10%
        "BEAR": 0.30,     # 熊市：最多30%
        "NEUTRAL": 0.60,  # 中性：最多60%
        "BULL": 0.80,     # 牛市：最多80%
        "OVERHEAT": 0.50  # 过热：最多50%
    }
    return caps.get(state, 0.50)
```

## 8.3 交易计划输出格式

```python
class TradingPlan(BaseModel):
    ticker: str
    stock_name: str
    date: str
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float              # 0-100%
    current_price: float
    entry_price: float             # 建议入场价
    stop_loss: float               # 止损价
    take_profit: float             # 止盈价
    position_size: float           # 建议仓位金额
    position_pct: float            # 占总资金比例
    time_horizon: Literal["short", "medium", "long"]
    review_date: str               # 下次review日期
    thesis: str                    # 投资论据（一句话）
    key_factors: list[str]         # 关键因素
    risks: list[str]               # 主要风险
    invalidation: str              # 论据失效条件
    source_agents: list[str]       # 参与决策的Agent
    debate_summary: str            # 辩论摘要
```

## 8.4 模拟交易

A股规则硬编码：
- T+1：当日买入次日才能卖出
- 100股整数倍
- 涨跌停限制（±10%，ST ±5%）
- 手续费：佣金(万2.5) + 印花税(千1，仅卖出) + 过户费(十万分之一)

## 8.5 回测引擎

### 回测范围

**仅回测量化因子，不回测LLM决策**（原因见S03 Section 3.11）。

| 回测类型 | 可信度 | 说明 |
|----------|--------|------|
| 因子回测 | 高 | PE/ROE/动量等量化因子的历史表现 |
| 纸上交易 | 中 | 每日记录交易计划，30/60/90天后统计 |
| 滚动分析 | 中 | 每天重新分析，验证LLM选股质量 |

### 回测指标

```python
class BacktestMetrics(BaseModel):
    """回测结果指标"""
    total_return: float                   # 总收益率
    annualized_return: float              # 年化收益率
    max_drawdown: float                   # 最大回撤
    sharpe_ratio: float                   # 夏普比率（无风险利率2%）
    win_rate: float                       # 胜率
    profit_loss_ratio: float              # 盈亏比
    total_trades: int                     # 总交易次数
    avg_holding_days: float               # 平均持仓天数
    turnover_rate: float                  # 换手率
    benchmark_return: float               # 基准收益率（沪深300）
    alpha: float                          # 超额收益
```

### A股规则模拟

```python
class AShareBroker:
    """A股Broker模拟（Backtrader模式）"""

    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}                # {stock_code: Position}
        self.trade_history = []

    def buy(self, stock_code: str, price: float, quantity: int, date: str) -> bool:
        """
        买入检查:
        - 100股整数倍
        - T+1: 不影响买入
        - 手续费: 佣金(万2.5) + 过户费(十万分之一)
        - 资金充足性
        """
        if quantity % 100 != 0:
            return False  # 必须100股整数倍

        cost = price * quantity
        commission = max(cost * 0.00025, 5)  # 佣金最低5元
        transfer_fee = cost * 0.00001
        total_cost = cost + commission + transfer_fee

        if total_cost > self.cash:
            return False  # 资金不足

        self.cash -= total_cost
        self.positions[stock_code] = Position(
            stock_code=stock_code,
            buy_price=price,
            quantity=quantity,
            buy_date=date,
        )
        return True

    def sell(self, stock_code: str, price: float, date: str) -> bool:
        """
        卖出检查:
        - T+1: 当日买入不能卖出
        - 手续费: 佣金(万2.5) + 印花税(千1) + 过户费(十万分之一)
        """
        pos = self.positions.get(stock_code)
        if not pos:
            return False

        if pos.buy_date == date:
            return False  # T+1限制

        revenue = price * pos.quantity
        commission = max(revenue * 0.00025, 5)
        stamp_tax = revenue * 0.001       # 印花税仅卖出
        transfer_fee = revenue * 0.00001
        net_revenue = revenue - commission - stamp_tax - transfer_fee

        self.cash += net_revenue
        del self.positions[stock_code]
        return True

    def check_limit(self, stock_code: str, price: float, prev_close: float) -> str:
        """
        涨跌停检查:
        - 普通股: ±10%
        - ST股: ±5%
        - 返回: "normal" / "limit_up" / "limit_down"
        """
        change_pct = (price - prev_close) / prev_close
        limit = 0.05 if is_st(stock_code) else 0.10

        if change_pct >= limit:
            return "limit_up"
        elif change_pct <= -limit:
            return "limit_down"
        return "normal"
```

### 回测数据源

| 数据 | 来源 | 用途 |
|------|------|------|
| 历史K线 | BaoStock | 价格/成交量 |
| 财务数据 | BaoStock | PE/PB/ROE |
| 指数数据 | BaoStock | 基准对比（沪深300） |
| 交易日历 | AKShare | 判断交易日 |

### 回测流程

```python
def run_factor_backtest(
    factor_fn,                            # 因子计算函数
    stock_pool: list[str],                # 股票池
    start_date: str,                      # 回测开始日期
    end_date: str,                        # 回测结束日期
    rebalance_days: int = 5,              # 调仓周期（天）
) -> BacktestMetrics:
    """
    因子回测流程:
    1. 获取历史数据
    2. 每个调仓日，计算因子评分
    3. 选出Top N股票
    4. 模拟买入/卖出
    5. 计算回测指标
    """
    broker = AShareBroker()
    # ... 执行回测逻辑
    return calculate_metrics(broker)
```

## 8.6 选股评分公式

### 多因子评分模型（0-100分）

```python
def compute_stock_score(stock: dict, style: str = "balanced") -> float:
    """
    多因子评分公式:
    - 价值因子 (25%): PE评分 + PB评分 + 股息率评分
    - 成长因子 (25%): 营收增速评分 + 利润增速评分
    - 动量因子 (25%): 20日涨幅评分 + RSI评分
    - 质量因子 (25%): ROE评分 + 现金流评分

    style参数可调整权重:
    - "value": 价值40%, 成长20%, 动量20%, 质量20%
    - "growth": 价值20%, 成长40%, 动量20%, 质量20%
    - "momentum": 价值20%, 成长20%, 动量40%, 质量20%
    - "balanced": 各25%
    """
    weights = {
        "balanced": {"value": 0.25, "growth": 0.25, "momentum": 0.25, "quality": 0.25},
        "value": {"value": 0.40, "growth": 0.20, "momentum": 0.20, "quality": 0.20},
        "growth": {"value": 0.20, "growth": 0.40, "momentum": 0.20, "quality": 0.20},
        "momentum": {"value": 0.20, "growth": 0.20, "momentum": 0.40, "quality": 0.20},
    }
    w = weights.get(style, weights["balanced"])

    # 价值因子: PE越低越好, PB越低越好, 股息率越高越好
    pe_score = max(0, min(100, 100 - (stock.get("pe_ratio", 50) - 10) * 3))
    pb_score = max(0, min(100, 100 - (stock.get("pb_ratio", 5) - 0.5) * 20))
    div_score = max(0, min(100, stock.get("dividend_yield", 0) * 20))
    value_score = (pe_score * 0.4 + pb_score * 0.3 + div_score * 0.3)

    # 成长因子: 营收增速越高越好, 利润增速越高越好
    rev_growth = stock.get("revenue_growth", 0) * 100  # 转为百分比
    profit_growth = stock.get("profit_growth", 0) * 100
    growth_score = max(0, min(100, (rev_growth + profit_growth) / 2 + 50))

    # 动量因子: 20日涨幅适中最好(5-15%), RSI适中最好(40-60)
    change_20d = stock.get("change_pct_20d", 0) * 100
    momentum_price = max(0, min(100, 100 - abs(change_20d - 10) * 5))
    rsi = stock.get("rsi_14", 50)
    momentum_rsi = max(0, min(100, 100 - abs(rsi - 55) * 3))
    momentum_score = (momentum_price * 0.5 + momentum_rsi * 0.5)

    # 质量因子: ROE越高越好, 现金流为正
    roe = stock.get("roe", 0) * 100
    quality_roe = max(0, min(100, roe * 3))
    ocf_ratio = stock.get("ocf_ratio", 0)
    quality_cashflow = max(0, min(100, ocf_ratio * 100))
    quality_score = (quality_roe * 0.6 + quality_cashflow * 0.4)

    # 加权总分
    total = (
        value_score * w["value"] +
        growth_score * w["growth"] +
        momentum_score * w["momentum"] +
        quality_score * w["quality"]
    )

    return round(total, 1)


def normalize_and_rank(stocks: list[dict], top_n: int = 20) -> list[dict]:
    """评分+排序+返回Top N"""
    for stock in stocks:
        stock["score"] = compute_stock_score(stock)

    # 排除ST和次新
    filtered = [s for s in stocks if not s.get("is_st", False) and s.get("listing_days", 999) > 60]

    # 排序
    ranked = sorted(filtered, key=lambda x: x["score"], reverse=True)

    return ranked[:top_n]
```

### 筛选条件（硬性过滤）

```python
def hard_filter(stock: dict, config: dict) -> bool:
    """硬性过滤条件，不满足直接排除"""
    # 排除ST
    if config.get("exclude_st", True) and stock.get("is_st", False):
        return False
    # 排除次新
    if stock.get("listing_days", 999) < config.get("exclude_new_days", 60):
        return False
    # 最低成交额
    if stock.get("amount", 0) < config.get("min_turnover", 5_000_000):
        return False
    # 排除停牌
    if stock.get("is_suspended", False):
        return False
    return True
```

---

**依赖**: S4(Agent), S5(数据)
**被依赖**: S6(工作流)
