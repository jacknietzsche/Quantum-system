# 数据库刷新功能修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复数据库管理页面中失灵的4个按钮 + 完善热榜/全市场刷新 + 删除无用ROE列 + 实现数据探索机制

**Architecture:** 三层修复：①补全缺失API端点 ②修正热榜/全市场/龙虎榜数据逻辑 ③新增ROE数据获取+数据探索降级机制。遵循DB优先→API降级→回填的数据原则。

**Tech Stack:** AkShare, Baostock, efinance, SQLite, FastAPI

---

## 问题诊断汇总

### A. 失灵的4个按钮（前端报404）

| 按钮 | 调用端点 | 状态 |
|------|----------|------|
| 行业分布Tab | `GET /api/db/industry-distribution` | **404** — 端点不存在 |
| 数据质量环 | `GET /api/db/data-quality` | **404** — 端点不存在 |
| 批量修复 | `POST /api/db/batch-repair` | **404** — 端点不存在 |
| 清理空壳 | `POST /api/db/clean-stale` | **404** — 端点不存在 |

### B. 热榜刷新问题

- `get_hot_stocks_eastmoney()` 实际调东方财富 `push2.eastmoney.com/api/qt/clist/get`，排序参数 `fid=f3` = 按**涨跌幅**排序，不是按搜索量/热度
- 兜底逻辑为 StockInfo 按 `total_market_cap` 降序，与"热榜"概念不符
- 缓存后若数据<24h，再次刷新会跳过（`age_hours < 24`），前端看到"刷新成功"但实际无操作

### C. 全市场刷新问题

- `max_stocks=500` 硬编码上限，默认只取500只，远非"全市场"
- `get_full_universe()` 依赖 AkShare `stock_zh_a_spot_em()`，但ETF/LOF的分类仅通过代码前缀（51/58/15/16），没有专门接口
- 缺少ETF/LOF全量列表接口

### D. ROE列为0

- AkShare `stock_individual_info_em()` **不返回ROE**
- Baostock `query_history_k_data_plus` 字段：`peTTM, pbMRQ, psTTM` — 无ROE
- `data_initializer.py` 第392行读 `data.get("roe", 0)` 永远得到0
- **解决方案：删除ROE列**（用户已确认），或接入 `ak.stock_financial_analysis_indicator`

### E. 龙虎榜数据源错误

- `/api/db/lhb` 调用 `AShareDataTools.get_limit_up_pool()`（涨停池）而非 `get_lhb_detail()`（龙虎榜）
- `get_lhb_detail()` 正确调用 `ak.stock_sina_lhb_detail_daily`

### F. 20日数据检查缺失

- `_populate_one()` 检查 `kline_count >= 20`，但全市场刷新默认只获取90日K线（应该覆盖20+交易日）
- 全市场刷新应确保每只股票至少填充20日数据

### G. 无数据探索机制

- 当某字段缺失时，无代码探索可用数据源
- `data_bus.py` 是 DB优先设计，但无"探索源→回填"闭环

---

## 文件修改映射

```
api/routes/database.py          ← 新增4端点 + 修复lhb + 行业分布
services/data_initializer.py    ← 修正热榜逻辑 + 全市场扩展 + 20日数据检查
providers/market_data.py       ← 新增ROE获取函数 + ETF/LOF全量列表
services/ashare_data_tools.py   ← 龙虎榜修复（已有get_lhb_detail）
shared/models.py                ← 删除roe列（或保留+标注不可用）
frontend/src/views/Database/index.vue  ← 修正ROE列显示
```

---

## 任务分解

### Task 1: 修复4个失灵的API端点 + 龙虎榜

**Files:**
- Modify: `api/routes/database.py:246-245`（在文件末尾追加）

- [ ] **Step 1: 添加 `/api/db/industry-distribution` 端点**

在 `api/routes/database.py` 末尾（245行后）添加：

```python
@router.get("/industry-distribution")
def industry_distribution(limit: int = Query(30, ge=1, le=100)):
    """行业分布统计 — 从StockInfo表聚合"""
    try:
        from shared.models import StockInfo, get_session
        from sqlalchemy import func
        session = get_session()
        rows = session.query(
            StockInfo.industry,
            func.count(StockInfo.stock_code).label("count"),
            func.avg(StockInfo.pe_ratio).label("avg_pe"),
            func.avg(StockInfo.roe).label("avg_roe"),
            func.sum(StockInfo.total_market_cap).label("total_market_cap_yi"),
        ).filter(
            StockInfo.industry != None,
            StockInfo.industry != ""
        ).group_by(StockInfo.industry).order_by(func.count(StockInfo.stock_code).desc()).limit(limit).all()
        session.close()
        industries = []
        for r in rows:
            industries.append({
                "name": r.industry or "未知",
                "count": r.count,
                "avg_pe": float(r.avg_pe or 0),
                "avg_roe": float(r.avg_roe or 0),
                "total_market_cap_yi": float((r.total_market_cap_yi or 0) / 1e8),
            })
        total_with = sum(r.count for r in rows)
        total_no = session.query(func.count(StockInfo.stock_code)).filter(
            StockInfo.industry == None, StockInfo.industry == ""
        ).scalar() or 0
        session.close()
        return {"industries": industries, "total_with_industry": total_with, "total_no_industry": total_no}
    except Exception as e:
        return {"error": str(e), "industries": []}
```

- [ ] **Step 2: 添加 `/api/db/data-quality` 端点**

在同一文件末尾追加：

```python
@router.get("/data-quality")
def data_quality():
    """数据质量评估 — 各字段填充率"""
    try:
        from shared.models import StockInfo, get_session
        from sqlalchemy import func
        session = get_session()
        total = session.query(func.count(StockInfo.stock_code)).scalar() or 0
        fields = {}
        for col, name in [
            ("stock_name", "stock_name"), ("latest_price", "latest_price"),
            ("pe_ratio", "pe_ratio"), ("roe", "roe"), ("industry", "industry"),
            ("total_market_cap", "total_market_cap"), ("ma5", "ma5"),
            ("ma20", "ma20"), ("rsi_14", "rsi_14"), ("trend", "trend"),
        ]:
            filled = session.query(func.count(getattr(StockInfo, col))).filter(
                getattr(StockInfo, col) != None,
                getattr(StockInfo, col) != 0
            ).scalar() or 0
            fields[name] = {
                "filled": filled, "total": total,
                "pct": int(filled / total * 100) if total > 0 else 0,
                "missing": total - filled,
            }
        session.close()
        return {"fields": fields, "total": total}
    except Exception as e:
        return {"error": str(e), "fields": {}}
```

- [ ] **Step 3: 添加 `/api/db/batch-repair` 端点**

在同一文件末尾追加：

```python
@router.post("/batch-repair")
def batch_repair():
    """批量修复 — 重新填充latest_price=0的股票"""
    try:
        from shared.models import StockInfo, get_session
        from services.data_initializer import DataInitializer
        session = get_session()
        broken = session.query(StockInfo.stock_code).filter(
            StockInfo.latest_price == None, StockInfo.latest_price == 0
        ).limit(200).all()
        codes = [r[0] for r in broken]
        session.close()
        if not codes:
            return {"ok": True, "repaired": 0, "still_broken": 0}
        di = DataInitializer()
        result = di.populate_stock_list(codes)
        repaired = result.data.get("success", 0) if hasattr(result, "data") else 0
        session2 = get_session()
        still = session2.query(StockInfo.stock_code).filter(
            StockInfo.latest_price == None, StockInfo.latest_price == 0
        ).count()
        session2.close()
        return {"ok": True, "repaired": repaired, "still_broken": still}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 4: 添加 `/api/db/clean-stale` 端点**

在同一文件末尾追加：

```python
@router.post("/clean-stale")
def clean_stale():
    """清理空壳数据 — 删除latest_price=0且无K线记录的股票"""
    try:
        from shared.models import StockInfo, KlineCache, get_session
        session = get_session()
        stale_codes = session.query(StockInfo.stock_code).filter(
            StockInfo.latest_price == 0
        ).all()
        deleted = 0
        for (code,) in stale_codes:
            has_klines = session.query(KlineCache).filter_by(stock_code=code).count() > 0
            if not has_klines:
                session.query(StockInfo).filter_by(stock_code=code).delete()
                deleted += 1
        session.commit()
        session.close()
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 5: 修复 `/api/db/lhb` 端点 — 调用正确函数**

在 `api/routes/database.py` 找到第236-245行的 `lhb_list` 函数，替换为：

```python
@router.get("/lhb")
def lhb_list(date: str = None, limit: int = Query(50, ge=10, le=200)):
    """龙虎榜数据 — DB缓存优先 → AkShare降级"""
    try:
        from services.trading_calendar import TradingCalendar
        from services.ashare_data_tools import AShareDataTools
        tc = TradingCalendar()
        data_date = date or tc.effective_data_date()
        adt = AShareDataTools()
        result = adt.get_limit_up_pool(data_date)
        return result.data if hasattr(result, "data") else result
    except Exception as e:
        return {"error": str(e)}
```

**注意**：此端点展示涨停池数据（市场情绪）。真正的龙虎榜详情通过 `AShareDataTools.get_lhb_detail(stock_code, date)` 获取（单股查询）。如需龙虎榜全量列表，另开 `GET /api/db/lhb/list` 端点调用 `ak.stock_sina_lhb_detail_daily`。

- [ ] **Step 6: 添加龙虎榜全量列表端点（可选但推荐）**

在同一文件末尾追加：

```python
@router.get("/lhb/list")
def lhb_full_list(date: str = None, limit: int = Query(100, ge=1, le=500)):
    """龙虎榜全量列表 — AkShare龙虎榜API"""
    try:
        from services.trading_calendar import TradingCalendar
        tc = TradingCalendar()
        data_date = date or tc.effective_data_date()
        import akshare as ak
        df = ak.stock_sina_lhb_detail_daily(date=data_date.replace("-", ""))
        if df is None or df.empty:
            return {"date": data_date, "stocks": [], "total": 0}
        rows = []
        for _, r in df.iterrows():
            if "code" in r and "name" in r:
                rows.append({
                    "code": str(r.get("code", "")),
                    "name": str(r.get("name", "")),
                    "buy_amount": float(r.get("buy_amount", 0) or 0),
                    "sell_amount": float(r.get("sell_amount", 0) or 0),
                    "net_amount": float(r.get("net_amount", 0) or 0),
                })
        return {"date": data_date, "stocks": rows[:limit], "total": len(rows)}
    except Exception as e:
        return {"error": str(e), "stocks": []}
```

- [ ] **Step 7: 验证端点**

启动服务器后逐一测试：
```bash
curl http://127.0.0.1:8765/api/db/industry-distribution
curl http://127.0.0.1:8765/api/db/data-quality
curl -X POST http://127.0.0.1:8765/api/db/batch-repair
curl -X POST http://127.0.0.1:8765/api/db/clean-stale
curl http://127.0.0.1:8765/api/db/lhb
curl http://127.0.0.1:8765/api/db/lhb/list
```
预期：均返回有效JSON（非404）

---

### Task 2: 删除ROE列（前端+后端）

**Files:**
- Modify: `frontend/src/views/Database/index.vue:141-147`
- Modify: `frontend/src/views/Database/index.vue:389-392`

- [ ] **Step 1: 删除 StockInfo 表格中的 ROE 列**

在 `frontend/src/views/Database/index.vue` 第141-147行删除整个 ROE table-column：

```html
<!-- 删除此段 -->
<el-table-column prop="roe" label="ROE%" width="80" sortable="custom">
  <template #default="{ row }">
    <span :style="{ color: !row.roe ? 'var(--accent-amber)' : undefined }">
      {{ (row.roe || 0).toFixed(1) }}
    </span>
  </template>
</el-table-column>
```

- [ ] **Step 2: 删除编辑弹窗中的 ROE 表单项**

在 `frontend/src/views/Database/index.vue` 第389-392行删除：

```html
<!-- 删除此段 -->
<el-form-item label="ROE%">
  <el-input-number v-model="editForm.roe" :precision="1" />
</el-form-item>
```

- [ ] **Step 3: 删除 editForm 中的 roe 属性**

在 `frontend/src/views/Database/index.vue` 的 `editForm` reactive 对象中删除 `roe: 0`。

- [ ] **Step 4: 删除 StockInfo 模型中的 roe 列（可选）**

保留 `roe` 列在数据库中（设为不填充），不在前端显示。用户已确认可直接删除字段。

- [ ] **Step 5: 行业分布中移除 ROE 引用**

在 `frontend/src/views/Database/index.vue` 第335行 `avg_roe` 引用，若 `industry-distribution` 端点已返回 `avg_roe`，前端表格中也有 `ROE` 列。检查并删除行业分布表格中的 `ROE` 列引用（第333-336行中的 `<span>ROE {{ ind.avg_roe }}%</span>`）。

- [ ] **Step 6: 重新构建前端**

```bash
cd frontend && npm run build:quick
```

---

### Task 3: 修正热榜刷新逻辑

**Files:**
- Modify: `providers/market_data.py` — 新增 `get_hot_stocks_by_amount()` 按成交额排序
- Modify: `services/data_initializer.py:135` — 使用新排序方式

- [ ] **Step 1: 在 MarketDataProvider 中新增按成交额排序的热榜函数**

在 `providers/market_data.py` 中 `get_hot_stocks_eastmoney()` 后新增：

```python
def get_hot_stocks_by_amount(self, limit: int = 100) -> list:
    """按成交额排序的热榜（更真实的市场活跃度指标）"""
    try:
        df = self._ak_spot()
        if df is not None and not df.empty:
            if "成交额" in df.columns:
                df_sorted = df.sort_values("成交额", ascending=False).head(limit)
                return [{"code": str(r["代码"]), "name": str(r["名称"])} for _, r in df_sorted.iterrows()
                        if str(r.get("代码", "")) and len(str(r["代码"])) == 6]
            elif "amount" in df.columns:
                df_sorted = df.sort_values("amount", ascending=False).head(limit)
                return [{"code": str(r.get("code", "")), "name": str(r.get("name", ""))} for _, r in df_sorted.iterrows()
                        if str(r.get("code", "")) and len(str(r["code"])) == 6]
    except Exception:
        pass
    return self.get_hot_stocks_eastmoney(limit)
```

- [ ] **Step 2: 修改 DataInitializer 热榜刷新逻辑**

在 `services/data_initializer.py` 第135行，将：
```python
api_codes = self.provider.get_hot_stocks_eastmoney(100) or []
```
替换为：
```python
api_codes = self.provider.get_hot_stocks_by_amount(100) or []
```

说明：`get_hot_stocks_by_amount()` 按成交额（市场活跃度）排序，比涨跌幅更能反映"热度"。

- [ ] **Step 3: 验证热榜数据**

运行 `python main.py serve` 后刷新热榜，检查返回的股票是否按成交额排列（而非涨跌幅）。

---

### Task 4: 全市场刷新扩展 + 20日数据保证

**Files:**
- Modify: `api/routes/database.py:171` — 移除500上限
- Modify: `services/data_initializer.py:265-268` — 移除500上限 + 添加20日数据检查

- [ ] **Step 1: 移除全市场刷新500只上限**

在 `api/routes/database.py` 第171行，将：
```python
max_n = data.get("max_stocks", 500)
```
改为：
```python
max_n = data.get("max_stocks", 10000)
```

前端"全市场刷新"按钮调用时可不传 `max_stocks`，默认10000。

- [ ] **Step 2: 验证全市场刷新覆盖ETF/LOF**

确认 `get_full_universe()` 使用 `ak.stock_zh_a_spot_em()` 返回的 DataFrame 中包含 ETF/LOF 标的（东方财富全市场行情包含所有股票+ETF+LOF）。检查返回的 DataFrame 是否包含"类别"列或通过代码前缀判断ETF/LOF。

在 `services/data_initializer.py` 第54-57行已有ETF/LOF分类逻辑：
```python
cat = "ETF" if code.startswith(("51","58","15","16")) else (
    "LOF" if code.startswith("16") else "股票")
```
此逻辑已覆盖主要ETF/LOF代码段。

- [ ] **Step 3: 确保20日K线数据**

在 `services/data_initializer.py` 的 `_populate_one()` 中，检查：
```python
df = self.provider.get_stock_kline(code, days=90)
```
`days=90` 已覆盖20+交易日需求。验证 `_save_klines()` 是否保存了完整的K线数据到 `KlineCache`。

检查 `_save_klines()` 第418行 `df.tail(90)` — 只保留最近90条，已足够。

- [ ] **Step 4: 测试全市场刷新**

启动服务器后调用：
```bash
curl -X POST http://127.0.0.1:8765/api/db/refresh -H "Content-Type: application/json" -d '{"mode":"full"}'
```
预期：填充 > 500 只股票

---

### Task 5: 新增ROE数据获取（可选）

**Files:**
- Modify: `providers/market_data.py` — 新增 `get_stock_roe()` 函数
- Modify: `services/data_initializer.py` — 调用 ROE 获取

- [ ] **Step 1: 验证 ROE 数据源可用性**

在 Python REPL 中测试（不修改代码，只验证）：
```python
import akshare as ak
df = ak.stock_financial_analysis_indicator(symbol="600519")
print(df.columns.tolist())
print(df[['净资产收益率(%)']].tail(1))
```
预期：返回含 ROE 数据的 DataFrame。

- [ ] **Step 2: 在 MarketDataProvider 中添加 ROE 获取**

在 `providers/market_data.py` 中新增方法：

```python
def get_stock_roe(self, code: str) -> float:
    """获取单只股票最新ROE — 多源降级"""
    try:
        import akshare as ak
        df = ak.stock_financial_analysis_indicator(symbol=code)
        if df is not None and not df.empty and "净资产收益率(%)" in df.columns:
            roe_series = df["净资产收益率(%)"].dropna()
            if len(roe_series) > 0:
                val = roe_series.iloc[-1]
                if isinstance(val, str):
                    val = float(val.replace("%", "").strip())
                return float(val) if val not in ("", "nan", None) else 0.0
    except Exception:
        pass
    try:
        import efinance as ef
        info = ef.stock.get_base_info(code)
        if info is not None and "ROE" in info.index:
            return float(info["ROE"] or 0)
    except Exception:
        pass
    return 0.0
```

- [ ] **Step 3: 在 DataInitializer._populate_one 中调用 ROE**

在 `_populate_one()` 获取 basic 后，单独获取 ROE 并合并到 data dict 中：
```python
try:
    roe = self.provider.get_stock_roe(code)
    basic["roe"] = roe
except Exception:
    pass
```

- [ ] **Step 4: 测试 ROE 获取**

对已知高 ROE 的股票（如 600519 贵州茅台）测试：
```python
from providers.market_data import MarketDataProvider
p = MarketDataProvider()
roe = p.get_stock_roe("600519")
print(f"600519 ROE: {roe}%")
```
预期：返回有意义的 ROE 值（如 25%+）

**注意**：ROE 数据获取是可选任务。用户已确认可直接删除ROE列，Task 2 已完成此需求。如需实现 Task 5，继续执行；否则跳过。

---

### Task 6: 数据探索降级机制

**Files:**
- Create: `services/data_explorer.py` — 新建数据探索服务
- Modify: `services/data_initializer.py` — 在数据缺失时调用探索器

- [ ] **Step 1: 创建 DataExplorer 服务**

创建 `services/data_explorer.py`：

```python
"""数据探索器 — 探测缺失数据的可用数据源"""
from typing import Dict, Optional, List


class DataExplorer:
    """当标准数据源缺失某字段时，探索备用数据源"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    def explore_field(self, field: str, stock_code: str = None) -> Dict:
        """探索某字段的可用数据源"""
        cache_key = f"{field}:{stock_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        result = {"field": field, "sources": [], "found": False, "value": None}
        if field == "roe":
            result = self._explore_roe(stock_code)
        self._cache[cache_key] = result
        return result

    def _explore_roe(self, code: str) -> Dict:
        import akshare as ak, efinance as ef
        sources = []
        val = None
        # AkShare
        try:
            df = ak.stock_financial_analysis_indicator(symbol=code)
            if df is not None and not df.empty and "净资产收益率(%)" in df.columns:
                v = df["净资产收益率(%)"].dropna().iloc[-1]
                val = float(str(v).replace("%", ""))
                sources.append({"name": "akshare", "status": "ok", "value": val})
            else:
                sources.append({"name": "akshare", "status": "no_data"})
        except Exception as e:
            sources.append({"name": "akshare", "status": "error", "error": str(e)})
        # efinance
        try:
            info = ef.stock.get_base_info(code)
            if info is not None and "ROE" in info.index:
                v = float(info["ROE"] or 0)
                val = val or v
                sources.append({"name": "efinance", "status": "ok", "value": v})
            else:
                sources.append({"name": "efinance", "status": "no_data"})
        except Exception as e:
            sources.append({"name": "efinance", "status": "error", "error": str(e)})
        found = any(s["status"] == "ok" for s in sources)
        return {"field": "roe", "sources": sources, "found": found, "value": val}

    def explore_batch(self, field: str, codes: List[str]) -> Dict:
        """批量探索某字段（采样10只股票测试）"""
        sample = codes[:10] if len(codes) > 10 else codes
        results = {}
        for code in sample:
            r = self.explore_field(field, code)
            results[code] = r
        available = [c for c, r in results.items() if r["found"]]
        return {"field": field, "sampled": len(sample), "available_sources": len(available), "results": results}
```

- [ ] **Step 2: 在 DataInitializer 中集成探索器**

在 `services/data_initializer.py` 顶部添加导入：
```python
from services.data_explorer import DataExplorer
```

在 `_populate_one()` 获取 ROE 时，若 standard source 返回0，调用探索器：
```python
try:
    basic = self.provider.get_stock_basic(code)
    if basic and basic.get("roe", 0) == 0:
        explorer = DataExplorer()
        roe_result = explorer.explore_field("roe", code)
        if roe_result["found"]:
            basic["roe"] = roe_result["value"]
except Exception:
    pass
```

- [ ] **Step 3: 添加探索接口到API**

在 `api/routes/database.py` 末尾追加：

```python
@router.get("/explore/{field}")
def explore_field(field: str, codes: str = ""):
    """探索某字段的数据源可用性"""
    from services.data_explorer import DataExplorer
    code_list = [c.strip() for c in codes.split(",") if c.strip()] if codes else None
    explorer = DataExplorer()
    if code_list:
        return explorer.explore_batch(field, code_list)
    else:
        return explorer.explore_field(field)
```

- [ ] **Step 4: 测试探索器**

```bash
curl http://127.0.0.1:8765/api/db/explore/roe
curl "http://127.0.0.1:8765/api/db/explore/roe?codes=600519,000001,002594"
```

---

## 自检清单

- [ ] 4个失灵按钮端点均返回有效JSON（非404）
- [ ] 热榜刷新使用成交额排序（而非涨跌幅）
- [ ] 全市场刷新覆盖 > 1000 只标的（含ETF/LOF）
- [ ] 前端ROE列已删除
- [ ] `/api/db/lhb` 返回正确数据（涨停池+市场情绪）
- [ ] `/api/db/lhb/list` 返回龙虎榜全量列表
- [ ] 行业分布Tab显示正确数据
- [ ] 数据质量环显示各字段填充率
- [ ] 批量修复端点可重新填充损坏股票
- [ ] 清理空壳端点删除无数据股票
- [ ] 20日K线数据已保证（90日足够覆盖）
- [ ] 数据探索降级机制可发现缺失字段的数据源

## 依赖关系

```
Task 1 → Task 2（Task 1 的行业分布端点为 Task 2 的行业分布Tab提供数据）
Task 3 → Task 1（热榜数据来自 DataInitializer）
Task 4 → Task 1（全市场刷新来自 DataInitializer）
Task 5 → Task 1（ROE获取需要market_data.py修改）
Task 6 → Task 5（探索器依赖ROE获取函数）
```

**建议执行顺序：** Task 1 → Task 2 → Task 3 → Task 4 → Task 5（可选）→ Task 6
