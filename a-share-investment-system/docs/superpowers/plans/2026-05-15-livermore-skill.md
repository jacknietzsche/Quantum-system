# Livermore Skill Integration Plan

> **For agentic workers:** Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Deeply integrate Jesse Livermore's trend-following + key-point + pyramiding trading philosophy as a QuantAnalyzer, MasterAgent, screening style, and injectable SKILL.md knowledge package.

**Architecture:** Livermore needs NO fundamentals (price/volume/trend only) — perfect for the current system where financial data is still being populated. Integration happens at 4 levels: (1) QuantAnalyzers (lightweight scoring), (2) MasterAgentRegistry (full analysis), (3) screening pipeline as a new style, (4) SkillEngine knowledge injection.

**Tech Stack:** Python/FastAPI, config.yaml, SKILL.md

---

### Integration Map

| Layer | File | What It Provides |
|-------|------|-----------------|
| Skill Doc | `quant-agents/livermore-skill/SKILL.md` | Livermore philosophy + rules + templates |
| QuantAnalyzer | `services/quant_analyzers.py` | `livermore_analyze()` method |
| MasterAgent | `services/master_agents.py` | `LivermoreMaster` class |
| Config | `config/config.yaml` | `livermore` style pipeline config |
| Screener | `services/stock_screener.py` | `_run_livermore_pipeline()` method |
| Frontend | `frontend/src/types/screening.ts` | `livermore` style config + tab |

#### Livermore Scoring System (Technical-Only)

| Factor | Weight | Data Source | Description |
|--------|--------|-------------|-------------|
| Trend Alignment | 30% | `trend`, `ma_alignment` | Price above key MAs, uptrend confirmed |
| Volume Confirmation | 20% | `turnover_rate`, `volume` | Breakout with volume, no divergence |
| Price Momentum | 20% | `change_pct`, `volatility_20d` | Strong recent performance, healthy volatility |
| Key Point Proximity | 15% | `ma5`, `ma10`, `ma20`, `ma60` | Close to/near breakout of key level |
| Risk Control | 15% | `max_drawdown_60d`, `atr_14` | Manageable drawdown, position sizing signal |

---

### Task 1: Create Livermore Skill Document

**Files:**
- Create: `quant-agents/livermore-skill/SKILL.md`
- Create: `quant-agents/livermore-skill/references/core-rules.md`

The SKILL.md must follow the same YAML frontmatter format as existing skills:
```yaml
---
name: livermore
description: 杰西·利弗莫尔趋势跟踪交易系统 — 关键点突破 + 金字塔加仓 + 最小阻力线
triggers: trend, momentum, breakout, pivotal, key point, pyramid, 趋势, 突破, 关键点, 加仓
category: trading
language: zh
---
```

Content should include:
- Livermore's core philosophy (最小阻力线, 市场永远是对的)
- 21 trading rules translated and explained
- Key Point theory (关键点突破策略)
- Pyramiding system (金字塔加仓法)
- Position sizing and risk control
- Output template for LLM analysis

Create `references/core-rules.md` with the 21 trading rules in detail.

---

### Task 2: Add LivermoreAnalyzer to QuantAnalyzers

**Files:**
- Modify: `services/quant_analyzers.py` — add `livermore_analyze()` method

The method signature must match existing analyzers:
```python
def livermore_analyze(self, stock_code: str, f: Dict) -> Dict:
```

Input fields needed (all from StockInfo, no fundamentals):
- `price` / `latest_price`
- `trend` ("上升"/"下降"/"横盘")
- `ma_alignment`
- `ma5`, `ma10`, `ma20`, `ma60`
- `change_pct`
- `turnover_rate`
- `volatility_20d`
- `max_drawdown_60d`
- `atr_14`

Scoring logic:
```python
def livermore_analyze(self, stock_code: str, f: Dict) -> Dict:
    if not f or f.get("price", 0) <= 0:
        return {"analyst": "livermore", "stock_code": stock_code,
                "score": 50, "signal": "neutral",
                "data_quality": "insufficient",
                "details": {"reason": "价格数据不可用"}}

    price = f.get("price", 1)
    trend = f.get("trend", "横盘")
    ma5 = f.get("ma5", 0)
    ma10 = f.get("ma10", 0)
    ma20 = f.get("ma20", 0)
    ma60 = f.get("ma60", 0)
    change_pct = f.get("change_pct", 0)
    turnover = f.get("turnover_rate", 0)
    volatility = f.get("volatility_20d", 30)
    drawdown = f.get("max_drawdown_60d", 0)
    atr = f.get("atr_14", 0)

    score = 0
    reasons = []

    # 1. Trend Alignment (30 points)
    trend_upper = trend in ("上升", "bullish")
    if trend_upper:
        score += 15
        reasons.append("主趋势向上 +15")
    elif trend in ("下降", "bearish"):
        score -= 10
        reasons.append("主趋势向下 -10")

    # Price above key MAs
    if price > ma20 > 0:
        score += 10
        reasons.append("价格>20日均线 +10")
    if price > ma60 > 0:
        score += 5
        reasons.append("价格>60日均线 +5")

    # MA alignment (short > medium > long = bullish)
    if ma5 > ma10 > ma20 > 0:
        score += 10
        reasons.append("均线多头排列 +10")
    elif ma60 > ma20 > 0:
        score -= 5
        reasons.append("均线空头排列 -5")

    # 2. Volume Confirmation (20 points)
    if turnover > 5:
        score += 15
        reasons.append(f"高换手率({turnover:.1f}%) +15")
    elif turnover > 2:
        score += 10
        reasons.append(f"换手率活跃({turnover:.1f}%) +10")
    elif turnover > 1:
        score += 5
        reasons.append(f"换手率正常({turnover:.1f}%) +5")

    # 3. Price Momentum (20 points)
    if change_pct > 2:
        score += 10
        reasons.append(f"涨幅{change_pct:.1f}% +10")
    elif change_pct > 5:
        score += 15
        reasons.append(f"强势涨幅{change_pct:.1f}% +15")
    elif change_pct < -3:
        score -= 5
        reasons.append(f"跌幅{change_pct:.1f}% -5")

    # 4. Key Point Proximity (15 points)
    if ma20 > 0 and abs(price - ma20) / ma20 < 0.02:
        score += 10
        reasons.append("价格邻近20日线(关键支撑) +10")
    if ma60 > 0 and abs(price - ma60) / ma60 < 0.02:
        score += 5
        reasons.append("价格邻近60日线(关键支撑) +5")

    # 5. Risk Control (15 points)
    if volatility < 20:
        score += 8
        reasons.append(f"低波动({volatility:.0f}%) +8")
    elif volatility > 50:
        score -= 10
        reasons.append(f"高波动({volatility:.0f}%) -10")
    if drawdown < 15:
        score += 7
        reasons.append(f"回撤可控({drawdown:.1f}%) +7")
    elif drawdown > 30:
        score -= 10
        reasons.append(f"回撤过大({drawdown:.1f}%) -10")

    score = max(0, min(100, score))
    signal = "买入" if score >= 65 else ("持有" if score >= 40 else "观望")

    return {
        "analyst": "livermore",
        "stock_code": stock_code,
        "score": round(score, 0),
        "signal": signal,
        "data_quality": "verified",
        "details": {
            "reason": "; ".join(reasons[:3]) if reasons else "综合评分",
            "trend": trend,
            "price_vs_ma20": f"{((price/ma20 - 1)*100):.1f}%" if ma20 > 0 else "N/A",
            "volatility": round(volatility, 1),
            "drawdown_60d": round(drawdown, 1),
        }
    }
```

Also add `livermore` to the `analyze_all()` method list.

---

### Task 3: Add LivermoreMaster to MasterAgentRegistry

**Files:**
- Modify: `services/master_agents.py` — add `LivermoreMaster` class before `LimitUpMaster`

```python
class LivermoreMaster(BaseMasterAnalyzer):
    """利弗莫尔大师 — 趋势跟踪+关键点+金字塔仓位管理"""
    name = "livermore_master"
    display_name = "Jesse Livermore"
    style = "momentum"

    def analyze(self, stock_code: str, f: Dict,
                prices: Optional[List[float]] = None) -> Dict:
        price = f.get("price", 1)
        trend = f.get("trend", "横盘")
        ma_alignment = f.get("ma_alignment", "")
        change_pct = f.get("change_pct", 0)
        turnover = f.get("turnover_rate", 0)
        volatility = f.get("volatility_20d", 30)
        
        # Signal Level (using the same logic as QuantAnalyzer)
        score = self._compute_score(f)
        
        # Pyramid position sizing suggestion
        position_tier = "观望"
        if score >= 80:
            position_tier = "第四次加仓(重仓)"
        elif score >= 70:
            position_tier = "第三次加仓"
        elif score >= 60:
            position_tier = "第二次加仓"
        elif score >= 50:
            position_tier = "试探性建仓"
        
        # Key point status
        key_point_status = "等待突破"
        if trend in ("上升", "bullish") and change_pct > 2:
            key_point_status = "突破确认"

        signal = "买入" if score >= 65 else ("持有" if score >= 45 else "观望")
        return {
            "analyst": "livermore_master",
            "display_name": "Jesse Livermore",
            "stock_code": stock_code,
            "score": round(score, 0),
            "signal": signal,
            "data_quality": "verified",
            "style": "momentum",
            "details": {
                "trend": trend,
                "ma_alignment": ma_alignment,
                "pyramid_tier": position_tier,
                "key_point_status": key_point_status,
                "volatility": round(volatility, 1),
                "suggestion": self._get_suggestion(score, trend),
            }
        }

    def _compute_score(self, f: Dict) -> float:
        """Core scoring logic (same as quant analyzer)"""
        price = f.get("price", 1)
        trend = f.get("trend", "横盘")
        ma5 = f.get("ma5", 0); ma10 = f.get("ma10", 0)
        ma20 = f.get("ma20", 0); ma60 = f.get("ma60", 0)
        change_pct = f.get("change_pct", 0)
        turnover = f.get("turnover_rate", 0)
        volatility = f.get("volatility_20d", 30)
        drawdown = f.get("max_drawdown_60d", 0)
        
        score = 50
        if trend in ("上升", "bullish"): score += 15
        if price > ma20 > 0: score += 10
        if price > ma60 > 0: score += 5
        if ma5 > ma10 > ma20 > 0: score += 10
        if turnover > 3: score += 10
        elif turnover > 1: score += 5
        if change_pct > 2: score += 10
        if volatility < 25: score += 5
        if drawdown < 15: score += 5
        elif drawdown > 25: score -= 10
        return max(0, min(100, score))

    def _get_suggestion(self, score: float, trend: str) -> str:
        if score >= 75 and trend in ("上升", "bullish"):
            return "趋势确认，可金字塔式加仓，设好移动止损"
        elif score >= 55:
            return "趋势初步形成，试探性建仓，跌破关键点离场"
        elif score >= 40:
            return "等待关键点突破确认后再入场"
        return "趋势不明朗，持币观望"
```

Register in `_register_all()`:
```python
"livermore_master": LivermoreMaster(),
```

---

### Task 4: Add Livermore Screening Style Config

**Files:**
- Modify: `config/config.yaml` — add `livermore` style to `screening.styles`

```yaml
livermore:
  description: "利弗莫尔趋势跟踪 — 关键点突破+金字塔加仓"
  hold_days: "1-8周"
  stage1:
    top_n: 500
    min_market_cap: 5
    min_turnover_rate: 0.5
    require_uptrend: true
    volatility_max: 40
    flexible_mode: true
    st_filter: true
  stage2:
    top_n: 50
    score_min: 4
    min_volume_ratio: 0.8
    flexible_mode: true
  stage3:
    deep_top: 20
    final_top: 10
    master_agents:
      - livermore_master
    weights:
      livermore_master: 0.40
      momentum_master: 0.30
      peter_lynch_growth: 0.30
    min_trend_strength: 30
  stage4:
    enabled: true
    top_n: 5
    model: "siliconflow:deepseek-ai/DeepSeek-R1"
    skills:
      - livermore
    workflow:
      - research
      - debate
      - risk
      - signal
```

---

### Task 5: Add Livermore Pipeline to StockScreener

**Files:**
- Modify: `services/stock_screener.py`

Add `livermore` to `VALID_STYLES`:
```python
VALID_STYLES = {"limit_up", "momentum", "value", "hybrid", "livermore"}
```

Add pipeline method:
```python
def _run_livermore_pipeline(self, universe, regime, top_n):
    emit_log("INFO", "screening", f"[livermore] Stage 1: 趋势初筛 ({len(universe)}只)...")
    s1 = []
    for stock in universe:
        name = stock.get("stock_name", "")
        if name.startswith(("*ST", "ST")):
            continue
        if not self._flexible_filter(stock, "momentum"):
            continue
        if stock.get("turnover_rate", 0) < self.stage1_turnover_min:
            continue
        if stock.get("market_cap", 0) < self.stage1_market_cap_min:
            continue
        trend = stock.get("trend", "")
        if getattr(self, 'stage1_require_uptrend', False) and trend not in ("上升", "bullish"):
            continue
        vol = stock.get("volatility", 100)
        if vol > getattr(self, 'stage1_volatility_max', 99):
            continue
        s1.append(stock)
    s1.sort(key=lambda x: x.get("turnover_rate", 0), reverse=True)
    s1 = s1[:self.stage1_top_n]
    emit_log("INFO", "screening", f"[livermore] Stage 1: {len(s1)}只通过")
    
    emit_log("INFO", "screening", f"[livermore] Stage 2: 技术评分 ({len(s1)}只)...")
    s2 = []
    for stock in s1:
        score = 0
        dvr = stock.get("daily_volume_ratio", 0)
        turnover = stock.get("turnover_rate", 0)
        trend = stock.get("trend", "")
        chg = stock.get("change_pct", 0)
        
        if trend in ("上升", "bullish"): score += 3
        if dvr > 1.5: score += 3
        elif dvr > 1.0: score += 2
        if turnover > 3: score += 3
        elif turnover > 1: score += 2
        if chg > 2: score += 2
        elif chg > 0: score += 1
        
        if score >= self.stage2_score_min:
            stock["_stage2_score"] = score
            s2.append(stock)
    
    if len(s2) < 3:
        for stock in s1[:self.stage2_top_n]:
            if stock not in s2:
                stock["_stage2_score"] = 1
                s2.append(stock)
    s2.sort(key=lambda x: x.get("_stage2_score", 0), reverse=True)
    s2 = s2[:self.stage2_top_n]
    emit_log("INFO", "screening", f"[livermore] Stage 2: {len(s2)}只通过")
    
    emit_log("INFO", "screening", f"[livermore] Stage 3: 大师分析 ({len(s2)}只)...")
    stage3 = self._stage3_enhanced_livermore(s2)
    emit_log("INFO", "screening", f"[livermore] Stage 3: {len(stage3)}只通过")
    
    emit_log("INFO", "screening", f"[livermore] Stage 4: Agent工作流...")
    stage4 = self._run_stage4_agent_workflow(stage3)
    
    results = []
    for i, stock in enumerate(stage3[:top_n]):
        score = stock.get("_stage3_master_score", 50)
        signal = "买入" if score >= 65 else ("持有" if score >= 45 else "观望")
        results.append({
            "rank": i+1, "stock_code": stock["stock_code"],
            "stock_name": stock["stock_name"],
            "score": round(score, 0), "signal": signal,
            "industry": stock.get("industry", ""),
            "pe": stock.get("pe", 0), "roe": stock.get("roe", 0),
            "confidence": round(min(score / 100, 1.0), 2),
            "reason": f"利弗莫尔{score:.0f}分",
            "style_metrics": {
                "trend": stock.get("trend", ""),
                "turnover_rate": stock.get("turnover_rate", 0),
            },
        })
    final = results[:top_n]
    emit_log("INFO", "screening", f"[livermore] 完成: {len(final)}只推荐")
    return ServiceResult.ok(data={
        "total_screened": len(universe), "stage1_passed": len(s1),
        "stage2_passed": len(s2), "stage3_recommended": len(stage3),
        "stage4_enhanced": len(stage4), "recommendations": final,
        "style": "livermore", "stage4_analyses": stage4,
    })
```

Add `_stage3_enhanced_livermore` method:
```python
def _stage3_enhanced_livermore(self, candidates: List[Dict]) -> List[Dict]:
    """Stage3: Livermore + Momentum masters"""
    from services.master_agents import get_master_agents
    agents = get_master_agents()
    results = []
    for stock in candidates:
        code = stock.get("stock_code", "")
        master_results = agents.analyze_selected(
            stock_code=code,
            financials={
                "price": stock.get("price", 0),
                "trend": stock.get("trend", ""),
                "change_pct": stock.get("change_pct", 0),
                "turnover_rate": stock.get("turnover_rate", 0),
                "pe_ratio": stock.get("pe", 0),
                "ma5": stock.get("ma5", 0),
                "ma10": stock.get("ma10", 0),
                "ma20": stock.get("ma20", 0),
                "ma60": stock.get("ma60", 0),
                "volatility_20d": stock.get("volatility", 0),
                "max_drawdown_60d": stock.get("max_drawdown_60d", 0),
                "ma_alignment": stock.get("ma_alignment", ""),
            },
            agent_names=["livermore_master", "momentum_master", "peter_lynch_growth"]
        )
        total = 0
        weights = [0.4, 0.3, 0.3]
        for i, mr in enumerate(master_results):
            if mr and "score" in mr:
                total += mr.get("score", 50) * weights[i]
        stock["_stage3_master_score"] = total
        stock["_stage3_masters"] = master_results
        results.append(stock)
    results.sort(key=lambda x: x.get("_stage3_master_score", 0), reverse=True)
    return results[:self.stage3_deep_top]
```

Update the pipeline map in `run()`:
```python
pipeline_map = {
    "limit_up": self._run_limit_up_pipeline,
    "momentum": self._run_momentum_pipeline,
    "value": self._run_value_pipeline,
    "hybrid": self._run_hybrid_pipeline,
    "livermore": self._run_livermore_pipeline,
}
```

---

### Task 6: Add Frontend Config for Livermore Style

**Files:**
- Modify: `frontend/src/types/screening.ts`

Add to `ScreenStyle` type:
```typescript
export type ScreenStyle = 'limit_up' | 'momentum' | 'value' | 'hybrid' | 'livermore'
```

Add to `STYLE_CONFIGS`:
```typescript
livermore: { label: '利弗莫尔', color: '#8b5cf6', desc: '趋势跟踪+关键点突破' },
```

Add to `ALL_STYLES`:
```typescript
{ name: 'livermore', label: '💜 利弗莫尔' },
```

---

### Task 7: Update Screening API Enum

**Files:**
- Modify: `api/routes/screening.py`

Update the `style` parameter enum in both `run_screening` and `run_screening_stream`:
```python
style: str = Query("hybrid", enum=["limit_up", "momentum", "value", "hybrid", "livermore"]),
```

Also update `STYLES`:
```python
STYLES = ["limit_up", "momentum", "value", "hybrid", "livermore"]
```

---

### Implementation Order

1. Task 1: Create SKILL.md + reference docs (standalone)
2. Tasks 2+3: Add QuantAnalyzer + MasterAgent (independent, can be parallel)
3. Task 4: Config (depends on understanding styles)
4. Task 5: Screener pipeline (depends on Task 3)
5. Tasks 6+7: Frontend + API (independent)
