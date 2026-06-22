# P0/P1 因子与选股引擎优化方案

**日期**: 2026-06-07  
**来源**: 量化工程师、专业投资人、机构视角三方评审  
**优先级**: P0（编码前必须）→ P1（Phase 2 完成前必须）  
**目标**: 解决当前因子层的三类硬伤 + 补齐机构级基础设施

---

## 实现状态（2026-06-12 更新）

| 优化项 | 状态 | 说明 |
|--------|------|------|
| P0-1 Winsorize + 缺失填充 | ⏭️ 跳过 | 个人使用不需要，当前评分够用 |
| P0-2 因子定义标准化 | ⚠️ 部分实现 | factor_farm.py 有基础实现 |
| P0-3 流动性过滤 | ✅ 已实现 | hard_filter.py 有成交额过滤 |
| P1-4 ICIR 加权 | ⏭️ 跳过 | 个人使用等权足够 |
| P1-5 分风格推荐 | ✅ 已实现 | 4 种风格已支持 |
| P1-6 合规输出 | ⏭️ 跳过 | 个人使用不对外发布 |
| P1-7 用户黑名单 | ✅ 已实现 | hard_filter.py 有黑名单 |

**结论**: 7 项优化中，3 项已实现，4 项跳过（个人使用不需要）。

---

## 目录

| # | 优先级 | 优化点 | 所属模块 |
|---|--------|--------|---------|
| 1 | P0 | Winsorize 缩尾 + 行业中位数填充缺失值 | `quant.hard_filter` / `quant.calculate_factors` |
| 2 | P0 | 因子定义标准化（E/P 替代 PE, 对数收益率） | `quant.calculate_factors` / `factor_spec.yaml` |
| 3 | P0 | 流动性过滤 + 黑名单 + 退市风险 | `quant.hard_filter` |
| 4 | P1 | ICIR 加权替代等权 | `quant.screening_pipeline` |
| 5 | P1 | 分风格独立推荐 | `quant.master_score` / `analyst_agent` |
| 6 | P1 | 合规输出（免责声明 + 弱化 buy/sell 措辞） | `report.generate_markdown` |
| 7 | P1 | 用户黑名单表 + 可配置过滤规则 | DB + `quant.hard_filter` |

---

## P0-1: 因子标准化方法论

### 目标

解决 z-score 受异常值和缺失值污染导致的评分失真问题。

### 设计

#### 1. Winsorize 缩尾（在标准化之前）

```python
# backend/skills/quant/factor_normalizer.py
import numpy as np

def winsorize_series(series: np.ndarray, lower: float = 0.01, upper: float = 0.99) -> np.ndarray:
    """
    对因子值做分位数截断。
    参数:
        series: 股票的因子值数组（截面，如 5000 只股票的 PE）
        lower: 下分位数 (默认 1%)
        upper: 上分位数 (默认 99%)
    返回:
        截断后的数组
    """
    lo = np.quantile(series, lower)
    hi = np.quantile(series, upper)
    return np.clip(series, lo, hi)


def standardize_zscore(series: np.ndarray, ddof: int = 0) -> np.ndarray:
    """
    Winsorize 后的 z-score 标准化。
    不在此函数中处理缺失——缺失必须在调用前填充。
    """
    mean = np.nanmean(series)
    std = np.nanstd(series, ddof=ddof)
    if std == 0:
        return np.zeros_like(series)
    return (series - mean) / std


def neutralize_by_industry(
    factor_series: np.ndarray,
    industry_labels: np.ndarray,
) -> np.ndarray:
    """
    行业中性化：对因子值减去行业内均值。
    用于排除"某个行业整体被高估/低估"带来的信号偏差。
    """
    industries = np.unique(industry_labels)
    neutralized = factor_series.copy().astype(float)
    for ind in industries:
        mask = industry_labels == ind
        neutralized[mask] = factor_series[mask] - np.nanmean(factor_series[mask])
    return neutralized
```

#### 2. 缺失值填充策略（统一规则）

| 因子类型 | 填充方法 | 理由 |
|---------|---------|------|
| 估值因子 (PE, PB, PS) | **行业中位数** | 同一行业内估值水平相似 |
| 质量因子 (ROE, GrossMargin) | **行业中位数** | 行业间差异大，全市场中位数偏移严重 |
| 动量因子 (Momentum) | **0** | 无数据视为无动量信号 |
| 技术因子 (RSI, MACD) | **0.5 (中性值)** | RSI 范围 0-100，中性 50 |
| 流动性因子 (Volume, Turnover) | **行业中位数** | 行业间流动性差异大 |
| 市值因子 | **行业中位数** | — |

```python
# factor_normalizer.py (续)
def fill_missing_by_type(
    series: pd.Series,
    fill_method: str,
    industry_median_map: dict[str, float] | None = None,
    global_median: float | None = None,
) -> pd.Series:
    """
    按 fill_method 填充缺失值。
    
    fill_method 支持:
        "industry_median" — 需要 industry_median_map
        "zero" — 填 0
        "neutral_0.5" — 填 0.5
        "global_median" — 需要 global_median
    """
    if fill_method == "industry_median" and industry_median_map:
        return series.fillna(series.map(industry_median_map))
    elif fill_method == "zero":
        return series.fillna(0)
    elif fill_method == "neutral_0.5":
        return series.fillna(0.5)
    elif fill_method == "global_median" and global_median is not None:
        return series.fillna(global_median)
    else:
        raise ValueError(f"Unknown fill method: {fill_method}")
```

#### 3. factor_spec.yaml（因子定义配置文件）

```yaml
# backend/skills/quant/factor_spec.yaml
# 每个因子的完整定义。新增因子必须在此注册。

factors:
  momentum_1m:
    description: "过去 20 个交易日对数收益率"
    data_source: "kline_cache.close"
    window: 20
    log_return: true          # true=对数收益率, false=简单收益率
    remove_suspended: true    # 停牌日从窗口排除
    fill_method: "zero"
    winsorize: [0.01, 0.99]
    neutralize: "industry"    # 行业中性化
    weight_method: "icir"     # ICIR 加权

  momentum_3m:
    description: "过去 60 个交易日对数收益率"
    data_source: "kline_cache.close"
    window: 60
    log_return: true
    remove_suspended: true
    fill_method: "zero"
    winsorize: [0.01, 0.99]
    neutralize: "industry"
    weight_method: "icir"

  ep_ratio:
    description: "盈利收益率 (E/P), 负值设为 0"
    data_source: "stock_info.pe_ratio"
    compute: "1 / pe_ratio if pe_ratio > 0 else 0"
    fill_method: "global_median"
    winsorize: [0.01, 0.99]
    neutralize: "industry"
    weight_method: "icir"

  roe:
    description: "净资产收益率"
    data_source: "stock_info.roe"
    fill_method: "industry_median"
    winsorize: [0.005, 0.995]  # ROE 异常值少，缩尾更宽松
    neutralize: "industry"
    weight_method: "icir"

  volume_ratio:
    description: "量比 (当日量 / 5 日均量)"
    data_source: "kline_cache.volume"
    window: 5
    fill_method: "zero"
    winsorize: [0.01, 0.99]
    neutralize: null           # 量比不中性化
    weight_method: "icir"
```

### 影响范围

- **新增文件**: `backend/skills/quant/factor_normalizer.py`, `backend/skills/quant/factor_spec.yaml`
- **修改文件**: `backend/skills/quant/factor_calculator.py`（拆自 `services/factor_farm.py`）
- **测试要点**:
  - PE=5000 的股票缩尾后是否为正常值
  - ROE=None 的股票是否被填入行业中位数
  - 停牌股票的 20 日动量是否剔除停牌日

---

## P0-2: 因子定义标准化

### 目标

消除所有因子定义中的歧义，统一计算方法。

### 变更清单

| 当前问题 | 改为 | 影响 |
|---------|------|------|
| PE 倒数参与评分, 负值无处理 | E/P, 负值统一设为 0 | `quant.master_score` 各大师函数 |
| 简单收益率 `(close - close_prev) / close_prev` | 对数收益率 `ln(close / close_prev)` | `quant.calculate_factors` |
| 停牌日计入窗口 | 从窗口排除 | `quant.calculate_factors` |
| 因子权重等权 | 变为 ICIR 加权（见 P1-4） | `quant.screening_pipeline` |
| PE 默认值 0 | 变为 None → 触发行业中位数填充 | `shared.models.StockInfo` |

### E/P 落地细节

```python
# backend/skills/quant/factor_calculator.py

def calc_ep_ratio(stock: dict) -> float:
    """
    计算盈利收益率 (E/P)。
    
    规则:
    1. pe_ratio > 0 → 1 / pe_ratio
    2. pe_ratio == 0 → None（触发缺失填充）
    3. pe_ratio < 0 → 0（亏损公司 E/P = 0，不参与正向排名）
    """
    pe = stock.get("pe_ratio", 0)
    if pe is None or pe == 0:
        return None
    if pe < 0:
        return 0.0
    return 1.0 / pe
```

### 对数收益率落地

```python
import numpy as np

def calc_log_return(prices: list[float]) -> float:
    """
    计算一段时间内的对数收益率。
    prices: 按日期升序排列的收盘价数组
    返回: ln(last / first)
    """
    if len(prices) < 2:
        return 0.0
    first = prices[0]
    last = prices[-1]
    if first <= 0 or last <= 0:
        return 0.0
    return float(np.log(last / first))
```

---

## P0-3: 流动性过滤 + 黑名单 + 退市风险

### 设计原则

**硬过滤只做"排除垃圾"，不做"选择好股"。** 好股由因子评分和大师评分去选。

原来 18 个 AND 条件的思路有问题——一只高成长高 PE 的股票因为 PE 超标被排除，但它在其他 17 个维度可能都很优秀。改为：

| 过滤类型 | 条件数 | 逻辑 | 通过率 | 作用 |
|---------|--------|------|--------|------|
| 排除性过滤（硬） | 6 个 | AND | 排除 < 10% | 仅排除不可交易垃圾股 |
| 质量门槛（软） | 0 个 | 转为评分因子 | — | 低 ROE 不排除，只是不加分 |
| 自适应截断（动态） | — | 按得分取 Top N | — | 确保候选池数量稳定 |
| 黑名单 | 自定义 | AND | 用户自行管理 | 用户手动排除特定股票 |

### 硬过滤条件（仅保留 6 个）

```python
# backend/skills/quant/hard_filter.py
# 仅排除不可交易的股票。不评判股票质量（那是因子评分的事）。

HARD_FILTER_EXCLUSIONS = {
    "exclude_st": {
        "value": True,
        "description": "排除 ST / *ST 股票",
        "field": "is_st",
        "action": "exclude",
    },
    "exclude_delisting": {
        "value": True,
        "description": "排除退市整理期股票",
        "field": "is_delisting",
        "action": "exclude",
    },
    "min_listing_days": {
        "value": 60,
        "description": "上市超过 60 天（新股未稳定）",
        "field": "listing_days",
        "action": "exclude",
    },
    "min_price": {
        "value": 1.0,
        "description": "股价 > 1 元（面值退市风险线）",
        "field": "latest_price",
        "action": "exclude",
    },
    "flag_limit_up": {
        "value": True,
        "description": "涨停标记（不排除，仅标注'当前涨停无法买入'）",
        "field": "is_limit_up",
        "action": "flag_only",
    },
    "flag_limit_down": {
        "value": True,
        "description": "跌停标记（不排除，仅标注风险）",
        "field": "is_limit_down",
        "action": "flag_only",
    },
}
```

6 个硬条件，5000 只排除约 400-500 只，**剩 4500+ 全部进入因子评分**。

### 原来 12 个质量条件改为评分因子

| 原硬条件 | 改为 | 理由 |
|---------|------|------|
| PE > 0 / PE < 50 | 转为 E/P 因子参与评分 | 亏损 E/P=0，高 PE 少加分，但不排除 |
| ROE > 10% | 转为 ROE 因子参与评分 | ROE=3% 得 0 分，ROE=25% 得高分 |
| 日均成交额 > 5000 万 | 转为流动性因子 | 低流动性少加分，好标的不排除 |
| 流通市值 > 20 亿 | 转为市值因子 | 微盘股不加分，但不排除 |
| 换手率 > 1% | 转为换手率因子 | 低换手不等于坏股票（机构重仓） |
| 其他 7 个质量条件 | 全部转为对应因子 | 同上逻辑：低分不加分，但不排除 |

### 自适应候选池

后续 Analyst Agent 只处理 10-30 只，但用 **自适应截断** 而非入口硬过滤：

```python
def adaptive_topk(
    candidates: list[dict],
    score_field: str = "composite_score",
    target_min: int = 30,
    target_max: int = 50,
) -> list[dict]:
    """
    确保候选池稳定在 30-50 只。
    不在此排除任何股票——仅基于得分排序截断。
    """
    sorted_candidates = sorted(candidates, key=lambda x: x.get(score_field, 0), reverse=True)
    
    for topk in [50, 100, 150, 200, 300, 500]:
        pool = sorted_candidates[:topk]
        qualified = [s for s in pool if s.get(score_field, 0) >= 60]
        if len(qualified) >= target_min:
            if len(pool) <= target_max:
                return pool
    
    # 兜底：股票数量实在不够，给多少算多少
    return sorted_candidates[:target_max] if len(sorted_candidates) > target_min else sorted_candidates
```

### 修改后的完整 Pipeline

```
Stage 1（排除性硬过滤 — 6 条件 AND）:
  5000 → 4500+（排除 ~10% 垃圾）

Stage 2（因子评分 — 15 因子 ICIR 加权）:
  4500 只全部评分，不排除任何股票
  每只股票 composite_score = Σ(wi × factor_score_i)

Stage 3（自适应截断 — 仅排序截断，非排除）:
  取 Top 30-50（动态调整）
  高分少 → 扩大范围；高分多 → 缩小范围

Stage 4（大师评分 — 5 风格独立评分）:
  14 位大师，分 5 组风格
  每组独立输出 Top 10

Stage 5（Analyst Agent — 仅对 Top 10 LLM 分析）:
  并发执行，每只股票独立深度分析
```

### 黑名单表

```sql
CREATE TABLE user_blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL UNIQUE,
    reason TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

```python
def _apply_blacklist(self, universe: list[dict], blacklist: set[str]) -> list[dict]:
    return [s for s in universe if s["stock_code"] not in blacklist]
```

### 影响范围

- `backend/skills/quant/hard_filter.py` — 6 条件替代 18 条件
- `backend/shared/models_v2.py` — 新增 `user_blacklist` 表
- Pipeline 流程调整为 5 阶段
- `backend/skills/quant/hard_filter.py` — 涨停标记逻辑

---

## P1-4: ICIR 加权替代等权

### 目标

用信息系数信息比（ICIR）替代等权，在不增加模型复杂度的情况下显著提升因子组合效率。

### ICIR 定义

```
ICIR_i = mean(RankIC_i) / std(RankIC_i)  过去 60 个交易日

因子权重:
  w_i = max(0, ICIR_i) / sum(max(0, ICIR_j) for all j)
```

Rank IC：每个交易日，计算因子值与下个 5 日收益率之间的截面 Spearman 秩相关系数。ICIR 是 IC 的均值 / IC 的标准差。

```python
# backend/skills/quant/icir_calculator.py
import numpy as np
from scipy.stats import spearmanr


def calc_daily_rank_ic(
    factor_values: np.ndarray,
    forward_returns: np.ndarray,
) -> float:
    """
    计算单日 Rank IC。
    factor_values: 截面因子值 (N 只股票)
    forward_returns: 截面未来 5 日收益率 (N 只股票)
    返回: Spearman 相关系数
    """
    valid = ~(np.isnan(factor_values) | np.isnan(forward_returns))
    if valid.sum() < 30:  # 最少 30 只有效股票
        return 0.0
    ic, _ = spearmanr(factor_values[valid], forward_returns[valid])
    return float(ic)


def calc_icir(daily_ics: list[float], window: int = 60) -> float:
    """
    计算 ICIR。
    daily_ics: 最近 N 个交易日的每日 IC 值
    window: 仅用最近 window 个交易日的数据
    
    如果 ICIR 为负（因子反指），返回 0（不参与加权）。
    """
    if len(daily_ics) < 10:
        return 0.0
    ics = np.array(daily_ics[-window:])
    mean_ic = np.mean(ics)
    std_ic = np.std(ics, ddof=1)
    if std_ic == 0:
        return 0.0
    icir = mean_ic / std_ic
    return max(0.0, icir)  # 负 ICIR 视为 0


def calc_factor_weights(factor_icirs: dict[str, float]) -> dict[str, float]:
    """
    根据各因子的 ICIR 计算归一化权重。
    
    示例输入:
        {"momentum_1m": 0.35, "ep_ratio": 0.28, "roe": 0.15}
    示例输出:
        {"momentum_1m": 0.45, "ep_ratio": 0.36, "roe": 0.19}
    """
    total = sum(factor_icirs.values())
    if total <= 0:
        return {k: 1.0 / len(factor_icirs) for k in factor_icirs}  # 等权 fallback
    return {k: v / total for k, v in factor_icirs.items()}
```

### IC 计算频率

- **日频**: 每个交易日收盘后计算当日 Rank IC
- **存储**: `factor_ic_history` 表，保留 120 个交易日
- **权重更新**: 每日自动更新，ICIR 用 60 日滚动窗口

```sql
CREATE TABLE factor_ic_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    rank_ic REAL,
    UNIQUE(factor_name, trade_date)
);
```

### 影响范围

- **新增文件**: `backend/skills/quant/icir_calculator.py`
- **修改文件**: `backend/skills/quant/screening_pipeline.py`（权重计算逻辑）
- **依赖**: `scipy.stats.spearmanr`（建议用 `scipy>=1.7`，一般已安装）

---

## P1-5: 分风格独立推荐

### 目标

取消 14 位大师同时评分 + 加权平均的方案，改为分风格独立推荐，让用户根据自己偏好选择。

### 风格分组

```python
# backend/skills/quant/master_scores.py

STYLE_GROUPS = {
    "value": {
        "display_name": "价值风格",
        "masters": ["buffett", "graham", "greenblatt"],
        "description": "低估值 + 高安全边际 + 好价格",
    },
    "growth": {
        "display_name": "成长风格",
        "masters": ["lynch", "cathie_wood", "phil_fisher"],
        "description": "高增长 + 大市场 + 颠覆性创新",
    },
    "quality": {
        "display_name": "质量风格",
        "masters": ["damodaran", "howard_marks"],
        "description": "高 ROE + 强大护城河 + 低风险",
    },
    "special_situation": {
        "display_name": "特殊情形",
        "masters": ["burry", "ackman", "druckenmiller", "jhunjhunwala"],
        "description": "逆向投资 + 事件驱动 + 宏观对冲",
    },
    "momentum": {
        "display_name": "趋势风格",
        "masters": ["momentum_master", "limit_up_master"],
        "description": "强者恒强 + 涨停跟随",
    },
}
```

### 推荐流程

```
Stage 3 输出:
  Top 30 只候选 + 15 个因子评分

分风格评分:
  价值组: Buffett(40%) + Graham(35%) + Greenblatt(25%)
     → 价值风格 Top 10
  成长组: Lynch(40%) + Cathie(35%) + Fisher(25%)
     → 成长风格 Top 10
  质量组: Damodaran(50%) + Marks(50%)
     → 质量风格 Top 10

每只候选股票获得 5 个风格标签:
  例如: 000001 平安银行
    value_score: 85 (Top 1 of 5000)
    growth_score: 45 (Top 120 of 5000)
    quality_score: 72 (Top 8 of 5000)
    special_score: 30
    momentum_score: 55

Master Agent 汇总时:
  默认展示所有风格中得分最高的股票
  用户可指定 "只看价值风格"
```

### Market Agent 的角色变化

Market Agent **不再控制大师权重**。它的职责缩减为：
1. 输出市场状态（牛市/熊市/震荡）
2. 输出风��偏好建议（供用户参考，不是硬约束）
3. 输出风险等级（控制总体仓位建议）

风格选择权交给**用户**（通过对话或配置）。

### 影响范围

- **修改文件**: `backend/skills/quant/master_scores.py`, `backend/agents/market_agent.py`
- **新增文件**: 无（逻辑变更）
- **前端影响**: 推荐卡片增加风格标签显示

---

## P1-6: 合规输出

### 目标

消除投资建议的法律风险，确保系统输出不能被解读为"投资建议"。

### 报告免责声明

```python
# backend/skills/report/generate_markdown.py

DISCLAIMER = """

---

> **免责声明**  
> 本报告由 AShare-X Quant Agent 自动生成，仅供研究参考，不构成任何投资建议。  
> 报告中的评分、信号、推荐等均为基于历史数据的量化分析结果，  
> 不代表对未来表现的预测或保证。投资者应根据自身风险承受能力独立做出投资决策。  
> 投资有风险，入市需谨慎。
"""

def inject_disclaimer(markdown: str) -> str:
    """在报告末尾注入免责声明"""
    return markdown.strip() + DISCLAIMER
```

### 信号措辞映射

| 内部枚举 | 对外展示 | 不使用 |
|---------|---------|--------|
| `strong_buy` | "研究关注" | "强烈买入" |
| `buy` | "技术信号偏多" | "买入" |
| `hold` | "估值合理" | "持有" |
| `sell` | "估值偏高" | "卖出" |
| `strong_sell` | "风险提示" | "强烈卖出" |

```python
SIGNAL_DISPLAY_MAP = {
    "strong_buy": "研究关注",
    "buy": "技术信号偏多",
    "hold": "估值合理",
    "sell": "估值偏高",
    "strong_sell": "风险提示",
}
```

这里的映射关系对 LLM 透明——Analyst Agent 的 prompt 中直接使用"研究关注"等措辞，不再使用"buy/sell"表达。

### 影响范围

- **修改文件**: `backend/skills/report/generate_markdown.py`
- **修改文件**: `backend/agents/analyst_agent.py`（prompt 措辞调整）
- **新增文件**: 无

---

## P1-7: 用户黑名单 + 可配置过滤

### 目标

用户在对话中可以直接添加黑名单，系统下次选股自动排除。

### API 端点

```
POST /api/portfolio/blacklist
  body: {stock_code: "600000", reason: "财务造假历史"}
  → {ok: true}

DELETE /api/portfolio/blacklist/{stock_code}
  → {ok: true}

GET /api/portfolio/blacklist
  → {ok: true, data: [{stock_code, reason, created_at}]}
```

### 数据库

```sql
CREATE TABLE user_blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL UNIQUE,
    reason TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 过滤集成

```python
# HardFilter 执行流程修改
def run(universe, market_regime, blacklist=None):
    # 1. 基础硬过滤
    passed = self._apply_base_filters(universe)
    # 2. 黑名单过滤（新增，P1-7）
    if blacklist:
        passed = self._apply_blacklist(passed, blacklist)
    # 3. 退市风险过滤（新增，P0-3）
    passed = self._apply_delisting_filter(passed)
    ...
```

### 影响范围

- **新增表**: `user_blacklist`
- **新增 API**: 3 个端点
- **修改文件**: `backend/skills/quant/hard_filter.py`

---

## 实施顺序

| 顺序 | 优化项 | 估计工时 | 前置依赖 |
|------|--------|---------|---------|
| 1 | P0-2: 因子定义标准化（E/P, 对数收益率） | 4h | 无 |
| 2 | P0-1: Winsorize + 缺失填充 | 6h | P0-2 |
| 3 | P0-3: 流动性过滤 + 退市风险 | 3h | P0-2 |
| 4 | P1-4: ICIR 加权 | 8h | P0-1 (需要标准化后的因子) |
| 5 | P1-5: 分风格推荐 | 6h | P1-4 |
| 6 | P1-6: 合规输出 | 2h | 无 |
| 7 | P1-7: 黑名单 + 配置过滤 | 4h | P0-3 |
